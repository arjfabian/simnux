"""Tests for the ``cp`` command implementation.

Covers copying file content to new and existing targets, implicit
directory appending when the target is a directory, and error handling
for nonexistent paths, directories, and missing operands.
"""

import pytest

from simnux.core.commands.errors import CommandError
from simnux.core.runtime.models import ExitCode
from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestCpCommand:
    """File copy via the ``cp`` command.

    Uses the ``shell_with_commands`` fixture which provides a shell with
    all standard commands loaded and the ``base_layer`` filesystem
    (containing ``/home/user/notes.txt``, ``/etc/hostname``, etc.).
    """

    async def test_cp_file_to_new_file(self, shell_with_commands):
        """Cp copies content to a new file path."""
        result = await shell_with_commands.execute("cp /etc/hostname /home/user/hostname_copy")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/hostname_copy")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

    async def test_cp_overwrite_existing(self, shell_with_commands):
        """Cp overwrites the target file when it already exists."""
        result = await shell_with_commands.execute("cp /etc/hostname /home/user/notes.txt")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/notes.txt")
        assert "simnux-edge" in stdout_text(result)

    async def test_cp_nonexistent_source(self, shell_with_commands):
        """Cp on a nonexistent source returns ERROR with NOT_FOUND."""
        result = await shell_with_commands.execute("cp /missing/file /home/user/target")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_cp_source_is_directory(self, shell_with_commands):
        """Cp with a directory source returns ERROR with IS_A_DIRECTORY."""
        result = await shell_with_commands.execute("cp /home /home/user/target")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_cp_to_directory_appends_basename(self, shell_with_commands):
        """Cp to a directory implicitly appends the source basename."""
        result = await shell_with_commands.execute("cp /etc/hostname /home/user")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

    async def test_cp_to_directory_with_trailing_slash(self, shell_with_commands):
        """Cp to a directory with trailing slash appends basename."""
        result = await shell_with_commands.execute("cp /etc/hostname /home/user/")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

    async def test_cp_to_directory_overwrites_existing(self, shell_with_commands):
        """Cp to a directory overwrites an existing file at the implied path."""
        await shell_with_commands.execute("touch /home/user/hostname")

        result = await shell_with_commands.execute("cp /etc/hostname /home/user")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/hostname")
        assert "simnux-edge" in stdout_text(result)

    async def test_cp_to_directory_implied_target_is_directory(self, shell_with_commands):
        """Cp to directory errors when the implied path is itself a directory."""
        await shell_with_commands.execute("mkdir /home/user/hostname")

        result = await shell_with_commands.execute("cp /etc/hostname /home/user")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_cp_same_file(self, shell_with_commands):
        """Cp with source == target is a no-op and returns SUCCESS."""
        result = await shell_with_commands.execute("cp /etc/hostname /etc/hostname")
        assert_success(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert "simnux-edge" in stdout_text(result)

    async def test_cp_same_file_via_directory_appending(self, shell_with_commands):
        """Cp with source basename resolving to itself via dir appending is a no-op."""
        result = await shell_with_commands.execute("cp /etc/hostname /etc")
        assert_success(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert "simnux-edge" in stdout_text(result)

    async def test_cp_missing_operand(self, shell_with_commands):
        """Cp with no arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("cp")
        assert result.exit_code == ExitCode.INVALID_ARGUMENT
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_cp_single_arg(self, shell_with_commands):
        """Cp with only a source returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("cp /etc/hostname")
        assert result.exit_code == ExitCode.INVALID_ARGUMENT
        assert CommandError.MISSING_OPERAND in stderr_text(result)
