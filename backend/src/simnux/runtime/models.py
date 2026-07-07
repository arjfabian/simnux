"""Core runtime models shared across command execution pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import IntEnum


class ExitCode(IntEnum):
    """Simplified POSIX exit codes: SUCCESS(0), ERROR(1), INVALID_ARGUMENT(2)."""

    SUCCESS = 0
    ERROR = 1
    INVALID_ARGUMENT = 2


@dataclass
class CommandResult:
    """Dispatched command output — drained stream queues bundled into a result."""

    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    exit_code: ExitCode = ExitCode.SUCCESS
    clear_screen: bool = False
