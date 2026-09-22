"""Tests for the ``userdel`` command implementation.

Covers removing a scenario-local user through the shared
``IdentityManager.delete_user`` operation: member/private-group teardown,
unknown-user and root rejection, argument/error behavior, re-rendering of the
``/etc`` account-file projections after deletion, and preservation of both the
scenario's ``users``/``groups`` compatibility projections and all filesystem
state (``userdel`` never removes ``/home/<user>``).
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


class TestUserdelCommand:
    """Scenario-local user removal via the ``userdel`` command.

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

    async def test_userdel_removes_user_and_private_group(self, shell_with_commands):
        """Userdel unregisters the user and its empty private primary group."""
        result = await shell_with_commands.execute("useradd alice")
        assert_success(result)
        assert self._manager(shell_with_commands).user_by_identifier("alice") is not None

        result = await shell_with_commands.execute("userdel alice")
        assert_success(result)
        assert "deleted" in stdout_text(result)

        assert self._manager(shell_with_commands).user_by_identifier("alice") is None
        assert self._manager(shell_with_commands).group_by_identifier("alice") is None

    async def test_userdel_removes_loader_seeded_user(self, runtime_shell):
        """A user seeded by the loader (hello's ``user``) is removed."""
        manager = self._manager(runtime_shell)
        assert manager.user_by_identifier("user") is not None

        result = await runtime_shell.execute("userdel user")
        assert_success(result)

        assert manager.user_by_identifier("user") is None
        assert manager.group_by_identifier("user") is None

    async def test_userdel_unknown_user(self, shell_with_commands):
        """Unknown usernames error through the semantic operation."""
        result = await shell_with_commands.execute("userdel alice")
        assert_error(result)
        assert "not registered" in stderr_text(result)

    async def test_userdel_rejects_root(self, runtime_shell):
        """The system root identity cannot be deleted."""
        result = await runtime_shell.execute("userdel root")
        assert_error(result)
        assert "root" in stderr_text(result)
        assert self._manager(runtime_shell).user_by_identifier("root") is not None

    async def test_userdel_missing_operand(self, shell_with_commands):
        """Userdel with no arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("userdel")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_userdel_too_many_arguments(self, shell_with_commands):
        """Userdel with more than one argument returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("userdel alice bob")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)

    async def test_userdel_empty_username(self, shell_with_commands):
        """Userdel with an empty username returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute('userdel ""')
        assert_invalid_args(result)
        assert stderr_text(result)

    async def test_userdel_never_deletes_home_directory(self, shell_with_commands):
        """Deletion never removes /home/<user> or any filesystem state."""
        result = await shell_with_commands.execute("useradd alice")
        assert_success(result)

        fs = shell_with_commands.filesystem
        fs.create_directory("/home/alice", execution=ExecutionContext.root())
        fs.create_file("/home/alice/notes.txt", execution=ExecutionContext.root())
        fs.write("/home/alice/notes.txt", "keep me", execution=ExecutionContext.root())

        result = await shell_with_commands.execute("userdel alice")
        assert_success(result)

        assert fs.get_node("/home/alice").is_directory
        assert fs.get_node("/home/alice/notes.txt").content == "keep me"
        assert self._manager(shell_with_commands).user_by_identifier("alice") is None

    async def test_userdel_updates_account_files(self, runtime_shell):
        """Account projections drop the deleted user, keep the remaining ones."""
        result = await runtime_shell.execute("useradd alice")
        assert_success(result)
        assert "alice" in self._account_file(runtime_shell, "/etc/passwd")

        result = await runtime_shell.execute("userdel alice")
        assert_success(result)

        passwd = self._account_file(runtime_shell, "/etc/passwd")
        group = self._account_file(runtime_shell, "/etc/group")
        shadow = self._account_file(runtime_shell, "/etc/shadow")

        assert "alice" not in passwd
        assert "alice" not in group
        assert "alice" not in shadow
        assert "user:x:1001:1001:user:/home/user:/bin/sh" in passwd
        assert "user:x:1001:user" in group
        assert "user:!:20000:0:99999:7:::" in shadow

    async def test_userdel_preserves_other_shadow_fields(self, runtime_shell):
        """Deleting one user leaves the remaining users' shadow lines intact."""
        custom_line = "user:$6$rounds=5000$saltsalts$abcdefgh:19876:5:99999:7:::"
        shadow_before = self._account_file(runtime_shell, "/etc/shadow")
        replaced = [
            custom_line if line.startswith("user:") else line for line in shadow_before.splitlines()
        ]
        runtime_shell.filesystem.write(
            "/etc/shadow",
            "\n".join(replaced) + "\n",
            execution=ExecutionContext.root(),
        )

        result = await runtime_shell.execute("useradd alice")
        assert_success(result)
        result = await runtime_shell.execute("userdel alice")
        assert_success(result)

        shadow_after = self._account_file(runtime_shell, "/etc/shadow")
        assert custom_line in shadow_after.splitlines()
        assert "root:!:20000:0:99999:7:::" in shadow_after.splitlines()
        assert not any(line.startswith("alice:") for line in shadow_after.splitlines())

    async def test_recreated_user_after_delete(self, runtime_shell):
        """A deleted username can be recreated through useradd."""
        result = await runtime_shell.execute("useradd alice")
        assert_success(result)
        result = await runtime_shell.execute("userdel alice")
        assert_success(result)

        result = await runtime_shell.execute("useradd alice")
        assert_success(result)
        assert self._manager(runtime_shell).user_by_identifier("alice") is not None

    async def test_userdel_does_not_touch_scenario_projection(self, shell_with_commands):
        """The command mutates identity state only, never SNXScenario users/groups."""
        scenario = shell_with_commands.scenario
        users_before = set(scenario.users)
        groups_before = set(scenario.groups)

        await shell_with_commands.execute("useradd alice")
        result = await shell_with_commands.execute("userdel alice")
        assert_success(result)

        assert set(scenario.users) == users_before
        assert set(scenario.groups) == groups_before
        assert self._manager(shell_with_commands).user_by_identifier("alice") is None
