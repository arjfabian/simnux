"""Tests for the ``usermod`` command implementation.

Covers the supported surface — primary-group change (``-g``) and
supplementary-group append (``-a -G``) — through the shared
``IdentityManager`` operations: argument/error behavior, the rejection of
unsupported semantics (``-G`` without ``-a``, ``-a`` without ``-G``, no
changes, unknown users/groups), state-level assertions against
``IdentityState``, the ``/etc`` account-file refresh, and how a newly built
``ExecutionContext`` (a fresh session) observes the membership change while
the running shell's context snapshot does not.
"""

import pytest

from simnux.core.commands.errors import CommandError
from simnux.core.scenarios.identity import IdentityManager
from simnux.security.execution.models import ExecutionContext
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestUsermodCommand:
    """Scenario-local user modification via the ``usermod`` command."""

    @staticmethod
    def _manager(shell):
        return IdentityManager(shell.scenario.identity_state)

    async def test_usermod_change_primary_group(self, shell_with_commands):
        """``-g GROUP`` establishes GROUP as the user's primary group."""
        assert_success(await shell_with_commands.execute("useradd alice"))
        assert_success(await shell_with_commands.execute("groupadd staff"))

        result = await shell_with_commands.execute("usermod -g staff alice")
        assert_success(result)
        assert "updated" in stdout_text(result)

        manager = self._manager(shell_with_commands)
        alice = manager.user_by_identifier("alice")
        staff = manager.group_by_identifier("staff")
        membership = manager.membership_view()
        assert alice is not None and staff is not None
        assert membership.primary_group(alice) == staff
        assert membership.is_member(alice.user_id, staff.group_id)

    async def test_usermod_append_supplementary_groups(self, shell_with_commands):
        """``-a -G A,B`` appends supplementary memberships without touching primary."""
        assert_success(await shell_with_commands.execute("useradd alice"))
        assert_success(await shell_with_commands.execute("groupadd staff"))
        assert_success(await shell_with_commands.execute("groupadd ops"))

        result = await shell_with_commands.execute("usermod -a -G staff,ops alice")
        assert_success(result)

        manager = self._manager(shell_with_commands)
        alice = manager.user_by_identifier("alice")
        private = manager.group_by_identifier("alice")
        staff = manager.group_by_identifier("staff")
        ops = manager.group_by_identifier("ops")
        membership = manager.membership_view()
        assert alice is not None and staff is not None and ops is not None
        assert membership.primary_group(alice) == private
        assert membership.is_member(alice.user_id, staff.group_id)
        assert membership.is_member(alice.user_id, ops.group_id)

    async def test_usermod_append_requires_append_flag(self, shell_with_commands):
        """``-G`` without ``-a`` (group-list replacement) is not supported."""
        assert_success(await shell_with_commands.execute("useradd alice"))
        assert_success(await shell_with_commands.execute("groupadd staff"))

        result = await shell_with_commands.execute("usermod -G staff alice")
        assert_invalid_args(result)
        assert "'-G' requires '-a'" in stderr_text(result)

    async def test_usermod_append_flag_requires_groups(self, shell_with_commands):
        """``-a`` without ``-G`` is rejected."""
        assert_success(await shell_with_commands.execute("useradd alice"))

        result = await shell_with_commands.execute("usermod -a alice")
        assert_invalid_args(result)
        assert "'-a' may only be used with '-G'" in stderr_text(result)

    async def test_usermod_no_changes(self, shell_with_commands):
        """Usermod with no options reports that nothing would change."""
        assert_success(await shell_with_commands.execute("useradd alice"))

        result = await shell_with_commands.execute("usermod alice")
        assert_invalid_args(result)
        assert "no changes" in stderr_text(result)

    async def test_usermod_missing_operand(self, shell_with_commands):
        """Usermod with no arguments returns INVALID_ARGUMENT (MISSING_OPERAND)."""
        result = await shell_with_commands.execute("usermod")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_usermod_too_many_arguments(self, shell_with_commands):
        """Usermod with more than one login returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("usermod -g staff alice bob")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)

    async def test_usermod_unknown_user(self, shell_with_commands):
        """Usermod on a user the scenario does not register errors."""
        result = await shell_with_commands.execute("usermod -g staff ghost")
        assert_error(result)
        assert "user 'ghost' does not exist" in stderr_text(result)

    async def test_usermod_unknown_group(self, shell_with_commands):
        """Usermod referencing an unknown group errors before mutating state."""
        assert_success(await shell_with_commands.execute("useradd alice"))

        result = await shell_with_commands.execute("usermod -g nope alice")
        assert_error(result)
        assert "group 'nope' does not exist" in stderr_text(result)

        manager = self._manager(shell_with_commands)
        alice = manager.user_by_identifier("alice")
        membership = manager.membership_view()
        assert alice is not None
        assert membership.primary_group(alice) == manager.group_by_identifier("alice")

    async def test_usermod_does_not_touch_scenario_projection(self, shell_with_commands):
        """The command mutates identity state only, never SNXScenario users/groups."""
        scenario = shell_with_commands.scenario
        users_before = set(scenario.users)
        groups_before = set(scenario.groups)

        assert_success(await shell_with_commands.execute("useradd alice"))
        assert_success(await shell_with_commands.execute("groupadd staff"))
        result = await shell_with_commands.execute("usermod -g staff alice")
        assert_success(result)

        assert set(scenario.users) == users_before
        assert set(scenario.groups) == groups_before
        assert self._manager(shell_with_commands).user_by_identifier("alice") is not None


class TestUsermodRuntime:
    """Usermod through the full loader/runtime path (``hello`` scenario)."""

    @staticmethod
    def _manager(shell):
        return IdentityManager(shell.scenario.identity_state)

    @staticmethod
    def _account_file(shell, path):
        result = shell.filesystem.read(path, execution=ExecutionContext.root())
        assert result.node is not None
        return result.node.content

    async def test_usermod_primary_group_account_files(self, runtime_shell):
        """Primary-group change updates state and re-renders /etc account files.

        The /etc projections follow the bootstrap same-named-group convention,
        so lines are regenerated identically; identity state stays the
        authoritative record of the changed primary group.
        """
        passwd_before = self._account_file(runtime_shell, "/etc/passwd")
        group_before = self._account_file(runtime_shell, "/etc/group")
        shadow_before = self._account_file(runtime_shell, "/etc/shadow")

        result = await runtime_shell.execute("usermod -g root user")
        assert_success(result)

        manager = self._manager(runtime_shell)
        user = manager.user_by_identifier("user")
        root_group = manager.group_by_identifier("root")
        membership = manager.membership_view()
        assert user is not None and root_group is not None
        assert membership.primary_group(user) == root_group
        assert membership.is_member(user.user_id, root_group.group_id)

        assert self._account_file(runtime_shell, "/etc/passwd") == passwd_before
        assert self._account_file(runtime_shell, "/etc/group") == group_before
        assert self._account_file(runtime_shell, "/etc/shadow") == shadow_before

    async def test_usermod_membership_seen_by_new_execution_context(self, runtime_shell):
        """Appended memberships reach newly built credential snapshots only.

        Mirrors the composition root: a fresh ``ExecutionContext`` built over
        the scenario's membership view observes the new group, while the
        running shell's immutable context snapshot does not (re-login
        semantics).
        """
        assert_success(await runtime_shell.execute("groupadd staff"))
        result = await runtime_shell.execute("usermod -a -G staff user")
        assert_success(result)

        manager = self._manager(runtime_shell)
        user = manager.user_by_identifier("user")
        staff = manager.group_by_identifier("staff")
        assert user is not None and staff is not None

        membership = manager.membership_view()
        assert membership.is_member(user.user_id, staff.group_id)

        fresh = ExecutionContext.for_user(user, membership)
        assert staff.group_id in {group.group_id for group in fresh.credentials.groups}

        live_group_ids = {
            group.group_id for group in runtime_shell.execution_context.credentials.groups
        }
        assert staff.group_id not in live_group_ids
