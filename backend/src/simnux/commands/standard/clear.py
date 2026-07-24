from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode
from simnux.runtime.models import TerminalAction


class Command(SNXCommand):
    """Clear the terminal screen."""

    name = "clear"
    action_type = TerminalAction.CLEAR_SCREEN

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:

        if self.args:
            await stderr.write(f"clear: {CommandError.TOO_MANY_ARGUMENTS}")
            return ExitCode.INVALID_ARGUMENT

        return ExitCode.SUCCESS
