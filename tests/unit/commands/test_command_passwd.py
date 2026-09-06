"""Tests for the ``passwd`` command implementation.

Covers password updates through ``/etc/shadow`` via SNXPAM credentials,
piped two-line input and interactive two-turn suspension, confirmation
mismatch handling, missing-account errors, and guaranteed absence of
plaintext in the simulated world.
"""

from __future__ import annotations

import asyncio

import pytest

from simnux.core.commands.standard.passwd import _PasswdState
from simnux.core.commands.streams import QueueStreamReader
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.runtime.models import ExitCode
from simnux.security.groups.models import SNXGroup
from simnux.security.pam import SNXPAM
from simnux.security.pam.models import SNXPasswordCredential
from simnux.security.users.models import SNXUser
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


ROOT_USER = SNXUser(0, "root")
ROOT_GROUP = SNXGroup(0, "root")
USER_OWNER = SNXUser(1001, "user")
USER_GROUP = SNXGroup(1001, "user")

_PASSWD_LINE = "user:x:1001:1001::/home/user:/bin/bash"
_SHADOW_LINE = "user:!:20000:0:99999:7:::"
_NEW_PW = "SecurePass123"
_MISMATCH_PW = "Different456"


def _parse_credential(token: str) -> SNXPasswordCredential:
    """Decode a shadow-field credential token back into a credential."""
    parts = token.split("$")
    assert len(parts) == 5 and parts[0] == ""
    return SNXPasswordCredential(
        algorithm=parts[1],
        iterations=int(parts[2]),
        salt=parts[3],
        password_hash=parts[4],
    )


@pytest.fixture
def base_layer():
    """Extend the standard base layer with passwd/shadow files."""
    return {
        "/": SNXNode(
            path="/",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home": SNXNode(
            path="/home",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home/user": SNXNode(
            path="/home/user",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/etc": SNXNode(
            path="/etc",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/etc/passwd": SNXNode(
            path="/etc/passwd",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="root:x:0:0:root:/root:/bin/bash\n" + _PASSWD_LINE,
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
        "/etc/shadow": SNXNode(
            path="/etc/shadow",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="root:!:20000:0:99999:7:::\n" + _SHADOW_LINE,
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
    }


def _shadow_user_line(shell) -> str:
    """Return the ``user`` line from the effective /etc/shadow content."""
    node = shell.filesystem.read("/etc/shadow").node
    assert node is not None
    return next(line for line in node.content.split("\n") if line.startswith("user:"))


def _write_lined_input(shell, pw1: str, pw2: str | None) -> str:
    """Write a piped input file and return its path for ``cat``."""
    path = "/home/user/pw-input.txt"
    content = pw1 + "\n" if pw2 is None else f"{pw1}\n{pw2}\n"
    shell.filesystem.touch(path)
    assert shell.filesystem.write(path, content).exit_code == ExitCode.SUCCESS
    return path


async def _run_single_line_passwd(shell, pw1: str):
    """Execute ``passwd`` with a single piped line via ``cat``."""
    path = _write_lined_input(shell, pw1, None)
    return await shell.execute(f"cat {path} | passwd")


async def _run_piped_passwd(shell, pw1: str, pw2: str):
    """Execute ``passwd`` with the two lines piped via ``cat``."""
    path = _write_lined_input(shell, pw1, pw2)
    return await shell.execute(f"cat {path} | passwd")


# ── Basic invocation ─────────────────────────────────────────────────────


class TestPasswdBasic:
    async def test_passwd_no_args_suspends(self, shell_with_commands):
        """Without piped input passwd prompts and suspends for the bridge."""
        result = await shell_with_commands.execute("passwd")
        assert_success(result)
        assert shell_with_commands.awaiting_input is True
        assert shell_with_commands.pending_command == "passwd"
        assert isinstance(shell_with_commands.pending_state, _PasswdState)
        assert shell_with_commands.pending_state.phase == "enter"

    async def test_passwd_too_many_arguments(self, shell_with_commands):
        """Positional arguments are rejected."""
        result = await shell_with_commands.execute("passwd foo")
        assert_invalid_args(result)
        assert "too many arguments" in stderr_text(result)


# ── Piped input ──────────────────────────────────────────────────────────


class TestPasswdPiped:
    async def test_passwd_changes_password(self, shell_with_commands):
        """Matching piped passwords update the shadow credential."""
        result = await _run_piped_passwd(shell_with_commands, _NEW_PW, _NEW_PW)
        assert_success(result)
        assert "passwd: password updated successfully" in stdout_text(result)
        field = _shadow_user_line(shell_with_commands).split(":")[1]
        assert field != "!"
        assert field.startswith("$pbkdf2-sha256$")

    async def test_passwd_confirmation_mismatch(self, shell_with_commands):
        """A confirmation that differs from the password is rejected."""
        result = await _run_piped_passwd(
            shell_with_commands,
            _NEW_PW,
            _MISMATCH_PW,
        )
        assert_error(result)
        assert "passwd: passwords do not match" in stderr_text(result)

    async def test_passwd_unexpected_eof(self, shell_with_commands):
        """A single piped line is an error and never reaches the shadow file."""
        result = await _run_single_line_passwd(shell_with_commands, _NEW_PW)
        assert_error(result)
        assert "passwd: unexpected EOF" in stderr_text(result)
        field = _shadow_user_line(shell_with_commands).split(":")[1]
        assert field == "!"

    async def test_passwd_account_not_found(self, shell_with_commands):
        """A missing /etc/passwd account entry aborts the change."""
        node = shell_with_commands.filesystem.get_node("/etc/passwd")
        assert node is not None
        lines = [line for line in node.content.split("\n") if line and not line.startswith("user:")]
        shell_with_commands.filesystem.delta_layer["/etc/passwd"] = SNXNode(
            path="/etc/passwd",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="\n".join(lines),
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        )
        result = await _run_piped_passwd(shell_with_commands, _NEW_PW, _NEW_PW)
        assert_error(result)
        assert "passwd: user 'user' not found" in stderr_text(result)

    async def test_passwd_shadow_entry_not_found(self, shell_with_commands):
        """A missing /etc/shadow entry for the account aborts the change."""
        node = shell_with_commands.filesystem.get_node("/etc/shadow")
        assert node is not None
        lines = [line for line in node.content.split("\n") if line and not line.startswith("user:")]
        shell_with_commands.filesystem.delta_layer["/etc/shadow"] = SNXNode(
            path="/etc/shadow",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="\n".join(lines),
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        )
        result = await _run_piped_passwd(shell_with_commands, _NEW_PW, _NEW_PW)
        assert_error(result)
        assert "passwd: no shadow entry for user 'user'" in stderr_text(result)


# ── Shadow record semantics ──────────────────────────────────────────────


class TestPasswdShadowSemantics:
    async def test_credential_replaces_shadow_field(self, shell_with_commands):
        """The locked ``!`` field is replaced by a valid SNXPAM credential."""
        result = await _run_piped_passwd(shell_with_commands, _NEW_PW, _NEW_PW)
        assert_success(result)
        token = _shadow_user_line(shell_with_commands).split(":")[1]
        assert token != "!"
        assert SNXPAM().verify(_NEW_PW, _parse_credential(token)) is True

    async def test_non_password_shadow_fields_preserved(self, shell_with_commands):
        """Only the password field changes; the shadow tail is untouched."""
        result = await _run_piped_passwd(shell_with_commands, _NEW_PW, _NEW_PW)
        assert_success(result)
        user_line = _shadow_user_line(shell_with_commands)
        assert ":".join(user_line.split(":")[2:]) == "20000:0:99999:7:::"

    async def test_passwd_file_unchanged(self, shell_with_commands):
        """/etc/passwd is read-only for passwd; only /etc/shadow changes."""
        before = shell_with_commands.filesystem.read("/etc/passwd").node.content
        result = await _run_piped_passwd(shell_with_commands, _NEW_PW, _NEW_PW)
        assert_success(result)
        after = shell_with_commands.filesystem.read("/etc/passwd").node.content
        assert after == before

    async def test_plaintext_never_stored(self, shell_with_commands):
        """The plaintext password never lands in shadow or passwd files."""
        result = await _run_piped_passwd(shell_with_commands, _NEW_PW, _NEW_PW)
        assert_success(result)
        shadow_node = shell_with_commands.filesystem.read("/etc/shadow").node
        passwd_node = shell_with_commands.filesystem.read("/etc/passwd").node
        assert _NEW_PW not in shadow_node.content
        assert _NEW_PW not in passwd_node.content


# ── Interactive suspension over REST ─────────────────────────────────────


class TestPasswdInteractive:
    async def test_resume_confirm_then_change(self, shell_with_commands):
        """Two resume turns collect both passwords and apply the change."""
        await shell_with_commands.execute("passwd")
        assert shell_with_commands.awaiting_input is True

        first_queue: asyncio.Queue = asyncio.Queue()
        first_queue.put_nowait(f"{_NEW_PW}\n")
        first_queue.put_nowait(None)
        result = await shell_with_commands.execute_resume(
            shell_with_commands.pending_command,
            QueueStreamReader(first_queue),
        )
        assert_success(result)
        assert shell_with_commands.awaiting_input is True
        pending = shell_with_commands.pending_state
        assert isinstance(pending, _PasswdState)
        assert pending.phase == "confirm"
        assert pending.new_password == _NEW_PW

        second_queue: asyncio.Queue = asyncio.Queue()
        second_queue.put_nowait(f"{_NEW_PW}\n")
        second_queue.put_nowait(None)
        result = await shell_with_commands.execute_resume(
            shell_with_commands.pending_command,
            QueueStreamReader(second_queue),
        )
        assert_success(result)
        assert "passwd: password updated successfully" in stdout_text(result)
        assert shell_with_commands.awaiting_input is False
        assert shell_with_commands.pending_state is None

    async def test_resume_eof_clears_interaction_state(self, shell_with_commands):
        """EOF on resume aborts and drops pending plaintext state."""
        await shell_with_commands.execute("passwd")

        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait(None)
        result = await shell_with_commands.execute_resume(
            shell_with_commands.pending_command,
            QueueStreamReader(queue),
        )
        assert_error(result)
        assert "passwd: unexpected EOF" in stderr_text(result)
        assert shell_with_commands.awaiting_input is False
        assert shell_with_commands.pending_state is None


# ── Loader bootstrap integration ──────────────────────────────────────────


class TestPasswdBootstrapIntegration:
    """``passwd`` against loader-bootstrapped account files (hello scenario)."""

    async def test_bootstrapped_accounts_present(self, runtime_shell):
        """The hello scenario ships a loader-generated account database."""
        passwd_node = runtime_shell.filesystem.read("/etc/passwd").node
        shadow_node = runtime_shell.filesystem.read("/etc/shadow").node
        assert passwd_node is not None
        assert "root:x:0:0:root:/root:/bin/sh" in passwd_node.content
        assert "user:x:1001:1001:user:/home/user:/bin/sh" in passwd_node.content
        assert shadow_node is not None
        assert "root:!:20000:0:99999:7:::" in shadow_node.content
        assert "user:!:20000:0:99999:7:::" in shadow_node.content

    async def test_passwd_updates_only_current_user_shadow_field(self, runtime_shell):
        """``passwd`` flips only the acting user's shadow field to a credential."""
        before_passwd = runtime_shell.filesystem.read("/etc/passwd").node.content
        result = await _run_piped_passwd(runtime_shell, _NEW_PW, _NEW_PW)
        assert_success(result)
        assert "passwd: password updated successfully" in stdout_text(result)

        shadow = runtime_shell.filesystem.read("/etc/shadow").node.content
        user_line = next(line for line in shadow.split("\n") if line.startswith("user:"))
        root_line = next(line for line in shadow.split("\n") if line.startswith("root:"))
        assert user_line.split(":")[1] != "!"
        assert user_line.split(":")[1].startswith("$pbkdf2-sha256$")
        assert root_line.split(":")[1] == "!"

        after_passwd = runtime_shell.filesystem.read("/etc/passwd").node.content
        assert after_passwd == before_passwd
