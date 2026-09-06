"""Scenario-local group membership resolution.

A frozen view over the scenario's users/groups that answers "which
scenario-local groups does this user belong to?" for permission
evaluation. Built at the composition root from ``SNXScenario.users`` /
``SNXScenario.groups`` and injected into the filesystem; filesystem nodes
never carry membership state of their own.
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

    Follows the loader convention of one group per user: a user is a member
    of the group whose ``identifier`` matches the user's ``identifier``, and
    that group is treated as the user's primary group. Supplementary
    membership is not represented in scenario YAML today.
    """

    _group_ids_by_user: dict[int, frozenset[int]] = field(default_factory=dict)
    _primary_groups: dict[int, SNXGroup] = field(default_factory=dict)

    @classmethod
    def from_identities(
        cls,
        users: Mapping[str, SNXUser],
        groups: Mapping[str, SNXGroup],
    ) -> SNXGroupMembership:
        """Build membership from scenario identity collections.

        A user is a member of the group with the same ``identifier`` when one
        exists; that group also becomes the user's primary group. Users
        without a matching group simply have no memberships.
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
        )

    def is_member(self, user_id: int, group_id: int) -> bool:
        """Return True when *user_id* belongs to *group_id*."""
        return group_id in self._group_ids_by_user.get(user_id, frozenset())

    def group_ids_of(self, user: SNXUser) -> frozenset[int]:
        """All scenario-local group ids the user belongs to."""
        return self._group_ids_by_user.get(user.user_id, frozenset())

    def primary_group(self, user: SNXUser) -> SNXGroup | None:
        """The user's primary group, when known."""
        return self._primary_groups.get(user.user_id)
