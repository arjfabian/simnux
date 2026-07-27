"""Tests for the ``ls`` command implementation.

Covers listing root and nested directories, nonexistent/file targets,
CWD default, POSIX dotfile filtering (``-a``, ``-A``), and alphabetical
sorting.
"""

import pytest

from simnux.commands.errors import CommandError
from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestLsCommand:
    """Directory listing via the ``ls`` command.

    Uses the ``shell_with_commands`` fixture for basic tests and
    ``runtime_shell`` (hello scenario) for hidden-file tests.
    """

    async def test_ls_root(self, shell_with_commands):
        """Listing root (``/``) shows top-level directories (no hidden by default)."""
        result = await shell_with_commands.execute("ls /")
        assert_success(result)
        stdout = stdout_text(result)
        assert "etc" in stdout
        assert "home" in stdout
        assert "var" in stdout

    async def test_ls_nonexistent(self, shell_with_commands):
        """Listing a nonexistent path returns ERROR with NO_SUCH_FILE_OR_DIR."""
        result = await shell_with_commands.execute("ls /nonexistent")
        assert_error(result)
        assert CommandError.NO_SUCH_FILE_OR_DIR in stderr_text(result)

    async def test_ls_file_instead_of_directory(self, shell_with_commands):
        """Listing a file path returns ERROR with NOT_A_DIRECTORY."""
        result = await shell_with_commands.execute("ls /etc/hostname")
        assert_error(result)
        assert CommandError.NOT_A_DIRECTORY in stderr_text(result)

    async def test_ls_without_args_uses_cwd(self, shell_with_commands):
        """``ls`` with no args lists the current working directory."""
        result = await shell_with_commands.execute("ls")
        assert_success(result)
        assert "notes.txt" in stdout_text(result)

    async def test_ls_root_with_a(self, shell_with_commands):
        """``ls -a /`` includes ``.`` but not ``..`` (POSIX — parent of root is root)."""
        result = await shell_with_commands.execute("ls -a /")
        stdout = stdout_text(result)
        assert "." in stdout
        assert ".." not in stdout

    async def test_ls_non_root_with_a(self, shell_with_commands):
        """``ls -a`` on a non-root directory includes both ``.`` and ``..``."""
        result = await shell_with_commands.execute("ls -a /home")
        stdout = stdout_text(result)
        assert "." in stdout
        assert ".." in stdout

    async def test_ls_hides_dotfiles_by_default(self, runtime_shell):
        """Default ``ls`` filters out names starting with ``.``."""
        result = await runtime_shell.execute("ls /home/user")
        stdout = stdout_text(result)
        assert ".config" not in stdout
        assert "notes.txt" in stdout

    async def test_ls_a_shows_dotfiles(self, runtime_shell):
        """``ls -a`` includes hidden files, ``.``, and ``..``."""
        result = await runtime_shell.execute("ls -a /home/user")
        stdout = stdout_text(result)
        assert "." in stdout
        assert ".." in stdout
        assert ".config/" in stdout or ".config" in stdout
        assert "notes.txt" in stdout

    async def test_ls_almost_all_shows_dotfiles_without_dot_entries(self, runtime_shell):
        """``ls -A`` includes hidden files but NOT ``.`` or ``..``."""
        result = await runtime_shell.execute("ls -A /home/user")
        stdout = stdout_text(result)
        entries = stdout.split("  ")
        assert "." not in entries
        assert ".." not in entries
        assert ".config/" in entries
        assert "notes.txt" in entries

    async def test_ls_sorted_output(self, shell_with_commands):
        """Output entries are sorted alphabetically."""
        result = await shell_with_commands.execute("ls /")
        stdout = stdout_text(result)
        names = stdout.split("  ")
        assert names == sorted(names)
