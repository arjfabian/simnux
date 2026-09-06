"""Unit tests for the single authoritative permission evaluator.

Covers owner/group/other class selection, the never-combined precedence rule,
root bypass, and the numeric mode <-> SNXPermissions round-trip helpers.
"""

import pytest

from simnux.core.filesystem.models import PermissionFlags
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.models import SNXPermissions
from simnux.core.filesystem.models import mode_from_permissions
from simnux.core.filesystem.models import permissions_from_mode
from simnux.core.filesystem.permissions import Access
from simnux.core.filesystem.permissions import PermissionEvaluator
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
    return SNXGroupMembership(
        _group_ids_by_user={MEMBER.user_id: frozenset([TEAM.group_id])},
        _primary_groups={MEMBER.user_id: TEAM},
    )


def _node(permissions: SNXPermissions) -> SNXNode:
    return SNXNode(
        path="/data/file.txt",
        owner=OWNER,
        group=TEAM,
        content="data",
        is_directory=False,
        permissions=permissions,
    )


def _evaluator() -> PermissionEvaluator:
    return PermissionEvaluator(_membership())


class TestClassSelection:
    def test_owner_uses_user_bits(self):
        """The node owner is matched against the user tier."""
        evaluator = _evaluator()
        node = _node(
            SNXPermissions(
                user=PermissionFlags(read=False, write=False, execute=True),
                group=PermissionFlags.rwx(),
                other=PermissionFlags.rwx(),
            )
        )
        assert evaluator.check(OWNER, node, Access.EXECUTE) is True
        assert evaluator.check(OWNER, node, Access.READ) is False
        assert evaluator.check(OWNER, node, Access.WRITE) is False

    def test_group_member_uses_group_bits(self):
        """A member of the node's group is matched against the group tier."""
        evaluator = _evaluator()
        node = _node(
            SNXPermissions(
                user=PermissionFlags(),
                group=PermissionFlags(read=True, write=True, execute=True),
                other=PermissionFlags(),
            )
        )
        assert evaluator.check(MEMBER, node, Access.READ) is True
        assert evaluator.check(MEMBER, node, Access.WRITE) is True
        assert evaluator.check(MEMBER, node, Access.EXECUTE) is True

    def test_outsider_uses_other_bits(self):
        """Everyone else is matched against the other tier."""
        evaluator = _evaluator()
        node = _node(
            SNXPermissions(
                user=PermissionFlags.rw(),
                group=PermissionFlags(),
                other=PermissionFlags.r(),
            )
        )
        assert evaluator.check(OUTSIDER, node, Access.READ) is True
        assert evaluator.check(OUTSIDER, node, Access.WRITE) is False


class TestPrecedence:
    def test_owner_wins_over_group(self):
        """Owner class is decided first and never combined with group bits."""
        evaluator = _evaluator()
        node = _node(
            SNXPermissions(
                user=PermissionFlags(read=False, write=False, execute=False),
                group=PermissionFlags.rwx(),
                other=PermissionFlags.r(),
            )
        )
        # Owner has no permissions even though group is fully open.
        assert evaluator.check(OWNER, node, Access.READ) is False
        assert evaluator.check(OWNER, node, Access.WRITE) is False

    def test_group_wins_over_other(self):
        """Group member class is decided before other bits."""
        evaluator = _evaluator()
        node = _node(
            SNXPermissions(
                user=PermissionFlags.rw(),
                group=PermissionFlags(read=False, write=False, execute=False),
                other=PermissionFlags.rwx(),
            )
        )
        # Member has no permissions even though other is fully open.
        assert evaluator.check(MEMBER, node, Access.READ) is False

    def test_owner_not_rerolled_as_group_member(self):
        """An owner who is also a group member still uses only owner bits."""
        evaluator = PermissionEvaluator(
            SNXGroupMembership(
                _group_ids_by_user={
                    OWNER.user_id: frozenset([TEAM.group_id]),
                },
                _primary_groups={OWNER.user_id: TEAM},
            )
        )
        node = _node(
            SNXPermissions(
                user=PermissionFlags(read=True, write=True),
                group=PermissionFlags(read=True, write=True, execute=True),
                other=PermissionFlags(),
            )
        )
        # group bits would grant execute, but owner-bits win (no execute).
        assert evaluator.check(OWNER, node, Access.WRITE) is True
        assert evaluator.check(OWNER, node, Access.EXECUTE) is False


class TestRootBypass:
    def test_root_bypasses_all_checks(self):
        """``user_id == 0`` bypasses permission checks entirely."""
        evaluator = _evaluator()
        node = _node(SNXPermissions())
        assert evaluator.check(ROOT_USER, node, Access.READ) is True
        assert evaluator.check(ROOT_USER, node, Access.WRITE) is True
        assert evaluator.check(ROOT_USER, node, Access.EXECUTE) is True

    def test_root_bypasses_even_when_owner_matches(self):
        """Root needs no ownership to bypass."""
        evaluator = _evaluator()
        node = _node(SNXPermissions())
        assert evaluator.check(ROOT_USER, node, Access.WRITE) is True


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
        """FILE_DEFAULT is 0644 on disk within evaluator tested gate semantics."""
        assert mode_from_permissions(PermissionPresets.FILE_DEFAULT) == 0o644
        assert mode_from_permissions(PermissionPresets.DIRECTORY_DEFAULT) == 0o755
