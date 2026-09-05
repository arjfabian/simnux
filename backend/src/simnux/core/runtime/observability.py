"""Runtime observation value types.

Read-only data carriers for runtime introspection. Defined in core so that
core components can produce snapshots without depending on infrastructure;
``infrastructure/observability/snapshots.py`` re-exports these at the
observability boundary.
"""

from dataclasses import dataclass


@dataclass
class ShellSnapshot:
    """Read-only view of a running shell."""

    session_id: str
    scenario_name: str
    loaded_commands: list[str]
    filesystem: list[str]
    filesystem_nodes: int
    current_path: str
    recent_history: list[str]
    history_count: int


@dataclass
class RuntimeSnapshot:
    """Aggregated view of all active runtime sessions."""

    active_sessions: list[ShellSnapshot]
    total_sessions: int
