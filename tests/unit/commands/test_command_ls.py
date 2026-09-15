"""Tests for the ``ls`` command implementation.

Covers listing root and nested directories, nonexistent/file targets,
CWD default, POSIX dotfile filtering (``-a``, ``-A``), alphabetical
sorting, and the ``-l`` long format (file type, permission bits, owner,
group, name).
"""

import datetime

import pytest

from simnux.core.commands.errors import CommandError
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import permissions_symbolic
from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import make_command_shell
from tests.helpers import stderr_text
from tests.helpers import stdout_text


_FIXED_NOW = datetime.datetime(2023, 5, 9, 14, 22, 0)


class TestLsCommand:
    """Directory listing via the ``ls`` command.

    Uses the ``shell_with_commands`` fixture for basic tests and
    ``runtime_shell`` (hello scenario) for hidden-file tests.
    """

    pytestmark = pytest.mark.asyncio

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
        assert "lipsum.txt" in stdout

    async def test_ls_a_shows_dotfiles(self, runtime_shell):
        """``ls -a`` includes hidden files, ``.``, and ``..``."""
        result = await runtime_shell.execute("ls -a /home/user")
        stdout = stdout_text(result)
        assert "." in stdout
        assert ".." in stdout
        assert ".config/" in stdout or ".config" in stdout
        assert "lipsum.txt" in stdout

    async def test_ls_almost_all_shows_dotfiles_without_dot_entries(self, runtime_shell):
        """``ls -A`` includes hidden files but NOT ``.`` or ``..``."""
        result = await runtime_shell.execute("ls -A /home/user")
        stdout = stdout_text(result)
        entries = stdout.split("  ")
        assert "." not in entries
        assert ".." not in entries
        assert ".config/" in entries
        assert "lipsum.txt" in entries

    async def test_ls_sorted_output(self, shell_with_commands):
        """Output entries are sorted alphabetically."""
        result = await shell_with_commands.execute("ls /")
        stdout = stdout_text(result)
        names = stdout.split("  ")
        assert names == sorted(names)


class TestPermissionsSymbolic:
    """The nine-character permission renderer used by ``ls -l``."""

    def test_regular_file_default(self):
        assert permissions_symbolic(PermissionPresets.FILE_DEFAULT) == "rw-r--r--"

    def test_directory_default(self):
        assert permissions_symbolic(PermissionPresets.DIRECTORY_DEFAULT) == "rwxr-xr-x"

    def test_owner_only_write(self):
        from simnux.core.filesystem.models import PermissionFlags
        from simnux.core.filesystem.models import SNXPermissions

        permissions = SNXPermissions(user=PermissionFlags.rw())
        assert permissions_symbolic(permissions) == "rw-------"

    def test_none_set(self):
        from simnux.core.filesystem.models import SNXPermissions

        assert permissions_symbolic(SNXPermissions()) == "---------"

    def test_deterministic(self):
        assert permissions_symbolic(PermissionPresets.FILE_DEFAULT) == permissions_symbolic(
            PermissionPresets.FILE_DEFAULT
        )


class TestLsLongFormat:
    """``ls -l`` renders file type, perms, owner, group, size, mtime, and name."""

    pytestmark = pytest.mark.asyncio

    async def test_regular_file_644(self, shell_with_commands):
        result = await shell_with_commands.execute("ls -l /home/user")
        assert_success(result)
        assert "-rw-r--r-- user user 11 Jan  1  1970 notes.txt" in stdout_text(result)

    async def test_regular_file_empty_size_zero(self, base_layer, test_logger):
        """A freshly touched empty file reports size 0 and its mtime in ``ls -l``."""
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        fs = shell.filesystem
        fs.touch("/home/user/empty.txt", execution=shell.execution_context)
        result = await shell.execute("ls -l /home/user")
        assert_success(result)
        assert "-rw-r--r-- user user  0 May  9 14:22 empty.txt" in stdout_text(result)

    async def test_directory_755(self, shell_with_commands):
        result = await shell_with_commands.execute("ls -l /")
        assert_success(result)
        assert "drwxr-xr-x root root 0 Jan  1  1970 home" in stdout_text(result)

    async def test_file_600(self, shell_with_commands):
        fs = shell_with_commands.filesystem
        fs.chmod("/home/user/notes.txt", 0o600, execution=shell_with_commands.execution_context)
        result = await shell_with_commands.execute("ls -l /home/user")
        assert_success(result)
        assert "-rw------- user user 11 Jan  1  1970 notes.txt" in stdout_text(result)

    async def test_file_000(self, shell_with_commands):
        fs = shell_with_commands.filesystem
        fs.chmod("/home/user/notes.txt", 0o000, execution=shell_with_commands.execution_context)
        result = await shell_with_commands.execute("ls -l /home/user")
        assert_success(result)
        assert "---------- user user 11 Jan  1  1970 notes.txt" in stdout_text(result)

    async def test_owner_group_identifiers_rendered(self, shell_with_commands):
        """Owner and group are the in-memory ``identifier`` strings."""
        result = await shell_with_commands.execute("ls -l /home/user")
        stdout = stdout_text(result)
        assert "-rw-r--r-- user user 11 Jan  1  1970 notes.txt" in stdout
        assert "root" not in stdout.split("notes.txt")[0]

    async def test_ls_without_l_long_unchanged(self, shell_with_commands):
        """``ls`` without ``-l`` keeps the name-only single-line output."""
        result = await shell_with_commands.execute("ls /home/user")
        assert_success(result)
        assert stdout_text(result) == "notes.txt"

    async def test_ls_al_long_unchanged(self, runtime_shell):
        """``ls -a`` still renders name-only output (no metadata columns)."""
        result = await runtime_shell.execute("ls -a /home/user")
        stdout = stdout_text(result)
        assert "lipsum.txt" in stdout
        assert "rw-r--r--" not in stdout

    async def test_long_respects_permission_enforcement(self, shell_with_commands):
        """``ls -l`` on a sealed directory is denied via list_directory."""
        from simnux.security.execution.models import ExecutionContext
        from simnux.security.users.models import SNXUser

        root = ExecutionContext.for_user(SNXUser(0, "root"))
        fs = shell_with_commands.filesystem
        fs.create_directory("/sealed", execution=root)
        fs.chmod("/sealed", 0o700, execution=root)
        result = await shell_with_commands.execute("ls -l /sealed")
        assert_error(result)
        assert "permission denied" in stderr_text(result)

    async def test_long_combined_flag_la(self, base_layer, test_logger):
        """``ls -la`` includes dot entries with their directory metadata."""
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        await shell.execute("echo longer content > /home/user/notes.txt")
        result = await shell.execute("ls -la /home/user")
        assert_success(result)
        stdout = stdout_text(result)
        assert "drwxr-xr-x user user  0 Jan  1  1970 ." in stdout
        assert "drwxr-xr-x root root  0 Jan  1  1970 .." in stdout
        assert "-rw-r--r-- user user 14 May  9 14:22 notes.txt" in stdout

    async def test_long_combined_flag_al_root(self, shell_with_commands):
        """``ls -al /`` shows ``.`` but not ``..`` for the root directory."""
        result = await shell_with_commands.execute("ls -al /")
        assert_success(result)
        stdout = stdout_text(result)
        assert "drwxr-xr-x root root 0 Jan  1  1970 ." in stdout
        assert " .." not in stdout

    async def test_size_column_tracks_content(self, base_layer, test_logger):
        """The size column follows the current content of each file."""
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        await shell.execute("echo longer content > /home/user/notes.txt")
        result = await shell.execute("ls -l /home/user")
        assert_success(result)
        assert "-rw-r--r-- user user 14 May  9 14:22 notes.txt" in stdout_text(result)

    async def test_long_renders_mtime_column(self, shell_with_commands):
        """Each ``ls -l`` line carries an mtime column between size and name."""
        result = await shell_with_commands.execute("ls -l /home/user")
        assert_success(result)
        line = stdout_text(result)
        assert "Jan  1  1970" in line
        assert line.index("notes.txt") > line.index("Jan")
