"""End-to-end enforcement through existing commands.

Verifies that permission-sensitive commands route their reads, redirects, and
script execution through the VFS gates: ``cat`` denial on sealed files,
``echo >`` redirect denial on root-owned files, ``./script`` (EXECUTE) vs
``sh script`` (READ-only interpreter semantics), and ``cd`` denial.
"""

import pytest

from tests.helpers import assert_error
from tests.helpers import assert_success
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


@pytest.fixture
def sealed(session, test_logger, fs_rich):
    """A shell whose world is 0644 root files plus a sealed root-owned file."""
    from simnux.core.filesystem.vfs import SNXFileSystem
    from tests.helpers import create_shell_with_commands

    fs = SNXFileSystem(base_layer=dict(fs_rich))
    fs.chmod("/etc/passwd", 0o600, acting_user=session.scenario.users["root"])
    shell = create_shell_with_commands(session, fs, test_logger)
    shell.filesystem = fs
    return shell


class TestReadEnforcement:
    async def test_cat_sealed_file_denied(self, sealed):
        """A non-root user cannot ``cat`` a root-owned 0600 file."""
        result = await sealed.execute("cat /etc/passwd")
        assert_error(result)
        assert "permission denied" in stderr_text(result)

    async def test_cat_world_readable_allowed(self, session, test_logger, fs_rich):
        """World-readable files remain readable under enforcement."""
        from simnux.core.filesystem.vfs import SNXFileSystem
        from tests.helpers import create_shell_with_commands

        fs = SNXFileSystem(base_layer=dict(fs_rich))
        shell = create_shell_with_commands(session, fs, test_logger)
        shell.filesystem = fs
        result = await shell.execute("cat /etc/hostname")
        assert_success(result)


class TestRedirectEnforcement:
    async def test_redirect_to_root_owned_file_denied(self, shell_with_commands):
        """``echo > /etc/hostname`` is denied for the non-root user."""
        result = await shell_with_commands.execute("echo hacked > /etc/hostname")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        node = shell_with_commands.filesystem.get_node("/etc/hostname")
        assert node.content == "simnux-edge"

    async def test_redirect_to_own_file_allowed(self, shell_with_commands):
        """Redirects into the user's own files still work."""
        result = await shell_with_commands.execute("echo hello > /home/user/output.txt")
        assert_success(result)
        result = await shell_with_commands.execute("cat /home/user/output.txt")
        assert "hello" in "\n".join(result.stdout)

    async def test_append_redirect_to_root_file_denied(self, shell_with_commands):
        """``>>`` to a root-owned file is denied for the non-root user."""
        result = await shell_with_commands.execute("echo x >> /etc/hostname")
        assert_error(result)
        assert "permission denied" in stderr_text(result)


class TestScriptExecutionGates:
    async def test_script_readonly_cannot_direct_execute(self, session, test_logger, fs_with_home):
        """A non-executable script is readable (``sh``) but not runnable directly."""
        from simnux.core.filesystem.vfs import SNXFileSystem
        from tests.helpers import create_shell_with_commands

        fs = SNXFileSystem(base_layer=dict(fs_with_home))
        shell = create_shell_with_commands(session, fs, test_logger)
        shell.filesystem = fs
        fs.touch("/home/user/plain.sh", acting_user=shell.user)
        fs.delta_layer["/home/user/plain.sh"].content = "#!/bin/sh\necho executed\n"

        direct = await shell.execute("./plain.sh")
        assert_error(direct)
        assert "permission denied" in stderr_text(direct)

        via_sh = await shell.execute("sh /home/user/plain.sh")
        assert_success(via_sh)

    async def test_executable_script_runs_directly(self, session, test_logger, fs_with_home):
        """After ``chmod +x``-equivalent, ``./script.sh`` runs."""
        from simnux.core.filesystem.vfs import SNXFileSystem
        from tests.helpers import create_shell_with_commands

        fs = SNXFileSystem(base_layer=dict(fs_with_home))
        shell = create_shell_with_commands(session, fs, test_logger)
        shell.filesystem = fs
        fs.touch("/home/user/run.sh", acting_user=shell.user)
        fs.delta_layer["/home/user/run.sh"].content = "#!/bin/sh\necho ran\n"
        fs.chmod("/home/user/run.sh", 0o755, acting_user=shell.user)

        result = await shell.execute("./run.sh")
        assert_success(result)


class TestCdGate:
    async def test_cd_into_sealed_directory_denied(self, session, test_logger, fs_with_home):
        """``cd`` into a directory without EXECUTE/READ-of-dir is denied."""
        from simnux.core.filesystem.models import SNXNode
        from simnux.core.filesystem.models import permissions_from_mode
        from simnux.core.filesystem.vfs import SNXFileSystem
        from simnux.security.groups.models import SNXGroup
        from simnux.security.users.models import SNXUser
        from tests.helpers import create_shell_with_commands

        root_user = SNXUser(0, "root")
        root_group = SNXGroup(0, "root")
        base = dict(fs_with_home)
        base["/sealed"] = SNXNode(
            path="/sealed",
            owner=root_user,
            group=root_group,
            content="",
            is_directory=True,
            permissions=permissions_from_mode(0o700),
        )
        fs = SNXFileSystem(base_layer=base)
        shell = create_shell_with_commands(session, fs, test_logger)
        shell.filesystem = fs
        result = await shell.execute("cd /sealed")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        assert shell.current_directory == "/home/user"


class TestMutationEnforcement:
    """Creation/deletion commands enforce parent-directory WRITE+EXECUTE."""

    async def test_rm_root_owned_file_denied(self, shell_with_commands):
        """Regression: ``rm`` on a root-owned file is denied for the non-root user."""
        result = await shell_with_commands.execute("rm /etc/hostname")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        node = shell_with_commands.filesystem.get_node("/etc/hostname")
        assert node.content == "simnux-edge"

    async def test_rm_root_owned_directory_denied(self, shell_with_commands):
        """Regression: ``rmdir`` on a root-owned empty directory is denied."""
        result = await shell_with_commands.execute("rmdir /var/log")
        assert_error(result)
        assert "permission denied" in stderr_text(result)

    async def test_rm_own_file_allowed(self, shell_with_commands):
        """``rm`` of a user-owned file inside the user's home succeeds."""
        result = await shell_with_commands.execute("rm /home/user/notes.txt")
        assert_success(result)
        result = await shell_with_commands.execute("cat /home/user/notes.txt")
        assert_error(result)
        assert "not found" in stderr_text(result)

    async def test_mkdir_denied_outside_writable_dirs(self, shell_with_commands):
        """``mkdir`` in a root-owned non-writable directory is denied."""
        result = await shell_with_commands.execute("mkdir /etc/blocked")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        assert shell_with_commands.filesystem.get_node("/etc/blocked") is None

    async def test_mkdir_allowed_in_home(self, shell_with_commands):
        """``mkdir`` inside the user's home succeeds."""
        result = await shell_with_commands.execute("mkdir /home/user/freshdir")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/home/user/freshdir")
        assert node is not None
        assert node.is_directory

    async def test_redirect_denied_when_directory_not_writable(self, shell_with_commands):
        """``echo >`` into a root-owned directory is denied at creation time."""
        result = await shell_with_commands.execute("echo x > /etc/newfile.txt")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        assert shell_with_commands.filesystem.get_node("/etc/newfile.txt") is None

    async def test_mv_out_of_root_directory_denied(self, shell_with_commands):
        """``mv`` whose source delete is denied rolls back the written target."""
        result = await shell_with_commands.execute("mv /etc/hostname /home/user/hostname")
        assert_error(result)
        assert "permission denied" in stderr_text(result)
        assert shell_with_commands.filesystem.get_node("/etc/hostname") is not None
        assert shell_with_commands.filesystem.get_node("/home/user/hostname") is None

    async def test_mv_own_files_allowed(self, shell_with_commands):
        """``mv`` between paths the user can modify succeeds."""
        result = await shell_with_commands.execute("mv /home/user/notes.txt /home/user/renamed.txt")
        assert_success(result)
        node = shell_with_commands.filesystem.get_node("/home/user/renamed.txt")
        assert node is not None
        assert shell_with_commands.filesystem.get_node("/home/user/notes.txt") is None
