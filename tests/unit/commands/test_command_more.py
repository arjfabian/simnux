"""Tests for the ``more`` forward-only pager command."""

import asyncio

import pytest

from simnux.core.commands.models import PagerState
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.runtime.models import TerminalAction
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


_MULTILINE = "".join(f"row{i}\n" for i in range(1, 61))


def make_pager_file(shell):
    """Write a 60-line file into the VFS delta layer."""
    path = "/home/user/doc.txt"
    shell.filesystem.touch(path, acting_user=shell.user)
    shell.filesystem.delta_layer[path].content = _MULTILINE


async def press_key(shell, session, key: str, viewport_height: int | None = None):
    """Resume the suspended pager with a single keystroke."""
    queue: asyncio.Queue = asyncio.Queue()
    queue.put_nowait(key + "\n")
    queue.put_nowait(None)
    return await shell.execute_resume(
        session.pending_command,
        QueueStreamReader(queue),
        viewport_height=viewport_height,
    )


# ── Basic invocation ─────────────────────────────────────────────────────


class TestMoreBasicInvocation:
    async def test_more_suspends_with_pager_state(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        result = await shell_with_commands.execute("more doc.txt")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        assert session.awaiting_input is True
        assert isinstance(session.pending_state, PagerState)
        assert session.pending_command == "more doc.txt"

    async def test_more_first_page_is_viewport(self, shell_with_commands):
        make_pager_file(shell_with_commands)

        await shell_with_commands.execute("more doc.txt")
        ps: PagerState = shell_with_commands.pending_state
        # Viewport content flows via PagerState projection (pager_lines).
        ps_content = ps.current_page()
        assert len(ps_content) == ps.viewport
        assert ps_content[0] == "row1\n"
        assert ps_content[23] == "row24\n"

    async def test_more_missing_operand(self, shell_with_commands):
        result = await shell_with_commands.execute("more")
        assert_invalid_args(result)
        assert "missing file operand" in stderr_text(result)

    async def test_more_rejects_options(self, shell_with_commands):
        make_pager_file(shell_with_commands)

        result = await shell_with_commands.execute("more -X doc.txt")
        assert_invalid_args(result)
        assert "invalid option" in stderr_text(result)
        assert shell_with_commands.pending_state is None

    async def test_more_missing_file(self, shell_with_commands):
        result = await shell_with_commands.execute("more /nope/gone.txt")
        assert_error(result)
        assert "not found" in stderr_text(result)


# ── Forward-only navigation ──────────────────────────────────────────────


class TestMoreNavigation:
    async def test_space_advances_full_page(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        result = await press_key(shell_with_commands, session, "")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        ps: PagerState = session.pending_state
        assert ps.position == 24
        assert ps.current_page()[0] == "row25\n"

    async def test_f_advances_full_page(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        await press_key(shell_with_commands, session, "f")
        assert session.pending_state.position == 24

    async def test_j_scrolls_one_line(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        await press_key(shell_with_commands, session, "j")
        assert session.pending_state.position == 1

    async def test_b_backward_writes_error_and_stays(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        result = await press_key(shell_with_commands, session, "b")
        assert_success(result)  # stays in pager
        assert result.action_type == TerminalAction.PAGER
        assert "cannot go backward" in stderr_text(result)
        assert session.pending_state.position == 0

    async def test_k_backward_writes_error_and_stays(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        result = await press_key(shell_with_commands, session, "k")
        assert_success(result)
        assert "cannot go backward" in stderr_text(result)

    async def test_search_unsupported(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        result = await press_key(shell_with_commands, session, "/row5")
        assert_success(result)
        assert "unsupported operation" in stderr_text(result)
        assert session.pending_state.search_pattern is None

    async def test_g_jump_unsupported(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        result = await press_key(shell_with_commands, session, "g")
        assert_success(result)
        assert "unsupported operation" in stderr_text(result)


# ── Quit ─────────────────────────────────────────────────────────────────


class TestMoreQuit:
    async def test_q_clears_all_state(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        result = await press_key(shell_with_commands, session, "q")
        assert_success(result)
        assert result.action_type == TerminalAction.NONE
        assert session.awaiting_input is False
        assert session.pending_command is None
        assert session.pending_state is None

    async def test_eof_on_resume_exits_pager(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")

        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait(None)
        result = await shell_with_commands.execute_resume(
            session.pending_command,
            QueueStreamReader(queue),
        )
        assert_success(result)
        assert session.pending_state is None

    async def test_unknown_key_keeps_pager_open(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt")
        result = await press_key(shell_with_commands, session, "z")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        assert session.pending_state is not None


# ── Piped input ──────────────────────────────────────────────────────────


class TestMorePipedInput:
    async def test_pipe_dumps_content_without_pager(self, shell_with_commands):
        session = shell_with_commands

        result = await shell_with_commands.execute("echo piped | more")
        assert_success(result)
        assert result.action_type == TerminalAction.NONE
        assert stdout_text(result) == "piped"
        assert session.pending_state is None
        assert session.awaiting_input is False


# ── Dynamic viewport height ──────────────────────────────────────────────


class TestMoreDynamicViewport:
    async def test_default_viewport_without_geometry(self, shell_with_commands):
        make_pager_file(shell_with_commands)

        await shell_with_commands.execute("more doc.txt")
        ps: PagerState = shell_with_commands.pending_state
        assert ps.viewport == 24

    async def test_first_page_uses_request_viewport(self, shell_with_commands):
        make_pager_file(shell_with_commands)

        await shell_with_commands.execute("more doc.txt", viewport_height=6)
        ps: PagerState = shell_with_commands.pending_state
        assert ps.viewport == 6
        assert ps.current_page() == [f"row{i}\n" for i in range(1, 7)]

    async def test_resume_updates_viewport_and_clamps(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        # Park safely mid-file with a narrow viewport.
        await shell_with_commands.execute("more doc.txt", viewport_height=5)
        for _ in range(6):  # 6 pages x 5 lines -> position 30
            await press_key(shell_with_commands, session, "")
        ps: PagerState = session.pending_state
        assert ps.position == 30

        # Enlarge the terminal and advance: clamps into range, stays open.
        result = await press_key(shell_with_commands, session, "", viewport_height=12)
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        ps = session.pending_state
        assert ps.viewport == 12
        assert ps.position == 42  # 30 + 12, below bottom (60 - 12 = 48)
        assert len(ps.current_page()) == 12

    async def test_resume_without_geometry_keeps_viewport(self, shell_with_commands):
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt", viewport_height=9)
        await press_key(shell_with_commands, session, "j")
        ps: PagerState = session.pending_state
        assert ps.viewport == 9
        assert ps.position == 1


# ── POSIX auto-exit on EOF ───────────────────────────────────────────────


class TestMoreAutoExitOnEof:
    async def test_advance_landing_at_bottom_exits(self, shell_with_commands):
        """The advance that reaches (or passes) EOF terminates the pager."""
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt", viewport_height=5)

        result = None
        for _ in range(20):
            if session.pending_state is None:
                break
            result = await press_key(shell_with_commands, session, "")

        assert result is not None
        assert_success(result)
        assert result.action_type == TerminalAction.NONE
        assert session.awaiting_input is False
        assert session.pending_command is None
        assert session.pending_state is None

    async def test_space_when_initially_at_bottom_exits(self, shell_with_commands):
        """Space on a file smaller than the viewport exits immediately."""
        session = shell_with_commands

        # notes.txt (3 lines) fits in the default 24-line viewport.
        result = await shell_with_commands.execute("more notes.txt")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        ps: PagerState = session.pending_state
        assert ps.at_bottom()

        result = await press_key(shell_with_commands, session, "")
        assert_success(result)
        assert result.action_type == TerminalAction.NONE
        assert session.pending_state is None
        assert session.awaiting_input is False

    async def test_backward_error_does_not_exit_at_eof(self, shell_with_commands):
        """Non-advance keys never trigger the auto-exit path."""
        make_pager_file(shell_with_commands)
        session = shell_with_commands

        await shell_with_commands.execute("more doc.txt", viewport_height=5)
        for _ in range(6):
            await press_key(shell_with_commands, session, "")

        result = await press_key(shell_with_commands, session, "b")
        assert_success(result)
        assert result.action_type == TerminalAction.PAGER
        assert "cannot go backward" in stderr_text(result)
        assert session.pending_state is not None
