"""Runtime orchestration for SIMNUX.

Owns the lifecycle of app-level sessions (``SNXSession``) and the shells
(``SNXShell``) attached to them, wiring together filesystem, command
registry, and scenario loader. Per task, this is the composition root — all
per-shell dependencies flow through ``create_session()``.
"""

import logging

from simnux.core.commands.loader import CommandLoader
from simnux.core.commands.models import CommandContext
from simnux.core.commands.registry import CommandRegistry
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.core.runtime.config import LimitsConfig
from simnux.core.runtime.config import RuntimeConfig
from simnux.core.runtime.observability import RuntimeSnapshot
from simnux.core.scenarios.identity import IdentityManager
from simnux.core.scenarios.loader import ScenarioLoader
from simnux.core.sessions.runtime import SNXSession
from simnux.core.shell.runtime import SNXShell
from simnux.security.execution.models import ExecutionContext


class SNXRuntime:
    """Owns active sessions and orchestrates runtime components.

    Wires together filesystem, command registry, shell runtime, and scenario
    loader for each shell. One app-level ``SNXSession`` owns zero or more
    ``SNXShell`` instances; ``create_session()`` builds a shell and attaches
    it to the (possibly reused) session for *session_id*.
    """

    def __init__(
        self,
        logger: logging.Logger,
        config: RuntimeConfig,
        limits: LimitsConfig | None = None,
    ) -> None:
        self.logger = logger
        self.config = config
        self.limits = limits or LimitsConfig()
        self.sessions: dict[str, SNXSession] = {}

        self.logger.info("SNXRuntime ready")

    def create_session(
        self,
        scenario_name: str,
        session_id: str,
    ) -> SNXShell:
        """Factory method for a fully-wired shell under a session.

        Loads scenario YAML, creates the VFS (with scenario filesystem as
        ``base_layer``), registers all commands, and returns a ready-to-execute
        ``SNXShell`` attached to the app-level ``SNXSession`` identified by
        *session_id*. Reusing *session_id* attaches another shell to the same
        session; reusing (*session_id*, *scenario_name*) replaces the shell for
        that scenario in the session.
        """

        self.logger.info(f"Creating session {session_id} for scenario '{scenario_name}'")

        scenario = ScenarioLoader.load(scenario_name)

        # The identity manager owns the authoritative identity state; the
        # initial execution membership comes from that state's current view
        # (never from the scenario's declarative users/groups projections).
        manager = IdentityManager(scenario.identity_state)

        initial_user = next(
            (user for user in manager.users() if user.identifier != "root"),
            manager.user_by_identifier("root"),
        )
        if initial_user is None:
            raise KeyError("scenario defines no root user")

        membership = manager.membership_view()
        execution_context = ExecutionContext.for_user(initial_user, membership)

        filesystem = SNXFileSystem(
            base_layer=scenario.filesystem,
            logger=self.logger,
            vfs_limits=self.limits.vfs,
        )

        registry = CommandRegistry()

        shell = SNXShell(
            scenario=scenario,
            execution_context=execution_context,
            current_directory=scenario.starting_dir,
            filesystem=filesystem,
            registry=registry,
            logger=self.logger,
            limits=self.limits,
            identifier=scenario_name,
        )

        command_context = CommandContext(
            shell=shell,
            filesystem=filesystem,
            execution_context=shell.execution_context,
        )

        loader = CommandLoader(
            registry=registry,
            context=command_context,
            logger=self.logger,
        )

        loader.load_all()

        session = self.sessions.get(session_id)
        if session is None:
            session = SNXSession(session_id=session_id)
            self.sessions[session_id] = session

        session.add_shell(shell)

        self.logger.info(
            f"Session {session_id} initialized (scenario '{scenario_name}')",
        )

        return shell

    def get_session(self, session_id: str) -> SNXSession | None:
        """Return an app-level session by ID."""
        return self.sessions.get(session_id)

    def get_shell(self, session_id: str, scenario_name: str) -> SNXShell | None:
        """Return the shell for *scenario_name* within the session, if any."""
        session = self.get_session(session_id)
        if session is None:
            return None
        return session.get_shell(scenario_name)

    def exists(self, session_id: str) -> bool:
        """Check whether a session exists."""
        return session_id in self.sessions

    def destroy_session(self, session_id: str) -> bool:
        """Remove an active session and all its shells from the runtime.

        Returns ``True`` if the session existed and was removed,
        ``False`` if the session_id was not found.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.logger.info(f"Session {session_id} destroyed")
            return True
        return False

    def get_snapshot(self) -> RuntimeSnapshot:
        """Return runtime snapshot for observability."""
        active_sessions = [
            shell.get_snapshot(session_id)
            for session_id, session in self.sessions.items()
            for shell in session.shells.values()
        ]

        return RuntimeSnapshot(
            active_sessions=active_sessions,
            total_sessions=len(self.sessions),
        )
