from simnux.commands.runtime import SNXCommand
from simnux.runtime.models   import CommandResult, ExitCode


class Command(SNXCommand):
    """Simplified echo with basic quote-stripping.

    SIMNUX currently lacks a shell tokenizer/parser.
    Quotes are stripped here as an MVP compatibility layer.
    This is a documented deviation from real POSIX echo behavior.
    """

    name = "echo"

    def execute(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(
                exit_code = ExitCode.SUCCESS,
            )
        message = ' '.join(args)
        # In Linux, if a string begins with a single or double quote, but ends
        # without one, "echo" waits for STDIN.
        # For now, the command will detect whether the input is enclosed in
        # single or double quotes, remove them, and return the result.
        if len(message) >= 2:
            first, last = message[0], message[-1]
            # TEMP:
            # SIMNUX currently lacks a shell tokenizer/parser.
            # Quotes are stripped here as an MVP compatibility layer.
            if first == last and first in ("\"", "'"):
                message = message[1:-1]
        return CommandResult(
            stdout    = message,
            exit_code = ExitCode.SUCCESS,
        )
