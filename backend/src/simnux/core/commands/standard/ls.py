from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    """List directory contents (POSIX-like, single-line output)."""

    name = "ls"

    parameters = {
        "all": {
            "flags": ["-a", "--all"],
            "type": bool,
            "help": "include . and .. and hidden files",
        },
        "almost_all": {
            "flags": ["-A", "--almost-all"],
            "type": bool,
            "help": "include hidden files but not . and ..",
        },
    }

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        pos_args = self.parsed_args.positional if self.parsed_args else (self.args or [])
        if pos_args:
            raw_target = pos_args[0]
            target = self.resolve_path(raw_target, ctx)
        else:
            raw_target = "."
            target = ctx.shell.current_directory

        if not ctx.filesystem.exists(target):
            await stderr.write(
                f"ls: cannot access '{raw_target}': {CommandError.NO_SUCH_FILE_OR_DIR}"
            )
            return ExitCode.ERROR

        if not ctx.filesystem.is_directory(target):
            await stderr.write(f"ls: cannot access '{raw_target}': {CommandError.NOT_A_DIRECTORY}")
            return ExitCode.ERROR

        show_all = self.parsed_args and self.parsed_args.flags.get("all", False)
        show_almost_all = self.parsed_args and self.parsed_args.flags.get("almost_all", False)

        list_result = ctx.filesystem.list_directory(
            target,
            acting_user=ctx.shell.user,
        )
        if list_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"ls: cannot access '{raw_target}': {list_result.message}")
            return list_result.exit_code

        nodes = list_result.nodes

        names: list[str] = []

        if show_all:
            names.append(".")
            if target != "/":
                names.append("..")

        for node in sorted(nodes, key=lambda n: n.path.split("/")[-1]):
            name = node.path.split("/")[-1]

            if name.startswith(".") and not show_all and not show_almost_all:
                continue

            if node.is_directory:
                names.append(name + "/")
            else:
                names.append(name)

        if names:
            await stdout.write("  ".join(names))

        return ExitCode.SUCCESS
