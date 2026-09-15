import asyncio
import logging

from simnux.core.commands.argument_parser import parse_arguments
from simnux.core.commands.models import CommandContext
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.commands.streams import FileStreamWriter
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.commands.streams import QueueStreamWriter
from simnux.core.runtime.config import LimitsConfig
from simnux.core.runtime.models import CommandResult
from simnux.core.runtime.models import ExitCode
from simnux.core.runtime.models import TerminalAction
from simnux.core.scripting.runner import ScriptRunner


logger = logging.getLogger("simnux.commands")


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


class CommandDispatcher:
    """Resolves commands, wires I/O streams, delegates execution."""

    def __init__(self, registry, limits: LimitsConfig | None = None):
        self.registry = registry
        self._script_runner = ScriptRunner(registry, limits=limits)

    async def _resolve_script(
        self,
        cmd_name: str,
        ctx: CommandContext,
    ) -> tuple[str | None, str | None]:
        """Delegate to ScriptRunner for VFS path resolution."""
        return await self._script_runner.resolve(cmd_name, ctx)

    async def execute_script(
        self,
        content: str,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
        script_args: list[str] | None = None,
    ) -> CommandResult:
        """Delegate to ScriptRunner for line-by-line script execution."""
        return await self._script_runner.execute(
            content,
            ctx,
            stdin,
            stdout,
            stderr,
            script_args,
        )

    async def dispatch(
        self,
        cmd_name: str,
        args: list[str],
        ctx: CommandContext,
        stdin: AsyncStreamReader | None = None,
        stdout: AsyncStreamWriter | None = None,
        stderr: AsyncStreamWriter | None = None,
        stdout_redirect: str | None = None,
        stdout_append: bool = False,
    ) -> CommandResult:
        command = self.registry.get(cmd_name)

        if stdin is not None:
            stdin_reader = stdin
        else:
            stdin_queue: asyncio.Queue = asyncio.Queue()
            stdin_queue.put_nowait(None)
            stdin_reader = QueueStreamReader(stdin_queue)

        out_queue: asyncio.Queue = asyncio.Queue() if not stdout_redirect else None
        err_queue: asyncio.Queue = asyncio.Queue()

        if stdout_redirect is not None:
            resolved = ctx.filesystem.resolve_path(
                current_directory=ctx.shell.current_directory,
                target_path=stdout_redirect,
                home_directory=ctx.shell.home_directory,
            )
            out_writer = FileStreamWriter(
                ctx.filesystem,
                resolved,
                append=stdout_append,
                execution=ctx.execution_context,
            )
        else:
            out_writer = stdout or QueueStreamWriter(out_queue)

        err_writer = stderr or QueueStreamWriter(err_queue)

        if command is None:
            content, err = await self._resolve_script(cmd_name, ctx)
            if err:
                out_writer.close()
                err_writer.close()
                return CommandResult(stderr=[err], exit_code=ExitCode.ERROR)

            script_result = await self.execute_script(
                content,
                ctx,
                stdin_reader,
                out_writer,
                err_writer,
                args,
            )
            out_writer.close()
            err_writer.close()
            stdout_lines = _drain_queue(out_queue) if out_queue is not None else []
            stderr_lines = _drain_queue(err_queue)
            return CommandResult(
                stdout=stdout_lines,
                stderr=stderr_lines,
                exit_code=script_result.exit_code,
            )

        command.args = args
        command._invoked_name = cmd_name

        if command.parameters:
            normalized = command.normalize_args(args)
            parsed, errs = parse_arguments(normalized, command.parameters, cmd_name)
            if errs:
                out_writer.close()
                err_writer.close()
                return CommandResult(stderr=errs, exit_code=ExitCode.INVALID_ARGUMENT)
            command.parsed_args = parsed

        exit_code: ExitCode = await command.execute(ctx, stdin_reader, out_writer, err_writer)

        out_writer.close()
        if isinstance(out_writer, FileStreamWriter) and out_writer.last_error:
            await err_writer.write(f"{out_writer.last_error}\n")
            exit_code = ExitCode.ERROR
        err_writer.close()

        stdout_lines = _drain_queue(out_queue) if out_queue is not None else []
        stderr_lines = _drain_queue(err_queue)

        action_type = command.action_type if exit_code == ExitCode.SUCCESS else TerminalAction.NONE
        return CommandResult(
            stdout=stdout_lines,
            stderr=stderr_lines,
            exit_code=exit_code,
            action_type=action_type,
            pager_payload=getattr(command, "_pager_payload", None),
        )

    async def dispatch_pipeline(
        self,
        segments: list[tuple[str, list[str], str | None, bool]],
        ctx: CommandContext,
    ) -> CommandResult:
        n = len(segments)
        pipe_queues: list[asyncio.Queue] = [asyncio.Queue() for _ in range(n - 1)]
        merged_stderr: list[str] = []
        results: list[ExitCode | None] = [None] * n

        async def run_segment(idx: int) -> None:
            cmd_name, args, redirect, append = segments[idx]
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
                        current_directory=ctx.shell.current_directory,
                        target_path=redirect,
                        home_directory=ctx.shell.home_directory,
                    )
                    out_writer = FileStreamWriter(
                        ctx.filesystem,
                        resolved,
                        append=append,
                        execution=ctx.execution_context,
                    )
                else:
                    out_queue = asyncio.Queue()
                    out_writer = QueueStreamWriter(out_queue)
            else:
                out_writer = QueueStreamWriter(pipe_queues[idx])

            # Script path resolution
            if command is None:
                content, err = await self._resolve_script(cmd_name, ctx)
                if err:
                    err_writer.close()
                    merged_stderr.extend(_drain_queue(err_queue))
                    results[idx] = ExitCode.ERROR
                    return

                script_result = await self.execute_script(
                    content,
                    ctx,
                    stdin_reader,
                    out_writer,
                    err_writer,
                    args,
                )
                out_writer.close()
                err_writer.close()
                merged_stderr.extend(_drain_queue(err_queue))
                results[idx] = script_result.exit_code

                if out_queue is not None:
                    pipe_results[idx] = _drain_queue(out_queue)
                return

            command.args = args
            command._invoked_name = cmd_name

            if command.parameters:
                normalized = command.normalize_args(args)
                parsed, errs = parse_arguments(normalized, command.parameters, cmd_name)
                if errs:
                    err_writer.write("\n".join(errs))
                    err_writer.close()
                    merged_stderr.extend(_drain_queue(err_queue))
                    results[idx] = ExitCode.INVALID_ARGUMENT
                    return
                command.parsed_args = parsed

            segment_action_types.append(
                command.action_type if results[idx] == ExitCode.SUCCESS else TerminalAction.NONE
            )

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

        segment_action_types: list[TerminalAction] = []
        pipe_results: dict[int, list[str]] = {}

        await asyncio.gather(*[run_segment(i) for i in range(n)])

        last_stdout = pipe_results.get(n - 1, [])
        last_exit = results[-1] if results[-1] is not None else ExitCode.ERROR

        action_type = (
            segment_action_types[-1]
            if segment_action_types and last_exit == ExitCode.SUCCESS
            else TerminalAction.NONE
        )

        return CommandResult(
            stdout=last_stdout,
            stderr=merged_stderr,
            exit_code=last_exit,
            action_type=action_type,
            pager_payload=getattr(self.registry.get(segments[-1][0]), "_pager_payload", None),
        )
