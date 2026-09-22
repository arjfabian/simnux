"""Tests for the ``groupdel`` command implementation.

Covers deleting a scenario-local group through the shared
``IdentityManager.delete_group`` operation: non-primary removal, refusal when
the group is a registered user's primary group, unknown-group and
argument/error behavior, preservation of the scenario's ``users``/``groups``
compatibility projections, and the re-rendering of the ``/etc`` account-file
projections after deletion.
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


class TestGroupdelCommand:
    """Scenario-local group removal via the ``groupdel`` command.

    Uses the ``shell_with_commands`` fixture (standard commands loaded) for
    state-level behavior and ``runtime_shell`` (full loader/runtime path) for
    identity and account-file projection behavior.
    """

    @staticmethod
    def _manager(shell):
        return IdentityManager(shell.scenario.identity_state)

    @staticmethod
    def _account_file(shell, path):
        result = shell.filesystem.read(path, execution=ExecutionContext.root())
        assert result.node is not None
        return result.node.content

    async def test_groupdel_removes_group(self, shell_with_commands):
        """Groupdel unregisters a non-primary group and its id."""
        manager = self._manager(shell_with_commands)
        await shell_with_commands.execute("groupadd staff")
        group = manager.group_by_identifier("staff")
        assert group is not None

        result = await shell_with_commands.execute("groupdel staff")
        assert_success(result)
        assert "deleted" in stdout_text(result)

        assert manager.group_by_identifier("staff") is None
        assert manager.group_by_id(group.group_id) is None

    async def test_groupdel_unknown_group(self, shell_with_commands):
        """Unknown group names error through the semantic operation."""
        result = await shell_with_commands.execute("groupdel staff")
        assert_error(result)
        assert "not registered" in stderr_text(result)

    async def test_groupdel_refuses_primary_group(self, runtime_shell):
        """A group that is a registered user's primary group is kept."""
        manager = self._manager(runtime_shell)
        assert manager.group_by_identifier("user") is not None

        result = await runtime_shell.execute("groupdel user")
        assert_error(result)
        assert "primary group" in stderr_text(result)
        assert manager.group_by_identifier("user") is not None

    async def test_groupdel_removes_non_primary_group(self, runtime_shell):
        """A standalone secondary group is deletable in a seeded scenario."""
        manager = self._manager(runtime_shell)
        await runtime_shell.execute("groupadd staff")
        assert manager.group_by_identifier("staff") is not None

        result = await runtime_shell.execute("groupdel staff")
        assert_success(result)
        assert manager.group_by_identifier("staff") is None

    async def test_groupdel_missing_operand(self, shell_with_commands):
        """Groupdel with no arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("groupdel")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_groupdel_too_many_arguments(self, shell_with_commands):
        """Groupdel with more than one argument returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("groupdel staff ops")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)

    async def test_groupdel_empty_group_name(self, shell_with_commands):
        """Groupdel with an empty group name returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute('groupdel ""')
        assert_invalid_args(result)
        assert stderr_text(result)

    async def test_groupdel_refreshes_account_files(self, runtime_shell):
        """Deletion re-renders the account projections without corruption."""
        result = await runtime_shell.execute("groupadd staff")
        assert_success(result)
        result = await runtime_shell.execute("groupdel staff")
        assert_success(result)

        passwd = self._account_file(runtime_shell, "/etc/passwd")
        group = self._account_file(runtime_shell, "/etc/group")
        shadow = self._account_file(runtime_shell, "/etc/shadow")

        assert "user:x:1001:1001:user:/home/user:/bin/sh" in passwd
        assert "user:x:1001:user" in group
        assert "user:!:20000:0:99999:7:::" in shadow

    async def test_groupdel_does_not_touch_scenario_projection(self, shell_with_commands):
        """The command mutates identity state only, never SNXScenario groups."""
        scenario = shell_with_commands.scenario
        groups_before = set(scenario.groups)

        await shell_with_commands.execute("groupadd staff")
        result = await shell_with_commands.execute("groupdel staff")
        assert_success(result)

        assert set(scenario.groups) == groups_before
        assert self._manager(shell_with_commands).group_by_identifier("staff") is None
