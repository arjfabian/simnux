"""groupdel — delete a scenario-local group.

The ``groupdel`` command is a thin interface over the shared semantic
operation ``IdentityManager.delete_group``; it is intentionally NOT full Linux
``groupdel``. It removes the group from the scenario's authoritative
``IdentityState`` (together with every membership referencing it) and
re-renders the ``/etc`` account-file projections through the existing
mechanism. Deletion is refused when the group is the primary group of a
registered user. It does NOT implement user flags such as ``-f``.
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
    """Delete a scenario-local group."""

    name = "groupdel"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if not args:
            await stderr.write(f"groupdel: {CommandError.MISSING_OPERAND}\n")
            return ExitCode.INVALID_ARGUMENT
        if len(args) > 1:
            await stderr.write(f"groupdel: {CommandError.TOO_MANY_ARGUMENTS}\n")
            return ExitCode.INVALID_ARGUMENT

        identifier = args[0]
        if not identifier:
            await stderr.write("groupdel: invalid group name\n")
            return ExitCode.INVALID_ARGUMENT

        manager = IdentityManager(ctx.shell.scenario.identity_state)
        try:
            manager.delete_group(identifier)
        except ValueError as exc:
            await stderr.write(f"groupdel: {exc}\n")
            return ExitCode.ERROR

        ctx.shell.refresh_account_files()

        await stdout.write(f"groupdel: group '{identifier}' deleted\n")
        return ExitCode.SUCCESS
