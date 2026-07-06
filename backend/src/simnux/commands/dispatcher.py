import asyncio
import logging

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
    """Drain all non-None items from a queue, splitting each on newlines.

    Each queued item is split via ``str.splitlines()`` to normalize
    multi-line writes into individual lines. None (EOF sentinel) items
    are discarded.
    """
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
    """Thin dispatch layer that resolves command names to instances,
    wires I/O streams, and delegates execution.

    Precondition: the caller must verify command existence via
    ``registry.exists()`` before calling ``dispatch()``.
    """

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
        """Execute a registered command, wrapping it in live stream queues.

        When ``stdin``/``stdout``/``stderr`` are not provided (the common
        case), internal ``QueueStreamWriter`` instances are created and
        drained into a ``CommandResult`` after the command returns.
        Provided streams pass through for pipe/redirect support.

        When ``stdout_redirect`` is set, stdout is written directly to that
        VFS path via ``FileStreamWriter`` instead of appearing in the result.
        """

        command = self.registry.get(cmd_name)

        if command is None:
            raise ValueError(f"Command not registered: {cmd_name}")

        command.args = args

        if stdin is not None:
            stdin_reader = stdin
        else:
            stdin_queue: asyncio.Queue = asyncio.Queue()
            stdin_queue.put_nowait(None)  # immediate EOF for standalone commands
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
        )

    async def dispatch_pipeline(
        self,
        segments: list[tuple[str, list[str], str | None, bool]],
        ctx: CommandContext,
    ) -> CommandResult:
        """Execute a pipeline of commands connected by |.

        Each tuple is ``(command, args, stdout_redirect, stdout_append)``.
        Creates N-1 pipe queues between N commands, runs all concurrently,
        returns merged stderr and the last segment's stdout/exit code.
        """

        n = len(segments)
        pipe_queues: list[asyncio.Queue] = [asyncio.Queue() for _ in range(n - 1)]
        merged_stderr: list[str] = []
        results: list[ExitCode | None] = [None] * n

        async def run_segment(idx: int) -> None:
            cmd_name, args, redirect, append = segments[idx]
            command = self.registry.get(cmd_name)
            command.args = args

            # stdin: previous pipe or standalone EOF
            if idx == 0:
                stdin_queue: asyncio.Queue = asyncio.Queue()

                stdin_queue.put_nowait(None) 
                    
                stdin_reader = QueueStreamReader(stdin_queue)
            else:
                stdin_reader = QueueStreamReader(pipe_queues[idx - 1])

            # stdout: next pipe or capture/redirect for last
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

            # stderr: captured per-segment, merged after
            err_queue: asyncio.Queue = asyncio.Queue()
            err_writer = QueueStreamWriter(err_queue)

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

        pipe_results: dict[int, list[str]] = {}

        await asyncio.gather(*[run_segment(i) for i in range(n)])

        last_stdout = pipe_results.get(n - 1, [])
        last_exit = results[-1] if results[-1] is not None else ExitCode.ERROR

        return CommandResult(
            stdout=last_stdout,
            stderr=merged_stderr,
            exit_code=last_exit,
        )
