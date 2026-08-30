from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    """Display or manipulate the session command history."""

    name = "history"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []

        if args:
            if args[0] == "-c":
                ctx.session.history.clear()
                return ExitCode.SUCCESS

            if args[0].startswith("-"):
                await stderr.write(f"history: {args[0]}: invalid option")
                return ExitCode.ERROR

            if len(args) > 1:
                await stderr.write("history: too many arguments")
                return ExitCode.ERROR

            try:
                n = int(args[0])
            except ValueError:
                await stderr.write(f"history: {args[0]}: numeric argument required")
                return ExitCode.ERROR

            if n == 0:
                await stderr.write("history: 0: argument out of range")
                return ExitCode.ERROR

            total = len(ctx.session.history)
            n = min(n, total)
            start = total - n + 1
            entries = ctx.session.history[start - 1 :]
        else:
            start = 1
            entries = ctx.session.history

        for i, line in enumerate(entries, start=start):
            await stdout.write(f"{i:>4}  {line}\n")

        return ExitCode.SUCCESS
