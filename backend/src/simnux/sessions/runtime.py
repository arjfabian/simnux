"""Session state model for SIMNUX runtime."""

from dataclasses import dataclass
from dataclasses import field
from typing import Any

from simnux.scenarios.models import SNXScenario


@dataclass
class SNXSession:
    """Mutable session state. NOT thread-safe — currently runs in a
    single-threaded async context.

    If concurrent access is added, ``current_directory`` mutations will need
    synchronization. The ``metadata`` dict is opaque storage for scenario
    progress.
    """

    session_id: str
    scenario: SNXScenario
    current_directory: str

    tasks_total: int = 0
    tasks_completed: int = 0

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def motd(self) -> str:
        return self.scenario.motd

    @property
    def home_directory(self) -> str:
        return self.scenario.starting_dir

    @property
    def username(self) -> str:
        return self.scenario.username

    @property
    def hostname(self) -> str:
        return self.scenario.hostname

    def set_cwd(self, path: str) -> None:
        """Mutate session's working directory.

        Precondition: path must be absolute, normalized, and verified to exist
        as a directory by the caller (typically the ``cd`` command).
        """
        self.current_directory = path

    def get_status(self) -> dict:
        """Return aggregated session progress state."""
        scenario_solved = self.tasks_total > 0 and self.tasks_completed >= self.tasks_total

        return {
            "tasks_total": self.tasks_total,
            "tasks_completed": self.tasks_completed,
            "scenario_solved": scenario_solved,
        }
