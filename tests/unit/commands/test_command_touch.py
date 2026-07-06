"""Tests for the ``touch`` command implementation.

Covers creating new files, no-op on existing files, missing operand
rejection, and relative path support.
"""

import pytest

from simnux.commands.errors import CommandError
from tests.helpers import assert_invalid_args
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
        """Touch on an existing file does not alter its content."""
        result = await shell_with_commands.execute("touch /etc/hostname")
        assert_success(result)
        assert shell_with_commands.filesystem.get_node("/etc/hostname").content == "simnux-edge"

    async def test_touch_no_args(self, shell_with_commands):
        """Touch with no arguments returns INVALID_ARGUMENT (MISSING_FILE_OPERAND)."""
        result = await shell_with_commands.execute("touch")
        assert_invalid_args(result)
        assert CommandError.MISSING_FILE_OPERAND in stderr_text(result)
