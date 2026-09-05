from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    name = "cd"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        """Change the current working directory within the shell.

        Accepts relative, absolute, and ~-prefixed paths.
        Defaults to home (~) when no argument is given.
        Mutates ``ctx.shell.current_directory`` only if the resolved target
        exists and is a directory.
        """

        args = self.args or []
        if len(args) > 1:
            await stderr.write(f"cd: {CommandError.TOO_MANY_ARGUMENTS}")
            return ExitCode.INVALID_ARGUMENT

        target = args[0] if args else "~"

        resolved_path = self.resolve_path(target, ctx)

        result = ctx.filesystem.validate_directory(resolved_path)

        if result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"cd: {target}: {result.message}")
            return result.exit_code

        ctx.shell.set_cwd(resolved_path)

        return ExitCode.SUCCESS
