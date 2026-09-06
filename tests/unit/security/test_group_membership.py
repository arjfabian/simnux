"""Tests for scenario-local group membership resolution (``SNXGroupMembership``).

Membership is built at the composition root from ``SNXScenario.users`` /
``SNXScenario.groups`` (one group per user, matched by identifier) and injected
into the filesystem for permission evaluation.
"""

from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


ROOT_USER = SNXUser(0, "root")
ROOT_GROUP = SNXGroup(0, "root")
USER_OWNER = SNXUser(1001, "user")
USER_GROUP = SNXGroup(1001, "user")
OPS = SNXUser(1002, "ops")
OPS_GROUP = SNXGroup(1002, "ops")


def _membership() -> SNXGroupMembership:
    return SNXGroupMembership.from_identities(
        {
            "root": ROOT_USER,
            "user": USER_OWNER,
            "ops": OPS,
        },
        {
            "root": ROOT_GROUP,
            "user": USER_GROUP,
            "ops": OPS_GROUP,
        },
    )


class TestGroupMembership:
    def test_user_member_of_matching_group(self):
        """A user belongs to the group whose identifier matches their own."""
        membership = _membership()
        assert membership.is_member(USER_OWNER.user_id, USER_GROUP.group_id) is True

    def test_user_not_member_of_other_group(self):
        """A user does not belong to a group with a different identifier."""
        membership = _membership()
        assert membership.is_member(USER_OWNER.user_id, OPS_GROUP.group_id) is False

    def test_primary_group_matches_identifier(self):
        """The matching group becomes the user's primary group."""
        membership = _membership()
        assert membership.primary_group(USER_OWNER) == USER_GROUP

    def test_group_ids_of(self):
        """``group_ids_of`` returns all scenario-local group ids for a user."""
        membership = _membership()
        assert membership.group_ids_of(USER_OWNER) == frozenset([USER_GROUP.group_id])

    def test_user_without_matching_group_has_no_memberships(self):
        """A user with no matching group simply has no memberships."""
        lone = SNXUser(2000, "lone")
        membership = SNXGroupMembership.from_identities(
            {"root": ROOT_USER, "lone": lone},
            {"root": ROOT_GROUP},
        )
        assert membership.is_member(lone.user_id, ROOT_GROUP.group_id) is False
        assert membership.group_ids_of(lone) == frozenset()
        assert membership.primary_group(lone) is None

    def test_nodes_can_share_a_group(self):
        """Multiple users can belong to one group, enabling group-shared files."""
        membership = SNXGroupMembership.from_identities(
            {
                "root": ROOT_USER,
                "user": USER_OWNER,
                "ops": OPS,
            },
            {
                "root": ROOT_GROUP,
                "user": USER_GROUP,
                "ops": USER_GROUP,  # ops shares the "user" group deliberately
            },
        )
        assert membership.is_member(OPS.user_id, USER_GROUP.group_id) is True
        assert membership.is_member(USER_OWNER.user_id, USER_GROUP.group_id) is True
