"""
Session-bound shell runtime.

Orchestrates command execution, parsing, and session state
for a single interactive environment.
"""

import asyncio
import logging

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.commands.streams import AsyncStreamReader
from simnux.filesystem.vfs import SNXFileSystem
from simnux.init.config import LimitsConfig
from simnux.observability.snapshots import ShellSnapshot
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode
from simnux.sessions.runtime import SNXSession

from .parser import ShellParser
from .prompt import PromptRenderer
from .models import LogicalSegment


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
        limits: LimitsConfig | None = None,
    ) -> None:

        self.session = session

        # Exposed for introspection/debugging purposes
        self.filesystem = filesystem

        self.registry = registry
        self.logger = logger
        self.limits = limits or LimitsConfig()

        self.parser = ShellParser()

        self.dispatcher = CommandDispatcher(
            registry=self.registry,
            limits=self.limits,
        )

        self._lock = asyncio.Lock()

    async def execute(self, raw_input: str) -> CommandResult:
        """Full command lifecycle: (1) parse raw input via shlex,
        (2) validate command exists in registry, (3) dispatch to command's
        ``execute()``, (4) catch and wrap runtime exceptions.

        Returns ``CommandResult`` with structured output, never raises.
        """

        async with self._lock:
            return await self._execute_impl(raw_input)

    async def execute_resume(
        self,
        pending_command: str,
        stdin: AsyncStreamReader,
    ) -> CommandResult:
        """Re-dispatch a suspended command with fresh stdin.

        Used by the REST input bridge to resume a ``read`` (or similar)
        command that previously suspended and marked the session as
        ``awaiting_input``.
        """

        async with self._lock:
            return await self._resume_impl(pending_command, stdin)

    def _has_logical_operators(self, raw_input: str) -> bool:
        """Check if input contains && or || operators."""
        # Simple check - presence of && or ||
        return '&&' in raw_input or '||' in raw_input

    async def _execute_impl(self, raw_input: str) -> CommandResult:

        self.logger.info(f"[{self.session.session_id}] Executing: {raw_input}")

        self.session.add_history(raw_input)

        # Check for logical operators
        if self._has_logical_operators(raw_input):
            return await self._execute_logical(raw_input)

        # Fall back to regular parsing
        parsed = self.parser.parse(raw_input)

        if not parsed.segments:
            return CommandResult()

        for seg in parsed.segments:
            if not seg.command:
                continue
            if not self.registry.exists(seg.command) and "/" not in seg.command and not seg.command.startswith("~"):
                self.logger.warning(f"[{self.session.session_id}] Unknown command: {seg.command}")
                return CommandResult(
                    stderr=[f"{seg.command}: command not found"],
                    exit_code=ExitCode.ERROR,
                )

        try:
            ctx = CommandContext(
                session=self.session,
                filesystem=self.filesystem,
                dispatcher=self.dispatcher,
            )

            if len(parsed.segments) == 1:
                result = await self.dispatcher.dispatch(
                    parsed.command,
                    parsed.args,
                    ctx,
                    stdout_redirect=parsed.stdout_redirect,
                    stdout_append=parsed.stdout_append,
                )
            else:
                pipeline_segments = [
                    (seg.command, seg.args, seg.stdout_redirect, seg.stdout_append)
                    for seg in parsed.segments
                ]
                result = await self.dispatcher.dispatch_pipeline(
                    pipeline_segments,
                    ctx,
                )

            self.logger.info(f"[{self.session.session_id}] Exit code: {result.exit_code}")

            return result

        except Exception:
            self.logger.exception(f"[{self.session.session_id}] Execution error: {raw_input}")

            return CommandResult(
                stderr=["Internal runtime error"],
                exit_code=ExitCode.ERROR,
            )

    async def _execute_logical(self, raw_input: str) -> CommandResult:
        """Execute a command line with logical operators (&& and ||).

        Implements short-circuit evaluation:
        - AND (&&): execute next segment only if previous succeeded
        - OR (||): execute next segment only if previous failed
        """
        logical_segments = self.parser.parse_logical(raw_input)

        if not logical_segments:
            return CommandResult()

        # Validate all segments first
        for segment in logical_segments:
            for seg in segment.pipeline.segments:
                if not seg.command:
                    continue
                if not self.registry.exists(seg.command) and "/" not in seg.command and not seg.command.startswith("~"):
                    self.logger.warning(f"[{self.session.session_id}] Unknown command: {seg.command}")
                    return CommandResult(
                        stderr=[f"{seg.command}: command not found"],
                        exit_code=ExitCode.ERROR,
                    )

        try:
            ctx = CommandContext(
                session=self.session,
                filesystem=self.filesystem,
                dispatcher=self.dispatcher,
            )

            last_exit = ExitCode.SUCCESS
            combined_result = CommandResult()

            for idx, logical_seg in enumerate(logical_segments):
                # Apply short-circuit logic
                if idx > 0:
                    if logical_seg.operator.value == "and" and last_exit != ExitCode.SUCCESS:
                        # AND operator: skip if previous failed
                        continue
                    elif logical_seg.operator.value == "or" and last_exit == ExitCode.SUCCESS:
                        # OR operator: skip if previous succeeded
                        continue

                # Execute the pipeline for this segment
                pipeline = logical_seg.pipeline
                if len(pipeline.segments) == 1:
                    result = await self.dispatcher.dispatch(
                        pipeline.command,
                        pipeline.args,
                        ctx,
                        stdout_redirect=pipeline.stdout_redirect,
                        stdout_append=pipeline.stdout_append,
                    )
                else:
                    pipeline_segments = [
                        (seg.command, seg.args, seg.stdout_redirect, seg.stdout_append)
                        for seg in pipeline.segments
                    ]
                    result = await self.dispatcher.dispatch_pipeline(
                        pipeline_segments,
                        ctx,
                    )

                # Update combined result
                combined_result.stdout.extend(result.stdout)
                combined_result.stderr.extend(result.stderr)
                last_exit = result.exit_code

                # Preserve action type from successful commands
                if result.exit_code == ExitCode.SUCCESS and result.action_type != 0:
                    combined_result.action_type = result.action_type
                    combined_result.action_message = result.action_message

            combined_result.exit_code = last_exit
            self.logger.info(f"[{self.session.session_id}] Exit code: {last_exit}")

            return combined_result

        except Exception:
            self.logger.exception(f"[{self.session.session_id}] Execution error: {raw_input}")

            return CommandResult(
                stderr=["Internal runtime error"],
                exit_code=ExitCode.ERROR,
            )

    async def _resume_impl(
        self,
        pending_command: str,
        stdin: AsyncStreamReader,
    ) -> CommandResult:
        """Implementation of execute_resume — dispatches with custom stdin."""

        self.logger.info(
            f"[{self.session.session_id}] Resuming: {pending_command}",
        )

        self.session.add_history(pending_command)

        parsed = self.parser.parse(pending_command)

        if not parsed.segments:
            return CommandResult()

        try:
            ctx = CommandContext(
                session=self.session,
                filesystem=self.filesystem,
                dispatcher=self.dispatcher,
            )

            if len(parsed.segments) == 1:
                result = await self.dispatcher.dispatch(
                    parsed.command,
                    parsed.args,
                    ctx,
                    stdin=stdin,
                )
            else:
                pipeline_segments = [
                    (seg.command, seg.args, seg.stdout_redirect, seg.stdout_append)
                    for seg in parsed.segments
                ]
                result = await self.dispatcher.dispatch_pipeline(
                    pipeline_segments,
                    ctx,
                )

            self.logger.info(
                f"[{self.session.session_id}] Resume exit: {result.exit_code}",
            )

            return result

        except Exception:
            self.logger.exception(
                f"[{self.session.session_id}] Resume error: {pending_command}",
            )
            return CommandResult(
                stderr=["Internal runtime error"],
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
            recent_history=self.session.history[-20:] if self.session.history else [],
            history_count=len(self.session.history),
        )

    def render_prompt(self) -> str:
        """Render the current session prompt."""
        return PromptRenderer.render(self.session)
