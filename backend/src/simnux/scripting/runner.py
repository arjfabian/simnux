"""Script resolution and line-by-line execution for the VFS layer."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING

from simnux.commands.argument_parser import parse_arguments
from simnux.commands.models import CommandContext
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.commands.streams import FileStreamWriter
from simnux.init.config import LimitsConfig
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode


if TYPE_CHECKING:
    from simnux.commands.registry import CommandRegistry


logger = logging.getLogger("simnux.scripting")


_VAR_RE = re.compile(r"\$\{(\w+)\}|\$([a-zA-Z_]\w*)")
_ARITH_RE = re.compile(r"\$\(\((.+?)\)\)")
_ASSIGN_RE = re.compile(r"^(\w+)=(.*)$")

# Shell keywords that should be silently skipped in the dispatch loop
# rather than treated as unknown commands.
_KEYWORDS = frozenset({"done", "fi", "then", "else", "elif", "do", "in"})


class ScriptRunner:
    """Reads VFS script files and executes them line-by-line.

    Responsible for:
    - Resolving a command name to a VFS script file path.
    - Stripping comments and blank lines from script content.
    - Dispatching each line through the command registry.
    - Supporting ``while`` / ``for`` loop constructs with iteration and
      time bounds from ``LimitsConfig``.
    """

    def __init__(
        self,
        registry: CommandRegistry,
        limits: LimitsConfig | None = None,
    ) -> None:
        self.registry = registry
        self.limits = limits or LimitsConfig()

    async def resolve(
        self,
        cmd_name: str,
        ctx: CommandContext,
    ) -> tuple[str | None, str | None]:
        """Try to resolve *cmd_name* as a VFS path and return (content, error).

        Returns ``(content, None)`` on success or ``(None, error_message)``
        on failure.
        """
        abs_path = ctx.filesystem.resolve_path(
            current_directory=ctx.session.current_directory,
            target_path=cmd_name,
            home_directory=ctx.session.home_directory,
        )
        result = ctx.filesystem.read(abs_path)
        if result.exit_code != ExitCode.SUCCESS:
            return None, f"{cmd_name}: {result.message}"
        return (result.node.content or ""), None

    # ── Main execution entry point ────────────────────────────────────

    async def execute(
        self,
        content: str,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
        script_args: list[str] | None = None,
    ) -> CommandResult:
        """Execute *content* as a script line-by-line.

        Supports ``while`` / ``for`` loop constructs bounded by
        ``max_loop_iterations`` and ``max_execution_time_seconds``.
        """
        from simnux.shell.parser import ShellParser

        parser = ShellParser()
        lines = content.splitlines()
        num_lines = len(lines)

        max_lines = self.limits.script.max_lines
        if max_lines > 0 and num_lines > max_lines:
            await stderr.write(f"script: exceeded maximum line limit ({max_lines})\n")
            return CommandResult(exit_code=ExitCode.ERROR)

        last_exit = ExitCode.SUCCESS
        deadline = time.monotonic() + self.limits.script.max_execution_time_seconds
        line_idx = 0

        while line_idx < num_lines:
            # ── time guard ──
            if self.limits.script.max_execution_time_seconds > 0 and time.monotonic() >= deadline:
                await stderr.write("script: exceeded maximum execution time\n")
                return CommandResult(exit_code=ExitCode.ERROR)

            raw_line = lines[line_idx]
            stripped = raw_line.strip()
            line_idx += 1

            if not stripped or stripped.startswith("#"):
                continue

            # ── shell keyword (done, fi, etc.) — skip silently ──
            if stripped in _KEYWORDS:
                continue

            # ── variable assignment ──
            if self._try_assignment(stripped, ctx.session.environment):
                continue

            # ── while loop ──
            if stripped.startswith("while "):
                try:
                    result = await self._execute_while(
                        stripped,
                        lines,
                        line_idx,
                        ctx,
                        stdin,
                        stdout,
                        stderr,
                        deadline,
                    )
                    last_exit = result.exit_code
                    line_idx = result._next_line_idx  # type: ignore[attr-defined]
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            # ── for loop ──
            if stripped.startswith("for "):
                try:
                    result = await self._execute_for(
                        stripped,
                        lines,
                        line_idx,
                        ctx,
                        stdin,
                        stdout,
                        stderr,
                        deadline,
                    )
                    last_exit = result.exit_code
                    line_idx = result._next_line_idx  # type: ignore[attr-defined]
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            # ── logical operators ──
            if "&&" in stripped or "||" in stripped:
                try:
                    expanded = self._expand_vars(stripped, ctx.session.environment)
                    result = await self._execute_logical_line(
                        expanded,
                        ctx,
                        stdin,
                        stdout,
                        stderr,
                    )
                    last_exit = result.exit_code
                except ValueError as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.INVALID_ARGUMENT
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            # ── regular command ──
            expanded = self._expand_vars(stripped, ctx.session.environment)
            try:
                parsed = parser.parse(expanded)
            except ValueError as e:
                await stderr.write(f"script: {e}\n")
                last_exit = ExitCode.INVALID_ARGUMENT
                continue

            if not parsed.segments:
                continue

            if len(parsed.segments) > 1:
                pipe_segments = [
                    (s.command, s.args, s.stdout_redirect, s.stdout_append) for s in parsed.segments
                ]
                try:
                    result = await self._dispatch_pipeline(pipe_segments, ctx)
                    await stdout.writelines(result.stdout)
                    await stderr.writelines(result.stderr)
                    last_exit = result.exit_code
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            seg = parsed.segments[0]
            cmd_name = seg.command
            cmd_args = self._expand_args(seg.args, ctx.session.environment)

            command = self.registry.get(cmd_name)
            if command is None:
                await stderr.write(f"{cmd_name}: command not found\n")
                last_exit = ExitCode.ERROR
                continue

            command.args = cmd_args
            command._invoked_name = cmd_name
            if command.parameters:
                normalized = command.normalize_args(cmd_args)
                parsed_args, errs = parse_arguments(
                    normalized,
                    command.parameters,
                    cmd_name,
                )
                if errs:
                    for err in errs:
                        await stderr.write(f"{err}\n")
                    last_exit = ExitCode.INVALID_ARGUMENT
                    continue
                command.parsed_args = parsed_args

            cmd_stdout = stdout
            if seg.stdout_redirect:
                resolved = ctx.filesystem.resolve_path(
                    current_directory=ctx.session.current_directory,
                    target_path=seg.stdout_redirect,
                    home_directory=ctx.session.home_directory,
                )
                cmd_stdout = FileStreamWriter(
                    ctx.filesystem,
                    resolved,
                    append=seg.stdout_append,
                )

            try:
                exit_code = await command.execute(ctx, stdin, cmd_stdout, stderr)
            except Exception as e:
                await stderr.write(f"{cmd_name}: {e}\n")
                exit_code = ExitCode.ERROR
            last_exit = exit_code

            if seg.stdout_redirect:
                cmd_stdout.close()
                if isinstance(cmd_stdout, FileStreamWriter) and cmd_stdout.last_error:
                    await stderr.write(f"{cmd_stdout.last_error}\n")
                    last_exit = ExitCode.ERROR

        return CommandResult(exit_code=last_exit)

    # ── while loop ────────────────────────────────────────────────────

    async def _execute_while(
        self,
        header: str,
        lines: list[str],
        body_start: int,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
        deadline: float,
    ) -> CommandResult:
        """Execute a ``while COND; do BODY; done`` block.

        Returns a CommandResult with ``_next_line_idx`` set to the line
        after ``done``.
        """
        condition = self._extract_while_condition(header)
        body, body_end = self._collect_do_done(body_start, lines)

        max_iter = self.limits.script.max_loop_iterations
        iteration = 0
        last_exit = ExitCode.SUCCESS

        while True:
            if max_iter > 0 and iteration >= max_iter:
                await stderr.write(f"script: exceeded maximum loop iterations ({max_iter})\n")
                r = CommandResult(exit_code=ExitCode.ERROR)
                r._next_line_idx = body_end  # type: ignore[attr-defined]
                return r

            if self.limits.script.max_execution_time_seconds > 0 and time.monotonic() >= deadline:
                await stderr.write("script: exceeded maximum execution time\n")
                r = CommandResult(exit_code=ExitCode.ERROR)
                r._next_line_idx = body_end  # type: ignore[attr-defined]
                return r

            cond_true = await self._eval_condition(condition, ctx, stdin, stdout, stderr)
            if not cond_true:
                break

            last_exit = await self._execute_body(
                body,
                ctx,
                stdin,
                stdout,
                stderr,
                deadline,
            )
            iteration += 1  # noqa: SIM113

        r = CommandResult(exit_code=last_exit)
        r._next_line_idx = body_end  # type: ignore[attr-defined]
        return r

    # ── for loop ──────────────────────────────────────────────────────

    async def _execute_for(
        self,
        header: str,
        lines: list[str],
        body_start: int,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
        deadline: float,
    ) -> CommandResult:
        """Execute a ``for VAR in LIST; do BODY; done`` block."""
        var_name, word_list = self._parse_for_header(header)
        body, body_end = self._collect_do_done(body_start, lines)

        max_iter = self.limits.script.max_loop_iterations
        iteration = 0
        last_exit = ExitCode.SUCCESS

        for word in word_list:
            if max_iter > 0 and iteration >= max_iter:
                await stderr.write(f"script: exceeded maximum loop iterations ({max_iter})\n")
                r = CommandResult(exit_code=ExitCode.ERROR)
                r._next_line_idx = body_end  # type: ignore[attr-defined]
                return r

            if self.limits.script.max_execution_time_seconds > 0 and time.monotonic() >= deadline:
                await stderr.write("script: exceeded maximum execution time\n")
                r = CommandResult(exit_code=ExitCode.ERROR)
                r._next_line_idx = body_end  # type: ignore[attr-defined]
                return r

            ctx.session.environment[var_name] = word
            last_exit = await self._execute_body(
                body,
                ctx,
                stdin,
                stdout,
                stderr,
                deadline,
            )
            iteration += 1  # noqa: SIM113

        r = CommandResult(exit_code=last_exit)
        r._next_line_idx = body_end  # type: ignore[attr-defined]
        return r

    # ── helpers ───────────────────────────────────────────────────────

    def _extract_while_condition(self, header: str) -> str:
        """Extract the condition from ``while COND; do ...`` or ``while COND``."""
        rest = header[len("while ") :]
        # Strip trailing "do" if present on same line
        if "; do" in rest:
            return rest.split("; do")[0].strip()
        if ";do" in rest:
            return rest.split(";do")[0].strip()
        return rest.strip()

    def _parse_for_header(self, header: str) -> tuple[str, list[str]]:
        """Parse ``for VAR in WORD1 WORD2 ...`` and return (var_name, words)."""
        rest = header[len("for ") :]
        # Strip trailing "do" if present on same line
        if "; do" in rest:
            rest = rest.split("; do")[0].strip()
        elif ";do" in rest:
            rest = rest.split(";do")[0].strip()

        tokens = rest.split()
        if len(tokens) < 2 or tokens[1] != "in":
            # ``for VAR`` without ``in`` — treat as empty list
            return tokens[0] if tokens else "i", []

        var_name = tokens[0]
        word_list = tokens[2:]  # skip VAR and "in"
        return var_name, word_list

    def _collect_do_done(
        self,
        start_idx: int,
        lines: list[str],
    ) -> tuple[list[str], int]:
        """Collect the body of a ``do ... done`` block.

        Returns ``(body_lines, next_line_idx)`` where *next_line_idx* is
        the index of the line after ``done``.
        """
        body: list[str] = []
        depth = 0
        idx = start_idx

        while idx < len(lines):
            stripped = lines[idx].strip()

            # Handle nested do/done
            if stripped == "do":
                depth += 1
                idx += 1
                continue

            if stripped == "done":
                if depth == 0:
                    return body, idx + 1
                depth -= 1
                idx += 1
                continue

            # Count ``for/while ... do`` on one line as opening a do block
            if (
                depth >= 0
                and (stripped.startswith("for ") or stripped.startswith("while "))
                and re.search(r";\s*do\s*$", stripped)
            ):
                depth += 1
                body.append(lines[idx])
                idx += 1
                continue

            if depth > 0 or (depth == 0 and stripped not in ("do", "done")):
                body.append(lines[idx])

            idx += 1

        # Unclosed block — execute whatever we collected
        return body, idx

    # ── Variable expansion & assignment ──────────────────────────────

    def _expand_vars(self, text: str, environment: dict[str, str]) -> str:
        """Replace ``$var`` / ``${var}`` with values from *environment*.

        Unset variables expand to the empty string.  Arithmetic expansions
        (``$((expr))``) are evaluated by ``_eval_arithmetic``.
        """
        text = _ARITH_RE.sub(
            lambda m: str(self._eval_arithmetic(m.group(1), environment)),
            text,
        )

        def _replace(m: re.Match) -> str:
            name = m.group(1) or m.group(2)
            return environment.get(name, "")

        return _VAR_RE.sub(_replace, text)

    def _expand_args(
        self,
        args: list[str],
        environment: dict[str, str],
    ) -> list[str]:
        """Expand variables in a list of command arguments."""
        return [self._expand_vars(a, environment) for a in args]

    @staticmethod
    def _eval_arithmetic(expr: str, environment: dict[str, str]) -> int:
        """Evaluate a simple arithmetic expression.

        Supports: integers, ``$var`` / ``var`` references, ``+``, ``-``,
        ``*``, ``/``, ``%``, ``(``)``.  Division by zero returns 0.
        """

        # First expand $var / ${var} references
        def _replace_var(m: re.Match) -> str:
            name = m.group(1) or m.group(2)
            return environment.get(name, "0")

        expr = _VAR_RE.sub(_replace_var, expr)

        # Then expand bare identifiers (variables without $ prefix)
        def _replace_bare(m: re.Match) -> str:
            name = m.group(0)
            return environment.get(name, "0")

        expr = re.sub(r"[a-zA-Z_]\w*", _replace_bare, expr)

        allowed = set("0123456789+-*/%() ")
        if not all(c in allowed for c in expr):
            return 0

        try:
            result = eval(expr, {"__builtins__": {}})  # noqa: S307
            return int(result)
        except (ZeroDivisionError, SyntaxError, NameError, TypeError, ValueError):
            return 0

    @staticmethod
    def _try_assignment(
        line: str,
        environment: dict[str, str],
    ) -> bool:
        """Handle ``VAR=VALUE`` assignment.  Returns True if handled."""
        m = _ASSIGN_RE.match(line)
        if not m:
            return False
        var_name, raw_value = m.group(1), m.group(2)

        # Expand $((...)) arithmetic in the value
        def _arith_replace(am: re.Match) -> str:
            return str(ScriptRunner._eval_arithmetic(am.group(1), environment))

        value = _ARITH_RE.sub(_arith_replace, raw_value)

        # Expand $var references in the value
        def _var_replace(vm: re.Match) -> str:
            name = vm.group(1) or vm.group(2)
            return environment.get(name, "")

        value = _VAR_RE.sub(_var_replace, value)

        environment[var_name] = value
        return True

    async def _eval_condition(
        self,
        condition: str,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> bool:
        """Evaluate a while-condition and return True if it succeeds."""
        from simnux.shell.parser import ShellParser

        parser = ShellParser()

        # Expand variables and arithmetic in the condition string
        condition = self._expand_vars(condition, ctx.session.environment)

        # Handle simple builtins
        if condition == "true":
            return True
        if condition == "false":
            return False

        # Handle logical operators in condition
        if "&&" in condition or "||" in condition:
            try:
                result = await self._execute_logical_line(
                    condition,
                    ctx,
                    stdin,
                    stdout,
                    stderr,
                )
                return result.exit_code == ExitCode.SUCCESS
            except Exception:
                return False

        # Parse as a pipeline
        try:
            parsed = parser.parse(condition)
        except ValueError:
            return False

        if not parsed.segments:
            return False

        # Single command — dispatch directly
        if len(parsed.segments) == 1:
            seg = parsed.segments[0]
            command = self.registry.get(seg.command)
            if command is None:
                return False

            seg_args = self._expand_args(seg.args, ctx.session.environment)
            command.args = seg_args
            command._invoked_name = seg.command
            if command.parameters:
                normalized = command.normalize_args(seg_args)
                parsed_args, errs = parse_arguments(
                    normalized,
                    command.parameters,
                    seg.command,
                )
                if errs:
                    return False
                command.parsed_args = parsed_args

            err_q: asyncio.Queue = asyncio.Queue()
            err_writer = _QueueWriter(err_q)
            try:
                exit_code = await command.execute(ctx, stdin, stdout, err_writer)
            except Exception:
                return False
            return exit_code == ExitCode.SUCCESS

        # Pipeline
        pipe_segments = [
            (s.command, s.args, s.stdout_redirect, s.stdout_append) for s in parsed.segments
        ]
        result = await self._dispatch_pipeline(pipe_segments, ctx)
        return result.exit_code == ExitCode.SUCCESS

    async def _execute_body(
        self,
        body: list[str],
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
        deadline: float,
    ) -> ExitCode:
        """Execute the collected body lines, returning the last exit code."""
        from simnux.shell.parser import ShellParser

        parser = ShellParser()
        last_exit = ExitCode.SUCCESS
        env = ctx.session.environment
        idx = 0

        while idx < len(body):
            if self.limits.script.max_execution_time_seconds > 0 and time.monotonic() >= deadline:
                await stderr.write("script: exceeded maximum execution time\n")
                return ExitCode.ERROR

            raw_line = body[idx]
            stripped = raw_line.strip()
            idx += 1

            if not stripped or stripped.startswith("#"):
                continue

            # Shell keyword (done, fi, etc.) — skip silently
            if stripped in _KEYWORDS:
                continue

            # Variable assignment: VAR=VALUE
            if self._try_assignment(stripped, env):
                continue

            # Nested loops
            if stripped.startswith("while "):
                try:
                    result = await self._execute_while(
                        stripped,
                        body,
                        idx,
                        ctx,
                        stdin,
                        stdout,
                        stderr,
                        deadline,
                    )
                    last_exit = result.exit_code
                    idx = result._next_line_idx  # type: ignore[attr-defined]
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            if stripped.startswith("for "):
                try:
                    result = await self._execute_for(
                        stripped,
                        body,
                        idx,
                        ctx,
                        stdin,
                        stdout,
                        stderr,
                        deadline,
                    )
                    last_exit = result.exit_code
                    idx = result._next_line_idx  # type: ignore[attr-defined]
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            if "&&" in stripped or "||" in stripped:
                try:
                    expanded = self._expand_vars(stripped, env)
                    result = await self._execute_logical_line(
                        expanded,
                        ctx,
                        stdin,
                        stdout,
                        stderr,
                    )
                    last_exit = result.exit_code
                except ValueError as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.INVALID_ARGUMENT
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            # Expand variables in the whole line before parsing
            expanded = self._expand_vars(stripped, env)

            try:
                parsed = parser.parse(expanded)
            except ValueError as e:
                await stderr.write(f"script: {e}\n")
                last_exit = ExitCode.INVALID_ARGUMENT
                continue

            if not parsed.segments:
                continue

            if len(parsed.segments) > 1:
                pipe_segments = [
                    (s.command, s.args, s.stdout_redirect, s.stdout_append) for s in parsed.segments
                ]
                try:
                    result = await self._dispatch_pipeline(pipe_segments, ctx)
                    await stdout.writelines(result.stdout)
                    await stderr.writelines(result.stderr)
                    last_exit = result.exit_code
                except Exception as e:
                    await stderr.write(f"script: {e}\n")
                    last_exit = ExitCode.ERROR
                continue

            seg = parsed.segments[0]
            cmd_name = seg.command
            cmd_args = self._expand_args(seg.args, env)

            command = self.registry.get(cmd_name)
            if command is None:
                await stderr.write(f"{cmd_name}: command not found\n")
                last_exit = ExitCode.ERROR
                continue

            command.args = cmd_args
            command._invoked_name = cmd_name
            if command.parameters:
                normalized = command.normalize_args(cmd_args)
                parsed_args, errs = parse_arguments(
                    normalized,
                    command.parameters,
                    cmd_name,
                )
                if errs:
                    for err in errs:
                        await stderr.write(f"{err}\n")
                    last_exit = ExitCode.INVALID_ARGUMENT
                    continue
                command.parsed_args = parsed_args

            cmd_stdout = stdout
            if seg.stdout_redirect:
                resolved = ctx.filesystem.resolve_path(
                    current_directory=ctx.session.current_directory,
                    target_path=seg.stdout_redirect,
                    home_directory=ctx.session.home_directory,
                )
                cmd_stdout = FileStreamWriter(
                    ctx.filesystem,
                    resolved,
                    append=seg.stdout_append,
                )

            exit_code = await command.execute(ctx, stdin, cmd_stdout, stderr)
            last_exit = exit_code

            if seg.stdout_redirect:
                cmd_stdout.close()
                if isinstance(cmd_stdout, FileStreamWriter) and cmd_stdout.last_error:
                    await stderr.write(f"{cmd_stdout.last_error}\n")
                    last_exit = ExitCode.ERROR

        return last_exit

    # ── logical line execution ────────────────────────────────────────

    async def _execute_logical_line(
        self,
        line: str,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> CommandResult:
        """Execute a single line with logical operators (&& and ||)."""
        from simnux.shell.parser import ShellParser

        parser = ShellParser()
        logical_segments = parser.parse_logical(line)

        if not logical_segments:
            return CommandResult()

        last_exit = ExitCode.SUCCESS

        for idx, logical_seg in enumerate(logical_segments):
            if idx > 0 and (
                logical_seg.operator.value == "and"
                and last_exit != ExitCode.SUCCESS
                or logical_seg.operator.value == "or"
                and last_exit == ExitCode.SUCCESS
            ):
                continue

            pipeline = logical_seg.pipeline
            if len(pipeline.segments) > 1:
                pipe_segments = [
                    (s.command, s.args, s.stdout_redirect, s.stdout_append)
                    for s in pipeline.segments
                ]
                result = await self._dispatch_pipeline(pipe_segments, ctx)
                await stdout.writelines(result.stdout)
                await stderr.writelines(result.stderr)
                last_exit = result.exit_code
            else:
                seg = pipeline.segments[0]
                cmd_name = seg.command
                cmd_args = self._expand_args(seg.args, ctx.session.environment)

                command = self.registry.get(cmd_name)
                if command is None:
                    await stderr.write(f"{cmd_name}: command not found\n")
                    last_exit = ExitCode.ERROR
                    continue

                command.args = cmd_args
                command._invoked_name = cmd_name
                if command.parameters:
                    normalized = command.normalize_args(cmd_args)
                    parsed_args, errs = parse_arguments(
                        normalized,
                        command.parameters,
                        cmd_name,
                    )
                    if errs:
                        for err in errs:
                            await stderr.write(f"{err}\n")
                        last_exit = ExitCode.INVALID_ARGUMENT
                        continue
                    command.parsed_args = parsed_args

            cmd_stdout = stdout
            if seg.stdout_redirect:
                resolved = ctx.filesystem.resolve_path(
                    current_directory=ctx.session.current_directory,
                    target_path=seg.stdout_redirect,
                    home_directory=ctx.session.home_directory,
                )
                cmd_stdout = FileStreamWriter(
                    ctx.filesystem,
                    resolved,
                    append=seg.stdout_append,
                )

            try:
                exit_code = await command.execute(ctx, stdin, cmd_stdout, stderr)
            except Exception as e:
                await stderr.write(f"{cmd_name}: {e}\n")
                exit_code = ExitCode.ERROR
            last_exit = exit_code

            if seg.stdout_redirect:
                cmd_stdout.close()
                if isinstance(cmd_stdout, FileStreamWriter) and cmd_stdout.last_error:
                    await stderr.write(f"{cmd_stdout.last_error}\n")
                    last_exit = ExitCode.ERROR

        return CommandResult(exit_code=last_exit)

    # ── pipeline dispatch ─────────────────────────────────────────────

    async def _dispatch_pipeline(
        self,
        segments: list[tuple[str, list[str], str | None, bool]],
        ctx: CommandContext,
    ) -> CommandResult:
        """Dispatch a pipeline within a script context."""
        from simnux.commands.streams import QueueStreamReader
        from simnux.commands.streams import QueueStreamWriter

        n = len(segments)
        pipe_queues: list[asyncio.Queue] = [asyncio.Queue() for _ in range(n - 1)]
        merged_stderr: list[str] = []
        results: list[ExitCode | None] = [None] * n

        async def run_segment(idx: int) -> None:
            cmd_name, args, redirect, append = segments[idx]
            expanded_args = self._expand_args(args, ctx.session.environment)
            command = self.registry.get(cmd_name)

            err_queue: asyncio.Queue = asyncio.Queue()
            err_writer = QueueStreamWriter(err_queue)

            if idx == 0:
                stdin_queue: asyncio.Queue = asyncio.Queue()
                stdin_queue.put_nowait(None)
                stdin_reader = QueueStreamReader(stdin_queue)
            else:
                stdin_reader = QueueStreamReader(pipe_queues[idx - 1])

            out_queue: asyncio.Queue | None = None
            if idx == n - 1:
                if redirect is not None:
                    resolved = ctx.filesystem.resolve_path(
                        current_directory=ctx.session.current_directory,
                        target_path=redirect,
                        home_directory=ctx.session.home_directory,
                    )
                    out_writer = FileStreamWriter(ctx.filesystem, resolved, append=append)
                else:
                    out_queue = asyncio.Queue()
                    out_writer = QueueStreamWriter(out_queue)
            else:
                out_writer = QueueStreamWriter(pipe_queues[idx])

            if command is None:
                await err_writer.write(f"{cmd_name}: command not found\n")
                out_writer.close()
                err_writer.close()
                merged_stderr.extend(_drain_queue(err_queue))
                results[idx] = ExitCode.ERROR
                return

            command.args = expanded_args
            command._invoked_name = cmd_name
            if command.parameters:
                normalized = command.normalize_args(expanded_args)
                parsed, errs = parse_arguments(
                    normalized,
                    command.parameters,
                    cmd_name,
                )
                if errs:
                    for err in errs:
                        await err_writer.write(f"{err}\n")
                    out_writer.close()
                    err_writer.close()
                    merged_stderr.extend(_drain_queue(err_queue))
                    results[idx] = ExitCode.INVALID_ARGUMENT
                    return
                command.parsed_args = parsed

            try:
                results[idx] = await command.execute(
                    ctx,
                    stdin_reader,
                    out_writer,
                    err_writer,
                )
            finally:
                out_writer.close()
                if isinstance(out_writer, FileStreamWriter) and out_writer.last_error:
                    await err_writer.write(f"{out_writer.last_error}\n")
                    results[idx] = ExitCode.ERROR
                err_writer.close()

            merged_stderr.extend(_drain_queue(err_queue))
            if out_queue is not None:
                pipe_results[idx] = _drain_queue(out_queue)

        pipe_results: dict[int, list[str]] = {}
        await asyncio.gather(*[run_segment(i) for i in range(n)])

        last_stdout = pipe_results.get(n - 1, [])
        last_exit = results[-1] if results[-1] is not None else ExitCode.ERROR

        return CommandResult(
            stdout=last_stdout,
            stderr=merged_stderr,
            exit_code=last_exit,
        )


# ── Internal helpers ─────────────────────────────────────────────────────


def _drain_queue(queue: asyncio.Queue) -> list[str]:
    """Drain all non-None items, splitting each on newlines."""
    lines: list[str] = []
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is not None:
            lines.extend(item.splitlines())
    return lines


class _QueueWriter:
    """Minimal async writer that appends to an ``asyncio.Queue``."""

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue

    async def write(self, data: str) -> None:
        self._queue.put_nowait(data)

    async def writelines(self, lines: list[str]) -> None:
        for line in lines:
            self._queue.put_nowait(line)

    def close(self) -> None:
        pass
