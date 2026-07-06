from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Simplified echo with basic quote-stripping.

    SIMNUX currently lacks a shell tokenizer/parser.
    Quotes are stripped here as an MVP compatibility layer.
    This is a documented deviation from real POSIX echo behavior.
    """

    name = "echo"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if args:
            await stdout.write(" ".join(args))
        return ExitCode.SUCCESS
