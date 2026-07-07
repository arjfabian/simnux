"""head — output the first part of files."""

from __future__ import annotations

import re

from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


SHORTHAND = re.compile(r"^-(\d+)$")


class Command(SNXCommand):
    """Output the first N lines of each file (default 10)."""

    name = "head"

    parameters = {
        "lines": {"flags": ["-n", "--lines"], "type": str, "help": "number of lines"},
    }

    def normalize_args(self, args: list[str]) -> list[str]:
        """Expand ``-<digits>`` shorthand to ``-n <digits>``."""
        expanded: list[str] = []
        for arg in args:
            m = SHORTHAND.match(arg)
            if m:
                expanded.extend(["-n", m.group(1)])
            else:
                expanded.append(arg)
        return expanded

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:

        n = 10
        if self.parsed_args and "lines" in self.parsed_args.flags:
            raw = self.parsed_args.flags["lines"]
            try:
                n = int(raw)
            except ValueError:
                await stderr.write(f"head: invalid number of lines: '{raw}'")
                return ExitCode.INVALID_ARGUMENT

        file_args = self.parsed_args.positional if self.parsed_args else (self.args or [])

        if not file_args:
            count = 0
            async for line in stdin:
                if count >= n:
                    break
                await stdout.write(line)
                count += 1
            return ExitCode.SUCCESS

        for file_arg in file_args:
            abs_path = self.resolve_path(file_arg, ctx)
            result = ctx.filesystem.read(abs_path)

            if result.exit_code != ExitCode.SUCCESS:
                await stderr.write(f"head: {file_arg}: {result.message}")
                return result.exit_code

            if result.node.is_directory:
                await stderr.write(f"head: {file_arg}: {CommandError.IS_A_DIRECTORY}")
                return ExitCode.ERROR

            content = result.node.content or ""
            lines = content.splitlines()
            for line in lines[:n]:
                await stdout.write(f"{line}\n")

        return ExitCode.SUCCESS
