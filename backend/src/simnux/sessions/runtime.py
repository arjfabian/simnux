"""Session state model for SIMNUX runtime."""

from dataclasses import dataclass
from dataclasses import field
from typing import Any

from simnux.scenarios.models import SNXScenario


_HISTORY_CAPACITY = 1000


@dataclass
class SNXSession:
    """Mutable session state. NOT thread-safe — runs in a single-threaded async context."""

    session_id: str
    scenario: SNXScenario
    current_directory: str

    tasks_total: int = 0
    tasks_completed: int = 0

    metadata: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)

    awaiting_input: bool = False
    pending_var_name: str | None = None
    pending_command: str | None = None
    pending_state: Any | None = None

    @property
    def motd(self) -> str:
        node = self.scenario.filesystem.get("/etc/motd")
        return node.content if node else ""

    @property
    def home_directory(self) -> str:
        return self.scenario.starting_dir

    @property
    def username(self) -> str:
        return self.scenario.username

    @property
    def hostname(self) -> str:
        return self.scenario.hostname

    def add_history(self, raw_input: str) -> None:
        """Append a raw command line. Drops oldest entries past capacity."""
        if not raw_input.strip():
            return
        self.history.append(raw_input)
        if len(self.history) > _HISTORY_CAPACITY:
            self.history.pop(0)

    def set_cwd(self, path: str) -> None:
        """Update working directory. Caller must verify path exists and is a directory."""
        self.current_directory = path

    def get_status(self) -> dict:
        """Return aggregated session progress state."""
        scenario_solved = self.tasks_total > 0 and self.tasks_completed >= self.tasks_total

        return {
            "tasks_total": self.tasks_total,
            "tasks_completed": self.tasks_completed,
            "scenario_solved": scenario_solved,
        }
