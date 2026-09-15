"""Unit tests for the single authoritative authorization policy.

Covers owner/group/other class selection, the never-combined precedence rule,
root bypass, and the numeric mode <-> SNXPermissions round-trip helpers.
Authorization is asked through :class:`AuthorizationPolicy` with abstract
:class:`ProtectedResource`/:class:`AccessRequest` subjects built from real
execution contexts — the same contract the VFS uses.
"""

import pytest

from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.models import mode_from_permissions
from simnux.core.filesystem.models import permissions_from_mode
from simnux.security.authorization.models import Access
from simnux.security.authorization.models import AccessRequest
from simnux.security.authorization.models import PermissionFlags
from simnux.security.authorization.models import ProtectedResource
from simnux.security.authorization.models import SNXPermissions
from simnux.security.authorization.policy import AuthorizationPolicy
from simnux.security.execution.models import ExecutionContext
from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


ROOT_USER = SNXUser(0, "root")
ROOT_GROUP = SNXGroup(0, "root")
OWNER = SNXUser(1001, "owner")
MEMBER = SNXUser(1002, "member")
OUTSIDER = SNXUser(1003, "outsider")
TEAM = SNXGroup(1002, "team")


def _membership() -> SNXGroupMembership:
    """MEMBER belongs to TEAM — a group named differently from the member."""
    return SNXGroupMembership(
        _group_ids_by_user={MEMBER.user_id: frozenset([TEAM.group_id])},
        _primary_groups={MEMBER.user_id: TEAM},
        _groups_by_id={TEAM.group_id: TEAM},
    )


ROOT_EXEC = ExecutionContext.for_user(ROOT_USER)
OWNER_EXEC = ExecutionContext.for_user(OWNER)
MEMBER_EXEC = ExecutionContext.for_user(MEMBER, _membership())
OUTSIDER_EXEC = ExecutionContext.for_user(OUTSIDER)


def _resource(permissions: SNXPermissions) -> ProtectedResource:
    return ProtectedResource(owner=OWNER, group=TEAM, permissions=permissions)


def _request(subject: ExecutionContext, resource: ProtectedResource, right: Access) -> bool:
    return AuthorizationPolicy().authorize(
        AccessRequest(subject=subject, resource=resource, right=right)
    )


class TestClassSelection:
    def test_owner_uses_user_bits(self):
        """The resource owner is matched against the user tier."""
        resource = _resource(
            SNXPermissions(
                user=PermissionFlags(read=False, write=False, execute=True),
                group=PermissionFlags.rwx(),
                other=PermissionFlags.rwx(),
            )
        )
        assert _request(OWNER_EXEC, resource, Access.EXECUTE) is True
        assert _request(OWNER_EXEC, resource, Access.READ) is False
        assert _request(OWNER_EXEC, resource, Access.WRITE) is False

    def test_group_member_uses_group_bits(self):
        """A member of the resource's group is matched against the group tier."""
        resource = _resource(
            SNXPermissions(
                user=PermissionFlags(),
                group=PermissionFlags(read=True, write=True, execute=True),
                other=PermissionFlags(),
            )
        )
        assert _request(MEMBER_EXEC, resource, Access.READ) is True
        assert _request(MEMBER_EXEC, resource, Access.WRITE) is True
        assert _request(MEMBER_EXEC, resource, Access.EXECUTE) is True

    def test_outsider_uses_other_bits(self):
        """Everyone else is matched against the other tier."""
        resource = _resource(
            SNXPermissions(
                user=PermissionFlags.rw(),
                group=PermissionFlags(),
                other=PermissionFlags.r(),
            )
        )
        assert _request(OUTSIDER_EXEC, resource, Access.READ) is True
        assert _request(OUTSIDER_EXEC, resource, Access.WRITE) is False

    def test_supplementary_group_member_uses_group_bits(self):
        """A member via a supplementary group matches the group tier."""
        auxiliary = SNXGroup(2002, "aux")
        execs = ExecutionContext.for_user(
            MEMBER,
            SNXGroupMembership(
                _group_ids_by_user={
                    MEMBER.user_id: frozenset([TEAM.group_id, auxiliary.group_id]),
                },
                _primary_groups={MEMBER.user_id: TEAM},
                _groups_by_id={
                    TEAM.group_id: TEAM,
                    auxiliary.group_id: auxiliary,
                },
            ),
        )
        assert execs.credentials.primary_group == TEAM
        assert execs.credentials.supplementary_groups == (auxiliary,)
        resource = ProtectedResource(
            owner=OWNER,
            group=auxiliary,
            permissions=SNXPermissions(
                user=PermissionFlags(),
                group=PermissionFlags(read=True, write=True),
                other=PermissionFlags(),
            ),
        )
        assert _request(execs, resource, Access.READ) is True
        assert _request(execs, resource, Access.WRITE) is True

    def test_no_membership_is_not_root_group_member(self):
        """An identity with no membership view is never in the root group.

        Absent a membership view, the execution has an empty group set. A
        root-group resource must not grant it the group tier (and root
        privilege is decided purely by ``user_id == 0``, so it is not
        privileged either).
        """
        execs = ExecutionContext.for_user(OUTSIDER)
        assert execs.credentials.primary_group is None
        assert execs.credentials.groups == ()
        root_resource = ProtectedResource(
            owner=ROOT_USER,
            group=ROOT_GROUP,
            permissions=SNXPermissions(
                user=PermissionFlags(),
                group=PermissionFlags(read=True, write=True, execute=True),
                other=PermissionFlags(),
            ),
        )
        assert _request(execs, root_resource, Access.READ) is False
        assert _request(execs, root_resource, Access.WRITE) is False
        assert _request(execs, root_resource, Access.EXECUTE) is False
        assert AuthorizationPolicy().is_privileged(execs) is False


class TestPrecedence:
    def test_owner_wins_over_group(self):
        """Owner class is decided first and never combined with group bits."""
        resource = _resource(
            SNXPermissions(
                user=PermissionFlags(read=False, write=False, execute=False),
                group=PermissionFlags.rwx(),
                other=PermissionFlags.r(),
            )
        )
        assert _request(OWNER_EXEC, resource, Access.READ) is False
        assert _request(OWNER_EXEC, resource, Access.WRITE) is False

    def test_group_wins_over_other(self):
        """Group member class is decided before other bits."""
        resource = _resource(
            SNXPermissions(
                user=PermissionFlags.rw(),
                group=PermissionFlags(read=False, write=False, execute=False),
                other=PermissionFlags.rwx(),
            )
        )
        assert _request(MEMBER_EXEC, resource, Access.READ) is False

    def test_owner_not_rerolled_as_group_member(self):
        """An owner who is also a group member still uses only owner bits."""
        owner_exec = ExecutionContext.for_user(
            OWNER,
            SNXGroupMembership(
                _group_ids_by_user={OWNER.user_id: frozenset([TEAM.group_id])},
                _primary_groups={OWNER.user_id: TEAM},
                _groups_by_id={TEAM.group_id: TEAM},
            ),
        )
        resource = _resource(
            SNXPermissions(
                user=PermissionFlags(read=True, write=True),
                group=PermissionFlags(read=True, write=True, execute=True),
                other=PermissionFlags(),
            )
        )
        assert _request(owner_exec, resource, Access.WRITE) is True
        assert _request(owner_exec, resource, Access.EXECUTE) is False


class TestRootBypass:
    def test_root_bypasses_all_checks(self):
        """``user_id == 0`` bypasses class-based checks entirely."""
        resource = _resource(SNXPermissions())
        assert _request(ROOT_EXEC, resource, Access.READ) is True
        assert _request(ROOT_EXEC, resource, Access.WRITE) is True
        assert _request(ROOT_EXEC, resource, Access.EXECUTE) is True

    def test_root_needs_no_ownership(self):
        """Root bypasses even when it neither owns nor belongs to the group."""
        resource = _resource(SNXPermissions())
        assert _request(ROOT_EXEC, resource, Access.WRITE) is True


class TestOwnershipAndPrivilegeQueries:
    def test_is_owner(self):
        """``is_owner`` matches the effective identity against the owner."""
        policy = AuthorizationPolicy()
        resource = _resource(SNXPermissions())
        assert policy.is_owner(OWNER_EXEC, resource) is True
        assert policy.is_owner(MEMBER_EXEC, resource) is False

    def test_is_privileged(self):
        """``is_privileged`` reflects the root (user_id == 0) policy."""
        policy = AuthorizationPolicy()
        assert policy.is_privileged(ROOT_EXEC) is True
        assert policy.is_privileged(OWNER_EXEC) is False
        assert policy.is_privileged(MEMBER_EXEC) is False


class TestModeHelpers:
    @pytest.mark.parametrize(
        "mode",
        [0o000, 0o400, 0o600, 0o644, 0o664, 0o700, 0o754, 0o755, 0o777],
    )
    def test_mode_round_trip(self, mode):
        """``permissions_from_mode`` and ``mode_from_permissions`` are inverses."""
        permissions = permissions_from_mode(mode)
        assert mode_from_permissions(permissions) == mode

    def test_mode_644_decodes(self):
        """0o644 means owner rw, group r, other r."""
        permissions = permissions_from_mode(0o644)
        assert permissions.user == PermissionFlags(read=True, write=True, execute=False)
        assert permissions.group == PermissionFlags(read=True, write=False, execute=False)
        assert permissions.other == PermissionFlags(read=True, write=False, execute=False)

    @pytest.mark.parametrize("bad_mode", [-1, 0o1000, 0o2000, 0o4000, 0o7777])
    def test_mode_out_of_range_rejected(self, bad_mode):
        """Modes carrying setuid/sticky or out-of-range bits are rejected."""
        with pytest.raises(ValueError):
            permissions_from_mode(bad_mode)

    def test_file_default_preset(self):
        """Presets are 0644/0755, matching the gate semantics of the policy."""
        assert mode_from_permissions(PermissionPresets.FILE_DEFAULT) == 0o644
        assert mode_from_permissions(PermissionPresets.DIRECTORY_DEFAULT) == 0o755


class TestNodeSize:
    """``SNXNode.size`` is the live UTF-8 byte length of the file content."""

    def _node(self, content: str | None, is_directory: bool = False) -> SNXNode:
        return SNXNode(
            path="/etc/hostname",
            owner=OWNER,
            group=TEAM,
            content=content,
            is_directory=is_directory,
            permissions=PermissionPresets.FILE_DEFAULT,
        )

    def test_ascii_content_bytes(self):
        assert self._node("hello world").size == 11

    def test_empty_file_zero(self):
        assert self._node("").size == 0

    def test_none_content_zero(self):
        assert self._node(None).size == 0

    def test_multibyte_utf8_bytes(self):
        """Size counts UTF-8 code-unit bytes, not characters."""
        assert self._node("héllo").size == 6  # é is 2 bytes in UTF-8
        assert self._node("日本語").size == 9
        assert self._node("a💡").size == 5  # emoji is 4 bytes

    def test_directory_zero(self):
        """Directories do not report a simulated filesystem size yet."""
        assert self._node("", is_directory=True).size == 0
        assert self._node(None, is_directory=True).size == 0

    def test_node_survives_content_reassignment(self):
        """Size reflects the current content, so it cannot go stale."""
        node = self._node("small")
        assert node.size == 5
        node.content = "a considerably longer payload"
        assert node.size == len(b"a considerably longer payload")
