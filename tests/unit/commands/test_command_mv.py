"""Tests for the ``mv`` command implementation.

Covers moving (rename) file content to new and existing targets,
implicit directory appending when the target is a directory, atomic
cleanup on failed source deletion, and error handling for nonexistent
paths, directories, and missing operands.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from simnux.core.commands.errors import CommandError
from simnux.core.commands.streams import QueueStreamWriter
from simnux.core.runtime.models import ExitCode
from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import make_mock_context
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestMvCommand:
    """File move/rename via the ``mv`` command.

    Uses the ``shell_with_commands`` fixture which provides a shell with
    all standard commands loaded and the ``base_layer`` filesystem
    (containing ``/home/user/notes.txt``, ``/etc/hostname``, etc.).
    """

    async def test_mv_file_to_new_file(self, shell_with_commands):
        """Mv moves a file to a new path — target has content, source is gone."""
        result = await shell_with_commands.execute("mv /etc/hostname /home/user/moved_hostname")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/moved_hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_mv_overwrite_existing(self, shell_with_commands):
        """Mv overwrites the target file then deletes the source."""
        result = await shell_with_commands.execute("mv /etc/hostname /home/user/notes.txt")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/notes.txt")
        assert "simnux-edge" in stdout_text(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_error(result)

    async def test_mv_nonexistent_source(self, shell_with_commands):
        """Mv on a nonexistent source returns ERROR with NOT_FOUND."""
        result = await shell_with_commands.execute("mv /missing/file /home/user/target")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_mv_source_is_directory(self, shell_with_commands):
        """Mv with a directory source returns ERROR with IS_A_DIRECTORY."""
        result = await shell_with_commands.execute("mv /home /home/user/target")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_mv_to_directory_appends_basename(self, shell_with_commands):
        """Mv to a directory implicitly appends the source basename."""
        result = await shell_with_commands.execute("mv /etc/hostname /home/user")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_error(result)

    async def test_mv_to_directory_with_trailing_slash(self, shell_with_commands):
        """Mv to a directory with trailing slash appends basename."""
        result = await shell_with_commands.execute("mv /etc/hostname /home/user/")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_error(result)

    async def test_mv_to_directory_overwrites_existing(self, shell_with_commands):
        """Mv to a directory overwrites an existing file at the implied path."""
        await shell_with_commands.execute("touch /home/user/hostname")

        result = await shell_with_commands.execute("mv /etc/hostname /home/user")
        assert_success(result)

        result = await shell_with_commands.execute("cat /home/user/hostname")
        assert "simnux-edge" in stdout_text(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_error(result)

    async def test_mv_to_directory_implied_target_is_directory(self, shell_with_commands):
        """Mv to directory errors when the implied path is itself a directory."""
        await shell_with_commands.execute("mkdir /home/user/hostname")

        result = await shell_with_commands.execute("mv /etc/hostname /home/user")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_mv_same_file(self, shell_with_commands):
        """Mv with source == target is a no-op and returns SUCCESS."""
        result = await shell_with_commands.execute("mv /etc/hostname /etc/hostname")
        assert_success(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert "simnux-edge" in stdout_text(result)

    async def test_mv_same_file_via_directory_appending(self, shell_with_commands):
        """Mv with source basename resolving to itself via dir appending is a no-op."""
        result = await shell_with_commands.execute("mv /etc/hostname /etc")
        assert_success(result)

        result = await shell_with_commands.execute("cat /etc/hostname")
        assert "simnux-edge" in stdout_text(result)

    async def test_mv_missing_operand(self, shell_with_commands):
        """Mv with no arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("mv")
        assert result.exit_code == ExitCode.INVALID_ARGUMENT
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_mv_single_arg(self, shell_with_commands):
        """Mv with only a source returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("mv /etc/hostname")
        assert result.exit_code == ExitCode.INVALID_ARGUMENT
        assert CommandError.MISSING_OPERAND in stderr_text(result)


class TestMvAtomicCleanup:
    """Isolated unit tests for mv's atomic cleanup logic.

    These tests use mocked filesystems to verify that a failed source
    deletion triggers cleanup only for brand-new target paths. When
    the target pre-existed, the target is preserved (not deleted).
    """

    async def test_mv_cleanup_on_delete_failure(self):
        """If ``delete_file`` fails after target write, the target is cleaned up."""
        from simnux.core.commands.standard.mv import Command
        from simnux.core.filesystem.vfs import SNXFileSystem

        cmd = Command(context=MagicMock())
        cmd.args = ["/source", "/target"]
        cmd.resolve_path = lambda t, c: t

        fs = MagicMock(spec=SNXFileSystem)
        fs.read.return_value = MagicMock(
            exit_code=ExitCode.SUCCESS,
            node=MagicMock(content="data", is_directory=False),
        )
        fs.is_directory.return_value = False
        fs.exists.return_value = False  # target is a brand-new path
        fs.touch.return_value = MagicMock(exit_code=ExitCode.SUCCESS)
        fs.write.return_value = MagicMock(exit_code=ExitCode.SUCCESS)
        fs.delete_file.side_effect = [
            MagicMock(exit_code=ExitCode.ERROR, message="permission denied"),
            MagicMock(exit_code=ExitCode.SUCCESS),
        ]

        mock_ctx = make_mock_context(filesystem=fs)

        stdout_writer = QueueStreamWriter(asyncio.Queue())
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await cmd.execute(
            ctx=mock_ctx,
            stdin=MagicMock(),
            stdout=stdout_writer,
            stderr=stderr_writer,
        )

        assert result == ExitCode.ERROR
        assert fs.delete_file.call_count == 2
        fs.delete_file.assert_any_call("/source")
        fs.delete_file.assert_any_call("/target")

    async def test_mv_cleanup_not_called_on_success(self):
        """When ``delete_file`` succeeds, no extra cleanup call is made."""
        from simnux.core.commands.standard.mv import Command
        from simnux.core.filesystem.vfs import SNXFileSystem

        cmd = Command(context=MagicMock())
        cmd.args = ["/source", "/target"]
        cmd.resolve_path = lambda t, c: t

        fs = MagicMock(spec=SNXFileSystem)
        fs.read.return_value = MagicMock(
            exit_code=ExitCode.SUCCESS,
            node=MagicMock(content="data", is_directory=False),
        )
        fs.is_directory.return_value = False
        fs.touch.return_value = MagicMock(exit_code=ExitCode.SUCCESS)
        fs.write.return_value = MagicMock(exit_code=ExitCode.SUCCESS)
        fs.delete_file.return_value = MagicMock(exit_code=ExitCode.SUCCESS)

        mock_ctx = make_mock_context(filesystem=fs)

        stdout_writer = QueueStreamWriter(asyncio.Queue())
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await cmd.execute(
            ctx=mock_ctx,
            stdin=MagicMock(),
            stdout=stdout_writer,
            stderr=stderr_writer,
        )

        assert result == ExitCode.SUCCESS
        assert fs.delete_file.call_count == 1
        fs.delete_file.assert_called_once_with("/source")

    async def test_mv_failed_source_delete_preserves_pre_existing_target(self):
        """If ``delete_file`` fails and the target pre-existed, the target is not deleted."""
        from simnux.core.commands.standard.mv import Command
        from simnux.core.filesystem.vfs import SNXFileSystem

        cmd = Command(context=MagicMock())
        cmd.args = ["/source", "/target"]
        cmd.resolve_path = lambda t, c: t

        fs = MagicMock(spec=SNXFileSystem)
        fs.read.return_value = MagicMock(
            exit_code=ExitCode.SUCCESS,
            node=MagicMock(content="data", is_directory=False),
        )
        fs.is_directory.return_value = False
        fs.exists.return_value = True  # target already exists (overwrite)
        fs.touch.return_value = MagicMock(exit_code=ExitCode.SUCCESS)
        fs.write.return_value = MagicMock(exit_code=ExitCode.SUCCESS)
        fs.delete_file.return_value = MagicMock(
            exit_code=ExitCode.ERROR,
            message="permission denied",
        )

        mock_ctx = make_mock_context(filesystem=fs)

        stdout_writer = QueueStreamWriter(asyncio.Queue())
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await cmd.execute(
            ctx=mock_ctx,
            stdin=MagicMock(),
            stdout=stdout_writer,
            stderr=stderr_writer,
        )

        assert result == ExitCode.ERROR
        # delete_file called exactly once — for the source only; no target cleanup
        assert fs.delete_file.call_count == 1
        fs.delete_file.assert_called_once_with("/source")
