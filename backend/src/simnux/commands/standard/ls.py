from simnux.commands.errors import CommandError
from simnux.commands.runtime import SNXCommand
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """List directory contents.

    Currently supports a single target path argument.
    Always includes . and .. entries.
    Output is space-separated single-line (not columnated).
    Directories are suffixed with '/'.
    This is a simplified POSIX-like listing, not a full implementation.
    """

    name = "ls"

    def execute(self, args: list[str]) -> CommandResult:

        if args:
            raw_target = args[0]
            target = self.resolve_path(raw_target)
        else:
            raw_target = "."
            target = self.context.session.current_directory

        if not self.context.filesystem.exists(target):
            return CommandResult(
                stderr=f"ls: cannot access '{raw_target}': {CommandError.NO_SUCH_FILE_OR_DIR}",
                exit_code=ExitCode.ERROR,
            )

        if not self.context.filesystem.is_directory(target):
            return CommandResult(
                stderr=f"ls: cannot access '{raw_target}': {CommandError.NOT_A_DIRECTORY}",
                exit_code=ExitCode.ERROR,
            )

        nodes = self.context.filesystem.list_directory(target)

        if not nodes:
            return CommandResult(
                exit_code=ExitCode.SUCCESS,
            )

        # MVP: single-line space-separated output. No columns, colors, or
        # flags support. Real ls uses terminal-width-aware column layout.
        names = []

        # Add '.' and '..' entries following POSIX directory listing convention.
        names.append(".")
        if target != "/":
            names.append("..")

        for node in nodes:
            name = node.path.split("/")[-1]

            if node.is_directory:
                names.append(name + "/")
            else:
                names.append(name)

        # TODO:
        # This command assumes no flags are set. When implementing flags like
        # -l, -a, etc., stdout will send an array to the frontend.
        return CommandResult(
            stdout="  ".join(names),
            exit_code=ExitCode.SUCCESS,
        )
