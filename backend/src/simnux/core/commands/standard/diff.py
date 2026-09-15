"""diff — compare two files line by line."""

from __future__ import annotations

import difflib

from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import MAX_PAGER_FILE_SIZE
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    """Compare two files line by line with a unified diff."""

    name = "diff"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []

        if len(args) < 2:
            await stderr.write(f"diff: {CommandError.MISSING_OPERAND}")
            return ExitCode.INVALID_ARGUMENT

        if len(args) > 2:
            await stderr.write(f"diff: {CommandError.TOO_MANY_ARGUMENTS}")
            return ExitCode.INVALID_ARGUMENT

        file1, file2 = args

        # Pre-read stdin if either argument is "-"
        stdin_buf: list[str] | None = None

        async def _stdin_lines() -> list[str]:
            nonlocal stdin_buf
            if stdin_buf is None:
                stdin_buf = []
                async for line in stdin:
                    stdin_buf.append(line.rstrip("\n"))
            return stdin_buf

        async def _lines(arg: str) -> tuple[list[str] | None, str | None]:
            if arg == "-":
                return await _stdin_lines(), None
            path = self.resolve_path(arg, ctx)
            result = ctx.filesystem.read(path, execution=ctx.execution_context)
            if result.exit_code != ExitCode.SUCCESS:
                return None, f"diff: {arg}: {result.message}"
            content = result.node.content or ""
            if len(content.encode("utf-8")) > MAX_PAGER_FILE_SIZE:
                return None, f"diff: {arg}: file too large (max 1MB)"
            return content.splitlines(), None

        content1, err1 = await _lines(file1)
        if err1:
            await stderr.write(err1)
            return ExitCode.ERROR

        content2, err2 = await _lines(file2)
        if err2:
            await stderr.write(err2)
            return ExitCode.ERROR

        diff_lines = list(
            difflib.unified_diff(
                content1,
                content2,
                fromfile=file1,
                tofile=file2,
                fromfiledate="",
                tofiledate="",
                lineterm="",
            )
        )

        if not diff_lines:
            return ExitCode.SUCCESS

        for line in diff_lines:
            await stdout.write(f"{line}\n")

        return ExitCode.ERROR
