"""chown — change file owner and/or group.

Usage: chown [OWNER][:GROUP] FILE...

Supported specifications:
  OWNER               change the owner only
  :GROUP              change the group only
  OWNER:GROUP         change owner and group

Simulated users/groups resolve against the owning scenario's authoritative
identity state (``IdentityManager``); node ownership is mutated exclusively
through ``SNXFileSystem.chown``, which authorizes the acting execution
context (privilege for owner changes; owner-or-privileged plus target-group
membership for group-only changes).

Not supported: the login-group form ``OWNER:`` (empty group, per GNU a
synonym for the owner's primary group) and bare ``:`` / empty specifications;
they are rejected rather than silently given different semantics.
"""

from __future__ import annotations

from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode
from simnux.core.scenarios.identity import IdentityManager


def _parse_spec(spec: str) -> tuple[str, str, str | None]:
    """Split an OWNER[:GROUP] specification into (owner, group, error).

    Returns an error message when the specification is malformed or uses an
    unsupported form; ``owner``/``group`` may be empty strings in that case.
    """
    if ":" not in spec:
        if not spec:
            return "", "", "chown: invalid owner: ''\n"
        return spec, "", None

    owner_part, group_part = spec.split(":", 1)

    if owner_part and group_part:
        return owner_part, group_part, None
    if not owner_part and group_part:
        return "", group_part, None
    if owner_part and not group_part:
        return "", "", "chown: invalid group: ''\n"
    return "", "", "chown: invalid owner: ''\n"


class Command(SNXCommand):
    """Change file owner and/or group."""

    name = "chown"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []
        if not args:
            await stderr.write(f"chown: {CommandError.MISSING_OPERAND}\n")
            return ExitCode.INVALID_ARGUMENT

        spec = args[0]
        if len(args) == 1:
            await stderr.write(f"chown: {CommandError.MISSING_OPERAND}\n")
            return ExitCode.INVALID_ARGUMENT

        owner_name, group_name, error = _parse_spec(spec)
        if error is not None:
            await stderr.write(error)
            return ExitCode.INVALID_ARGUMENT

        manager = IdentityManager(ctx.shell.scenario.identity_state)

        owner = None
        if owner_name:
            owner = manager.user_by_identifier(owner_name)
            if owner is None:
                await stderr.write(f"chown: invalid user: '{owner_name}'\n")
                return ExitCode.ERROR

        group = None
        if group_name:
            group = manager.group_by_identifier(group_name)
            if group is None:
                await stderr.write(f"chown: invalid group: '{group_name}'\n")
                return ExitCode.ERROR

        for raw_target in args[1:]:
            target = self.resolve_path(raw_target, ctx)
            result = ctx.filesystem.chown(
                target,
                execution=ctx.execution_context,
                owner=owner,
                group=group,
            )
            if result.exit_code != ExitCode.SUCCESS:
                await stderr.write(f"chown: {raw_target}: {result.message}")
                return result.exit_code

        return ExitCode.SUCCESS
