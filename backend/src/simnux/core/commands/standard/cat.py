from simnux.core.commands.models import MAX_PAGER_FILE_SIZE
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    name = "cat"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        """Concatenate file content or stream input to stdout.

        With no arguments, reads from ``stdin`` until EOF.
        ``-`` as an argument reads from stdin at that position.
        File paths are resolved via the VFS layer.
        """

        args = self.args or []

        if not args:
            async for line in stdin:
                await stdout.write(line)
            return ExitCode.SUCCESS

        for arg in args:
            if arg == "-":
                async for line in stdin:
                    await stdout.write(line)
            else:
                abs_path = self.resolve_path(arg, ctx)
                result = ctx.filesystem.read(abs_path, acting_user=ctx.shell.user)

                if result.exit_code != ExitCode.SUCCESS:
                    await stderr.write(f"cat: {arg}: {result.message}")
                    return result.exit_code

                if result.node is None or result.node.content is None:
                    await stderr.write(f"cat: {arg}: not found\n")
                    return ExitCode.ERROR

                if len(result.node.content.encode("utf-8")) > MAX_PAGER_FILE_SIZE:
                    await stderr.write(f"cat: {arg}: file too large (max 1MB)\n")
                    return ExitCode.ERROR

                for line in result.node.content.splitlines(keepends=True):
                    await stdout.write(line)

        return ExitCode.SUCCESS
