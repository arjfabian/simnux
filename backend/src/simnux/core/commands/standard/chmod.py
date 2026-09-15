"""chmod — change file mode bits (numeric modes only)."""

from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.filesystem.models import permissions_from_mode
from simnux.core.runtime.models import ExitCode


class Command(SNXCommand):
    """Change file mode bits. Numeric modes only (e.g. ``644``, ``755``).

    Does NOT support symbolic modes (``ugoa +/- rwx``), recursion (``-R``),
    or setuid/setgid/sticky bits. The node owner (or root) may chmod; other
    users are denied. Files are never created.
    """

    name = "chmod"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if len(args) != 2:
            await stderr.write(f"chmod: {CommandError.MISSING_OPERAND}")
            await stderr.write("chmod: missing operand after 'chmod'\n")
            return ExitCode.INVALID_ARGUMENT

        raw_mode, raw_target = args

        try:
            mode = int(raw_mode, 8)
        except ValueError:
            await stderr.write(f"chmod: invalid mode: '{raw_mode}'\n")
            return ExitCode.INVALID_ARGUMENT

        try:
            permissions_from_mode(mode)
        except ValueError:
            await stderr.write(f"chmod: invalid mode: '{raw_mode}'\n")
            return ExitCode.INVALID_ARGUMENT

        target = self.resolve_path(raw_target, ctx)

        result = ctx.filesystem.chmod(target, mode, execution=ctx.execution_context)

        if result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"chmod: {raw_target}: {result.message}")
            return result.exit_code

        return ExitCode.SUCCESS
