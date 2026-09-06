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
