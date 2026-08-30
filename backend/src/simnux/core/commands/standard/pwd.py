from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    name = "pwd"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        """Print the session's current working directory.

        Reads from ``session.current_directory``, not from any real OS
        state. Rejects arguments (matching POSIX behavior).
        """

        args = self.args or []
        if args:
            await stderr.write(f"pwd: {CommandError.TOO_MANY_ARGUMENTS}")
            return ExitCode.INVALID_ARGUMENT

        await stdout.write(ctx.session.current_directory)
        return ExitCode.SUCCESS
