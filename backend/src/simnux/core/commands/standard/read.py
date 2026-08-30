"""read — Read a line from stdin into a shell variable.

Supports interactive suspension over REST: when stdin is empty (no pipe),
the command writes its prompt, stores state in the session, and returns
SUCCESS.  On the next HTTP turn the route handler feeds the user's input
as stdin and re-dispatches the pending command.
"""

from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    """Read a line from stdin and store it in a shell variable.

    Supports ``-p`` for prompt output, stores into a named variable
    (or ``REPLY`` by default).  When no stdin data is available the
    command suspends, writing the prompt and marking the session as
    ``awaiting_input`` so the REST bridge can resume on the next turn.
    """

    name = "read"

    parameters = {
        "prompt": {
            "flags": ["-p"],
            "type": str,
            "help": "Prompt string to display before reading",
        },
    }

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        # ── Resume path ──────────────────────────────────────────────
        if ctx.session.awaiting_input:
            var_name = ctx.session.pending_var_name or "REPLY"
            line = await stdin.readline()
            if line is None:
                await stderr.write("read: unexpected EOF\n")
                ctx.session.awaiting_input = False
                ctx.session.pending_var_name = None
                ctx.session.pending_command = None
                return ExitCode.ERROR

            ctx.session.environment[var_name] = line.rstrip("\n")
            ctx.session.awaiting_input = False
            ctx.session.pending_var_name = None
            ctx.session.pending_command = None
            return ExitCode.SUCCESS

        # ── First invocation — parse arguments ───────────────────────
        prompt = ""
        var_name = "REPLY"

        if self.parsed_args:
            prompt = self.parsed_args.flags.get("prompt", "")
            if self.parsed_args.positional:
                var_name = self.parsed_args.positional[0]
        elif self.args:
            non_flag_args = [a for a in self.args if not a.startswith("-")]
            if non_flag_args:
                var_name = non_flag_args[0]

        # ── Check whether stdin has data (piped) ─────────────────────
        if isinstance(stdin, QueueStreamReader) and not stdin.has_pending():
            # Interactive / no pipe — suspend for the REST bridge.
            if prompt:
                await stdout.write(prompt)

            ctx.session.awaiting_input = True
            ctx.session.pending_var_name = var_name
            ctx.session.pending_command = self._build_resumable_command(
                prompt,
                var_name,
            )
            return ExitCode.SUCCESS

        # ── Piped data available — consume immediately ───────────────
        if prompt:
            await stdout.write(prompt)

        line = await stdin.readline()
        if line is None:
            await stderr.write("read: unexpected EOF\n")
            return ExitCode.ERROR

        ctx.session.environment[var_name] = line.rstrip("\n")
        return ExitCode.SUCCESS

    @staticmethod
    def _build_resumable_command(prompt: str, var_name: str) -> str:
        """Reconstruct the minimal ``read`` command string for resumption."""
        parts = ["read"]
        if prompt:
            parts.extend(["-p", prompt])
        if var_name and var_name != "REPLY":
            parts.append(var_name)
        return " ".join(parts)
