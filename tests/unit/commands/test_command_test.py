"""Tests for the ``test`` / ``[`` command."""

import asyncio
from unittest.mock import MagicMock

import pytest

from simnux.core.commands.models import CommandContext
from simnux.core.commands.streams import QueueStreamWriter
from simnux.core.runtime.models import ExitCode
from tests.helpers import assert_error
from tests.helpers import assert_success


pytestmark = pytest.mark.asyncio


# ── Integration tests (shell-level) ──────────────────────────────────────


class TestTestCommand:
    """Shell-level integration tests for test / [."""

    async def test_bracket_file_exists(self, shell_with_commands):
        """``[ -f notes.txt ]`` returns SUCCESS."""
        result = await shell_with_commands.execute("[ -f notes.txt ]")
        assert_success(result)
        assert result.stdout == []
        assert result.stderr == []

    async def test_bracket_file_not_exists(self, shell_with_commands):
        """``[ -f nonexistent ]`` returns ERROR."""
        result = await shell_with_commands.execute("[ -f nonexistent ]")
        assert_error(result)

    async def test_test_directory_exists(self, shell_with_commands):
        """``test -d /home`` returns SUCCESS."""
        result = await shell_with_commands.execute("test -d /home")
        assert_success(result)

    async def test_test_directory_not_exists(self, shell_with_commands):
        """``test -d /nonexistent`` returns ERROR."""
        result = await shell_with_commands.execute("test -d /nonexistent")
        assert_error(result)

    async def test_test_exists(self, shell_with_commands):
        """``test -e /etc/hostname`` returns SUCCESS."""
        result = await shell_with_commands.execute("test -e /etc/hostname")
        assert_success(result)

    async def test_bracket_string_equal(self, shell_with_commands):
        """``[ "abc" = "abc" ]`` returns SUCCESS."""
        result = await shell_with_commands.execute('[ "abc" = "abc" ]')
        assert_success(result)

    async def test_bracket_string_not_equal(self, shell_with_commands):
        """``[ "abc" != "xyz" ]`` returns SUCCESS."""
        result = await shell_with_commands.execute('[ "abc" != "xyz" ]')
        assert_success(result)

    async def test_bracket_string_equal_fail(self, shell_with_commands):
        """``[ "abc" = "xyz" ]`` returns ERROR."""
        result = await shell_with_commands.execute('[ "abc" = "xyz" ]')
        assert_error(result)

    async def test_test_string_equal(self, shell_with_commands):
        """``test "hello" = "hello"`` returns SUCCESS."""
        result = await shell_with_commands.execute('test "hello" = "hello"')
        assert_success(result)

    async def test_test_integer_equal(self, shell_with_commands):
        """``test 5 -eq 5`` returns SUCCESS."""
        result = await shell_with_commands.execute("test 5 -eq 5")
        assert_success(result)

    async def test_test_integer_not_equal(self, shell_with_commands):
        """``test 5 -ne 3`` returns SUCCESS."""
        result = await shell_with_commands.execute("test 5 -ne 3")
        assert_success(result)

    async def test_test_integer_gt(self, shell_with_commands):
        """``test 10 -gt 5`` returns SUCCESS."""
        result = await shell_with_commands.execute("test 10 -gt 5")
        assert_success(result)

    async def test_test_integer_lt(self, shell_with_commands):
        """``test 3 -lt 7`` returns SUCCESS."""
        result = await shell_with_commands.execute("test 3 -lt 7")
        assert_success(result)

    async def test_test_integer_ge(self, shell_with_commands):
        """``test 5 -ge 5`` returns SUCCESS."""
        result = await shell_with_commands.execute("test 5 -ge 5")
        assert_success(result)

    async def test_test_integer_le(self, shell_with_commands):
        """``test 5 -le 5`` returns SUCCESS."""
        result = await shell_with_commands.execute("test 5 -le 5")
        assert_success(result)

    async def test_test_integer_gt_fail(self, shell_with_commands):
        """``test 3 -gt 5`` returns ERROR."""
        result = await shell_with_commands.execute("test 3 -gt 5")
        assert_error(result)

    async def test_test_string_empty(self, shell_with_commands):
        """``test -z ""`` returns SUCCESS."""
        result = await shell_with_commands.execute('test -z ""')
        assert_success(result)

    async def test_test_string_not_empty(self, shell_with_commands):
        """``test -n "hello"`` returns SUCCESS."""
        result = await shell_with_commands.execute('test -n "hello"')
        assert_success(result)

    async def test_test_string_empty_fail(self, shell_with_commands):
        """``test -z "hello"`` returns ERROR."""
        result = await shell_with_commands.execute('test -z "hello"')
        assert_error(result)

    async def test_test_string_not_empty_fail(self, shell_with_commands):
        """``test -n ""`` returns ERROR."""
        result = await shell_with_commands.execute('test -n ""')
        assert_error(result)

    async def test_test_negation(self, shell_with_commands):
        """``test ! "hello"`` returns ERROR (negated non-empty string)."""
        result = await shell_with_commands.execute('test ! "hello"')
        assert_error(result)

    async def test_test_negation_inverted(self, shell_with_commands):
        """``test ! ""`` returns SUCCESS (negated empty string)."""
        result = await shell_with_commands.execute('test ! ""')
        assert_success(result)

    async def test_bracket_no_args(self, shell_with_commands):
        """``[ ]`` returns ERROR with missing ] message."""
        result = await shell_with_commands.execute("[ ]")
        assert_error(result)

    async def test_test_no_args(self, shell_with_commands):
        """``test`` with no args returns ERROR."""
        result = await shell_with_commands.execute("test")
        assert_error(result)

    async def test_single_nonempty_string(self, shell_with_commands):
        """``test "hello"`` returns SUCCESS (non-empty string)."""
        result = await shell_with_commands.execute('test "hello"')
        assert_success(result)

    async def test_single_empty_string(self, shell_with_commands):
        """``test ""`` returns ERROR (empty string)."""
        result = await shell_with_commands.execute('test ""')
        assert_error(result)

    async def test_directory_not_file(self, shell_with_commands):
        """``[ -f /home ]`` returns ERROR (directory is not a file)."""
        result = await shell_with_commands.execute("[ -f /home ]")
        assert_error(result)

    async def test_file_not_directory(self, shell_with_commands):
        """``[ -d notes.txt ]`` returns ERROR (file is not a directory)."""
        result = await shell_with_commands.execute("[ -d notes.txt ]")
        assert_error(result)

    async def test_bracket_clean_stdout(self, shell_with_commands):
        """Boolean evaluation never writes to stdout."""
        result = await shell_with_commands.execute("[ -f notes.txt ]")
        assert result.stdout == []

    async def test_test_relative_path(self, shell_with_commands):
        """``[ -f notes.txt ]`` resolves relative path against CWD."""
        result = await shell_with_commands.execute("[ -f notes.txt ]")
        assert_success(result)


# ── Unit-level tests ─────────────────────────────────────────────────────


class TestTestCommandUnit:
    """Unit tests with direct command instantiation."""

    @pytest.fixture
    def test_command(self):
        from simnux.core.commands.standard.condition import Command

        return Command(context=MagicMock())

    @pytest.fixture
    def ctx(self):
        return MagicMock(spec=CommandContext)

    async def test_bracket_trailing_removed(self, test_command, ctx):
        """Bracket invocation removes trailing ]."""
        test_command.args = ["-n", "hello", "]"]
        test_command._invoked_name = "["

        stdout = QueueStreamWriter(asyncio.Queue())
        stderr = QueueStreamWriter(asyncio.Queue())

        result = await test_command.execute(ctx, None, stdout, stderr)
        assert result == ExitCode.SUCCESS

    async def test_bracket_missing_bracket(self, test_command, ctx):
        """Bracket invocation without trailing ] returns ERROR."""
        test_command.args = ["-n", "hello"]
        test_command._invoked_name = "["

        stderr_queue = asyncio.Queue()
        stderr = QueueStreamWriter(stderr_queue)

        result = await test_command.execute(ctx, None, QueueStreamWriter(asyncio.Queue()), stderr)

        assert result == ExitCode.ERROR
        stderr_text = []
        while not stderr_queue.empty():
            stderr_text.append(stderr_queue.get_nowait())
        assert any("missing ']'" in line for line in stderr_text)

    async def test_test_no_args(self, test_command, ctx):
        """test with no args returns ERROR."""
        test_command.args = []
        test_command._invoked_name = "test"

        result = await test_command.execute(
            ctx,
            None,
            QueueStreamWriter(asyncio.Queue()),
            QueueStreamWriter(asyncio.Queue()),
        )
        assert result == ExitCode.ERROR

    async def test_prefix_negation_string_equal_inverted(self, shell_with_commands):
        """``[ ! "a" = "b" ]`` — inner comparison is False, negated to True."""
        result = await shell_with_commands.execute('[ ! "a" = "b" ]')
        assert_success(result)

    async def test_prefix_negation_integer_gt(self, shell_with_commands):
        """``[ ! 10 -gt 5 ]`` — inner comparison is True, negated to False."""
        result = await shell_with_commands.execute("[ ! 10 -gt 5 ]")
        assert_error(result)
