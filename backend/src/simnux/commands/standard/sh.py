"""sh / bash — POSIX shell interpreter (script execution)."""

from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Execute a script file line-by-line."""

    name = "sh"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        if not ctx.dispatcher:
            await stderr.write("sh: dispatcher not available\n")
            return ExitCode.ERROR

        file_args = self.parsed_args.positional if self.parsed_args else (self.args or [])
        if not file_args:
            await stderr.write("sh: missing file operand\n")
            return ExitCode.INVALID_ARGUMENT

        target = file_args[0]
        script_args = file_args[1:]

        abs_path = ctx.filesystem.resolve_path(
            current_directory=ctx.session.current_directory,
            target_path=target,
            home_directory=ctx.session.home_directory,
        )
        result = ctx.filesystem.read(abs_path)
        if result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"sh: {target}: {result.message}\n")
            return result.exit_code

        content = result.node.content or ""
        script_result = await ctx.dispatcher.execute_script(
            content,
            ctx,
            stdin,
            stdout,
            stderr,
            script_args,
        )
        return script_result.exit_code


class BashCommand(Command):
    """Alias for ``sh`` with ``bash`` as the command name."""

    name = "bash"
