from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Print effective user name."""

    name = "whoami"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:

        if self.args:
            await stderr.write(f"whoami: {CommandError.TOO_MANY_ARGUMENTS}")
            return ExitCode.INVALID_ARGUMENT

        await stdout.write(f"{ctx.session.username}\n")
        return ExitCode.SUCCESS
