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


class TerminalAction(IntEnum):
    """Side-effect signals the frontend should apply after a command.

    ``NONE``         — no special action.
    ``CLEAR_SCREEN`` — the terminal display should be cleared.
    ``WIN``          — the scenario objective has been satisfied.
    ``FAIL``         — the scenario's failure condition has triggered.
    ``PAGER``        — a full-screen pager (less/more) is rendering output.
    """

    NONE = 0
    CLEAR_SCREEN = 1
    WIN = 2
    FAIL = 3
    PAGER = 4


@dataclass
class CommandResult:
    """Dispatched command output — drained stream queues bundled into a result."""

    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    exit_code: ExitCode = ExitCode.SUCCESS
    action_type: TerminalAction = TerminalAction.NONE
    action_message: str | None = None
    # Structured payload for client-side paging (see the non-suspended
    # ``less`` command). Populated by the dispatcher from the command.
    pager_payload: dict | None = None
