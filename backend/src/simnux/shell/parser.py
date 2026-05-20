"""Shell input parsing utilities for SIMNUX."""

import shlex

from simnux.shell.models import ParsedCommand


class ShellParser:
    """Stateless parser that tokenizes raw shell input into command + args.

    Uses shlex for POSIX-compatible tokenization (handles quoting, escaping).
    Returns empty command for blank input.
    """

    @staticmethod
    def parse(raw: str) -> ParsedCommand:
        """Tokenize user input into command + arguments."""

        tokens = shlex.split(raw)

        if not tokens:
            return ParsedCommand(command="", args=[])

        return ParsedCommand(
            command=tokens[0],
            args=tokens[1:],
        )
