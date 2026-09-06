from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    """Create an empty file or update its existence in the VFS.

    NOTE: does NOT update access/modification timestamps (no inode metadata
    layer yet). This is a documented deviation from POSIX touch(1).
    """

    name = "touch"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if not args:
            await stderr.write(f"touch: {CommandError.MISSING_FILE_OPERAND}")
            return ExitCode.INVALID_ARGUMENT

        target = self.resolve_path(args[0], ctx)

        result = ctx.filesystem.touch(
            path=target,
            acting_user=ctx.shell.user,
        )

        if result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"touch: {args[0]}: {result.message}")
            return result.exit_code

        return ExitCode.SUCCESS
