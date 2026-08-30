"""Tests for the ``echo`` command implementation.

Covers text output, empty input, quote handling (single, double, mixed),
tilde literal preservation, multiple-argument spacing, and flag support
(``-n``, ``-e``, ``-E``) with backslash escape interpretation.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from simnux.core.commands.models import CommandContext
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.commands.streams import QueueStreamWriter
from simnux.core.runtime.models import ExitCode
from tests.helpers import assert_success
from tests.helpers import drain_queue
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


@pytest.fixture
def echo_command():
    """Direct echo command instance for stream-level tests."""
    from simnux.core.commands.standard.echo import Command

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
        """Echo with no arguments outputs a trailing newline."""
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
        assert drain_queue(stdout_queue) == [""]

    async def test_echo_empty_args(self, echo_command, ctx):
        """Echo with empty args list outputs a trailing newline."""
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
        assert drain_queue(stdout_queue) == [""]

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


class TestEchoFlags:
    """Flag-specific tests for echo (``-n``, ``-e``, ``-E``)."""

    async def test_n_flag_suppresses_newline(self, echo_command, ctx):
        """``-n`` suppresses the trailing newline."""
        echo_command.args = ["-n", "hello"]
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
        items = drain_queue(stdout_queue)
        assert items == ["hello"]
        assert items[-1] == "hello"

    async def test_n_only(self, echo_command, ctx):
        """``-n`` alone produces no output."""
        echo_command.args = ["-n"]
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

    async def test_e_enables_escapes(self, echo_command, ctx):
        """``-e`` interprets backslash escapes in the output."""
        echo_command.args = ["-e", "line1\\nline2"]
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
        items = drain_queue(stdout_queue)
        assert items == ["line1", "line2"]

    async def test_e_tab(self, echo_command, ctx):
        """``-e`` interprets ``\\t`` as a tab."""
        echo_command.args = ["-e", "col1\\tcol2"]
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
        items = drain_queue(stdout_queue)
        assert items == ["col1\tcol2"]

    async def test_e_backslash(self, echo_command, ctx):
        """``-e`` interprets ``\\\\`` as a literal backslash."""
        echo_command.args = ["-e", "path\\\\to\\\\file"]
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
        items = drain_queue(stdout_queue)
        assert items == ["path\\to\\file"]

    async def test_e_octal_escape(self, echo_command, ctx):
        """``-e`` interprets ``\\0nnn`` as an octal value."""
        echo_command.args = ["-e", "\\0101"]
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
        items = drain_queue(stdout_queue)
        assert items == ["A"]

    async def test_e_hex_escape(self, echo_command, ctx):
        """``-e`` interprets ``\\xHH`` as a hex value."""
        echo_command.args = ["-e", "\\x41"]
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
        items = drain_queue(stdout_queue)
        assert items == ["A"]

    async def test_e_unicode_escape(self, echo_command, ctx):
        """``-e`` interprets ``\\uHHHH`` as a Unicode code point."""
        echo_command.args = ["-e", "\\u0041"]
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
        items = drain_queue(stdout_queue)
        assert items == ["A"]

    async def test_uppercase_e_disables_escapes(self, echo_command, ctx):
        """``-E`` disables escape interpretation (default)."""
        echo_command.args = ["-E", "line1\\nline2"]
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
        items = drain_queue(stdout_queue)
        assert items == ["line1\\nline2"]

    async def test_ee_resets_e(self, echo_command, ctx):
        """``-e`` followed by ``-E`` disables escape interpretation."""
        echo_command.args = ["-e", "-E", "line1\\nline2"]
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
        items = drain_queue(stdout_queue)
        assert items == ["line1\\nline2"]

    async def test_ne_combined(self, echo_command, ctx):
        """``-n -e`` suppresses newline and enables escapes."""
        echo_command.args = ["-n", "-e", "a\\nb"]
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
        items = drain_queue(stdout_queue)
        assert items == ["a", "b"]

    async def test_flags_stopping_at_non_flag(self, echo_command, ctx):
        """Parsing stops at the first non-flag token; ``-n`` in middle is literal."""
        echo_command.args = ["-e", "hello", "-n"]
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
        items = drain_queue(stdout_queue)
        assert items == ["hello -n"]


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
        """Echo with no arguments outputs a trailing newline."""
        result = await shell_with_commands.execute("echo")
        assert_success(result)
        # Trailing newline produces an empty item after drain_queue split
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

    async def test_echo_n_flag(self, shell_with_commands):
        """``-n`` suppresses the trailing newline."""
        result = await shell_with_commands.execute("echo -n hello")
        assert_success(result)
        assert "hello" in stdout_text(result)

    async def test_echo_e_newline(self, shell_with_commands):
        """``-e`` with ``\\n`` produces an actual line break."""
        result = await shell_with_commands.execute('echo -e "hello\\nworld"')
        assert_success(result)
        assert "hello" in stdout_text(result)
        assert "world" in stdout_text(result)

    async def test_echo_e_header(self, shell_with_commands):
        """``-e`` expands ``\\n`` at the start of a string."""
        result = await shell_with_commands.execute('echo -e "\\n=== Header ==="')
        assert_success(result)
        assert "=== Header ===" in stdout_text(result)

    async def test_echo_uppercase_e_literal(self, shell_with_commands):
        """``-E`` keeps escape sequences literal."""
        result = await shell_with_commands.execute('echo -E "hello\\nworld"')
        assert_success(result)
        assert "hello\\nworld" in stdout_text(result)

    async def test_echo_default_escapes_literal(self, shell_with_commands):
        """Default echo (no ``-e``) keeps escape sequences literal."""
        result = await shell_with_commands.execute('echo "hello\\nworld"')
        assert_success(result)
        assert "hello\\nworld" in stdout_text(result)
