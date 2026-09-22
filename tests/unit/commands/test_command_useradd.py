"""Tests for the ``useradd`` command implementation.

Covers creating a scenario-local user through the shared
``IdentityManager.create_user`` operation: automatic UID allocation, the
private primary-group default, duplicate rejection, argument/error behavior,
and resolution of the created user through the normal identity/runtime path.
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


class TestUseraddCommand:
    """Scenario-local user creation via the ``useradd`` command.

    Uses the ``shell_with_commands`` fixture (standard commands loaded) and
    asserts against the scenario's authoritative ``IdentityState`` through
    the same ``IdentityManager`` construction the runtime uses.
    """

    @staticmethod
    def _manager(shell):
        return IdentityManager(shell.scenario.identity_state)

    @staticmethod
    def _account_file(shell, path):
        result = shell.filesystem.read(path, execution=ExecutionContext.root())
        assert result.node is not None
        return result.node.content

    async def test_useradd_creates_user(self, shell_with_commands):
        """Useradd registers the requested scenario-local user."""
        result = await shell_with_commands.execute("useradd alice")
        assert_success(result)
        assert "created" in stdout_text(result)

        assert self._manager(shell_with_commands).user_by_identifier("alice") is not None

    async def test_useradd_auto_allocates_uid(self, shell_with_commands):
        """Each created user receives a distinct automatically allocated UID."""
        result = await shell_with_commands.execute("useradd alice")
        assert_success(result)
        result = await shell_with_commands.execute("useradd bob")
        assert_success(result)
        result = await shell_with_commands.execute("useradd carol")
        assert_success(result)

        manager = self._manager(shell_with_commands)
        alice = manager.user_by_identifier("alice")
        bob = manager.user_by_identifier("bob")
        carol = manager.user_by_identifier("carol")
        assert alice is not None and bob is not None and carol is not None

        ids = {alice.user_id, bob.user_id, carol.user_id}
        assert len(ids) == 3
        assert all(user_id >= IdentityManager.DEFAULT_UID_START for user_id in ids)

    async def test_useradd_private_primary_group(self, shell_with_commands):
        """Useradd creates a same-named primary group with gid == uid."""
        result = await shell_with_commands.execute("useradd alice")
        assert_success(result)

        manager = self._manager(shell_with_commands)
        alice = manager.user_by_identifier("alice")
        primary = manager.group_by_identifier("alice")
        assert alice is not None and primary is not None
        assert primary.group_id == alice.user_id

        membership = manager.membership_view()
        assert membership.primary_group(alice) == primary
        assert membership.is_member(alice.user_id, primary.group_id)

    async def test_useradd_duplicate_username_rejected(self, shell_with_commands):
        """A second useradd with the same username errors."""
        result = await shell_with_commands.execute("useradd alice")
        assert_success(result)

        result = await shell_with_commands.execute("useradd alice")
        assert_error(result)
        assert "already registered" in stderr_text(result)

    async def test_useradd_missing_operand(self, shell_with_commands):
        """Useradd with no arguments returns INVALID_ARGUMENT (MISSING_OPERAND)."""
        result = await shell_with_commands.execute("useradd")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_useradd_too_many_arguments(self, shell_with_commands):
        """Useradd with more than one argument returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("useradd alice bob")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)

    async def test_useradd_empty_username(self, shell_with_commands):
        """Useradd with an empty username returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute('useradd ""')
        assert_invalid_args(result)
        assert stderr_text(result)

    async def test_useradd_does_not_touch_scenario_projection(self, shell_with_commands):
        """The command mutates identity state only, never SNXScenario users/groups."""
        scenario = shell_with_commands.scenario
        users_before = set(scenario.users)
        groups_before = set(scenario.groups)

        result = await shell_with_commands.execute("useradd alice")
        assert_success(result)

        assert set(scenario.users) == users_before
        assert set(scenario.groups) == groups_before
        assert "alice" not in scenario.users and "alice" not in scenario.groups
        assert self._manager(shell_with_commands).user_by_identifier("alice") is not None

    async def test_created_user_resolvable_via_runtime_path(self, runtime_shell):
        """The created user resolves through the normal identity/runtime path.

        Mirrors ``core/runtime/runtime.py``: the composition root builds an
        ``IdentityManager`` over the scenario's identity state, produces a
        membership view, and turns it into an ``ExecutionContext``.
        """
        result = await runtime_shell.execute("useradd alice")
        assert_success(result)

        manager = IdentityManager(runtime_shell.scenario.identity_state)
        alice = manager.user_by_identifier("alice")
        assert alice is not None
        assert alice.user_id >= IdentityManager.DEFAULT_UID_START
        assert alice.user_id not in {0, 1001}

        private_group = manager.group_by_identifier("alice")
        assert private_group is not None
        assert private_group.group_id == alice.user_id

        membership = manager.membership_view()
        assert membership.primary_group(alice) == private_group

        execution_context = ExecutionContext.for_user(alice, membership)
        assert execution_context.effective_user == alice
        assert execution_context.credentials.primary_group == private_group
        assert alice.user_id in {group.group_id for group in execution_context.credentials.groups}

    async def test_useradd_updates_account_files(self, runtime_shell):
        """Useradd regenerates the /etc account files for the new user."""
        result = await runtime_shell.execute("useradd alice")
        assert_success(result)

        manager = self._manager(runtime_shell)
        alice = manager.user_by_identifier("alice")
        assert alice is not None

        passwd = self._account_file(runtime_shell, "/etc/passwd")
        assert f"alice:x:{alice.user_id}:{alice.user_id}:alice:/home/alice:/bin/sh" in passwd

        group = self._account_file(runtime_shell, "/etc/group")
        assert f"alice:x:{alice.user_id}:alice" in group

        shadow = self._account_file(runtime_shell, "/etc/shadow")
        assert "alice:!:20000:0:99999:7:::" in shadow

        assert "alice" not in runtime_shell.scenario.users
        assert "alice" not in runtime_shell.scenario.groups

    async def test_useradd_preserves_existing_shadow_fields(self, runtime_shell):
        """Useradd preserves existing /etc/shadow credential/aging lines verbatim."""
        custom_line = "user:$6$rounds=5000$saltsalts$abcdefgh:19876:5:99999:7:::"
        shadow_before = self._account_file(runtime_shell, "/etc/shadow")
        lines = shadow_before.splitlines()
        replaced = [custom_line if line.startswith("user:") else line for line in lines]
        assert any(line.startswith("user:") for line in lines)
        runtime_shell.filesystem.write(
            "/etc/shadow",
            "\n".join(replaced) + "\n",
            execution=ExecutionContext.root(),
        )

        result = await runtime_shell.execute("useradd alice")
        assert_success(result)

        shadow_after = self._account_file(runtime_shell, "/etc/shadow")
        assert custom_line in shadow_after.splitlines()
        assert "root:!:20000:0:99999:7:::" in shadow_after.splitlines()
        assert "alice:!:20000:0:99999:7:::" in shadow_after.splitlines()

    async def test_duplicate_useradd_does_not_mutate_account_files(self, runtime_shell):
        """A failed duplicate useradd leaves the /etc account files untouched."""
        result = await runtime_shell.execute("useradd alice")
        assert_success(result)

        before = {
            "/etc/passwd": self._account_file(runtime_shell, "/etc/passwd"),
            "/etc/group": self._account_file(runtime_shell, "/etc/group"),
            "/etc/shadow": self._account_file(runtime_shell, "/etc/shadow"),
        }

        result = await runtime_shell.execute("useradd alice")
        assert_error(result)

        for path, content in before.items():
            assert self._account_file(runtime_shell, path) == content
