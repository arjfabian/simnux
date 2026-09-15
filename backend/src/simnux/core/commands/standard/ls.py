from datetime import date
from datetime import datetime

from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.models import permissions_symbolic
from simnux.core.runtime.models import ExitCode


_EPOCH = datetime(1970, 1, 1)


def _format_mtime(modified_at: datetime | None, today: date) -> str:
    """Render an mtime for ``ls -l`` (GNU-style, space-padded day).

    Same year as *today* → ``May  9 14:22``; older → ``May  9  2025``.
    Nodes predating mtime metadata render as the epoch (``Jan  1  1970``).
    """
    if modified_at is None:
        modified_at = _EPOCH
    if modified_at.year == today.year:
        return f"{modified_at:%b} {modified_at.day:>2} {modified_at:%H:%M}"
    return f"{modified_at:%b} {modified_at.day:>2}  {modified_at.year}"


class Command(SNXCommand):
    """List directory contents (POSIX-like)."""

    name = "ls"

    parameters = {
        "all": {
            "flags": ["-a", "--all"],
            "type": bool,
            "help": "include . and .. and hidden files",
        },
        "almost_all": {
            "flags": ["-A", "--almost-all"],
            "type": bool,
            "help": "include hidden files but not . and ..",
        },
        "long": {
            "flags": ["-l", "--long"],
            "type": bool,
            "help": "include file type, permission bits, owner, group, size, and mtime",
        },
    }

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        pos_args = self.parsed_args.positional if self.parsed_args else (self.args or [])
        if pos_args:
            raw_target = pos_args[0]
            target = self.resolve_path(raw_target, ctx)
        else:
            raw_target = "."
            target = ctx.shell.current_directory

        if not ctx.filesystem.exists(target):
            await stderr.write(
                f"ls: cannot access '{raw_target}': {CommandError.NO_SUCH_FILE_OR_DIR}"
            )
            return ExitCode.ERROR

        if not ctx.filesystem.is_directory(target):
            await stderr.write(f"ls: cannot access '{raw_target}': {CommandError.NOT_A_DIRECTORY}")
            return ExitCode.ERROR

        show_all = self.parsed_args and self.parsed_args.flags.get("all", False)
        show_almost_all = self.parsed_args and self.parsed_args.flags.get("almost_all", False)
        show_long = self.parsed_args and self.parsed_args.flags.get("long", False)

        list_result = ctx.filesystem.list_directory(
            target,
            execution=ctx.execution_context,
        )
        if list_result.exit_code != ExitCode.SUCCESS:
            await stderr.write(f"ls: cannot access '{raw_target}': {list_result.message}")
            return list_result.exit_code

        nodes = list_result.nodes

        children = sorted(nodes, key=lambda n: n.path.split("/")[-1])

        if not show_long:
            names: list[str] = []

            if show_all:
                names.append(".")
                if target != "/":
                    names.append("..")

            for node in children:
                name = node.path.split("/")[-1]

                if name.startswith(".") and not show_all and not show_almost_all:
                    continue

                if node.is_directory:
                    names.append(name + "/")
                else:
                    names.append(name)

            if names:
                await stdout.write("  ".join(names))

            return ExitCode.SUCCESS

        today = ctx.filesystem.now().date()

        rows: list[tuple[str, str, str, str, str, str]] = []

        if show_all:
            target_node = ctx.filesystem.get_node(target)
            if target_node is not None:
                rows.append(self._long_row(target_node, ".", today))
            if target != "/":
                parent = self._parent_path(target)
                parent_node = ctx.filesystem.get_node(parent)
                if parent_node is not None:
                    rows.append(self._long_row(parent_node, "..", today))

        for node in children:
            name = node.path.split("/")[-1]

            if name.startswith(".") and not show_all and not show_almost_all:
                continue

            rows.append(self._long_row(node, name, today))

        if rows:
            await stdout.writelines(self._render_long(rows))

        return ExitCode.SUCCESS

    @staticmethod
    def _parent_path(path: str) -> str:
        """Absolute path of the parent directory (``/`` is its own parent)."""
        if path == "/":
            return "/"
        parent = path.rsplit("/", 1)[0]
        return parent or "/"

    @staticmethod
    def _long_row(
        node: SNXNode,
        name: str,
        today: date,
    ) -> tuple[str, str, str, str, str, str]:
        """Collect the columns needed for one ``ls -l`` line."""
        type_char = "d" if node.is_directory else "-"
        mode = f"{type_char}{permissions_symbolic(node.permissions)}"
        mtime = _format_mtime(node.modified_at, today)
        return (mode, node.owner.identifier, node.group.identifier, str(node.size), mtime, name)

    @staticmethod
    def _render_long(rows: list[tuple[str, str, str, str, str, str]]) -> list[str]:
        """Align variable-width columns across all rows before rendering."""
        owner_width = max(len(owner) for _, owner, _, _, _, _ in rows)
        group_width = max(len(group) for _, _, group, _, _, _ in rows)
        size_width = max(len(size) for _, _, _, size, _, _ in rows)
        return [
            f"{mode} {owner:<{owner_width}} {group:<{group_width}} {size:>{size_width}} {mtime:<12} {name}"
            for mode, owner, group, size, mtime, name in rows
        ]
