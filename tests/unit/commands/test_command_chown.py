"""Tests for the ``chown`` command implementation.

Covers specification parsing (``OWNER`` / ``:GROUP`` / ``OWNER:GROUP`` and
rejection of the unsupported ``OWNER:``/empty forms), scenario-local identity
resolution, the owner/group mutation through ``SNXFileSystem.chown``,
authorization (root-only owner changes; owner-plus-membership for group-only
changes), multi-target operation, and preservation of all other node fields.
"""

import pytest

from simnux.core.commands.errors import CommandError
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.scenarios.identity import IdentityManager
from simnux.security.execution.models import ExecutionContext
from simnux.security.users.models import SNXUser
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


class TestChownCommand:
    """Owner/group changes via the ``chown`` command."""

    @staticmethod
    def _manager(shell):
        return IdentityManager(shell.scenario.identity_state)

    @staticmethod
    def _as_root(shell):
        shell.execution_context = ExecutionContext.for_user(SNXUser(0, "root"))

    @staticmethod
    def _seed_owned_node(shell, path, owner_name, group_name, content="data"):
        manager = IdentityManager(shell.scenario.identity_state)
        owner = manager.user_by_identifier(owner_name)
        group = manager.group_by_identifier(group_name)
        assert owner is not None and group is not None
        shell.filesystem.delta_layer[path] = SNXNode(
            path=path,
            content=content,
            is_directory=False,
            owner=owner,
            group=group,
            permissions=PermissionPresets.FILE_DEFAULT,
        )

    async def test_chown_owner_only_as_root(self, runtime_shell):
        """Root may change only the owner; group and other fields are preserved."""
        self._as_root(runtime_shell)
        before = runtime_shell.filesystem.get_node("/etc/hostname")

        result = await runtime_shell.execute("chown user /etc/hostname")
        assert_success(result)

        node = runtime_shell.filesystem.get_node("/etc/hostname")
        manager = self._manager(runtime_shell)
        user = manager.user_by_identifier("user")
        assert node.owner == user
        assert node.group == before.group
        assert node.content == before.content
        assert node.permissions == before.permissions
        assert node.modified_at == before.modified_at
        assert node.is_directory == before.is_directory

    async def test_chown_group_only_as_root(self, runtime_shell):
        """Root may change only the group; owner stays untouched."""
        self._as_root(runtime_shell)
        result = await runtime_shell.execute("chown :user /etc/hostname")
        assert_success(result)

        node = runtime_shell.filesystem.get_node("/etc/hostname")
        manager = self._manager(runtime_shell)
        root_user = manager.user_by_identifier("root")
        user_group = manager.group_by_identifier("user")
        assert node.owner == root_user
        assert node.group == user_group

    async def test_chown_owner_and_group_as_root(self, runtime_shell):
        """Root may change owner and group together."""
        self._as_root(runtime_shell)
        result = await runtime_shell.execute("chown user:user /etc/passwd")
        assert_success(result)

        node = runtime_shell.filesystem.get_node("/etc/passwd")
        manager = self._manager(runtime_shell)
        user = manager.user_by_identifier("user")
        assert node.owner == user
        assert node.group == manager.group_by_identifier("user")

    async def test_chown_owner_change_requires_root(self, runtime_shell):
        """A non-root user cannot change a file's owner."""
        result = await runtime_shell.execute("chown root /home/user/lipsum.txt")
        assert_error(result)
        assert "permission denied" in stderr_text(result)

        node = runtime_shell.filesystem.get_node("/home/user/lipsum.txt")
        manager = self._manager(runtime_shell)
        assert node.owner == manager.user_by_identifier("user")

    async def test_chown_group_change_requires_membership(self, runtime_shell):
        """A non-root owner may change the group only to one it belongs to."""
        self._seed_owned_node(runtime_shell, "/tmp/owned.txt", "user", "root")

        result = await runtime_shell.execute("chown :root /tmp/owned.txt")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        node = runtime_shell.filesystem.get_node("/tmp/owned.txt")
        manager = self._manager(runtime_shell)
        assert node.group == manager.group_by_identifier("root")

    async def test_chown_group_change_requires_ownership(self, runtime_shell):
        """A member of the target group still needs to own the file."""
        result = await runtime_shell.execute("chown :user /etc/hostname")
        assert_error(result)
        assert "permission denied" in stderr_text(result)

    async def test_chown_group_change_by_owner_member(self, runtime_shell):
        """A non-root owner may change the group to a group it belongs to."""
        self._seed_owned_node(runtime_shell, "/tmp/owned.txt", "user", "root")

        result = await runtime_shell.execute("chown :user /tmp/owned.txt")
        assert_success(result)

        node = runtime_shell.filesystem.get_node("/tmp/owned.txt")
        manager = self._manager(runtime_shell)
        owner = manager.user_by_identifier("user")
        user_group = manager.group_by_identifier("user")
        assert node.owner == owner
        assert node.group == user_group

    async def test_chown_multiple_files(self, runtime_shell):
        """Chown applies the same owner/group to every listed file."""
        self._as_root(runtime_shell)
        for path in ("/home/user/one.txt", "/home/user/two.txt"):
            result = runtime_shell.filesystem.touch(path, execution=runtime_shell.execution_context)
            assert result.exit_code.value == 0

        result = await runtime_shell.execute(
            "chown user:user /home/user/one.txt /home/user/two.txt"
        )
        assert_success(result)

        manager = self._manager(runtime_shell)
        user = manager.user_by_identifier("user")
        for path in ("/home/user/one.txt", "/home/user/two.txt"):
            node = runtime_shell.filesystem.get_node(path)
            assert node.owner == user
            assert node.group == manager.group_by_identifier("user")

    async def test_chown_directory(self, runtime_shell):
        """Chown works on directories while preserving directory state."""
        self._as_root(runtime_shell)
        result = await runtime_shell.execute("chown user:user /home/user")
        assert_success(result)

        node = runtime_shell.filesystem.get_node("/home/user")
        manager = self._manager(runtime_shell)
        assert node.is_directory is True
        assert node.owner == manager.user_by_identifier("user")

    async def test_chown_resolves_scenario_local_user(self, runtime_shell):
        """Chown resolves against the scenario's authoritative identity state."""
        assert_success(await runtime_shell.execute("useradd alice"))
        self._as_root(runtime_shell)

        result = await runtime_shell.execute("chown alice /etc/hostname")
        assert_success(result)

        node = runtime_shell.filesystem.get_node("/etc/hostname")
        alice = self._manager(runtime_shell).user_by_identifier("alice")
        assert node.owner == alice
        assert "alice" not in runtime_shell.scenario.users

    async def test_chown_missing_operand(self, runtime_shell):
        """Chown with no arguments reports a missing operand."""
        result = await runtime_shell.execute("chown")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_chown_no_files(self, runtime_shell):
        """Chown with a spec but no files reports a missing operand."""
        result = await runtime_shell.execute("chown root")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_chown_invalid_owner(self, runtime_shell):
        """An unknown owner is rejected before touching the filesystem."""
        result = await runtime_shell.execute("chown ghost /etc/hostname")
        assert_error(result)
        assert "chown: invalid user: 'ghost'" in stderr_text(result)

    async def test_chown_invalid_group(self, runtime_shell):
        """An unknown group is rejected before touching the filesystem."""
        result = await runtime_shell.execute("chown :ghost /etc/hostname")
        assert_error(result)
        assert "chown: invalid group: 'ghost'" in stderr_text(result)

    async def test_chown_empty_spec(self, runtime_shell):
        """An empty specification is rejected."""
        result = await runtime_shell.execute("chown '' /etc/hostname")
        assert_invalid_args(result)
        assert "invalid owner: ''" in stderr_text(result)

    async def test_chown_trailing_colon_rejected(self, runtime_shell):
        """The login-group form ``OWNER:`` is unsupported and rejected."""
        result = await runtime_shell.execute("chown root: /etc/hostname")
        assert_invalid_args(result)
        assert "invalid group: ''" in stderr_text(result)

    async def test_chown_missing_file(self, runtime_shell):
        """A missing path reports not found."""
        self._as_root(runtime_shell)
        result = await runtime_shell.execute("chown root /nope")
        assert_error(result)
        assert "no such file or directory" in stderr_text(result)
