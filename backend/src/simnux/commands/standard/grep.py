from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Search input for lines matching a pattern.

    The first argument is the search pattern (substring match, not regex).
    Remaining arguments are file paths resolved via the VFS layer.
    With no file arguments, reads from ``stdin``.
    ``-`` reads from stdin at that position.
    Matching lines are written to ``stdout`` terminated by ``\\n``.

    Exit codes (POSIX grep convention):
      SUCCESS (0)  — at least one match found
      ERROR   (1)  — no matches found, or operational error
      INVALID_ARGUMENT (2) — missing pattern
    """

    name = "grep"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:

        args = self.args or []

        if not args:
            await stderr.write(f"grep: {CommandError.MISSING_OPERAND}")
            return ExitCode.INVALID_ARGUMENT

        pattern = args[0]
        file_args = args[1:]

        found_match = False
        stdin_consumed = False

        if not file_args:
            async for line in stdin:
                stripped = line.rstrip("\n")
                if pattern in stripped:
                    await stdout.write(f"{stripped}\n")
                    found_match = True
            return ExitCode.SUCCESS if found_match else ExitCode.ERROR

        for file_arg in file_args:
            if file_arg == "-":
                if stdin_consumed:
                    continue
                async for line in stdin:
                    stripped = line.rstrip("\n")
                    if pattern in stripped:
                        await stdout.write(f"{stripped}\n")
                        found_match = True
                stdin_consumed = True
            else:
                abs_path = self.resolve_path(file_arg, ctx)
                result = ctx.filesystem.read(abs_path)

                if result.exit_code != ExitCode.SUCCESS:
                    await stderr.write(f"grep: {file_arg}: {result.message}")
                    return result.exit_code

                if result.node.is_directory:
                    await stderr.write(f"grep: {file_arg}: {CommandError.IS_A_DIRECTORY}")
                    return ExitCode.ERROR

                content = result.node.content or ""
                for line in content.splitlines():
                    if pattern in line:
                        await stdout.write(f"{line}\n")
                        found_match = True

        return ExitCode.SUCCESS if found_match else ExitCode.ERROR
