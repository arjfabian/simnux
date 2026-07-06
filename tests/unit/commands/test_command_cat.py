"""Tests for the ``cat`` command implementation.

Covers reading existing files, stdin fallback, handling nonexistent
paths, directory rejection, relative path resolution, and ``-`` for
explicit stdin interleaved with file paths.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.streams import QueueStreamReader
from simnux.commands.streams import QueueStreamWriter
from simnux.runtime.models import ExitCode
from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import drain_queue
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestCatCommand:
    """File content display via the ``cat`` command.

    Uses the ``shell_with_commands`` fixture which provides a shell with
    all standard commands loaded and the ``base_layer`` filesystem
    (containing ``/home/user/notes.txt``, ``/etc/hostname``, etc.).
    """

    async def test_cat_existing_file(self, shell_with_commands):
        """Cat on an existing file returns its content with SUCCESS."""
        result = await shell_with_commands.execute("cat /etc/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

    async def test_cat_nonexistent(self, shell_with_commands):
        """Cat on a nonexistent path returns ERROR with NOT_FOUND."""
        result = await shell_with_commands.execute("cat /missing")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_cat_no_args_reads_stdin(self, shell_with_commands):
        """Cat with no arguments reads from stdin (immediate EOF yields empty output)."""
        result = await shell_with_commands.execute("cat")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_cat_stdin_explicit(self, shell_with_commands):
        """``cat -`` reads from stdin (immediate EOF yields empty output)."""
        result = await shell_with_commands.execute("cat -")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_cat_directory(self, shell_with_commands):
        """Cat on a directory returns ERROR with IS_A_DIRECTORY."""
        result = await shell_with_commands.execute("cat /home")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_cat_relative_path(self, shell_with_commands):
        """Cat resolves relative paths against the session's CWD."""
        result = await shell_with_commands.execute("cat notes.txt")
        assert_success(result)
        assert "hello world" in stdout_text(result)

    async def test_cat_multiple_files(self, shell_with_commands):
        """Cat with multiple file arguments concatenates their content."""
        result = await shell_with_commands.execute(
            "cat /etc/hostname /home/user/notes.txt"
        )
        assert_success(result)
        stdout = stdout_text(result)
        assert "simnux-edge" in stdout
        assert "hello world" in stdout

    async def test_cat_first_file_fails_stops(self, shell_with_commands):
        """Cat stops at the first file error (no further files processed)."""
        result = await shell_with_commands.execute("cat /missing /etc/hostname")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)


class TestCatCommandStream:
    """Stream-level tests for cat's stdin reading.

    Feeds inline data via QueueStreamReader to verify that cat reads
    from stdin when no arguments are given and when ``-`` is used.
    """

    @pytest.fixture
    def cat_command(self):
        from simnux.commands.standard.cat import Command

        return Command(context=MagicMock())

    @pytest.fixture
    def ctx(self):
        return MagicMock(spec=CommandContext)

    async def test_cat_no_args_with_stdin_data(self, cat_command, ctx):
        """Cat with no arguments reads and outputs stdin data."""
        cat_command.args = None

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("line one")
        stdin_queue.put_nowait("line two")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await cat_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["line one", "line two"]

    async def test_cat_dash_with_stdin_data(self, cat_command, ctx):
        """``cat -`` reads and outputs stdin data."""
        cat_command.args = ["-"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("hello from stdin")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await cat_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["hello from stdin"]

    async def test_cat_dash_between_files(self):
        """``cat file -`` interleaves file content with stdin."""
        from simnux.commands.standard.cat import Command
        from simnux.filesystem.models import SNXNode
        from simnux.filesystem.vfs import SNXFileSystem

        cmd = Command(context=MagicMock())
        cmd.args = ["/etc/hostname", "-"]

        hostname_node = SNXNode(path="/etc/hostname", content="simnux-edge\n")
        fs = MagicMock(spec=SNXFileSystem)
        fs.read.return_value = MagicMock(
            exit_code=ExitCode.SUCCESS,
            node=hostname_node,
        )
        cmd.resolve_path = lambda t, c: t

        mock_ctx = MagicMock(spec=CommandContext)
        mock_ctx.filesystem = fs

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("piped input")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await cmd.execute(
            ctx=mock_ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["simnux-edge", "piped input"]
