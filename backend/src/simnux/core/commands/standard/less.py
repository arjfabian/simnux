"""less — Full-screen file viewer with client-side navigation.

``less`` no longer suspends the session into an interactive backend
``PagerState`` loop.  Instead it reads the target file (guarded by
``MAX_PAGER_FILE_SIZE``) and returns the full content so the frontend can
render a local pager and handle navigation (Arrow/j/k, PageUp/PageDown,
Space, q) entirely client-side without further HTTP roundtrips.

The response signals the local pager via ``action_type == TerminalAction.PAGER``
and carries ``is_pager: True`` plus the line content so the frontend captures
viewport focus and pages locally.
"""

from simnux.core.commands.models import MAX_PAGER_FILE_SIZE
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.runtime.models import ExitCode
from simnux.core.runtime.models import TerminalAction


class Command(SNXCommand):
    """View a file in a full-screen pager rendered on the frontend.

    Supports ``-N`` for line numbers.  Navigation is handled client-side:
    Space/f and PageDown page forward, b and PageUp page back, j/ArrowDown
    and k/ArrowUp scroll a single line, and q quits the local pager.
    """

    name = "less"

    parameters = {
        "line_numbers": {
            "flags": ["-N"],
            "type": bool,
            "help": "Display line numbers",
        },
    }

    # Structured payload handed to the dispatcher/route so the API response
    # can signal the frontend to render a client-side pager view.
    _pager_payload: dict | None = None

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        self._pager_payload = None

        # ── Parse arguments ─────────────────────────────────────────
        line_numbers = False
        if self.parsed_args:
            line_numbers = bool(self.parsed_args.flags.get("line_numbers", False))

        args = self.args or []
        positional = [a for a in args if not a.startswith("-")]

        # ── Piped input — consume stdin and dump, no pager ───────────
        if isinstance(stdin, QueueStreamReader) and stdin.has_pending():
            async for line in stdin:
                await stdout.write(line)
            self.action_type = TerminalAction.NONE
            return ExitCode.SUCCESS

        if not positional:
            await stderr.write("less: missing file operand\n")
            return ExitCode.INVALID_ARGUMENT

        path = positional[0]
        abs_path = self.resolve_path(path, ctx)
        read_result = ctx.filesystem.read(abs_path, execution=ctx.execution_context)

        if read_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"less: {path}: {read_result.message}")
            return read_result.exit_code

        node = read_result.node
        if node is None or node.content is None:
            await stderr.write(f"less: {path}: not found\n")
            return ExitCode.ERROR

        if len(node.content.encode("utf-8")) > MAX_PAGER_FILE_SIZE:
            await stderr.write(f"less: {path}: file too large (max 1MB)\n")
            return ExitCode.ERROR

        lines = node.content.splitlines()
        if line_numbers:
            width = len(str(len(lines)))
            lines = [f"{i + 1:>{width}}  {line}" for i, line in enumerate(lines)]

        self._pager_payload = {
            "is_pager": True,
            "lines": lines,
            "filename": path,
        }

        self.action_type = TerminalAction.PAGER
        return ExitCode.SUCCESS

    @property
    def help_text(self) -> str:
        return (
            "Usage: less [-N] FILE\n"
            "View FILE in a full-screen pager rendered locally.\n"
            "Keys: Space/f/PageDown next page, b/PageUp back,\n"
            "j/ArrowDown and k/ArrowUp scroll by line, q quit."
        )
