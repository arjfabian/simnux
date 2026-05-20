from simnux.commands.runtime import SNXCommand
from simnux.runtime.models import CommandResult, ExitCode
from simnux.commands.errors import CommandError


class Command(SNXCommand):

    name = "cat"

    def execute(self, args: list[str]) -> CommandResult:
        """Read file content from VFS.

        Only handles the first positional argument; multi-file concatenation
        is not implemented. Returns 'missing operand' when no argument is
        given (matching GNU coreutils behavior).
        """

        if not args:
            return CommandResult(
                stderr = f"cat: {CommandError.MISSING_OPERAND}",
                exit_code=ExitCode.INVALID_ARGUMENT,
            )

        raw_target = args[0]

        abs_path = self.resolve_path(raw_target)

        result = self.context.filesystem.read(abs_path)

        if result.exit_code != ExitCode.SUCCESS:

            return CommandResult(
                stderr=f"cat: {raw_target}: {result.message}",
                exit_code=result.exit_code,
            )

        return CommandResult(
            stdout=result.node.content,
            exit_code=ExitCode.SUCCESS,
        )