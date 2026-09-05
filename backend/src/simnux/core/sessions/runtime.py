"""Application-level session model for SIMNUX.

``SNXSession`` is the client/backend connection and the shell router: it
owns the session token and the set of ``SNXShell`` instances attached to it.
It deliberately carries NO scenario-bound interaction state (no scenario, no
current user, no cwd, no history) — that state belongs to ``SNXShell``.
"""

from dataclasses import dataclass
from dataclasses import field

from simnux.core.shell.runtime import SNXShell


@dataclass
class SNXSession:
    """Application-level SIMNUX session: shell router.

    NOT thread-safe — runs in a single-threaded async context.
    """

    session_id: str
    shells: dict[str, SNXShell] = field(default_factory=dict)

    def add_shell(self, shell: SNXShell) -> None:
        """Attach *shell* to this session, keyed by the shell's identifier.

        Adding a shell whose identifier already exists replaces it
        (last-wins), matching the runtime's session semantics.
        """
        self.shells[shell.identifier] = shell

    def get_shell(self, identifier: str) -> SNXShell | None:
        """Return the shell identified by *identifier*, or ``None``."""
        return self.shells.get(identifier)

    def remove_shell(self, identifier: str) -> None:
        """Detach the shell identified by *identifier* if present."""
        self.shells.pop(identifier, None)

    @property
    def active_shells(self) -> list[SNXShell]:
        """All shells currently attached to this session, in insertion order."""
        return list(self.shells.values())
