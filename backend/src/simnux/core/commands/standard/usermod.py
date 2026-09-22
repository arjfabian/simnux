"""usermod — modify a scenario-local user account.

The ``usermod`` command is a thin interface over the shared semantic
operations ``IdentityManager.set_primary_group`` and
``IdentityManager.add_user_to_group``; it is intentionally NOT full Linux
``usermod``. It only changes a user's primary group (``-g``) and/or appends
supplementary group memberships (``-a -G``) in the scenario's authoritative
``IdentityState``, then re-renders the ``/etc`` account-file projections
through the existing mechanism.

It does NOT support renaming (``-l``), uid/password/home/shell changes, or
group-list replacement: replacing the supplementary group list (``-G``
without ``-a``) requires removing memberships, which the identity
architecture does not model — the append form ``-a -G`` is the supported
surface. Membership changes take effect for execution contexts constructed
after the change (re-login semantics); the current shell's snapshot is
immutable.
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
    """Modify a scenario-local user account's primary/supplementary groups."""

    name = "usermod"

    parameters = {
        "append": {
            "flags": ["-a", "--append"],
            "type": bool,
            "help": "append the groups from -G to the supplementary group list",
        },
        "gid": {
            "flags": ["-g", "--gid"],
            "type": str,
            "help": "new primary group for the user",
        },
        "groups": {
            "flags": ["-G", "--groups"],
            "type": str,
            "help": "comma-separated supplementary groups to append (requires -a)",
        },
    }

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        parsed = self.parsed_args
        positionals = list(parsed.positional) if parsed else list(self.args or [])
        flags = parsed.flags if parsed else {}

        if not positionals:
            await stderr.write(f"usermod: {CommandError.MISSING_OPERAND}\n")
            return ExitCode.INVALID_ARGUMENT
        if len(positionals) > 1:
            await stderr.write(f"usermod: {CommandError.TOO_MANY_ARGUMENTS}\n")
            return ExitCode.INVALID_ARGUMENT

        identifier = positionals[0]
        if not identifier:
            await stderr.write("usermod: invalid user name\n")
            return ExitCode.INVALID_ARGUMENT

        append = flags.get("append", False)
        gid_name = flags.get("gid")
        groups_list = flags.get("groups")

        if append and not groups_list:
            await stderr.write("usermod: '-a' may only be used with '-G'\n")
            return ExitCode.INVALID_ARGUMENT
        if groups_list and not append:
            await stderr.write(
                "usermod: '-G' requires '-a': replacing the supplementary "
                "group list is not supported\n"
            )
            return ExitCode.INVALID_ARGUMENT
        if gid_name is None and groups_list is None:
            await stderr.write("usermod: no changes\n")
            return ExitCode.INVALID_ARGUMENT

        manager = IdentityManager(ctx.shell.scenario.identity_state)

        user = manager.user_by_identifier(identifier)
        if user is None:
            await stderr.write(f"usermod: user '{identifier}' does not exist\n")
            return ExitCode.ERROR

        if gid_name is not None:
            group = manager.group_by_identifier(gid_name)
            if group is None:
                await stderr.write(f"usermod: group '{gid_name}' does not exist\n")
                return ExitCode.ERROR
            manager.set_primary_group(user, group)

        if groups_list:
            for group_name in groups_list.split(","):
                group_name = group_name.strip()
                if not group_name:
                    await stderr.write("usermod: invalid group name\n")
                    return ExitCode.INVALID_ARGUMENT
                group = manager.group_by_identifier(group_name)
                if group is None:
                    await stderr.write(f"usermod: group '{group_name}' does not exist\n")
                    return ExitCode.ERROR
                manager.add_user_to_group(user, group)

        ctx.shell.refresh_account_files()

        await stdout.write(f"usermod: user '{identifier}' updated\n")
        return ExitCode.SUCCESS
