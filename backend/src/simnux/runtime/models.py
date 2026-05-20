"""Core runtime models shared across command execution pipeline."""

from dataclasses import dataclass, field
from enum import IntEnum


class ExitCode(IntEnum):
    """Standardized process exit codes for command execution.

    Simplified compared to real Linux: only SUCCESS(0), ERROR(1), and
    INVALID_ARGUMENT(2). Missing: SIGINT(130), SIGPIPE(141), and the full
    sysexits.h range. This is an intentional simplification — real POSIX
    exit codes are not needed for the training use case.
    """

    SUCCESS = 0
    ERROR = 1
    INVALID_ARGUMENT = 2


@dataclass
class CommandResult:
    """Normalized result returned by all commands in the runtime.

    ``stdout`` and ``stderr`` are normalized to ``list[str]`` in
    ``__post_init__`` for consistent JSON serialization. Strings are wrapped
    in a single-element list; None becomes []. This is the sole output
    contract between commands and the shell runtime.
    """

    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    exit_code: ExitCode = ExitCode.SUCCESS

    def __post_init__(self) -> None:
        """Normalize string outputs into list form for consistent transport."""
        if isinstance(self.stdout, str):
            self.stdout = [self.stdout] if self.stdout else []
        if isinstance(self.stderr, str):
            self.stderr = [self.stderr] if self.stderr else []
