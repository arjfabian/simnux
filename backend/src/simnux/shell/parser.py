"""Shell input parsing utilities for SIMNUX."""

import re
import shlex

from simnux.shell.models import ParseResult
from simnux.shell.models import ParsedCommand


class ShellParser:
    """Stateless parser that tokenizes raw shell input into command + args.

    Uses shlex for POSIX-compatible tokenization (handles quoting, escaping).
    Supports pipelines (``|``) and output redirection (``>``, ``>>``).
    Returns a ``ParseResult`` with one or more ``ParsedCommand`` segments.
    Raises ``ValueError`` on malformed input (e.g., missing redirect target,
    empty pipeline segment).
    """

    _ADD_SPACES = re.compile(r"(>>|>|\|)")

    @classmethod
    def _preprocess(cls, raw: str) -> str:
        """Add spaces around ``|``, ``>``, ``>>`` so shlex splits them correctly."""
        return cls._ADD_SPACES.sub(r" \1 ", raw)

    @staticmethod
    def _parse_segment(tokens: list[str]) -> ParsedCommand:
        """Convert a token list into a ParsedCommand, extracting redirects."""
        stdout_redirect: str | None = None
        stdout_append = False
        cmd_tokens: list[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == ">":
                if i + 1 >= len(tokens):
                    raise ValueError("Missing redirect target for '>'")
                stdout_redirect = tokens[i + 1]
                stdout_append = False
                i += 2
                continue
            if token == ">>":
                if i + 1 >= len(tokens):
                    raise ValueError("Missing redirect target for '>>'")
                stdout_redirect = tokens[i + 1]
                stdout_append = True
                i += 2
                continue
            cmd_tokens.append(token)
            i += 1

        return ParsedCommand(
            command=cmd_tokens[0] if cmd_tokens else "",
            args=cmd_tokens[1:],
            stdout_redirect=stdout_redirect,
            stdout_append=stdout_append,
        )

    @classmethod
    def parse(cls, raw: str) -> ParseResult:
        """Tokenize user input into one or more command segments.

        Splits on ``|`` tokens for pipeline support. Each segment undergoes
        redirect extraction (``>``, ``>>``). Returns a ``ParseResult``
        wrapping all segments; backward-compatible properties (``.command``,
        ``.args``, ``.stdout_redirect``) delegate to the first segment.
        Raises ``ValueError`` on empty segments or missing redirect targets.
        """

        tokens = shlex.split(cls._preprocess(raw))

        if not tokens:
            return ParseResult(segments=[])

        segments: list[ParsedCommand] = []
        current: list[str] = []

        for token in tokens:
            if token == "|":
                if not current:
                    raise ValueError("Empty pipeline segment")
                segments.append(cls._parse_segment(current))
                current = []
            else:
                current.append(token)

        if not current:
            raise ValueError("Empty pipeline segment")

        segments.append(cls._parse_segment(current))

        return ParseResult(segments=segments)
