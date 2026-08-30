"""more — Forward-only full-screen file pager.

The historical predecessor of ``less``: pages forward through a file with
no backward scrolling and no search.  Interactive suspension over REST
mirrors ``read``: on first invocation with no piped stdin, the command
buffers the target file into a ``PagerState``, stores it on
``session.pending_state``, marks the session as ``awaiting_input``, and
returns the first viewport.  Each subsequent HTTP turn feeds one keystroke
as stdin until ``q`` exits pager mode.
"""

from simnux.core.commands.models import _DEFAULT_PAGER_VIEWPORT
from simnux.core.commands.models import CommandContext
from simnux.core.commands.models import PagerState
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.runtime.models import ExitCode
from simnux.core.runtime.models import TerminalAction


class Command(SNXCommand):
    """Page through FILE forwards only.

    Navigation keys delivered as single-line stdin payloads on resume:

    - Space / Enter / f — forward one page
    - j                 — scroll down one line
    - q                 — quit

    Backward keys (``b``/``k``) and search (``/``) are not supported.
    """

    name = "more"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        # ── Resume path (pager active) ───────────────────────────────
        if isinstance(ctx.session.pending_state, PagerState):
            return await self._resume(ctx, stdin, stderr)

        # ── First invocation — validate arguments ────────────────────
        args = self.args or []
        positional = [a for a in args if not a.startswith("-")]

        if len(args) != len(positional):
            await stderr.write("more: invalid option\n")
            return ExitCode.INVALID_ARGUMENT

        # ── Piped input — consume stdin and dump, no pager ───────────
        if isinstance(stdin, QueueStreamReader) and stdin.has_pending():
            async for line in stdin:
                await stdout.write(line)
            self.action_type = TerminalAction.NONE
            return ExitCode.SUCCESS

        if not positional:
            await stderr.write("more: missing file operand\n")
            return ExitCode.INVALID_ARGUMENT

        path = positional[0]
        abs_path = self.resolve_path(path, ctx)
        read_result = ctx.filesystem.read(abs_path)

        if read_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"more: {path}: {read_result.message}")
            return read_result.exit_code

        node = read_result.node
        if node is None or node.content is None:
            await stderr.write(f"more: {path}: not found\n")
            return ExitCode.ERROR

        lines = node.content.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"

        # ── Enter pager mode ─────────────────────────────────────────
        ctx.session.pending_state = PagerState(
            content=lines,
            filename=path,
            viewport=ctx.viewport_height or _DEFAULT_PAGER_VIEWPORT,
            program="more",
        )
        ctx.session.awaiting_input = True
        ctx.session.pending_command = f"more {path}"

        self.action_type = TerminalAction.PAGER
        return ExitCode.SUCCESS

    async def _resume(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        """Process one navigation keystroke and refresh the viewport."""
        ps = ctx.session.pending_state
        if not isinstance(ps, PagerState):
            return ExitCode.ERROR

        # Re-clamp against current terminal geometry before slicing.
        if ctx.viewport_height:
            ps.viewport = ctx.viewport_height
            ps.clamp()

        raw = await stdin.readline()
        key = "" if raw is None else raw.rstrip("\n")

        exit_pager = False
        advanced = False
        if raw is None or key == "q":
            exit_pager = True
        elif key in ("", " ", "\n", "f"):
            ps.advance()
            advanced = True
        elif key == "j":
            ps.advance(1)
            advanced = True
        elif key in ("b", "k"):
            await stderr.write("more: cannot go backward\n")
        elif key in ("g", "G") or key.startswith("/"):
            await stderr.write("more: unsupported operation\n")
        # Unknown keys are silently ignored (viewport unchanged).

        # POSIX behavior: once the end of file is reached — including a
        # Space/Enter pressed while already showing the last page —
        # ``more`` exits automatically back to the shell prompt.
        if advanced and ps.at_bottom():
            exit_pager = True

        if exit_pager:
            self._clear_pager(ctx.session)
            self.action_type = TerminalAction.NONE
            return ExitCode.SUCCESS

        self.action_type = TerminalAction.PAGER
        return ExitCode.SUCCESS

    @staticmethod
    def _clear_pager(ctx_session) -> None:
        """Release all suspended pager state."""
        ctx_session.awaiting_input = False
        ctx_session.pending_command = None
        ctx_session.pending_state = None

    @property
    def help_text(self) -> str:
        return (
            "Usage: more FILE\n"
            "View FILE in a forward-only pager.\n"
            "Keys: Space/Enter next page, j next line, q quit.\n"
            "Exits automatically when the end of file is passed."
        )
