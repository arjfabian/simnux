import asyncio
import logging

from simnux.commands.argument_parser import parse_arguments
from simnux.commands.models import CommandContext
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.commands.streams import FileStreamWriter
from simnux.commands.streams import QueueStreamReader
from simnux.commands.streams import QueueStreamWriter
from simnux.runtime.models import CommandResult
from simnux.runtime.models import ExitCode


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

    def __init__(self, registry):
        self.registry = registry

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
        """Execute a registered command. Creates internal stream queues if none provided."""

        command = self.registry.get(cmd_name)

        if command is None:
            raise ValueError(f"Command not registered: {cmd_name}")

        command.args = args

        if command.parameters:
            normalized = command.normalize_args(args)
            parsed, errs = parse_arguments(normalized, command.parameters, cmd_name)
            if errs:
                return CommandResult(stderr=errs, exit_code=ExitCode.INVALID_ARGUMENT)
            command.parsed_args = parsed

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
                current_directory=ctx.session.current_directory,
                target_path=stdout_redirect,
                home_directory=ctx.session.home_directory,
            )
            out_writer = FileStreamWriter(ctx.filesystem, resolved, append=stdout_append)
        else:
            out_writer = stdout or QueueStreamWriter(out_queue)

        err_writer = stderr or QueueStreamWriter(err_queue)

        exit_code: ExitCode = await command.execute(ctx, stdin_reader, out_writer, err_writer)

        out_writer.close()
        err_writer.close()

        stdout_lines = _drain_queue(out_queue) if out_queue is not None else []
        stderr_lines = _drain_queue(err_queue)

        return CommandResult(
            stdout=stdout_lines,
            stderr=stderr_lines,
            exit_code=exit_code,
            clear_screen=command.clear_screen and exit_code == ExitCode.SUCCESS,
        )

    async def dispatch_pipeline(
        self,
        segments: list[tuple[str, list[str], str | None, bool]],
        ctx: CommandContext,
    ) -> CommandResult:
        """Execute a | pipeline: concurrent segments connected by pipe queues."""

        n = len(segments)
        pipe_queues: list[asyncio.Queue] = [asyncio.Queue() for _ in range(n - 1)]
        merged_stderr: list[str] = []
        results: list[ExitCode | None] = [None] * n

        async def run_segment(idx: int) -> None:
            cmd_name, args, redirect, append = segments[idx]
            command = self.registry.get(cmd_name)
            command.args = args

            err_queue: asyncio.Queue = asyncio.Queue()
            err_writer = QueueStreamWriter(err_queue)

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

            segment_clear.append(command.clear_screen)

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

            try:
                results[idx] = await command.execute(
                    ctx, stdin_reader, out_writer, err_writer,
                )
            finally:
                out_writer.close()
                err_writer.close()

            merged_stderr.extend(_drain_queue(err_queue))

            if out_queue is not None:
                pipe_results[idx] = _drain_queue(out_queue)

        segment_clear: list[bool] = []
        pipe_results: dict[int, list[str]] = {}

        await asyncio.gather(*[run_segment(i) for i in range(n)])

        last_stdout = pipe_results.get(n - 1, [])
        last_exit = results[-1] if results[-1] is not None else ExitCode.ERROR

        return CommandResult(
            stdout=last_stdout,
            stderr=merged_stderr,
            exit_code=last_exit,
            clear_screen=segment_clear[-1] and last_exit == ExitCode.SUCCESS if segment_clear else False,
        )
