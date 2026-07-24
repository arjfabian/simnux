"""test / [ — Evaluate conditional expressions (POSIX shell)."""

from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


class Command(SNXCommand):
    """Evaluate a conditional expression and return success/failure.

    Supports file tests (``-f``, ``-d``, ``-e``), string tests
    (``-z``, ``-n``, ``=``, ``!=``), integer comparisons
    (``-eq``, ``-ne``, ``-gt``, ``-ge``, ``-lt``, ``-le``),
    and boolean operators (``!``).

    Registered as ``[`` with ``test`` as an alias.
    When invoked as ``[``, the last argument must be ``]``.
    """

    name = "["
    aliases = ["test"]

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = list(self.args or [])

        invoked_as_bracket = self._invoked_name == "["
        if invoked_as_bracket:
            if not args or args[-1] != "]":
                await stderr.write("[: missing ']'\n")
                return ExitCode.ERROR
            args.pop()

        if not args:
            return ExitCode.ERROR

        result = self._evaluate(ctx, args)
        return ExitCode.SUCCESS if result else ExitCode.ERROR

    def _evaluate(self, ctx: CommandContext, args: list[str]) -> bool:
        # Handle prefix negation: [ ! expr ] → not expr
        if args and args[0] == "!":
            return not self._evaluate(ctx, args[1:])

        if len(args) == 2:
            op, val = args[0], args[1]

            if op in ("-f", "-d", "-e"):
                path = self.resolve_path(val, ctx)
                if op == "-f":
                    return (
                        ctx.filesystem.exists(path)
                        and not ctx.filesystem.is_directory(path)
                    )
                if op == "-d":
                    return (
                        ctx.filesystem.exists(path)
                        and ctx.filesystem.is_directory(path)
                    )
                return ctx.filesystem.exists(path)

            if op == "-z":
                return len(val) == 0
            if op == "-n":
                return len(val) > 0
            if op == "!":
                return not self._evaluate(ctx, [val])

        if len(args) == 3:
            lhs, op, rhs = args[0], args[1], args[2]

            if op in ("=", "=="):
                return lhs == rhs
            if op == "!=":
                return lhs != rhs

            try:
                lv, rv = int(lhs), int(rhs)
            except ValueError:
                return False

            if op == "-eq":
                return lv == rv
            if op == "-ne":
                return lv != rv
            if op == "-gt":
                return lv > rv
            if op == "-ge":
                return lv >= rv
            if op == "-lt":
                return lv < rv
            if op == "-le":
                return lv <= rv

            return False

        if len(args) == 1:
            return len(args[0]) > 0

        return False
