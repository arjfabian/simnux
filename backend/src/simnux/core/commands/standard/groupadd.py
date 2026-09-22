"""groupadd — create a scenario-local group.

The ``groupadd`` command is a thin interface over the shared semantic
operation ``IdentityManager.create_group``; it is intentionally NOT full Linux
``groupadd``. It only registers the group in the scenario's authoritative
``IdentityState`` and re-renders the ``/etc`` account-file projections through
the existing mechanism. It does NOT accept ``-g``/``-o``, create system
groups, passwords, or supplementary memberships.
"""

from __future__ import annotations

from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode
from simnux.core.scenarios.identity import IdentityManager


class Command(SNXCommand):
    """Create a scenario-local group."""

    name = "groupadd"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if not args:
            await stderr.write(f"groupadd: {CommandError.MISSING_OPERAND}\n")
            return ExitCode.INVALID_ARGUMENT
        if len(args) > 1:
            await stderr.write(f"groupadd: {CommandError.TOO_MANY_ARGUMENTS}\n")
            return ExitCode.INVALID_ARGUMENT

        identifier = args[0]
        if not identifier:
            await stderr.write("groupadd: invalid group name\n")
            return ExitCode.INVALID_ARGUMENT

        manager = IdentityManager(ctx.shell.scenario.identity_state)
        try:
            manager.create_group(identifier)
        except ValueError as exc:
            await stderr.write(f"groupadd: {exc}\n")
            return ExitCode.ERROR

        ctx.shell.refresh_account_files()

        await stdout.write(f"groupadd: group '{identifier}' created\n")
        return ExitCode.SUCCESS
