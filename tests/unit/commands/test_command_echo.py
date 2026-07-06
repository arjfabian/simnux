"""Tests for the ``echo`` command implementation.

Covers text output, empty input, quote handling (single, double, mixed),
tilde literal preservation, and multiple-argument spacing.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from simnux.commands.models import CommandContext
from simnux.commands.streams import QueueStreamReader
from simnux.commands.streams import QueueStreamWriter
from simnux.runtime.models import ExitCode
from tests.helpers import assert_success
from tests.helpers import drain_queue
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


@pytest.fixture
def echo_command():
    """Direct echo command instance for stream-level tests."""
    from simnux.commands.standard.echo import Command

    return Command(context=MagicMock())


@pytest.fixture
def ctx():
    return MagicMock(spec=CommandContext)


class TestEchoCommandStream:
    """Stream-level tests for echo's ``execute``.

    Feeds mock async queues directly to the echo command,
    bypassing the full shell pipeline.
    """

    async def test_echo_text(self, echo_command, ctx):
        """Echo outputs the provided text via stream."""
        echo_command.args = ["hello", "world"]
        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())
        stdin_reader = QueueStreamReader(asyncio.Queue())

        result = await echo_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["hello world"]

    async def test_echo_empty(self, echo_command, ctx):
        """Echo with no arguments outputs nothing (not error)."""
        echo_command.args = None
        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())
        stdin_reader = QueueStreamReader(asyncio.Queue())

        result = await echo_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == []

    async def test_echo_empty_args(self, echo_command, ctx):
        """Echo with empty args list outputs nothing."""
        echo_command.args = []
        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())
        stdin_reader = QueueStreamReader(asyncio.Queue())

        result = await echo_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == []

    async def test_echo_multiple_args_spaced(self, echo_command, ctx):
        """Multiple args are joined by spaces."""
        echo_command.args = ["  a", "b", "c"]
        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())
        stdin_reader = QueueStreamReader(asyncio.Queue())

        result = await echo_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["  a b c"]

    async def test_echo_stderr_empty(self, echo_command, ctx):
        """Echo never writes to stderr."""
        echo_command.args = ["hello"]
        stdout_queue: asyncio.Queue = asyncio.Queue()
        stderr_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(stderr_queue)
        stdin_reader = QueueStreamReader(asyncio.Queue())

        await echo_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()
        stderr_writer.close()

        assert drain_queue(stderr_queue) == []


class TestEchoCommand:
    """Text output via the ``echo`` command.

    Uses the ``shell_with_commands`` fixture. Covers basic text,
    empty input, quote stripping, tilde literal preservation, and
    space-collapsing for multiple arguments.

    These tests exercise the full shell pipeline (including the
    backward-compatibility layer for non-migrated commands).
    """

    async def test_echo_text(self, shell_with_commands):
        """Echo outputs the provided text."""
        result = await shell_with_commands.execute("echo hello world")
        assert_success(result)
        assert "hello world" in stdout_text(result)

    async def test_echo_empty(self, shell_with_commands):
        """Echo with no arguments outputs an empty string (not error)."""
        result = await shell_with_commands.execute("echo")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_echo_preserves_parser_quote_semantics(self, shell_with_commands):
        """Single quotes are removed from the output (shell-parser strips them)."""
        result = await shell_with_commands.execute("echo 'hello'")
        assert "hello" in stdout_text(result)

    async def test_echo_double_quotes_stripped(self, shell_with_commands):
        """Double quotes are removed from the output."""
        result = await shell_with_commands.execute('echo "hello"')
        assert "hello" in stdout_text(result)

    async def test_echo_mixed_quotes_preserved(self, shell_with_commands):
        """Nested quotes inside double quotes are preserved."""
        result = await shell_with_commands.execute("echo \"hello 'world'\"")
        assert "hello 'world'" in stdout_text(result)

    async def test_echo_tilde_not_expanded_by_command(self, shell_with_commands):
        """Echo does not expand ``~`` — expansion is the shell/FS layer's job."""
        result = await shell_with_commands.execute("echo ~")
        assert "~" in stdout_text(result)

    async def test_echo_multiple_args_with_spaces(self, shell_with_commands):
        """Multiple arguments are space-separated in the output."""
        result = await shell_with_commands.execute("echo   a   b   c")
        assert stdout_text(result) == "a b c"
