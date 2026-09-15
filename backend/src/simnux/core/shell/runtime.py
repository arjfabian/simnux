"""
Shell runtime bound to exactly one scenario.

Owns all mutable interaction state for its scenario (current user, cwd,
history, environment, pending input/progress) and orchestrates command
execution: parse -> validate -> dispatch -> return.
"""

import asyncio
import logging

from simnux.core.commands.dispatcher import CommandDispatcher
from simnux.core.commands.models import CommandContext
from simnux.core.commands.registry import CommandRegistry
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.core.runtime.config import LimitsConfig
from simnux.core.runtime.models import CommandResult
from simnux.core.runtime.models import ExitCode
from simnux.core.runtime.observability import ShellSnapshot
from simnux.core.scenarios.models import SNXScenario
from simnux.core.scripting.history import CommandHistory
from simnux.security.execution.models import ExecutionContext
from simnux.security.users.models import SNXUser

from .parser import ShellParser
from .prompt import PromptRenderer


class SNXShell:
    """
    Stateful shell runtime bound to a single scenario.

    Each shell owns exactly one scenario reference and its own interaction
    state (current execution context, cwd, history, environment, pending
    input). The shell is the source of truth commands read
    scenario-interaction state from; it does not reference the
    application-level session.
    """

    def __init__(
        self,
        *,
        scenario: SNXScenario,
        execution_context: ExecutionContext,
        current_directory: str,
        filesystem: SNXFileSystem,
        registry: CommandRegistry,
        logger: logging.Logger,
        limits: LimitsConfig | None = None,
        tasks_total: int = 0,
        tasks_completed: int = 0,
        metadata: dict | None = None,
        environment: dict[str, str] | None = None,
        history: list[str] | None = None,
        identifier: str | None = None,
    ) -> None:
        # Interaction state owned by this shell.
        self.identifier = identifier or scenario.name
        self.scenario = scenario
        self.execution_context = execution_context
        self.current_directory = current_directory
        self.tasks_total = tasks_total
        self.tasks_completed = tasks_completed
        self.metadata: dict = metadata if metadata is not None else {}
        self.environment: dict[str, str] = environment if environment is not None else {}
        self.history: list[str] = history if history is not None else []

        self.awaiting_input = False
        self.pending_var_name: str | None = None
        self.pending_command: str | None = None
        self.pending_state: object | None = None

        # Execution machinery
        self.filesystem = filesystem
        self.registry = registry
        self.logger = logger
        self.limits = limits or LimitsConfig()

        self.parser = ShellParser()

        self.dispatcher = CommandDispatcher(
            registry=self.registry,
            limits=self.limits,
        )

        self.history_expander = CommandHistory(self.history)

        self._lock = asyncio.Lock()

    # ── Scenario-derived passthroughs ────────────────────────────────────

    @property
    def user(self) -> SNXUser:
        """The effective identity of the current execution context (display
        convenience). Authorization must go through ``execution_context``.
        """
        return self.execution_context.credentials.effective_user

    @property
    def motd(self) -> str:
        node = self.scenario.filesystem.get("/etc/motd")
        return node.content if node else ""

    @property
    def home_directory(self) -> str:
        return self.scenario.starting_dir

    @property
    def hostname(self) -> str:
        return self.scenario.hostname

    # ── Interaction-state helpers ────────────────────────────────────────

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
        """Return aggregated scenario progress state."""
        scenario_solved = self.tasks_total > 0 and self.tasks_completed >= self.tasks_total

        return {
            "tasks_total": self.tasks_total,
            "tasks_completed": self.tasks_completed,
            "scenario_solved": scenario_solved,
        }

    # ── Command lifecycle ────────────────────────────────────────────────

    async def execute(
        self,
        raw_input: str,
        viewport_height: int | None = None,
    ) -> CommandResult:
        """Full command lifecycle: (1) parse raw input via shlex,
        (2) validate command exists in registry, (3) dispatch to command's
        ``execute()``, (4) catch and wrap runtime exceptions.

        ``viewport_height`` carries optional terminal geometry (text lines)
        from the frontend for dynamic full-screen pager viewports.

        Returns ``CommandResult`` with structured output, never raises.
        """

        async with self._lock:
            return await self._execute_impl(raw_input, viewport_height)

    async def execute_resume(
        self,
        pending_command: str,
        stdin: AsyncStreamReader,
        viewport_height: int | None = None,
    ) -> CommandResult:
        """Re-dispatch a suspended command with fresh stdin.

        Used by the REST input bridge to resume a ``read`` (or similar)
        command that previously suspended and marked this shell as
        ``awaiting_input``. ``viewport_height`` refreshes suspended pager
        viewports against current terminal geometry.
        """

        async with self._lock:
            return await self._resume_impl(pending_command, stdin, viewport_height)

    def _has_logical_operators(self, raw_input: str) -> bool:
        """Check if input contains && or || operators."""
        # Simple check - presence of && or ||
        return "&&" in raw_input or "||" in raw_input

    def _build_context(self, viewport_height: int | None = None) -> CommandContext:
        return CommandContext(
            shell=self,
            filesystem=self.filesystem,
            execution_context=self.execution_context,
            dispatcher=self.dispatcher,
            viewport_height=viewport_height,
        )

    async def _execute_impl(
        self,
        raw_input: str,
        viewport_height: int | None = None,
    ) -> CommandResult:
        self.logger.info(f"[{self.identifier}] Executing: {raw_input}")

        # POSIX history expansion before parsing
        try:
            raw_input, was_expanded = self.history_expander.expand(raw_input)
        except ValueError as e:
            return CommandResult(
                stderr=[str(e)],
                exit_code=ExitCode.ERROR,
            )

        self.add_history(raw_input)

        # Check for logical operators
        if self._has_logical_operators(raw_input):
            result = await self._execute_logical(raw_input, viewport_height)
        else:
            # Fall back to regular parsing
            parsed = self.parser.parse(raw_input)

            if not parsed.segments:
                return CommandResult()

            for seg in parsed.segments:
                if not seg.command:
                    continue
                if (
                    not self.registry.exists(seg.command)
                    and "/" not in seg.command
                    and not seg.command.startswith("~")
                ):
                    self.logger.warning(f"[{self.identifier}] Unknown command: {seg.command}")
                    return CommandResult(
                        stderr=[f"{seg.command}: command not found"],
                        exit_code=ExitCode.ERROR,
                    )

            try:
                ctx = self._build_context(viewport_height)

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

            except Exception:
                self.logger.exception(f"[{self.identifier}] Execution error: {raw_input}")

                return CommandResult(
                    stderr=["Internal runtime error"],
                    exit_code=ExitCode.ERROR,
                )

        # Echo expanded command to stdout (POSIX behavior)
        if was_expanded:
            result.stdout.insert(0, raw_input)

        self.logger.info(f"[{self.identifier}] Exit code: {result.exit_code}")

        return result

    async def _execute_logical(
        self,
        raw_input: str,
        viewport_height: int | None = None,
    ) -> CommandResult:
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
                if (
                    not self.registry.exists(seg.command)
                    and "/" not in seg.command
                    and not seg.command.startswith("~")
                ):
                    self.logger.warning(f"[{self.identifier}] Unknown command: {seg.command}")
                    return CommandResult(
                        stderr=[f"{seg.command}: command not found"],
                        exit_code=ExitCode.ERROR,
                    )

        try:
            ctx = self._build_context(viewport_height)

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
            self.logger.info(f"[{self.identifier}] Exit code: {last_exit}")

            return combined_result

        except Exception:
            self.logger.exception(f"[{self.identifier}] Execution error: {raw_input}")

            return CommandResult(
                stderr=["Internal runtime error"],
                exit_code=ExitCode.ERROR,
            )

    async def _resume_impl(
        self,
        pending_command: str,
        stdin: AsyncStreamReader,
        viewport_height: int | None = None,
    ) -> CommandResult:
        """Implementation of execute_resume — dispatches with custom stdin."""

        self.logger.info(
            f"[{self.identifier}] Resuming: {pending_command}",
        )

        # Suspended-state resumes (e.g. full-screen pager keystrokes) are
        # interactive turns, not new user commands — do not record history.
        if self.pending_state is None:
            self.add_history(pending_command)

        parsed = self.parser.parse(pending_command)

        if not parsed.segments:
            return CommandResult()

        try:
            ctx = self._build_context(viewport_height)

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
                f"[{self.identifier}] Resume exit: {result.exit_code}",
            )

            return result

        except Exception:
            self.logger.exception(
                f"[{self.identifier}] Resume error: {pending_command}",
            )
            return CommandResult(
                stderr=["Internal runtime error"],
                exit_code=ExitCode.ERROR,
            )

    # ── Introspection ─────────────────────────────────────────────────────

    def get_snapshot(self, session_id: str) -> ShellSnapshot:
        """Return shell state snapshot for debugging/inspection."""

        filesystem_paths = self.filesystem.list_paths()

        return ShellSnapshot(
            session_id=session_id,
            scenario_name=self.scenario.name,
            loaded_commands=self.registry.list_commands(),
            filesystem=filesystem_paths,
            filesystem_nodes=len(filesystem_paths),
            current_path=self.current_directory,
            recent_history=self.history[-20:] if self.history else [],
            history_count=len(self.history),
        )

    def render_prompt(self) -> str:
        """Render the current shell prompt."""
        return PromptRenderer.render(self)


_HISTORY_CAPACITY = 1000
