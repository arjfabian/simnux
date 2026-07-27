import posixpath

from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Move (rename) a file to a target location.

    Usage: mv <source> <target>

    Reads ``source`` from the VFS, writes its content to ``target``
    (creating or overwriting), then deletes ``source``. If ``target``
    resolves to an existing directory, the source basename is implicitly
    appended (e.g. ``mv foo /dir/`` creates ``/dir/foo`` and removes
    ``foo``). If source and target refer to the same file, the move is a
    no-op (returns SUCCESS).

    If ``delete_file`` fails after the target has been written, the
    written target is cleaned up only when it was a brand-new path.
    Pre-existing target files are left intact (not deleted) to avoid
    corrupting the filesystem.
    """

    name = "mv"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []

        if len(args) < 2:
            await stderr.write(f"mv: {CommandError.MISSING_OPERAND}")
            return ExitCode.INVALID_ARGUMENT

        raw_source = args[0]
        raw_target = args[1]

        source_path = self.resolve_path(raw_source, ctx)
        target_path = self.resolve_path(raw_target, ctx)
        target_display = raw_target

        read_result = ctx.filesystem.read(source_path)
        if read_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"mv: {raw_source}: {read_result.message}")
            return read_result.exit_code

        source_node = read_result.node

        if source_node.is_directory:
            await stderr.write(f"mv: {raw_source}: {CommandError.IS_A_DIRECTORY}")
            return ExitCode.ERROR

        if ctx.filesystem.is_directory(target_path):
            source_basename = posixpath.basename(source_path)
            target_path = posixpath.join(target_path, source_basename)
            target_display = f"{raw_target}/{source_basename}"

        if ctx.filesystem.is_directory(target_path):
            await stderr.write(f"mv: {target_display}: {CommandError.IS_A_DIRECTORY}")
            return ExitCode.ERROR

        if source_path == target_path:
            return ExitCode.SUCCESS

        target_pre_existed = ctx.filesystem.exists(target_path)

        touch_result = ctx.filesystem.touch(target_path)
        if touch_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"mv: {target_display}: {touch_result.message}")
            return touch_result.exit_code

        write_result = ctx.filesystem.write(
            target_path,
            source_node.content or "",
        )
        if write_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"mv: {target_display}: {write_result.message}")
            return write_result.exit_code

        delete_result = ctx.filesystem.delete_file(source_path)
        if delete_result.exit_code != ExitCode.SUCCESS:
            if not target_pre_existed:
                ctx.filesystem.delete_file(target_path)
            await stderr.write(f"mv: {raw_source}: {delete_result.message}")
            return delete_result.exit_code

        return ExitCode.SUCCESS
