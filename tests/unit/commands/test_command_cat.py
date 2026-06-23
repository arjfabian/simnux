"""Tests for the ``cat`` command implementation.

Covers reading existing files, handling nonexistent paths, missing
operands, directory rejection, and relative path resolution.
"""

from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text

from simnux.commands.errors import CommandError


class TestCatCommand:
    """File content display via the ``cat`` command.

    Uses the ``shell_with_commands`` fixture which provides a shell with
    all standard commands loaded and the ``base_layer`` filesystem
    (containing ``/home/user/notes.txt``, ``/etc/hostname``, etc.).
    """

    def test_cat_existing_file(self, shell_with_commands):
        """Cat on an existing file returns its content with SUCCESS."""
        result = shell_with_commands.execute("cat /etc/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

    def test_cat_nonexistent(self, shell_with_commands):
        """Cat on a nonexistent path returns ERROR with NOT_FOUND."""
        result = shell_with_commands.execute("cat /missing")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    def test_cat_no_args(self, shell_with_commands):
        """Cat with no arguments returns INVALID_ARGUMENT with MISSING_OPERAND."""
        result = shell_with_commands.execute("cat")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    def test_cat_directory(self, shell_with_commands):
        """Cat on a directory returns ERROR with IS_A_DIRECTORY (prevents binary output)."""
        result = shell_with_commands.execute("cat /home")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    def test_cat_relative_path(self, shell_with_commands):
        """Cat resolves relative paths against the session's CWD."""
        result = shell_with_commands.execute("cat notes.txt")
        assert_success(result)
        assert "hello world" in stdout_text(result)
