"""Tests for the ``ls`` command implementation.

Covers listing root and nested directories, nonexistent/file targets,
CWD default, and entry-format markers (``.`` and ``..``).
"""

from simnux.runtime.models import ExitCode
from simnux.commands.errors import CommandError

from tests.helpers import (
    assert_error,
    assert_success,
    stderr_text,
    stdout_text
)


class TestLsCommand:
    """Directory listing via the ``ls`` command.

    Uses the ``shell_with_commands`` fixture. Covers root/nested listing,
    nonexistent/file target errors, CWD default behavior, and entry
    markers (``.`` / ``..``).
    """

    def test_ls_root(self, shell_with_commands):
        """Listing root (``/``) shows top-level directories."""
        result = shell_with_commands.execute("ls /")
        assert_success(result)
        stdout = stdout_text(result)
        assert "home" in stdout
        assert "etc" in stdout

    def test_ls_nonexistent(self, shell_with_commands):
        """Listing a nonexistent path returns ERROR with NO_SUCH_FILE_OR_DIR."""
        result = shell_with_commands.execute("ls /nonexistent")
        assert_error(result)
        assert CommandError.NO_SUCH_FILE_OR_DIR in stderr_text(result)

    def test_ls_file_instead_of_directory(self, shell_with_commands):
        """Listing a file path returns ERROR with NOT_A_DIRECTORY."""
        result = shell_with_commands.execute("ls /etc/hostname")
        assert_error(result)
        assert CommandError.NOT_A_DIRECTORY in stderr_text(result)

    def test_ls_without_args_uses_cwd(self, shell_with_commands):
        """``ls`` with no args lists the current working directory."""
        result = shell_with_commands.execute("ls")
        assert_success(result)
        assert "notes.txt" in stdout_text(result)

    def test_ls_root_has_dot(self, shell_with_commands):
        """Root listing includes ``.`` as an entry."""
        result = shell_with_commands.execute("ls /")
        assert "." in result.stdout

    def test_ls_non_root_has_dotdot(self, shell_with_commands):
        """Non-root directory listing includes both ``.`` and ``..``."""
        result = shell_with_commands.execute("ls /home")
        assert "." in result.stdout
        assert ".." in result.stdout
