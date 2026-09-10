"""Tests for the ``touch`` command implementation.

Covers creating new files, no-op on existing files, missing operand
rejection, and relative path support.
"""

import datetime

import pytest

from simnux.core.commands.errors import CommandError
from tests.helpers import assert_invalid_args
from tests.helpers import assert_not_success
from tests.helpers import assert_success
from tests.helpers import make_command_shell
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


_FIXED_NOW = datetime.datetime(2024, 6, 15, 9, 30, 0)


class TestTouchCommand:
    """File creation via the ``touch`` command.

    Uses the ``shell_with_commands`` fixture. Covers new file creation,
    no-op on existing files, missing operand rejection, and verification
    via ``ls``.
    """

    async def test_touch_new_file(self, shell_with_commands):
        """Touch creates a new empty file."""
        result = await shell_with_commands.execute("touch /home/user/newfile.txt")
        assert_success(result)
        assert shell_with_commands.filesystem.exists("/home/user/newfile.txt")

    async def test_touch_existing_file_is_noop(self, shell_with_commands):
        """Touch by the non-root user on a root-owned file is denied (WRITE gate)."""
        result = await shell_with_commands.execute("touch /etc/hostname")
        assert_not_success(result)
        assert "permission denied" in stderr_text(result)
        assert shell_with_commands.filesystem.get_node("/etc/hostname").content == "simnux-edge"

    async def test_touch_existing_owned_file_is_noop(self, session, test_logger):
        """Touch on a file the acting user owns succeeds without altering content."""
        filesystem = session.filesystem
        from tests.helpers import create_shell_with_commands

        filesystem.touch("/home/user/locked.txt", acting_user=session.user)
        filesystem.delta_layer["/home/user/locked.txt"].content = "data"

        shell = create_shell_with_commands(session, filesystem, test_logger)
        result = await shell.execute("touch /home/user/locked.txt")
        assert_success(result)
        assert shell.filesystem.get_node("/home/user/locked.txt").content == "data"

    async def test_touch_no_args(self, shell_with_commands):
        """Touch with no arguments returns INVALID_ARGUMENT (MISSING_FILE_OPERAND)."""
        result = await shell_with_commands.execute("touch")
        assert_invalid_args(result)
        assert CommandError.MISSING_FILE_OPERAND in stderr_text(result)

    async def test_touch_new_file_gets_mtime(self, base_layer, test_logger):
        """Touch stamps a new file with the current simulated mtime."""
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        fs = shell.filesystem
        result = await shell.execute("touch /home/user/newfile.txt")
        assert_success(result)
        node = fs.get_node("/home/user/newfile.txt")
        assert node.modified_at == _FIXED_NOW

    async def test_touch_existing_file_updates_mtime(self, base_layer, test_logger):
        """Touch bumps the mtime of an owned file without altering content."""
        current = _FIXED_NOW
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: current,
        )
        fs = shell.filesystem
        result = await shell.execute("touch /home/user/notes.txt")
        assert_success(result)
        node = fs.get_node("/home/user/notes.txt")
        assert node.modified_at == current
        assert node.content == "hello world"

        current = _FIXED_NOW + datetime.timedelta(hours=1)
        result = await shell.execute("touch /home/user/notes.txt")
        assert_success(result)
        node = fs.get_node("/home/user/notes.txt")
        assert node.modified_at == current
        assert node.content == "hello world"

    async def test_touch_denied_does_not_update_mtime(self, base_layer, test_logger):
        """A denied touch leaves the base node's mtime unset."""
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        fs = shell.filesystem
        result = await shell.execute("touch /etc/hostname")
        assert_not_success(result)
        assert fs.get_node("/etc/hostname").modified_at is None
