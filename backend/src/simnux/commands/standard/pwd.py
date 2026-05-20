from simnux.commands.errors  import CommandError
from simnux.commands.runtime import SNXCommand
from simnux.runtime.models   import CommandResult, ExitCode


class Command(SNXCommand):

    name = "pwd"

    def execute(self, args: list[str]) -> CommandResult:
        """Print the session's current working directory.

        Reads from ``session.current_directory``, not from any real OS
        state. Rejects arguments (matching POSIX behavior).
        """

        if args:
            return CommandResult(
                stderr    = f"pwd: {CommandError.TOO_MANY_ARGUMENTS}",
                exit_code = ExitCode.INVALID_ARGUMENT,
            )

        return CommandResult(
            stdout    = self.context.session.current_directory,
            exit_code = ExitCode.SUCCESS,
        )
