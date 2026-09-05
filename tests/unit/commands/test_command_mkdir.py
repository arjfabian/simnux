"""Tests for the ``mkdir`` command implementation.

Covers creating new directories, error handling for existing paths,
missing parent directories, file-as-parent, missing operand, and
relative path resolution.
"""

import pytest

from simnux.core.commands.errors import CommandError
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


class TestMkdirCommand:
    """Directory creation via the ``mkdir`` command.

    Uses the ``shell_with_commands`` fixture. Covers new directory
    creation, error handling for existing paths, missing parents,
    and argument validation.
    """

    async def test_mkdir_new_dir(self, shell_with_commands):
        """Mkdir creates a new directory."""
        result = await shell_with_commands.execute("mkdir /home/user/newdir")
        assert_success(result)
        assert shell_with_commands.filesystem.get_node("/home/user/newdir").is_directory

    async def test_mkdir_existing(self, shell_with_commands):
        """Mkdir on an existing directory returns FILE_EXISTS."""
        result = await shell_with_commands.execute("mkdir /home/user")
        assert_error(result)
        assert CommandError.FILE_EXISTS in stderr_text(result)

    async def test_mkdir_existing_file(self, shell_with_commands):
        """Mkdir on an existing file path returns FILE_EXISTS."""
        result = await shell_with_commands.execute("mkdir /etc/hostname")
        assert_error(result)
        assert CommandError.FILE_EXISTS in stderr_text(result)

    async def test_mkdir_no_args(self, shell_with_commands):
        """Mkdir with no arguments returns MISSING_FILE_OPERAND."""
        result = await shell_with_commands.execute("mkdir")
        assert_invalid_args(result)
        assert CommandError.MISSING_FILE_OPERAND in stderr_text(result)

    async def test_mkdir_parent_nonexistent(self, shell_with_commands):
        """Mkdir where the parent does not exist returns NOT_FOUND."""
        result = await shell_with_commands.execute("mkdir /nonexistent/subdir")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_mkdir_parent_is_file(self, shell_with_commands):
        """Mkdir where the parent is a file returns NOT_A_DIRECTORY."""
        result = await shell_with_commands.execute("mkdir /etc/hostname/subdir")
        assert_error(result)
        assert CommandError.NOT_A_DIRECTORY in stderr_text(result)

    async def test_mkdir_relative_path(self, shell_with_commands):
        """Mkdir with a relative path resolves against the session CWD."""
        shell_with_commands.set_cwd("/etc")
        result = await shell_with_commands.execute("mkdir newdir")
        assert_success(result)
        assert shell_with_commands.filesystem.get_node("/etc/newdir").is_directory

    async def test_mkdir_verify_created(self, shell_with_commands):
        """Mkdir directory is visible via the filesystem."""
        result = await shell_with_commands.execute("mkdir /var/log/nginx")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/var/log/nginx")
        assert node is not None
        assert node.is_directory
        assert node.content == ""
