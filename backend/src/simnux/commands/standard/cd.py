from simnux.commands.errors import CommandError
from simnux.commands.runtime import SNXCommand
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    name = "cd"

    def execute(self, args: list[str]) -> CommandResult:
        """Change the current working directory within the session.

        Accepts relative, absolute, and ~-prefixed paths.
        Defaults to home (~) when no argument is given.
        Mutates ``session.current_directory`` only if the resolved target
        exists and is a directory.
        """

        if len(args) > 1:
            return CommandResult(
                stderr=f"cd: {CommandError.TOO_MANY_ARGUMENTS}",
                exit_code=ExitCode.INVALID_ARGUMENT,
            )

        target = args[0] if args else "~"

        resolved_path = self.resolve_path(target)

        result = self.context.filesystem.validate_directory(resolved_path)

        if result.exit_code != ExitCode.SUCCESS:
            return CommandResult(
                stderr=f"cd: {target}: {result.message}",
                exit_code=result.exit_code,
            )

        self.context.session.set_cwd(resolved_path)

        return CommandResult()
