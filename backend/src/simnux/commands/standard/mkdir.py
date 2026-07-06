from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    name = "mkdir"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:

        args = self.args or []
        if not args:
            await stderr.write(f"mkdir: {CommandError.MISSING_FILE_OPERAND}")
            return ExitCode.INVALID_ARGUMENT

        raw_target = args[0]

        target = self.resolve_path(raw_target, ctx)

        result = ctx.filesystem.create_directory(target)

        if result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"mkdir: {raw_target}: {result.message}")
            return result.exit_code

        return ExitCode.SUCCESS
