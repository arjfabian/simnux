from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """List directory contents (simplified POSIX-like, single-line output)."""

    name = "ls"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:

        args = self.args or []
        if args:
            raw_target = args[0]
            target = self.resolve_path(raw_target, ctx)
        else:
            raw_target = "."
            target = ctx.session.current_directory

        if not ctx.filesystem.exists(target):
            await stderr.write(
                f"ls: cannot access '{raw_target}': {CommandError.NO_SUCH_FILE_OR_DIR}"
            )
            return ExitCode.ERROR

        if not ctx.filesystem.is_directory(target):
            await stderr.write(
                f"ls: cannot access '{raw_target}': {CommandError.NOT_A_DIRECTORY}"
            )
            return ExitCode.ERROR

        nodes = ctx.filesystem.list_directory(target)

        if not nodes:
            return ExitCode.SUCCESS

        names = []
        names.append(".")
        if target != "/":
            names.append("..")

        for node in nodes:
            name = node.path.split("/")[-1]

            if node.is_directory:
                names.append(name + "/")
            else:
                names.append(name)

        await stdout.write("  ".join(names))
        return ExitCode.SUCCESS
