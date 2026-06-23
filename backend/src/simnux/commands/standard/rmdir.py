from simnux.commands.errors import CommandError
from simnux.commands.runtime import SNXCommand
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    name = "rmdir"

    def execute(self, args: list[str]) -> CommandResult:

        if not args:
            return CommandResult(
                stderr=f"rmdir: {CommandError.MISSING_OPERAND}",
                exit_code=ExitCode.INVALID_ARGUMENT,
            )

        raw_target = args[0]

        abs_path = self.resolve_path(raw_target)

        result = self.context.filesystem.delete(abs_path, delete_dir=True)

        if result.exit_code != ExitCode.SUCCESS:
            return CommandResult(
                stderr=f"rmdir: {raw_target}: {result.message}",
                exit_code=result.exit_code,
            )

        return CommandResult(
            exit_code=ExitCode.SUCCESS,
        )
