from simnux.commands.errors import CommandError
from simnux.commands.runtime import SNXCommand
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Create an empty file or update its existence in the VFS.

    NOTE: does NOT update access/modification timestamps (no inode metadata
    layer yet). This is a documented deviation from POSIX touch(1).
    """

    name = "touch"

    def execute(self, args: list[str]) -> CommandResult:

        if not args:
            return CommandResult(
                stderr=f"touch: {CommandError.MISSING_FILE_OPERAND}",
                exit_code=ExitCode.INVALID_ARGUMENT,
            )

        target = self.resolve_path(args[0])

        result = self.context.filesystem.touch(
            path=target,
        )

        return CommandResult(
            stderr=result.message if result.exit_code != ExitCode.SUCCESS else "",
            exit_code=result.exit_code,
        )
