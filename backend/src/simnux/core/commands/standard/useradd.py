"""useradd — create a scenario-local user account.

The ``useradd`` command is a thin interface over the shared semantic
operation ``IdentityManager.create_user``; it is intentionally NOT full Linux
``useradd``. It only registers the user (and, by default, a private primary
group) in the scenario's authoritative ``IdentityState``. It does NOT add
passwords, modify ``/etc`` account files or ``/etc/shadow``, create home
directories, or accept shell/home/supplementary-group options — those remain
separate follow-ups.
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
    """Create a scenario-local user account."""

    name = "useradd"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if not args:
            await stderr.write(f"useradd: {CommandError.MISSING_OPERAND}\n")
            return ExitCode.INVALID_ARGUMENT
        if len(args) > 1:
            await stderr.write(f"useradd: {CommandError.TOO_MANY_ARGUMENTS}\n")
            return ExitCode.INVALID_ARGUMENT

        identifier = args[0]
        if not identifier:
            await stderr.write("useradd: invalid user name\n")
            return ExitCode.INVALID_ARGUMENT

        manager = IdentityManager(ctx.shell.scenario.identity_state)
        try:
            manager.create_user(identifier)
        except ValueError as exc:
            await stderr.write(f"useradd: {exc}\n")
            return ExitCode.ERROR

        ctx.shell.refresh_account_files()

        await stdout.write(f"useradd: user '{identifier}' created\n")
        return ExitCode.SUCCESS
