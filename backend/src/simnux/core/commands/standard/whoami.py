from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


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

        await stdout.write(f"{ctx.shell.user.identifier}\n")
        return ExitCode.SUCCESS
