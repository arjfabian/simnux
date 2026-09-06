"""Tests for the ``less`` command (client-side pager protocol).

``less`` no longer suspends the session into a backend ``PagerState``.
Instead it returns the full file content via ``pager_payload`` so the
frontend can render and navigate a local pager without further HTTP
roundtrips.
"""

import pytest

from simnux.core.commands.models import MAX_PAGER_FILE_SIZE
from simnux.core.runtime.models import TerminalAction
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


_MULTILINE = "".join(f"line{i}\n" for i in range(1, 51))


def make_pager_file(shell, path="/home/user/big.txt", content=_MULTILINE):
    """Write a file into the VFS delta layer."""
    shell.filesystem.touch(path, acting_user=shell.user)
    shell.filesystem.delta_layer[path].content = content


def pager_lines(result):
    """Extract the line content from a ``less`` result payload."""
    return result.pager_payload["lines"]


# ── Basic invocation ─────────────────────────────────────────────────────


class TestLessBasicInvocation:
    async def test_less_does_not_suspend_session(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        result = await shell_with_commands.execute("less big.txt")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        assert result.pager_payload is not None
        assert result.pager_payload["is_pager"] is True
        assert result.pager_payload["filename"] == "big.txt"
        # No interactive suspension on the backend.
        assert session.awaiting_input is False
        assert session.pending_state is None
        assert session.pending_command is None

    async def test_less_returns_all_lines(self, shell_with_commands):
        make_pager_file(shell_with_commands)

        result = await shell_with_commands.execute("less big.txt")
        lines = pager_lines(result)
        assert len(lines) == 50
        assert lines[0] == "line1"
        assert lines[49] == "line50"

    async def test_less_short_file(self, shell_with_commands):
        result = await shell_with_commands.execute("less notes.txt")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        assert pager_lines(result) == ["hello world"]

    async def test_less_missing_operand(self, shell_with_commands):
        result = await shell_with_commands.execute("less")
        assert_invalid_args(result)
        assert "missing file operand" in stderr_text(result)
        assert result.pager_payload is None

    async def test_less_missing_file(self, shell_with_commands):
        result = await shell_with_commands.execute("less /nope/missing.txt")
        assert_error(result)
        assert "not found" in stderr_text(result)
        assert result.pager_payload is None


# ── File size limit ──────────────────────────────────────────────────────


class TestLessSizeLimit:
    async def test_less_rejects_oversized_file(self, shell_with_commands):
        oversized = "x" * (MAX_PAGER_FILE_SIZE + 1)
        make_pager_file(shell_with_commands, content=oversized)

        result = await shell_with_commands.execute("less big.txt")
        assert_error(result)
        assert result.action_type == TerminalAction.NONE
        assert "file too large (max 1MB)" in stderr_text(result)
        assert result.pager_payload is None

    async def test_less_allows_file_at_limit(self, shell_with_commands):
        at_limit = "x" * MAX_PAGER_FILE_SIZE
        make_pager_file(shell_with_commands, content=at_limit)

        result = await shell_with_commands.execute("less big.txt")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        assert pager_lines(result) == ["x" * MAX_PAGER_FILE_SIZE]


# ── Piped input / flags ──────────────────────────────────────────────────


class TestLessFlags:
    async def test_uppercase_n_prepends_numbers(self, shell_with_commands):
        make_pager_file(shell_with_commands)

        result = await shell_with_commands.execute("less -N big.txt")
        assert_success(result)
        lines = pager_lines(result)
        # Width-padded right-aligned numbers: 50 lines -> width 2.
        assert lines[0] == " 1  line1"
        assert lines[24] == "25  line25"

    async def test_pipe_dumps_content_without_pager(self, shell_with_commands):
        result = await shell_with_commands.execute("echo hello | less")
        assert_success(result)
        assert result.action_type == TerminalAction.NONE
        assert result.pager_payload is None
        assert stdout_text(result) == "hello"

    async def test_relative_and_absolute_paths(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        result = await shell_with_commands.execute("less /home/user/big.txt")
        assert_success(result)
        assert len(pager_lines(result)) == 50


class TestCatSizeLimit:
    async def test_cat_rejects_oversized_file(self, shell_with_commands):
        oversized = "x" * (MAX_PAGER_FILE_SIZE + 1)
        make_pager_file(shell_with_commands, content=oversized)

        result = await shell_with_commands.execute("cat big.txt")
        assert_error(result)
        assert "file too large (max 1MB)" in stderr_text(result)
        assert result.stdout == []

    async def test_cat_allows_file_at_limit(self, shell_with_commands):
        at_limit = "x" * MAX_PAGER_FILE_SIZE
        make_pager_file(shell_with_commands, content=at_limit)

        result = await shell_with_commands.execute("cat big.txt")
        assert_success(result)
        assert "x" * MAX_PAGER_FILE_SIZE in stdout_text(result)


class TestInspectionCommandsSizeLimit:
    async def test_head_rejects_oversized_file(self, shell_with_commands):
        oversized = "x" * (MAX_PAGER_FILE_SIZE + 1)
        make_pager_file(shell_with_commands, content=oversized)

        result = await shell_with_commands.execute("head big.txt")
        assert_error(result)
        assert "file too large (max 1MB)" in stderr_text(result)

    async def test_tail_rejects_oversized_file(self, shell_with_commands):
        oversized = "x" * (MAX_PAGER_FILE_SIZE + 1)
        make_pager_file(shell_with_commands, content=oversized)

        result = await shell_with_commands.execute("tail big.txt")
        assert_error(result)
        assert "file too large (max 1MB)" in stderr_text(result)

    async def test_grep_rejects_oversized_file(self, shell_with_commands):
        oversized = "x" * (MAX_PAGER_FILE_SIZE + 1)
        make_pager_file(shell_with_commands, content=oversized)

        result = await shell_with_commands.execute("grep zzz big.txt")
        assert_error(result)
        assert "file too large (max 1MB)" in stderr_text(result)

    async def test_diff_rejects_oversized_file(self, shell_with_commands):
        oversized = "x" * (MAX_PAGER_FILE_SIZE + 1)
        make_pager_file(shell_with_commands, content=oversized)

        result = await shell_with_commands.execute("diff big.txt notes.txt")
        assert_error(result)
        assert "file too large (max 1MB)" in stderr_text(result)
