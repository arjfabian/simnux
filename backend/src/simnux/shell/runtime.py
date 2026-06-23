"""
Session-bound shell runtime.

Orchestrates command execution, parsing, and session state
for a single interactive environment.
"""

import logging

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.registry import CommandRegistry
from simnux.filesystem.vfs import SNXFileSystem
from simnux.observability.snapshots import ShellSnapshot
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode
from simnux.sessions.runtime import SNXSession

from .parser import ShellParser
from .prompt import PromptRenderer


class SNXShell:
    """
    Stateful shell runtime bound to a single session.

    Orchestrates the command lifecycle: parse -> validate -> dispatch -> return.
    Each shell owns one session, one filesystem instance, one command registry.
    This is the primary public API for the command execution pipeline.
    """

    def __init__(
        self,
        session: SNXSession,
        filesystem: SNXFileSystem,
        registry: CommandRegistry,
        logger: logging.Logger,
    ) -> None:

        self.session = session

        # Exposed for introspection/debugging purposes
        self.filesystem = filesystem

        self.registry = registry
        self.logger = logger

        self.parser = ShellParser()

        self.dispatcher = CommandDispatcher(registry=self.registry)

    def execute(self, raw_input: str) -> CommandResult:
        """Full command lifecycle: (1) parse raw input via shlex,
        (2) validate command exists in registry, (3) dispatch to command's
        ``execute()``, (4) catch and wrap runtime exceptions.

        Returns ``CommandResult`` with structured output, never raises.
        """

        self.logger.info(f"[{self.session.session_id}] Executing: {raw_input}")

        parsed = self.parser.parse(raw_input)

        if not parsed.command:
            return CommandResult()

        if not self.registry.exists(parsed.command):
            self.logger.warning(f"[{self.session.session_id}] Unknown command: {parsed.command}")

            return CommandResult(
                stderr=f"{parsed.command}: command not found",
                exit_code=ExitCode.ERROR,
            )

        try:
            result = self.dispatcher.dispatch(
                parsed.command,
                parsed.args,
            )

            self.logger.info(f"[{self.session.session_id}] Exit code: {result.exit_code}")

            return result

        except Exception:
            self.logger.exception(f"[{self.session.session_id}] Execution error: {parsed.command}")

            return CommandResult(
                stderr="Internal runtime error",
                exit_code=ExitCode.ERROR,
            )

    def get_snapshot(self) -> ShellSnapshot:
        """Return shell state snapshot for debugging/inspection."""

        filesystem_paths = self.filesystem.list_paths()

        return ShellSnapshot(
            session_id=self.session.session_id,
            scenario_name=self.session.scenario.name,
            loaded_commands=self.registry.list_commands(),
            filesystem=filesystem_paths,
            filesystem_nodes=len(filesystem_paths),
            current_path=self.session.current_directory,
        )

    def render_prompt(self) -> str:
        """Render the current session prompt."""
        return PromptRenderer.render(self.session)
