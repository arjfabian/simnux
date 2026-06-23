from simnux.commands.errors import CommandError
from simnux.commands.runtime import SNXCommand
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    name = "mkdir"

    def execute(self, args: list[str]) -> CommandResult:

        if not args:
            return CommandResult(
                stderr=f"mkdir: {CommandError.MISSING_FILE_OPERAND}",
                exit_code=ExitCode.INVALID_ARGUMENT,
            )

        raw_target = args[0]

        target = self.resolve_path(raw_target)

        result = self.context.filesystem.create_directory(target)

        if result.exit_code != ExitCode.SUCCESS:
            return CommandResult(
                stderr=f"mkdir: {raw_target}: {result.message}",
                exit_code=result.exit_code,
            )

        return CommandResult(
            exit_code=ExitCode.SUCCESS,
        )
