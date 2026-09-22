"""userdel — remove a scenario-local user account.

The ``userdel`` command is a thin interface over the shared semantic
operation ``IdentityManager.delete_user``; it is intentionally NOT full Linux
``userdel``. It only unregisters the user (and its private primary group, when
that group is empty) from the scenario's authoritative ``IdentityState``, then
re-renders the ``/etc/passwd``, ``/etc/group``, and ``/etc/shadow`` account
files through the existing projection mechanism. It does NOT support ``-r``,
does NOT delete the user's ``/home`` directory or any other filesystem state,
and adds no password, session, process, or group-management semantics.
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
    """Remove a scenario-local user account."""

    name = "userdel"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if not args:
            await stderr.write(f"userdel: {CommandError.MISSING_OPERAND}\n")
            return ExitCode.INVALID_ARGUMENT
        if len(args) > 1:
            await stderr.write(f"userdel: {CommandError.TOO_MANY_ARGUMENTS}\n")
            return ExitCode.INVALID_ARGUMENT

        identifier = args[0]
        if not identifier:
            await stderr.write("userdel: invalid user name\n")
            return ExitCode.INVALID_ARGUMENT

        manager = IdentityManager(ctx.shell.scenario.identity_state)
        try:
            manager.delete_user(identifier)
        except ValueError as exc:
            await stderr.write(f"userdel: {exc}\n")
            return ExitCode.ERROR

        ctx.shell.refresh_account_files()

        await stdout.write(f"userdel: user '{identifier}' deleted\n")
        return ExitCode.SUCCESS
