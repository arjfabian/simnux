"""VFS permission enforcement tests.

Exercises the centralized enforcement gates in ``SNXFileSystem``: ``read``
(READ), ``write``/``append`` (WRITE), ``touch`` (WRITE on existing file),
``list_directory`` (READ on directory), ``validate_directory`` (EXECUTE on
directory), and ``chmod`` (owner-or-root authorization). Uses real identity
objects and an injected ``SNXGroupMembership``, matching runtime wiring.
"""

from simnux.core.commands.errors import CommandError
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.permissions import Access
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser
from tests.helpers import assert_not_success
from tests.helpers import assert_success


ROOT_USER = SNXUser(0, "root")
ROOT_GROUP = SNXGroup(0, "root")
USER_OWNER = SNXUser(1001, "user")
USER_GROUP = SNXGroup(1001, "user")
TEAM_USER = SNXUser(1002, "teammate")
TEAM_GROUP = SNXGroup(1002, "team")


def _membership() -> SNXGroupMembership:
    return SNXGroupMembership(
        _group_ids_by_user={
            USER_OWNER.user_id: frozenset([USER_GROUP.group_id]),
            TEAM_USER.user_id: frozenset([TEAM_GROUP.group_id]),
        },
        _primary_groups={
            USER_OWNER.user_id: USER_GROUP,
            TEAM_USER.user_id: TEAM_GROUP,
        },
    )


def _permissions(mode: int):
    from simnux.core.filesystem.models import permissions_from_mode

    return permissions_from_mode(mode)


def _make_fs() -> SNXFileSystem:
    """Root-owned 0644 files plus a group-owned 0660 file and a sealed 0600 file."""
    base_layer = {
        "/": SNXNode(
            path="/",
            owner=ROOT_USER,
            group=ROOT_GROUP,
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
        "/etc/hostname": SNXNode(
            path="/etc/hostname",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="simnux-edge",
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
        "/etc/secret": SNXNode(
            path="/etc/secret",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="classified",
            is_directory=False,
            permissions=_permissions(0o600),
        ),
        "/etc/owned-writable": SNXNode(
            path="/etc/owned-writable",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="mine but not removable",
            is_directory=False,
            permissions=_permissions(0o600),
        ),
        "/etc/rootdir": SNXNode(
            path="/etc/rootdir",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/nox": SNXNode(
            path="/nox",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="",
            is_directory=True,
            permissions=_permissions(0o200),
        ),
        "/nox/bits": SNXNode(
            path="/nox/bits",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="x",
            is_directory=False,
            permissions=_permissions(0o600),
        ),
        "/data": SNXNode(
            path="/data",
            owner=TEAM_USER,
            group=TEAM_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/data/team-note": SNXNode(
            path="/data/team-note",
            owner=USER_OWNER,
            group=TEAM_GROUP,
            content="shared",
            is_directory=False,
            permissions=_permissions(0o660),
        ),
        "/locked": SNXNode(
            path="/locked",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="",
            is_directory=True,
            permissions=_permissions(0o700),
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
    }
    return SNXFileSystem(base_layer=base_layer, membership=_membership())


class TestReadEnforcement:
    def test_owner_reads_own_file(self):
        """A user can read their own file."""
        fs = _make_fs()
        result = fs.read("/etc/secret", acting_user=ROOT_USER)
        assert_success(result)
        assert result.node.content == "classified"

    def test_read_denied_for_non_owner_of_0600(self):
        """``cat``-path reads are gated on READ for the acting user."""
        fs = _make_fs()
        result = fs.read("/etc/secret", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_read_world_readable_allows_anyone(self):
        """World-readable 0644 files may be read by non-owners."""
        fs = _make_fs()
        result = fs.read("/etc/hostname", acting_user=USER_OWNER)
        assert_success(result)

    def test_read_group_member_allowed(self):
        """A member of the node's group reads it via group bits (0660)."""
        fs = _make_fs()
        result = fs.read("/data/team-note", acting_user=TEAM_USER)
        assert_success(result)


class TestWriteEnforcement:
    def test_owner_write_allowed(self):
        """The owner of a file may write it."""
        fs = _make_fs()
        result = fs.write("/etc/secret", "new-content", acting_user=ROOT_USER)
        assert_success(result)

    def test_write_denied_for_outsider(self):
        """A non-owner, non-member cannot write a 0600 file."""
        fs = _make_fs()
        result = fs.write("/etc/secret", "x", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED
        assert fs.read("/etc/secret", acting_user=ROOT_USER).node.content == "classified"

    def test_append_denied_for_world_readable(self):
        """WRITE gates append; world-read (0644) does not grant write."""
        fs = _make_fs()
        result = fs.append("/etc/hostname", "\n", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_write_denied_does_not_touch_delta(self):
        """A denied write leaves no trace in the delta layer."""
        fs = _make_fs()
        fs.append("/etc/hostname", "x", acting_user=USER_OWNER)
        assert "/etc/hostname" not in fs.delta_layer


class TestTouchEnforcement:
    def test_touch_existing_file_needs_write(self):
        """Touch on an existing file enforces WRITE."""
        fs = _make_fs()
        result = fs.touch("/etc/hostname", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_touch_existing_file_as_owner_succeeds(self):
        """Touch on an existing file the owner can write succeeds (no-op)."""
        fs = _make_fs()
        result = fs.touch("/etc/hostname", acting_user=ROOT_USER)
        assert_success(result)


class TestDirectoryEnforcement:
    def test_list_denied_without_read(self):
        """Listing a directory enforces READ; a sealed directory is denied."""
        fs = _make_fs()
        result = fs.list_directory("/locked", acting_user=TEAM_USER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_list_allowed_for_owner(self):
        """The owner may list their own sealed directory."""
        fs = _make_fs()
        result = fs.list_directory("/locked", acting_user=USER_OWNER)
        assert_success(result)

    def test_validate_directory_needs_execute(self):
        """``cd`` into a directory enforces EXECUTE."""
        fs = _make_fs()
        result = fs.validate_directory("/locked", acting_user=TEAM_USER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_root_bypasses_directory_permissions(self):
        """Root bypasses READ/EXECUTE gates on directories."""
        fs = _make_fs()
        result = fs.list_directory("/locked", acting_user=ROOT_USER)
        assert_success(result)


class TestRootBypass:
    def test_root_reads_sealed_file(self):
        """Root bypasses the READ gate."""
        fs = _make_fs()
        result = fs.read("/etc/secret", acting_user=ROOT_USER)
        assert_success(result)

    def test_root_writes_world_readable_file(self):
        """Root bypasses the WRITE gate."""
        fs = _make_fs()
        result = fs.write("/etc/hostname", "overwritten", acting_user=ROOT_USER)
        assert_success(result)
        assert fs.get_node("/etc/hostname").content == "overwritten"


class TestCheckAccess:
    def test_check_access_reflects_evaluator(self):
        """The public helper surfaces the same decision the gates use."""
        fs = _make_fs()
        assert fs.check_access("/etc/hostname", Access.WRITE, USER_OWNER).exit_code != 0
        assert fs.check_access("/etc/hostname", Access.READ, USER_OWNER).exit_code == 0

    def test_check_access_missing_path(self):
        """check_access on a missing path reports not found."""
        fs = _make_fs()
        result = fs.check_access("/nope", Access.READ, USER_OWNER)
        assert_not_success(result)
        assert CommandError.NOT_FOUND in result.message


class TestCreateEnforcement:
    """Creation is authorized on the parent directory: WRITE + EXECUTE."""

    def test_create_file_allowed_in_own_writable_parent(self):
        """A user creates a file in a directory they own with w+x."""
        fs = _make_fs()
        result = fs.create_file("/home/user/new.txt", acting_user=USER_OWNER)
        assert_success(result)

    def test_create_file_denied_in_readonly_parent(self):
        """A 0755 root-owned directory (rx for others) blocks creation."""
        fs = _make_fs()
        result = fs.create_file("/etc/new.txt", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_create_file_denied_with_write_but_no_execute(self):
        """A 0300 directory grants write but not search; creation still denied."""
        fs = _make_fs()
        result = fs.create_file("/nox/new.txt", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_create_directory_denied_in_readonly_parent(self):
        """mkdir in a non-writable directory is denied."""
        fs = _make_fs()
        result = fs.create_directory("/etc/newdir", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_create_directory_allowed_in_writable_parent(self):
        """mkdir in the owner's writable directory succeeds."""
        fs = _make_fs()
        result = fs.create_directory("/home/user/newdir", acting_user=USER_OWNER)
        assert_success(result)

    def test_root_bypasses_create_gate(self):
        """Root creates anywhere regardless of parent permissions."""
        fs = _make_fs()
        result = fs.create_file("/etc/rooted.txt", acting_user=ROOT_USER)
        assert_success(result)


class TestDeleteEnforcement:
    """Deletion is authorized on the parent directory: WRITE + EXECUTE."""

    def test_non_owner_cannot_delete_root_file(self):
        """Regression: a non-root user cannot remove a root-owned file."""
        fs = _make_fs()
        result = fs.delete_file("/etc/hostname", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED
        assert fs.get_node("/etc/hostname").content == "simnux-edge"

    def test_file_write_bits_do_not_grant_deletion(self):
        """Regression: the file's own writable mode never authorizes removal."""
        fs = _make_fs()
        assert fs.check_access("/etc/owned-writable", Access.WRITE, USER_OWNER).exit_code == 0
        result = fs.delete_file("/etc/owned-writable", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_delete_denied_with_write_but_no_execute_parent(self):
        """A 0300 parent denies removal even for files the user owns."""
        fs = _make_fs()
        assert fs.check_access("/nox/bits", Access.WRITE, USER_OWNER).exit_code == 0
        result = fs.delete_file("/nox/bits", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_owner_removes_own_file(self):
        """The owner removes their file from a directory they can modify."""
        fs = _make_fs()
        fs.create_file("/home/user/drop.txt", acting_user=USER_OWNER)
        result = fs.delete_file("/home/user/drop.txt", acting_user=USER_OWNER)
        assert_success(result)
        assert (
            CommandError.NOT_FOUND in fs.read("/home/user/drop.txt", acting_user=USER_OWNER).message
        )

    def test_root_can_delete_anywhere(self):
        """Root removes files regardless of parent permissions."""
        fs = _make_fs()
        result = fs.delete_file("/etc/secret", acting_user=ROOT_USER)
        assert_success(result)

    def test_delete_directory_gated_on_parent(self):
        """``delete_directory`` uses the same parent WRITE+EXECUTE gate."""
        fs = _make_fs()
        assert fs.get_node("/etc/rootdir").is_directory
        denied = fs.delete_directory("/etc/rootdir", acting_user=USER_OWNER)
        assert_not_success(denied)
        assert denied.message == CommandError.PERMISSION_DENIED

    def test_delete_directory_allowed_with_parent_access(self):
        """rmdir of an own directory inside a modifiable parent succeeds."""
        fs = _make_fs()
        fs.create_directory("/home/user/scratch", acting_user=USER_OWNER)
        result = fs.delete_directory("/home/user/scratch", acting_user=USER_OWNER)
        assert_success(result)

    def test_touch_missing_path_gated_on_parent(self):
        """Creating via ``touch`` enforces the same parent gate as create_file."""
        fs = _make_fs()
        denied = fs.touch("/etc/new.txt", acting_user=USER_OWNER)
        assert_not_success(denied)
        assert denied.message == CommandError.PERMISSION_DENIED
        allowed = fs.touch("/home/user/new.txt", acting_user=USER_OWNER)
        assert_success(allowed)


class TestMoveCompositeEnforcement:
    """Rename/move permission checks: target creation gate + source deletion gate."""

    def test_move_own_files_allowed(self):
        """A move within an owner-modifiable directory succeeds end to end."""
        fs = _make_fs()
        fs.create_file("/home/user/a.txt", acting_user=USER_OWNER)
        fs.write("/home/user/a.txt", "content", acting_user=USER_OWNER)
        assert_success(fs.touch("/home/user/b.txt", acting_user=USER_OWNER))
        assert_success(fs.write("/home/user/b.txt", "content", acting_user=USER_OWNER))
        assert_success(fs.delete_file("/home/user/a.txt", acting_user=USER_OWNER))
        assert CommandError.NOT_FOUND in fs.read("/home/user/a.txt", acting_user=USER_OWNER).message

    def test_move_target_creation_gate(self):
        """Target construction inside a non-writable directory is denied."""
        fs = _make_fs()
        result = fs.touch("/etc/target.txt", acting_user=USER_OWNER)
        assert_not_success(result)
        assert result.message == CommandError.PERMISSION_DENIED

    def test_move_source_deletion_gate_with_cleanup(self):
        """Source removal in an unmodifiable directory is denied; target is rolled back."""
        fs = _make_fs()
        assert_success(fs.touch("/home/user/target.txt", acting_user=USER_OWNER))
        assert_success(fs.write("/home/user/target.txt", "simnux-edge", acting_user=USER_OWNER))
        denied = fs.delete_file("/etc/hostname", acting_user=USER_OWNER)
        assert_not_success(denied)
        assert denied.message == CommandError.PERMISSION_DENIED
        assert fs.get_node("/etc/hostname").content == "simnux-edge"


class TestAuthorizationMatrix:
    """Audit table: operation x acting user x expected allowed/denied.

    Mirrors the runtime enforcement matrix in one place so a regression in any
    gate (read/write/create/delete/list/cd/chmod/root-bypass) surfaces here.
    """

    def _matrix(self):
        fs = _make_fs()
        fs.create_file("/home/user/owned.txt", acting_user=USER_OWNER)
        fs.write("/home/user/owned.txt", "data", acting_user=USER_OWNER)
        fs.create_file("/home/user/notes.txt", acting_user=USER_OWNER)
        fs.write("/home/user/notes.txt", "chmod target", acting_user=USER_OWNER)
        fs.create_directory("/home/user/box", acting_user=USER_OWNER)
        cases = [
            # (label, result, allowed)
            (
                "read world-readable /etc/hostname by user",
                fs.read("/etc/hostname", acting_user=USER_OWNER),
                True,
            ),
            (
                "read sealed /etc/secret by user",
                fs.read("/etc/secret", acting_user=USER_OWNER),
                False,
            ),
            (
                "read /etc/secret by root",
                fs.read("/etc/secret", acting_user=ROOT_USER),
                True,
            ),
            (
                "write own file by user",
                fs.write("/home/user/owned.txt", "v2", acting_user=USER_OWNER),
                True,
            ),
            (
                "write sealed /etc/secret by user",
                fs.write("/etc/secret", "v2", acting_user=USER_OWNER),
                False,
            ),
            (
                "append world-readable by user",
                fs.append("/etc/hostname", "\n", acting_user=USER_OWNER),
                False,
            ),
            (
                "touch existing /etc/hostname by user",
                fs.touch("/etc/hostname", acting_user=USER_OWNER),
                False,
            ),
            (
                "touch existing /etc/hostname by root",
                fs.touch("/etc/hostname", acting_user=ROOT_USER),
                True,
            ),
            (
                "create file in /etc by user",
                fs.create_file("/etc/n", acting_user=USER_OWNER),
                False,
            ),
            (
                "create file in /home/user by user",
                fs.create_file("/home/user/n.txt", acting_user=USER_OWNER),
                True,
            ),
            (
                "create file in /etc by root",
                fs.create_file("/etc/n", acting_user=ROOT_USER),
                True,
            ),
            (
                "mkdir in /etc by user",
                fs.create_directory("/etc/n", acting_user=USER_OWNER),
                False,
            ),
            (
                "mkdir in /home/user by user",
                fs.create_directory("/home/user/ndir", acting_user=USER_OWNER),
                True,
            ),
            (
                "delete /etc/hostname by user",
                fs.delete_file("/etc/hostname", acting_user=USER_OWNER),
                False,
            ),
            (
                "delete /etc/hostname by root",
                fs.delete_file("/etc/hostname", acting_user=ROOT_USER),
                True,
            ),
            (
                "delete own home file by user",
                fs.delete_file("/home/user/owned.txt", acting_user=USER_OWNER),
                True,
            ),
            (
                "rmdir /etc/rootdir by user",
                fs.delete_directory("/etc/rootdir", acting_user=USER_OWNER),
                False,
            ),
            (
                "rmdir own home dir by user",
                fs.delete_directory("/home/user/box", acting_user=USER_OWNER),
                True,
            ),
            (
                "list sealed /locked by user",
                fs.list_directory("/locked", acting_user=USER_OWNER),
                True,
            ),
            (
                "list sealed /locked by teammate",
                fs.list_directory("/locked", acting_user=TEAM_USER),
                False,
            ),
            (
                "cd into sealed /locked by teammate",
                fs.validate_directory("/locked", acting_user=TEAM_USER),
                False,
            ),
        ]
        chmod_result = fs.chmod("/home/user/notes.txt", 0o644, acting_user=USER_OWNER)
        cases.append(("chmod own file by user", chmod_result, True))
        chmod_denied = fs.chmod("/etc/hostname", 0o644, acting_user=USER_OWNER)
        cases.append(("chmod root-owned file by user", chmod_denied, False))
        return cases

    def test_authorization_matrix(self):
        """Every row of the operation/user matrix behaves as documented."""
        for label, result, allowed in self._matrix():
            if allowed:
                assert result.exit_code == 0, f"{label}: expected allowed but denied"
            else:
                assert result.exit_code != 0, f"{label}: expected denied but allowed"
