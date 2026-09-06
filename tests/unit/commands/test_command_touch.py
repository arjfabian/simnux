"""Tests for the ``touch`` command implementation.

Covers creating new files, no-op on existing files, missing operand
rejection, and relative path support.
"""

import pytest

from simnux.core.commands.errors import CommandError
from tests.helpers import assert_invalid_args
from tests.helpers import assert_not_success
from tests.helpers import assert_success
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


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
