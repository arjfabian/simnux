"""Tests for the ``ls`` command implementation.

Covers listing root and nested directories, nonexistent/file targets,
CWD default, POSIX dotfile filtering (``-a``, ``-A``), alphabetical
sorting, and the ``-l`` long format (file type, permission bits, owner,
group, name).
"""

import pytest

from simnux.core.commands.errors import CommandError
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import permissions_symbolic
from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


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
    """``ls -l`` renders file type, perms, owner, group, and name."""

    pytestmark = pytest.mark.asyncio

    async def test_regular_file_644(self, shell_with_commands):
        result = await shell_with_commands.execute("ls -l /home/user")
        assert_success(result)
        assert "-rw-r--r-- user user notes.txt" in stdout_text(result)

    async def test_directory_755(self, shell_with_commands):
        result = await shell_with_commands.execute("ls -l /")
        assert_success(result)
        assert "drwxr-xr-x root root home" in stdout_text(result)

    async def test_file_600(self, shell_with_commands):
        fs = shell_with_commands.filesystem
        fs.chmod("/home/user/notes.txt", 0o600, acting_user=shell_with_commands.user)
        result = await shell_with_commands.execute("ls -l /home/user")
        assert_success(result)
        assert "-rw------- user user notes.txt" in stdout_text(result)

    async def test_file_000(self, shell_with_commands):
        fs = shell_with_commands.filesystem
        fs.chmod("/home/user/notes.txt", 0o000, acting_user=shell_with_commands.user)
        result = await shell_with_commands.execute("ls -l /home/user")
        assert_success(result)
        assert "---------- user user notes.txt" in stdout_text(result)

    async def test_owner_group_identifiers_rendered(self, shell_with_commands):
        """Owner and group are the in-memory ``identifier`` strings."""
        result = await shell_with_commands.execute("ls -l /home/user")
        stdout = stdout_text(result)
        assert "-rw-r--r-- user user notes.txt" in stdout
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
        from simnux.security.users.models import SNXUser

        root = SNXUser(0, "root")
        fs = shell_with_commands.filesystem
        fs.create_directory("/sealed", acting_user=root)
        fs.chmod("/sealed", 0o700, acting_user=root)
        result = await shell_with_commands.execute("ls -l /sealed")
        assert_error(result)
        assert "permission denied" in stderr_text(result)

    async def test_long_combined_flag_la(self, shell_with_commands):
        """``ls -la`` includes dot entries with their directory metadata."""
        result = await shell_with_commands.execute("ls -la /home/user")
        assert_success(result)
        stdout = stdout_text(result)
        assert "drwxr-xr-x user user ." in stdout
        assert "drwxr-xr-x root root .." in stdout
        assert "-rw-r--r-- user user notes.txt" in stdout

    async def test_long_combined_flag_al_root(self, shell_with_commands):
        """``ls -al /`` shows ``.`` but not ``..`` for the root directory."""
        result = await shell_with_commands.execute("ls -al /")
        assert_success(result)
        stdout = stdout_text(result)
        assert "drwxr-xr-x root root ." in stdout
        assert " .." not in stdout

    async def test_no_size_or_timestamp_columns(self, shell_with_commands):
        """Each long line has exactly four fields: perms, owner, group, name."""
        result = await shell_with_commands.execute("ls -l /")
        assert_success(result)
        for line in stdout_text(result).splitlines():
            fields = line.split()
            assert len(fields) == 4
            assert fields[0].startswith(("d", "-"))
            assert not fields[1][0].isdigit()
