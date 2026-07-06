import posixpath

from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Copy a file to a target location.

    Usage: cp <source> <target>

    Reads ``source`` from the VFS, creates or overwrites ``target`` with
    the same content. If ``target`` resolves to an existing directory, the
    source basename is implicitly appended (e.g. ``cp foo /dir/`` creates
    ``/dir/foo``). If source and target refer to the same file, the copy
    is a no-op (returns SUCCESS).
    """

    name = "cp"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:

        args = self.args or []

        if len(args) < 2:
            await stderr.write(f"cp: {CommandError.MISSING_OPERAND}")
            return ExitCode.INVALID_ARGUMENT

        raw_source = args[0]
        raw_target = args[1]

        source_path = self.resolve_path(raw_source, ctx)
        target_path = self.resolve_path(raw_target, ctx)
        target_display = raw_target

        read_result = ctx.filesystem.read(source_path)
        if read_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"cp: {raw_source}: {read_result.message}")
            return read_result.exit_code

        source_node = read_result.node

        if source_node.is_directory:
            await stderr.write(f"cp: {raw_source}: {CommandError.IS_A_DIRECTORY}")
            return ExitCode.ERROR

        if ctx.filesystem.is_directory(target_path):
            source_basename = posixpath.basename(source_path)
            target_path = posixpath.join(target_path, source_basename)
            target_display = f"{raw_target}/{source_basename}"

        if ctx.filesystem.is_directory(target_path):
            await stderr.write(f"cp: {target_display}: {CommandError.IS_A_DIRECTORY}")
            return ExitCode.ERROR

        if source_path == target_path:
            return ExitCode.SUCCESS

        touch_result = ctx.filesystem.touch(target_path)
        if touch_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"cp: {target_display}: {touch_result.message}")
            return touch_result.exit_code

        write_result = ctx.filesystem.write(
            target_path, source_node.content or "",
        )
        if write_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"cp: {target_display}: {write_result.message}")
            return write_result.exit_code

        return ExitCode.SUCCESS
