"""Shell input parsing utilities for SIMNUX."""

import re
import shlex

from simnux.shell.models import LogicalOperator
from simnux.shell.models import LogicalSegment
from simnux.shell.models import ParseResult
from simnux.shell.models import ParsedCommand


class ShellParser:
    """Stateless parser that tokenizes raw shell input into command + args.

    Uses shlex for POSIX-compatible tokenization (handles quoting, escaping).
    Supports pipelines (``|``), logical operators (``&&``, ``||``),
    and output redirection (``>``, ``>>``).
    Returns a ``ParseResult`` with one or more ``ParsedCommand`` segments,
    or a list of ``LogicalSegment`` for commands with logical operators.
    Raises ``ValueError`` on malformed input (e.g., missing redirect target,
    empty pipeline segment).
    """

    _ADD_SPACES = re.compile(r"(&&|\|\||>>|>|\|)")

    @classmethod
    def _preprocess(cls, raw: str) -> str:
        """Add spaces around ``&&``, ``||``, ``|``, ``>``, ``>>`` so shlex splits them correctly."""
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

    @staticmethod
    def _parse_pipeline(tokens: list[str]) -> ParseResult:
        """Parse a list of tokens into a ParseResult with pipeline segments."""
        if not tokens:
            return ParseResult(segments=[])

        segments: list[ParsedCommand] = []
        current: list[str] = []

        for token in tokens:
            if token == "|":
                if not current:
                    raise ValueError("Empty pipeline segment")
                segments.append(ShellParser._parse_segment(current))
                current = []
            else:
                current.append(token)

        if not current:
            raise ValueError("Empty pipeline segment")

        segments.append(ShellParser._parse_segment(current))
        return ParseResult(segments=segments)

    @classmethod
    def parse(cls, raw: str) -> ParseResult:
        """Tokenize user input into one or more command segments.

        Splits on ``|`` tokens for pipeline support. Each segment undergoes
        redirect extraction (``>``, ``>>``). Returns a ``ParseResult``
        wrapping all segments; backward-compatible properties (``.command``,
        ``.args``, ``.stdout_redirect``) delegate to the first segment.
        Raises ``ValueError`` on empty segments or missing redirect targets.
        """
        preprocessed = cls._preprocess(raw)

        tokens = shlex.split(preprocessed)

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

    @classmethod
    def parse_logical(cls, raw: str) -> list[LogicalSegment]:
        """Parse input into logical segments separated by && and ||.

        Returns a list of LogicalSegment, each containing a pipeline.
        The first segment always has operator=NONE.
        """
        # First, handle && and || by splitting on them
        # We need to be careful with || not to match single |
        parts = []
        current_parts = []
        pending_op = None
        i = 0
        raw_stripped = raw.strip()

        # Tokenize manually to handle && and || correctly
        while i < len(raw_stripped):
            # Skip whitespace
            while i < len(raw_stripped) and raw_stripped[i] in ' \t':
                i += 1

            if i >= len(raw_stripped):
                break

            # Check for && or ||
            if raw_stripped[i:i+2] in ('&&', '||'):
                op = LogicalOperator.AND if raw_stripped[i:i+2] == '&&' else LogicalOperator.OR
                segment_str = ''.join(current_parts).strip()
                if segment_str:
                    parts.append((pending_op or LogicalOperator.NONE, segment_str))
                pending_op = op
                current_parts = []
                i += 2
            # Check for | (single pipe) - add to current_parts
            elif raw_stripped[i] == '|':
                current_parts.append('|')
                i += 1
            else:
                # Read until next operator or end
                start = i
                while i < len(raw_stripped) and raw_stripped[i:i+2] not in ('&&', '||'):
                    if raw_stripped[i] == '|':
                        # Check if it's || or just |
                        if i + 1 < len(raw_stripped) and raw_stripped[i+1] == '|':
                            break
                        else:
                            current_parts.append('|')
                            i += 1
                            break
                    else:
                        current_parts.append(raw_stripped[i])
                        i += 1

        # Add the last segment
        segment_str = ''.join(current_parts).strip()
        if segment_str:
            parts.append((pending_op or LogicalOperator.NONE, segment_str))

        # Now parse each segment as a pipeline
        logical_segments = []
        for idx, (op, segment_str) in enumerate(parts):
            # For the first segment, operator should be NONE
            if idx == 0:
                op = LogicalOperator.NONE

            try:
                pipeline = cls.parse(segment_str)
                logical_segments.append(LogicalSegment(operator=op, pipeline=pipeline))
            except ValueError as e:
                # Re-raise with context
                raise ValueError(f"Error parsing logical segment: {e}")

        return logical_segments
