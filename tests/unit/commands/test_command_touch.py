"""Tests for the ``touch`` command implementation.

Covers creating new files, no-op on existing files, missing operand
rejection, and relative path support.
"""

from simnux.commands.errors import CommandError

from tests.helpers import (
    assert_success,
    assert_invalid_args,
    stderr_text,
    stdout_text,
) 

class TestTouchCommand:
    """File creation via the ``touch`` command.

    Uses the ``shell_with_commands`` fixture. Covers new file creation,
    no-op on existing files, missing operand rejection, and verification
    via ``ls``.
    """

    def test_touch_new_file(self, shell_with_commands):
        """Touch creates a new empty file."""
        result = shell_with_commands.execute("touch /home/user/newfile.txt")
        assert_success(result)
        assert shell_with_commands.filesystem.exists("/home/user/newfile.txt")

    def test_touch_existing_file_is_noop(self, shell_with_commands):
        """Touch on an existing file does not alter its content."""
        result = shell_with_commands.execute("touch /etc/hostname")
        assert_success(result)
        assert shell_with_commands.filesystem.get_node("/etc/hostname").content == "simnux-edge"

    def test_touch_no_args(self, shell_with_commands):
        """Touch with no arguments returns INVALID_ARGUMENT (MISSING_FILE_OPERAND)."""
        result = shell_with_commands.execute("touch")
        assert_invalid_args(result)
        assert CommandError.MISSING_FILE_OPERAND in stderr_text(result)

    def test_touch_relative_path(self, shell_with_commands):
        """Touch creates a file and it appears in subsequent directory listings."""
        result = shell_with_commands.execute("touch /home/user/newfile.txt")

        assert_success(result)

        result_check = shell_with_commands.execute("ls /home/user")

        assert "newfile.txt" in stdout_text(result_check)
