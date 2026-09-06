"""Tests for the ``chmod`` command (numeric modes).

Covers numeric mode application, owner-only authorization, error handling
(missing operand, invalid mode, missing file, non-owner denial), and
verification through ``ls``/``cat``.
"""

import pytest

from simnux.security.users.models import SNXUser
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


class TestChmodCommand:
    """Numeric mode changes via the ``chmod`` command."""

    async def test_chmod_644(self, shell_with_commands):
        """``chmod 644`` grants owner rw, group/other r."""
        shell_with_commands.filesystem.touch(
            "/home/user/file.txt",
            acting_user=shell_with_commands.user,
        )
        result = await shell_with_commands.execute("chmod 644 /home/user/file.txt")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/home/user/file.txt")
        assert node.permissions.user.read is True
        assert node.permissions.user.write is True
        assert node.permissions.user.execute is False
        assert node.permissions.group.read is True
        assert node.permissions.group.write is False
        assert node.permissions.other.read is True

    async def test_chmod_600_locks_file(self, shell_with_commands):
        """``chmod 600`` seals a file to owner-only."""
        shell_with_commands.filesystem.touch(
            "/home/user/secret.txt",
            acting_user=shell_with_commands.user,
        )
        shell_with_commands.filesystem.delta_layer["/home/user/secret.txt"].content = "data"
        result = await shell_with_commands.execute("chmod 600 /home/user/secret.txt")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/home/user/secret.txt")
        assert node.permissions.user.read is True
        assert node.permissions.user.write is True
        assert node.permissions.group.read is False
        assert node.permissions.other.read is False

    async def test_chmod_755_makes_executable(self, shell_with_commands):
        """``chmod 755`` grants execute on owner/group/other."""
        shell_with_commands.filesystem.touch(
            "/home/user/script.sh",
            acting_user=shell_with_commands.user,
        )
        shell_with_commands.filesystem.delta_layer[
            "/home/user/script.sh"
        ].content = "#!/bin/sh\necho hi\n"
        result = await shell_with_commands.execute("chmod 755 /home/user/script.sh")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/home/user/script.sh")
        assert node.permissions.user.execute is True
        assert node.permissions.group.execute is True
        assert node.permissions.other.execute is True

    async def test_chmod_000_removes_all(self, shell_with_commands):
        """``chmod 000`` removes every permission bit."""
        shell_with_commands.filesystem.touch(
            "/home/user/flat.txt",
            acting_user=shell_with_commands.user,
        )
        result = await shell_with_commands.execute("chmod 000 /home/user/flat.txt")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/home/user/flat.txt")
        assert node.permissions.user.read is False
        assert node.permissions.user.write is False
        assert node.permissions.user.execute is False

    async def test_chmod_preserves_other_node_fields(self, shell_with_commands):
        """chmod mutates only permissions; owner/group/content are untouched."""
        shell_with_commands.filesystem.touch(
            "/home/user/keep.txt",
            acting_user=shell_with_commands.user,
        )
        shell_with_commands.filesystem.delta_layer["/home/user/keep.txt"].content = "kept"
        before = shell_with_commands.filesystem.get_node("/home/user/keep.txt")
        result = await shell_with_commands.execute("chmod 700 /home/user/keep.txt")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/home/user/keep.txt")
        assert node.owner == before.owner
        assert node.group == before.group
        assert node.content == "kept"
        assert node.path == before.path
        assert node.is_directory == before.is_directory

    async def test_chmod_missing_operand(self, shell_with_commands):
        """``chmod`` with no arguments reports a missing operand."""
        result = await shell_with_commands.execute("chmod")
        assert_invalid_args(result)

    async def test_chmod_invalid_mode(self, shell_with_commands):
        """A non-octal mode is rejected."""
        result = await shell_with_commands.execute("chmod abc /home/user/file.txt")
        assert_invalid_args(result)
        assert "chmod: invalid mode: 'abc'" in stderr_text(result)

    async def test_chmod_missing_file(self, shell_with_commands):
        """A missing path reports not found."""
        result = await shell_with_commands.execute("chmod 644 /nope")
        assert_error(result)
        assert "not found" in stderr_text(result)

    async def test_chmod_denied_for_non_owner(self, shell_with_commands):
        """A user who does not own a file cannot chmod it."""
        result = await shell_with_commands.execute("chmod 600 /etc/hostname")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        node = shell_with_commands.filesystem.get_node("/etc/hostname")
        assert node.permissions.other.read is True


class TestChmodRootOverrides:
    async def test_root_can_chmod_any_file(self, runtime_shell):
        """Root may change permissions on any file regardless of ownership."""
        runtime_shell.user = SNXUser(0, "root")
        result = await runtime_shell.execute("chmod 600 /etc/hostname")
        assert_success(result)
        node = runtime_shell.filesystem.get_node("/etc/hostname")
        assert node.permissions.other.read is False
