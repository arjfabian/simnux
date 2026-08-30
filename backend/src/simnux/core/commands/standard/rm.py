from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    name = "rm"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if not args:
            await stderr.write(f"rm: {CommandError.MISSING_OPERAND}")
            return ExitCode.INVALID_ARGUMENT

        raw_target = args[0]

        abs_path = self.resolve_path(raw_target, ctx)

        result = ctx.filesystem.delete(abs_path)

        if result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"rm: {raw_target}: {result.message}")
            return result.exit_code

        return ExitCode.SUCCESS
