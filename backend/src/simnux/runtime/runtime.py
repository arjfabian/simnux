"""Session runtime orchestration for SIMNUX.

This module owns the lifecycle of active shells and wires together
filesystem, command registry, and session state into a single runtime.
"""

import logging

from simnux.commands.loader import CommandLoader
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.filesystem.vfs import SNXFileSystem
from simnux.init.config import LimitsConfig
from simnux.init.config import RuntimeConfig
from simnux.observability.snapshots import RuntimeSnapshot
from simnux.scenarios.loader import ScenarioLoader
from simnux.sessions.runtime import SNXSession
from simnux.shell.runtime import SNXShell


class SNXRuntime:
    """Owns active sessions and orchestrates runtime components.

    Wires together filesystem, command registry, shell runtime, and scenario
    loader for each session. This is the composition root — all per-session
    dependencies flow through ``create_session()``.
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
        self.shells: dict[str, SNXShell] = {}

        self.logger.info("SNXRuntime ready")

    def create_session(
        self,
        scenario_name: str,
        session_id: str,
    ) -> SNXShell:
        """Factory method for a fully-wired shell session.

        Loads scenario YAML, creates the VFS (with scenario filesystem as
        ``base_layer``), registers all commands, and returns a ready-to-execute
        ``SNXShell``. The ``session_id`` must be unique or it will overwrite an
        existing session.
        """

        self.logger.info(f"Creating session {session_id} for scenario '{scenario_name}'")

        scenario = ScenarioLoader.load(scenario_name)

        session = SNXSession(
            session_id=session_id,
            scenario=scenario,
            current_directory=scenario.starting_dir,
        )

        filesystem = SNXFileSystem(
            base_layer=scenario.filesystem,
            logger=self.logger,
            vfs_limits=self.limits.vfs,
        )

        registry = CommandRegistry()

        command_context = CommandContext(
            session=session,
            filesystem=filesystem,
        )

        loader = CommandLoader(
            registry=registry,
            context=command_context,
            logger=self.logger,
        )

        loader.load_all()

        shell = SNXShell(
            session=session,
            filesystem=filesystem,
            registry=registry,
            logger=self.logger,
            limits=self.limits,
        )

        self.shells[session_id] = shell

        self.logger.info(f"Session {session_id} initialized")

        return shell

    def get_session(self, session_id: str) -> SNXShell | None:
        """Return a session shell by ID."""
        return self.shells.get(session_id)

    def exists(self, session_id: str) -> bool:
        """Check whether a session exists."""
        return session_id in self.shells

    def destroy_session(self, session_id: str) -> bool:
        """Remove an active session from the runtime.

        Returns ``True`` if the session existed and was removed,
        ``False`` if the session_id was not found.
        """
        if session_id in self.shells:
            del self.shells[session_id]
            self.logger.info(f"Session {session_id} destroyed")
            return True
        return False

    def get_snapshot(self) -> RuntimeSnapshot:
        """Return runtime snapshot for observability."""
        active_sessions = [shell.get_snapshot() for shell in self.shells.values()]

        return RuntimeSnapshot(
            active_sessions=active_sessions,
            total_sessions=len(self.shells),
        )
