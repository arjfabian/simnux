"""Tests for the ``history`` command."""

from __future__ import annotations

import pytest

from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestHistoryCommand:
    """Shell-level integration tests for the history command."""

    async def test_history_shows_own_entry(self, shell_with_commands):
        """The ``history`` command invocation is itself recorded."""
        result = await shell_with_commands.execute("history")
        assert_success(result)
        assert stdout_text(result) == "   1  history"

    async def test_history_records_commands(self, shell_with_commands):
        """Commands executed before ``history`` appear in the output."""
        await shell_with_commands.execute("echo hello")
        await shell_with_commands.execute("pwd")
        result = await shell_with_commands.execute("history")
        assert_success(result)
        stdout = stdout_text(result)
        assert "echo hello" in stdout
        assert "pwd" in stdout

    async def test_history_line_numbers(self, shell_with_commands):
        """Entries are numbered sequentially from 1."""
        await shell_with_commands.execute("echo alpha")
        await shell_with_commands.execute("echo beta")
        result = await shell_with_commands.execute("history")
        assert_success(result)
        stdout = stdout_text(result)
        assert "  1  echo alpha" in stdout
        assert "  2  echo beta" in stdout
        assert "  3  history" in stdout

    async def test_history_n_show_last_n(self, shell_with_commands):
        """``history N`` shows only the last N entries."""
        await shell_with_commands.execute("echo a")
        await shell_with_commands.execute("echo b")
        await shell_with_commands.execute("echo c")
        result = await shell_with_commands.execute("history 2")
        assert_success(result)
        stdout = stdout_text(result)
        assert "echo c" in stdout
        assert "history 2" in stdout
        assert "echo a" not in stdout and "echo b" not in stdout

    async def test_history_n_preserves_original_numbers(self, shell_with_commands):
        """``history N`` shows original line numbers, not 1-based slice."""
        await shell_with_commands.execute("echo first")
        await shell_with_commands.execute("echo second")
        result = await shell_with_commands.execute("history 1")
        assert_success(result)
        stdout = stdout_text(result)
        assert "  3  history 1" in stdout

    async def test_history_n_zero(self, shell_with_commands):
        """``history 0`` returns error with 'out of range'."""
        result = await shell_with_commands.execute("history 0")
        assert_error(result)
        assert "out of range" in stderr_text(result)

    async def test_history_negative_n(self, shell_with_commands):
        """``history -5`` returns error (invalid option)."""
        result = await shell_with_commands.execute("history -5")
        assert_error(result)

    async def test_history_bad_arg(self, shell_with_commands):
        """Non-numeric argument produces an error."""
        result = await shell_with_commands.execute("history abc")
        assert_error(result)
        assert "numeric argument required" in stderr_text(result)

    async def test_history_clear(self, shell_with_commands):
        """``history -c`` clears the history; subsequent ``history`` shows only itself."""
        await shell_with_commands.execute("echo hello")
        await shell_with_commands.execute("history -c")
        result = await shell_with_commands.execute("history")
        assert_success(result)
        assert stdout_text(result) == "   1  history"

    async def test_history_records_pipeline(self, shell_with_commands):
        """Piped commands are recorded as a single entry."""
        await shell_with_commands.execute("echo foo | cat")
        result = await shell_with_commands.execute("history")
        assert_success(result)
        assert "echo foo | cat" in stdout_text(result)

    async def test_history_does_not_record_empty_input(self, shell_with_commands):
        """Blank lines are not added to history."""
        await shell_with_commands.execute("")
        result = await shell_with_commands.execute("history")
        assert_success(result)
        assert stdout_text(result) == "   1  history"

    async def test_history_too_many_args(self, shell_with_commands):
        """``history`` with more than 1 positional arg returns error."""
        result = await shell_with_commands.execute("history 1 2")
        assert_error(result)
