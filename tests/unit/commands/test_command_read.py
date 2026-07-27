"""Tests for the ``read`` command."""

import asyncio
from unittest.mock import MagicMock

import pytest

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


# ── Integration tests (shell-level) ──────────────────────────────────────


class TestReadCommand:
    """Shell-level integration tests for read."""

    async def test_read_default_reply_variable(self, shell_with_commands):
        """``read`` stores input in REPLY when no variable name given."""
        shell_with_commands.session.environment.clear()
        result = await shell_with_commands.execute("echo hello | read")
        assert_success(result)
        assert shell_with_commands.session.environment.get("REPLY") == "hello"

    async def test_read_custom_variable(self, shell_with_commands):
        """``read NAME`` stores input in the named variable."""
        shell_with_commands.session.environment.clear()
        result = await shell_with_commands.execute("echo world | read NAME")
        assert_success(result)
        assert shell_with_commands.session.environment.get("NAME") == "world"

    async def test_read_with_prompt_flag(self, shell_with_commands):
        """``read -p "prompt: "`` writes the prompt to stdout before reading."""
        shell_with_commands.session.environment.clear()
        result = await shell_with_commands.execute('echo data | read -p "Enter value: " MYVAR')
        assert_success(result)
        assert "Enter value: " in stdout_text(result)
        assert shell_with_commands.session.environment.get("MYVAR") == "data"

    async def test_read_eof_returns_error(self, shell_with_commands):
        """``read`` with no pipe suspends (interactive mode)."""
        shell_with_commands.session.environment.clear()
        result = await shell_with_commands.execute("read")
        assert_success(result)
        assert shell_with_commands.session.awaiting_input is True

    async def test_read_strips_trailing_newline(self, shell_with_commands):
        """Read input is stripped of trailing newline."""
        shell_with_commands.session.environment.clear()
        result = await shell_with_commands.execute("echo 'hello world' | read MSG")
        assert_success(result)
        assert shell_with_commands.session.environment.get("MSG") == "hello world"


# ── Suspension / resumption tests ────────────────────────────────────────


class TestReadSuspension:
    """Tests for interactive read suspension over the REST bridge."""

    async def test_read_suspends_when_stdin_empty(self, shell_with_commands):
        """``read`` with no pipe suspends and sets awaiting_input."""
        shell_with_commands.session.environment.clear()
        session = shell_with_commands.session

        result = await shell_with_commands.execute('read -p "Enter: " MYVAR')
        assert_success(result)
        assert session.awaiting_input is True
        assert session.pending_var_name == "MYVAR"
        assert session.pending_command is not None

    async def test_read_suspension_writes_prompt(self, shell_with_commands):
        """Suspension writes the prompt string to stdout."""
        shell_with_commands.session.environment.clear()

        result = await shell_with_commands.execute('read -p "Password: " PASS')
        assert_success(result)
        assert "Password: " in stdout_text(result)

    async def test_read_resume_assigns_variable(self, shell_with_commands):
        """After suspension, re-dispatch with stdin assigns the variable."""
        shell_with_commands.session.environment.clear()
        session = shell_with_commands.session

        # Turn 1: suspend
        await shell_with_commands.execute('read -p "Name: " NAME')
        assert session.awaiting_input is True

        # Turn 2: resume via execute_resume with stdin
        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("Alice\n")
        stdin_queue.put_nowait(None)
        resume_stdin = QueueStreamReader(stdin_queue)

        result = await shell_with_commands.execute_resume(
            session.pending_command,
            resume_stdin,
        )
        assert_success(result)
        assert session.environment.get("NAME") == "Alice"
        assert session.awaiting_input is False
        assert session.pending_var_name is None
        assert session.pending_command is None

    async def test_read_resume_default_reply(self, shell_with_commands):
        """Suspension without a variable name resumes into REPLY."""
        shell_with_commands.session.environment.clear()
        session = shell_with_commands.session

        await shell_with_commands.execute("read")
        assert session.awaiting_input is True

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("default test\n")
        stdin_queue.put_nowait(None)
        resume_stdin = QueueStreamReader(stdin_queue)

        result = await shell_with_commands.execute_resume(
            session.pending_command,
            resume_stdin,
        )
        assert_success(result)
        assert session.environment.get("REPLY") == "default test"
        assert session.awaiting_input is False

    async def test_read_resume_eof_errors(self, shell_with_commands):
        """Resume with EOF (empty stdin) returns ERROR and clears state."""
        shell_with_commands.session.environment.clear()
        session = shell_with_commands.session

        await shell_with_commands.execute('read -p "Val: " V')
        assert session.awaiting_input is True

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait(None)
        resume_stdin = QueueStreamReader(stdin_queue)

        result = await shell_with_commands.execute_resume(
            session.pending_command,
            resume_stdin,
        )
        assert_error(result)
        assert "unexpected EOF" in stderr_text(result)
        assert session.awaiting_input is False
        assert session.pending_var_name is None


# ── Unit-level stream tests ──────────────────────────────────────────────


class TestReadCommandStream:
    """Unit-level tests with direct QueueStreamReader injection."""

    @pytest.fixture
    def read_command(self):
        from simnux.commands.standard.read import Command

        return Command(context=MagicMock())

    @pytest.fixture
    def ctx(self):
        session = MagicMock()
        session.environment = {}
        session.awaiting_input = False
        session.pending_var_name = None
        session.pending_command = None
        ctx = MagicMock(spec=CommandContext)
        ctx.session = session
        return ctx

    async def test_read_default_reply(self, read_command, ctx):
        """Read without args stores in REPLY."""
        read_command.args = None
        read_command.parsed_args = None

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("test line\n")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_writer = QueueStreamWriter(asyncio.Queue())
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await read_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )

        assert result == ExitCode.SUCCESS
        assert ctx.session.environment["REPLY"] == "test line"

    async def test_read_custom_var(self, read_command, ctx):
        """Read with a variable name stores in that variable."""
        read_command.args = ["MYVAR"]
        read_command.parsed_args = MagicMock()
        read_command.parsed_args.flags = {}
        read_command.parsed_args.positional = ["MYVAR"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("custom value\n")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_writer = QueueStreamWriter(asyncio.Queue())
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await read_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )

        assert result == ExitCode.SUCCESS
        assert ctx.session.environment["MYVAR"] == "custom value"

    async def test_read_with_prompt(self, read_command, ctx):
        """Read with -p flag writes prompt to stdout."""
        read_command.args = ["-p", "prompt: ", "VAR"]
        read_command.parsed_args = MagicMock()
        read_command.parsed_args.flags = {"prompt": "prompt: "}
        read_command.parsed_args.positional = ["VAR"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("input\n")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await read_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert drain_queue(stdout_queue) == ["prompt: "]
        assert ctx.session.environment["VAR"] == "input"

    async def test_read_eof(self, read_command, ctx):
        """Read suspends when stdin has no data (interactive mode)."""
        read_command.args = None
        read_command.parsed_args = None

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_writer = QueueStreamWriter(asyncio.Queue())
        stderr_queue: asyncio.Queue = asyncio.Queue()
        stderr_writer = QueueStreamWriter(stderr_queue)

        result = await read_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )

        assert result == ExitCode.SUCCESS
        assert ctx.session.awaiting_input is True

    async def test_read_suspends_on_empty_stdin(self, read_command, ctx):
        """Read suspends when stdin has no data (interactive mode)."""
        read_command.args = ["-p", "enter: ", "MYVAR"]
        read_command.parsed_args = MagicMock()
        read_command.parsed_args.flags = {"prompt": "enter: "}
        read_command.parsed_args.positional = ["MYVAR"]

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_queue: asyncio.Queue = asyncio.Queue()
        stdout_writer = QueueStreamWriter(stdout_queue)
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await read_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )
        stdout_writer.close()

        assert result == ExitCode.SUCCESS
        assert ctx.session.awaiting_input is True
        assert ctx.session.pending_var_name == "MYVAR"
        assert ctx.session.pending_command is not None
        assert drain_queue(stdout_queue) == ["enter: "]

    async def test_read_resume_path(self, read_command, ctx):
        """Read resumes from awaiting_input state."""
        ctx.session.awaiting_input = True
        ctx.session.pending_var_name = "ANSWER"

        read_command.args = None
        read_command.parsed_args = None

        stdin_queue: asyncio.Queue = asyncio.Queue()
        stdin_queue.put_nowait("42\n")
        stdin_queue.put_nowait(None)
        stdin_reader = QueueStreamReader(stdin_queue)

        stdout_writer = QueueStreamWriter(asyncio.Queue())
        stderr_writer = QueueStreamWriter(asyncio.Queue())

        result = await read_command.execute(
            ctx=ctx,
            stdin=stdin_reader,
            stdout=stdout_writer,
            stderr=stderr_writer,
        )

        assert result == ExitCode.SUCCESS
        assert ctx.session.environment["ANSWER"] == "42"
        assert ctx.session.awaiting_input is False
        assert ctx.session.pending_var_name is None
        assert ctx.session.pending_command is None
