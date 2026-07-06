"""Shell-level command parsing models for SIMNUX."""

from dataclasses import dataclass


@dataclass
class ParsedCommand:
    command: str
    args: list[str]
    stdout_redirect: str | None = None
    stdout_append: bool = False


@dataclass
class ParseResult:
    """Result of parsing a shell command line, holding one or more segments.

    For single commands (no pipes) *and* for the first segment of a pipeline,
    the convenience properties (``command``, ``args``, etc.) delegate to the
    first segment for backward compatibility with existing callers.
    """

    segments: list[ParsedCommand]

    @property
    def command(self) -> str:
        return self.segments[0].command if self.segments else ""

    @property
    def args(self) -> list[str]:
        return self.segments[0].args if self.segments else []

    @property
    def stdout_redirect(self) -> str | None:
        return self.segments[0].stdout_redirect if self.segments else None

    @property
    def stdout_append(self) -> bool:
        return self.segments[0].stdout_append if self.segments else False
