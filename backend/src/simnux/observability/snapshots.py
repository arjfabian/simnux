"""Runtime and session snapshot models for SIMNUX observability."""

from dataclasses import dataclass


@dataclass
class ShellSnapshot:
    """Lightweight representation of a running shell session.

    Read-only view; mutations to this object do not affect the running
    session.
    """

    session_id: str
    scenario_name: str
    loaded_commands: list[str]
    filesystem: list[str]
    filesystem_nodes: int
    current_path: str


@dataclass
class RuntimeSnapshot:
    """Aggregated view of all active runtime sessions."""

    active_sessions: list[ShellSnapshot]
    total_sessions: int
