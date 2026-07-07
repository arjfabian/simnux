"""tail — output the last part of files."""

from __future__ import annotations

import re

from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


SHORTHAND = re.compile(r"^-(\d+)$")


class Command(SNXCommand):
    """Output the last N lines of each file (default 10)."""

    name = "tail"

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
                await stderr.write(f"tail: invalid number of lines: '{raw}'")
                return ExitCode.INVALID_ARGUMENT

        file_args = self.parsed_args.positional if self.parsed_args else (self.args or [])

        if not file_args:
            all_lines: list[str] = []
            async for line in stdin:
                all_lines.append(line)
            selected = all_lines[-n:] if n > 0 else []
            for line in selected:
                await stdout.write(line)
            return ExitCode.SUCCESS

        stdin_cache: list[str] | None = None
        multiple = len(file_args) > 1
        first = True

        for file_arg in file_args:
            if multiple:
                if not first:
                    await stdout.write("\n")
                await stdout.write(f"==> {file_arg} <==\n")

            if file_arg == "-":
                if stdin_cache is None:
                    stdin_cache = []
                    async for line in stdin:
                        stdin_cache.append(line)
                selected = stdin_cache[-n:] if n > 0 else []
                for line in selected:
                    await stdout.write(line)
            else:
                abs_path = self.resolve_path(file_arg, ctx)
                result = ctx.filesystem.read(abs_path)

                if result.exit_code != ExitCode.SUCCESS:
                    await stderr.write(f"tail: {file_arg}: {result.message}")
                    return result.exit_code

                content = result.node.content or ""
                lines = content.splitlines()
                selected = lines[-n:] if n > 0 else []
                for line in selected:
                    await stdout.write(f"{line}\n")

            first = False

        return ExitCode.SUCCESS
