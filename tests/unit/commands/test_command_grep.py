"""Tests for the ``grep`` command implementation.

Covers pattern matching against file content and stdin, handling
nonexistent paths, missing pattern, and ``-`` for explicit stdin.
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


class TestGrepCommand:
    """Pattern search via the ``grep`` command.

    Uses the ``shell_with_commands`` fixture which provides a shell with
    all standard commands loaded and the ``base_layer`` filesystem
    (containing ``/home/user/notes.txt``, ``/etc/hostname``, etc.).
    """

    async def test_grep_finds_match_in_file(self, shell_with_commands):
        """Grep on an existing file returns matching lines with SUCCESS."""
        result = await shell_with_commands.execute("grep simnux-edge /etc/hostname")
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)

    async def test_grep_no_match_returns_error(self, shell_with_commands):
        """Grep with a pattern that does not match returns ERROR (POSIX exit 1)."""
        result = await shell_with_commands.execute("grep nonexistent /etc/hostname")
        assert result.exit_code == ExitCode.ERROR
        assert stdout_text(result) == ""

    async def test_grep_nonexistent_file(self, shell_with_commands):
        """Grep on a nonexistent path returns ERROR with NOT_FOUND."""
        result = await shell_with_commands.execute("grep pattern /missing")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_grep_missing_pattern(self, shell_with_commands):
        """Grep with no arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("grep")
        assert result.exit_code == ExitCode.INVALID_ARGUMENT
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_grep_no_args_reads_stdin_empty(self, shell_with_commands):
        """Grep with a pattern but no files reads from stdin; empty stdin → no match → ERROR."""
        result = await shell_with_commands.execute("grep hello")
        assert result.exit_code == ExitCode.ERROR
        assert stdout_text(result) == ""

    async def test_grep_stdin_explicit_empty(self, shell_with_commands):
        """``grep pattern -`` reads from stdin; empty stdin → no match → ERROR."""
        result = await shell_with_commands.execute("grep hello -")
        assert result.exit_code == ExitCode.ERROR
        assert stdout_text(result) == ""

    async def test_grep_directory(self, shell_with_commands):
        """Grep on a directory returns ERROR with IS_A_DIRECTORY."""
        result = await shell_with_commands.execute("grep something /home")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_grep_multiple_files(self, shell_with_commands):
        """Grep with multiple file arguments searches each."""
        result = await shell_with_commands.execute(
            "grep e /etc/hostname /home/user/notes.txt"
        )
        assert_success(result)
        stdout = stdout_text(result)
        assert "simnux-edge" in stdout
        assert "hello world" in stdout

    async def test_grep_relative_path(self, shell_with_commands):
        """Grep resolves relative paths against the session's CWD."""
        result = await shell_with_commands.execute("grep hello notes.txt")
        assert_success(result)
        assert "hello world" in stdout_text(result)

    async def test_grep_multiple_dash_no_hang(self, shell_with_commands):
        """``grep pattern - -`` does not hang; second ``-`` reads exhausted stdin."""
        result = await shell_with_commands.execute("grep hello - -")
        assert result.exit_code == ExitCode.ERROR
        assert stdout_text(result) == ""

    async def test_grep_mixed_files_and_dash_no_hang(self, shell_with_commands):
        """``grep pattern file - -`` searches file then stdin twice (second ``-`` safe)."""
        result = await shell_with_commands.execute(
            "grep e /etc/hostname - -"
        )
        assert_success(result)
        assert "simnux-edge" in stdout_text(result)


class TestGrepCommandStream:
    """Stream-level tests for grep's stdin reading.

    Feeds inline data via QueueStreamReader to verify that grep reads
    from stdin when no file arguments are given and when ``-`` is used.
    """

    @pytest.fixture
    def grep_command(self):
        from simnux.commands.standard.grep import Command

        return Command(context=MagicMock())

    @pytest.fixture
    def ctx(self):
        return MagicMock(spec=CommandContext)

    async def test_grep_no_file_args_filters_stdin(self, grep_command, ctx):
        """Grep with only a pattern reads stdin and outputs matching lines."""
        grep_command.args = ["line"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("line one")
        stdin_queue.put_nowait("skip this")
        stdin_queue.put_nowait("another line")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await grep_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["line one", "another line"]

    async def test_grep_dash_reads_stdin(self, grep_command, ctx):
        """``grep pattern -`` reads and filters stdin data."""
        grep_command.args = ["hello", "-"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("hello from stdin")
        stdin_queue.put_nowait("goodbye")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await grep_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["hello from stdin"]

    async def test_grep_file_then_dash(self):
        """``grep pattern file -`` searches file then stdin."""
        from simnux.commands.standard.grep import Command
        from simnux.filesystem.models import SNXNode
        from simnux.filesystem.vfs import SNXFileSystem

        cmd = Command(context=MagicMock())
        cmd.args = ["edge", "/etc/hostname", "-"]

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
        stdin_queue.put_nowait("cutting edge")
        stdin_queue.put_nowait("boring line")
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
        assert drain_queue(stdout_queue) == ["simnux-edge", "cutting edge"]

    async def test_grep_no_matches_from_stdin(self, grep_command, ctx):
        """Grep with a pattern that does not match any stdin line returns ERROR."""
        grep_command.args = ["zzz"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("line one")
        stdin_queue.put_nowait("line two")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await grep_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.ERROR
        assert drain_queue(stdout_queue) == []

    async def test_grep_dash_after_stdin_exhausted(self, grep_command, ctx):
        """Multiple ``-`` args: second reads already-exhausted stdin without hanging."""
        grep_command.args = ["line", "-", "-"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("line one")
        stdin_queue.put_nowait("another line")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await grep_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["line one", "another line"]

    async def test_grep_write_preserves_newline(self, grep_command, ctx):
        """Each matching line is written with trailing ``\\n`` for clean pipelining.

        The queue item should end with ``\\n``, verifiable by checking that
        drain_queue (which uses splitlines) produces the expected line count
        and that the raw queue reflects newline-terminated records.
        """
        grep_command.args = ["hello"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("hello from stdin")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await grep_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS

        raw_items = []
        while True:
            try:
                item = stdout_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not None:
                raw_items.append(item)

        assert raw_items == ["hello from stdin\n"]
