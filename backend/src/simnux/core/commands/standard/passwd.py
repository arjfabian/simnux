"""passwd — Change the password for the current simulated Linux user.

Updates the user's entry in ``/etc/shadow`` with a credential produced by
``SNXPAM``. Supports interactive suspension over REST (two prompted turns)
and a piped two-line input path. The command never stores or exposes the
plaintext password; only the salted SNXPAM credential survives in the
shadow password field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from simnux.core.commands.errors import CommandError
from simnux.core.commands.models import CommandContext
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.runtime.models import ExitCode
from simnux.security.pam import SNXPAM
from simnux.security.pam.models import SNXPasswordCredential


if TYPE_CHECKING:
    from simnux.core.shell.runtime import SNXShell

_PASSWD_PATH = "/etc/passwd"
_SHADOW_PATH = "/etc/shadow"


@dataclass
class _PasswdState:
    """Transient interaction state for the two-turn interactive flow."""

    phase: str
    new_password: str | None = None


def _credential_token(credential: SNXPasswordCredential) -> str:
    """Serialize a credential into the shadow password field."""
    return (
        f"${credential.algorithm}"
        f"${credential.iterations}"
        f"${credential.salt}"
        f"${credential.password_hash}"
    )


class Command(SNXCommand):
    """Change the password for the current simulated Linux user."""

    name = "passwd"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        if self.args:
            await stderr.write(f"passwd: {CommandError.TOO_MANY_ARGUMENTS}")
            return ExitCode.INVALID_ARGUMENT

        shell = ctx.shell

        # ── Resume path (interactive two-turn flow) ─────────────────
        if shell.awaiting_input:
            pending = shell.pending_state
            assert isinstance(pending, _PasswdState)
            if pending.phase == "enter":
                line = await stdin.readline()
                if line is None:
                    await stderr.write("passwd: unexpected EOF\n")
                    self._clear_pending(shell)
                    return ExitCode.ERROR
                shell.pending_state = _PasswdState(
                    phase="confirm",
                    new_password=line.rstrip("\n"),
                )
                await stdout.write("Confirm new password: ")
                return ExitCode.SUCCESS
            if pending.phase == "confirm":
                line = await stdin.readline()
                if line is None:
                    await stderr.write("passwd: unexpected EOF\n")
                    self._clear_pending(shell)
                    return ExitCode.ERROR
                new_password = pending.new_password
                self._clear_pending(shell)
                if new_password != line.rstrip("\n"):
                    await stderr.write("passwd: passwords do not match\n")
                    return ExitCode.ERROR
                return await self._change_password(ctx, new_password, stdout, stderr)

        # ── First invocation, no piped input: suspend for the REST bridge ──
        if isinstance(stdin, QueueStreamReader) and not stdin.has_pending():
            await stdout.write("New password: ")
            shell.awaiting_input = True
            shell.pending_command = "passwd"
            shell.pending_state = _PasswdState(phase="enter")
            return ExitCode.SUCCESS

        # ── Piped input: read both passwords immediately ────────────
        pw1 = await stdin.readline()
        if pw1 is None:
            await stderr.write("passwd: unexpected EOF\n")
            return ExitCode.ERROR
        pw1 = pw1.rstrip("\n")

        pw2 = await stdin.readline()
        if pw2 is None:
            await stderr.write("passwd: unexpected EOF\n")
            return ExitCode.ERROR
        pw2 = pw2.rstrip("\n")

        if pw1 != pw2:
            await stderr.write("passwd: passwords do not match\n")
            return ExitCode.ERROR

        return await self._change_password(ctx, pw1, stdout, stderr)

    async def _change_password(
        self,
        ctx: CommandContext,
        new_password: str,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        pam = SNXPAM()
        user = ctx.shell.user.identifier

        # Locate the account entry in /etc/passwd.
        passwd_result = ctx.filesystem.read(_PASSWD_PATH, acting_user=ctx.shell.user)
        if passwd_result.message:
            await stderr.write(f"passwd: {passwd_result.message}\n")
            return ExitCode.ERROR
        passwd_node = passwd_result.node
        assert passwd_node is not None
        passwd_lines = (passwd_node.content or "").split("\n")
        if not any(line and line.split(":")[0] == user for line in passwd_lines):
            await stderr.write(f"passwd: user '{user}' not found\n")
            return ExitCode.ERROR

        # Locate the corresponding entry in /etc/shadow.
        shadow_result = ctx.filesystem.read(_SHADOW_PATH, acting_user=ctx.shell.user)
        if shadow_result.message:
            await stderr.write(f"passwd: {shadow_result.message}\n")
            return ExitCode.ERROR
        shadow_node = shadow_result.node
        assert shadow_node is not None
        shadow_lines = (shadow_node.content or "").split("\n")
        shadow_index = next(
            (
                index
                for index, line in enumerate(shadow_lines)
                if line and line.split(":")[0] == user
            ),
            None,
        )
        if shadow_index is None:
            await stderr.write(
                f"passwd: no shadow entry for user '{user}'\n",
            )
            return ExitCode.ERROR

        # Encode the new password and replace only the shadow field.
        credential = pam.encode(new_password)
        shadow_fields = shadow_lines[shadow_index].split(":")
        shadow_fields[1] = _credential_token(credential)
        shadow_lines[shadow_index] = ":".join(shadow_fields)

        write_result = ctx.filesystem.write(
            _SHADOW_PATH,
            "\n".join(shadow_lines),
            acting_user=ctx.shell.user,
        )
        if write_result.message:
            await stderr.write(f"passwd: {write_result.message}\n")
            return ExitCode.ERROR

        await stdout.write("passwd: password updated successfully\n")
        return ExitCode.SUCCESS

    @staticmethod
    def _clear_pending(shell: SNXShell) -> None:
        """Drop the interaction state so no plaintext lingers afterwards."""
        shell.awaiting_input = False
        shell.pending_command = None
        shell.pending_state = None
