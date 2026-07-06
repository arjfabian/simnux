"""Core runtime models shared across command execution pipeline."""

from dataclasses import dataclass
from dataclasses import field
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
    """Transport contract between command execution and the API layer.

    Built by the dispatcher after command execution by draining stream
    queues. Commands do not construct ``CommandResult`` directly — they
    write to ``stdout``/``stderr`` streams and return ``ExitCode``.
    """

    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    exit_code: ExitCode = ExitCode.SUCCESS
