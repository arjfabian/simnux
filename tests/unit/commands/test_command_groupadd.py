"""Tests for the ``groupadd`` command implementation.

Covers creating a scenario-local group through the shared
``IdentityManager.create_group`` operation: automatic/explicit-id allocation,
duplicate-identifier rejection, argument/error behavior, preservation of both
the scenario's ``users``/``groups`` compatibility projections, and the
re-rendering of the ``/etc`` account-file projections after creation (a
standalone group is not user-derived, so the per-user projection is refreshed
unchanged).
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


class TestGroupaddCommand:
    """Scenario-local group creation via the ``groupadd`` command.

    Uses the ``shell_with_commands`` fixture (standard commands loaded) for
    state-level behavior and ``runtime_shell`` (full loader/runtime path) for
    identity and account-file projection behavior.
    """

    _GID_FLOOR = IdentityManager.DEFAULT_GID_START

    @staticmethod
    def _manager(shell):
        return IdentityManager(shell.scenario.identity_state)

    @staticmethod
    def _account_file(shell, path):
        result = shell.filesystem.read(path, execution=ExecutionContext.root())
        assert result.node is not None
        return result.node.content

    async def test_groupadd_creates_group(self, shell_with_commands):
        """Groupadd registers the group with the first free id at the floor."""
        result = await shell_with_commands.execute("groupadd staff")
        assert_success(result)
        assert "created" in stdout_text(result)

        group = self._manager(shell_with_commands).group_by_identifier("staff")
        assert group is not None
        assert group.group_id >= self._GID_FLOOR

    async def test_groupadd_auto_allocates_distinct_gids(self, shell_with_commands):
        """Each created group gets a distinct automatically allocated id."""
        manager = self._manager(shell_with_commands)

        await shell_with_commands.execute("groupadd staff")
        await shell_with_commands.execute("groupadd ops")

        staff = manager.group_by_identifier("staff")
        ops = manager.group_by_identifier("ops")
        assert staff is not None and ops is not None
        assert staff.group_id != ops.group_id

    async def test_groupadd_duplicate_group(self, shell_with_commands):
        """A duplicate identifier errors through the semantic operation."""
        await shell_with_commands.execute("groupadd staff")
        result = await shell_with_commands.execute("groupadd staff")

        assert_error(result)
        assert "already registered" in stderr_text(result)

    async def test_groupadd_missing_operand(self, shell_with_commands):
        """Groupadd with no arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("groupadd")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_groupadd_too_many_arguments(self, shell_with_commands):
        """Groupadd with more than one argument returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("groupadd staff ops")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)

    async def test_groupadd_empty_group_name(self, shell_with_commands):
        """Groupadd with an empty group name returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute('groupadd ""')
        assert_invalid_args(result)
        assert stderr_text(result)

    async def test_groupadd_refreshes_account_files(self, runtime_shell):
        """Creation re-renders the account projections without corruption."""
        result = await runtime_shell.execute("groupadd staff")
        assert_success(result)
        assert self._manager(runtime_shell).group_by_identifier("staff") is not None

        passwd = self._account_file(runtime_shell, "/etc/passwd")
        group = self._account_file(runtime_shell, "/etc/group")
        shadow = self._account_file(runtime_shell, "/etc/shadow")

        # Standalone groups are not user-derived lines; the existing
        # per-user projection is refreshed intact.
        assert "user:x:1001:1001:user:/home/user:/bin/sh" in passwd
        assert "user:x:1001:user" in group
        assert "user:!:20000:0:99999:7:::" in shadow

    async def test_groupadd_does_not_touch_scenario_projection(self, shell_with_commands):
        """The command mutates identity state only, never SNXScenario groups."""
        scenario = shell_with_commands.scenario
        groups_before = set(scenario.groups)

        result = await shell_with_commands.execute("groupadd staff")
        assert_success(result)

        assert set(scenario.groups) == groups_before
        assert "staff" not in scenario.groups
        assert self._manager(shell_with_commands).group_by_identifier("staff") is not None
