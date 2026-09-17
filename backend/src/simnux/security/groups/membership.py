"""Scenario-local group membership resolution.

A frozen view over the scenario's users/groups that answers "which
scenario-local groups does this user belong to?" for permission
evaluation. Built at the composition root from ``SNXScenario.users`` /
``SNXScenario.groups`` and injected into the filesystem; filesystem nodes
never carry membership state of their own.

Membership is arbitrary: a user belongs to the scenario groups the view
records, regardless of whether a group's ``identifier`` matches the user's.
``from_identities`` is only a convenience constructor for the
identifier-matching loader convention; it is not the semantic definition of
membership.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field

from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


@dataclass(frozen=True)
class SNXGroupMembership:
    """user_id -> group membership map for a scenario.

    ``_group_ids_by_user`` records every group a user belongs to (by group
    id); ``_primary_groups`` designates the primary ``SNXGroup`` for users
    that have one; ``_groups_by_id`` is the scenario group registry the view
    resolves memberships through. Membership never depends on the user and
    group identifiers matching.

    Invariant: every group id referenced by ``_group_ids_by_user`` is
    resolvable through ``_groups_by_id``. ``from_identities`` satisfies it by
    registering the complete scenario group collection; constructors that
    build memberships directly must register every group they reference.
    """

    _group_ids_by_user: dict[int, frozenset[int]] = field(default_factory=dict)
    _primary_groups: dict[int, SNXGroup] = field(default_factory=dict)
    _groups_by_id: dict[int, SNXGroup] = field(default_factory=dict)

    @classmethod
    def from_membership_maps(
        cls,
        *,
        group_ids_by_user: Mapping[int, frozenset[int]],
        primary_groups: Mapping[int, SNXGroup],
        groups_by_id: Mapping[int, SNXGroup],
    ) -> SNXGroupMembership:
        """Build a membership view from explicit state maps.

        Unlike :meth:`from_identities`, membership here is fully explicit and
        does not depend on user/group identifiers matching. Membership is keyed
        by numeric user id; primary groups map user id to the user's primary
        ``SNXGroup``; ``groups_by_id`` is the scenario group registry the view
        resolves memberships through. Every group id referenced by
        ``group_ids_by_user`` must be resolvable through ``groups_by_id``.
        """
        return cls(
            _group_ids_by_user=dict(group_ids_by_user),
            _primary_groups=dict(primary_groups),
            _groups_by_id=dict(groups_by_id),
        )

    @classmethod
    def from_identities(
        cls,
        users: Mapping[str, SNXUser],
        groups: Mapping[str, SNXGroup],
    ) -> SNXGroupMembership:
        """Build membership from scenario identity collections.

        A user is a member of the group with the same ``identifier`` when one
        exists; that group also becomes the user's primary group. Users
        without a matching group simply have no memberships. This is a
        convenience for the loader convention, not the semantic definition of
        membership.
        """
        group_ids_by_user: dict[int, frozenset[int]] = {}
        primary_groups: dict[int, SNXGroup] = {}

        for identifier, user in users.items():
            group = groups.get(identifier)
            if group is not None:
                group_ids_by_user[user.user_id] = frozenset([group.group_id])
                primary_groups[user.user_id] = group

        return cls(
            _group_ids_by_user=group_ids_by_user,
            _primary_groups=primary_groups,
            _groups_by_id={group.group_id: group for group in groups.values()},
        )

    def is_member(self, user_id: int, group_id: int) -> bool:
        """Return True when *user_id* belongs to *group_id*."""
        return group_id in self._group_ids_by_user.get(user_id, frozenset())

    def group_ids_of(self, user: SNXUser) -> frozenset[int]:
        """All scenario-local group ids the user belongs to."""
        return self._group_ids_by_user.get(user.user_id, frozenset())

    def group_of(self, group_id: int) -> SNXGroup | None:
        """Resolve *group_id* to its scenario group via the registered registry."""
        return self._groups_by_id.get(group_id)

    def primary_group(self, user: SNXUser) -> SNXGroup | None:
        """The user's primary group, when known."""
        return self._primary_groups.get(user.user_id)
