"""Mutation-safe identity backbone for scenario world state.

This module owns the *current* scenario identity state and the semantic
operations over it. It is world/application state, not a ``security/``
primitive:

* :class:`IdentityState` — the mutable source of truth for which
  scenario-local users/groups currently exist, their explicit memberships,
  and their primary-group relationships.
* :class:`IdentityManager` — the semantic operation boundary over the state
  (seeding/creation, membership and primary-group establishment, resolution,
  and production of the derived :class:`SNXGroupMembership` view).

The important separations (per the v0.5.4 Identity & Ownership work):

* ``SNXUser``/``SNXGroup`` stay **immutable value objects**; the state never
  mutates them in place — it registers and replaces values only.
* ``SNXGroupMembership`` stays an **immutable derived/view object** consumed
  by ``security/execution``. It is produced from the current state and is a
  snapshot: later state changes do not affect it.
* ``ExecutionCredentials``/``ExecutionContext`` stay **immutable execution
  snapshots**; they never reference the state dynamically.
* Membership is always **explicit**: a user belongs exactly to the groups
  recorded in the state, never inferred from identifier equality. The loader
  convention "one same-named group per user" is expressed as explicit state
  by the bootstrap, not as the semantic definition of membership.

Dependency direction: ``core/scenarios/`` may depend on ``security/`` value
types; ``security/`` must never import this module, and the VFS must never
resolve identities through it (node ownership remains ``SNXUser``/``SNXGroup``
value objects).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field

from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


@dataclass
class IdentityState:
    """Mutable world state: the scenario's current identities and memberships.

    The single authoritative source of truth for which scenario-local users
    and groups *currently* exist, their explicit memberships, and primary
    group relationships. Identities are stored as immutable
    ``SNXUser``/``SNXGroup`` values (never mutated in place). Membership is
    explicit and never inferred from identifier equality: a user belongs
    exactly to the group ids recorded in ``_membership``.

    Identities are indexable and resolvable both by **numeric id** and by
    **identifier/name**, because authorization compares numeric ids while the
    loader/commands/display work with names.

    The mutable registration/membership hooks are low-level; semantic
    operations compose them through :class:`IdentityManager`.
    """

    _users_by_id: dict[int, SNXUser] = field(default_factory=dict)
    _users_by_identifier: dict[str, SNXUser] = field(default_factory=dict)
    _groups_by_id: dict[int, SNXGroup] = field(default_factory=dict)
    _groups_by_identifier: dict[str, SNXGroup] = field(default_factory=dict)
    _membership: dict[int, frozenset[int]] = field(default_factory=dict)
    _primary_groups: dict[int, int] = field(default_factory=dict)

    # ── Resolution ──────────────────────────────────────────────────────

    def user_by_id(self, user_id: int) -> SNXUser | None:
        """Return the user with numeric id *user_id*, or ``None``."""
        return self._users_by_id.get(user_id)

    def user_by_identifier(self, identifier: str) -> SNXUser | None:
        """Return the user with name *identifier*, or ``None``."""
        return self._users_by_identifier.get(identifier)

    def group_by_id(self, group_id: int) -> SNXGroup | None:
        """Return the group with numeric id *group_id*, or ``None``."""
        return self._groups_by_id.get(group_id)

    def group_by_identifier(self, identifier: str) -> SNXGroup | None:
        """Return the group with name *identifier*, or ``None``."""
        return self._groups_by_identifier.get(identifier)

    def all_users(self) -> tuple[SNXUser, ...]:
        """Every registered user (registration order)."""
        return tuple(self._users_by_id.values())

    def all_groups(self) -> tuple[SNXGroup, ...]:
        """Every registered group (registration order)."""
        return tuple(self._groups_by_id.values())

    def member_group_ids(self, user_id: int) -> frozenset[int]:
        """The group ids *user_id* explicitly belongs to (possibly empty)."""
        return self._membership.get(user_id, frozenset())

    def primary_group_id(self, user_id: int) -> int | None:
        """The primary group id of *user_id*, or ``None``."""
        return self._primary_groups.get(user_id)

    def primary_group(self, user_id: int) -> SNXGroup | None:
        """The primary group value of *user_id*, or ``None``."""
        group_id = self._primary_groups.get(user_id)
        if group_id is None:
            return None
        return self._groups_by_id.get(group_id)

    # ── Low-level registration/mutation (composed by IdentityManager) ────

    def register_user(self, user: SNXUser) -> None:
        """Register *user*; raise ``ValueError`` when the id or name is taken."""
        if user.user_id in self._users_by_id:
            raise ValueError(f"user id {user.user_id} is already registered")
        if user.identifier in self._users_by_identifier:
            raise ValueError(f"user identifier {user.identifier!r} is already registered")
        self._users_by_id[user.user_id] = user
        self._users_by_identifier[user.identifier] = user

    def register_group(self, group: SNXGroup) -> None:
        """Register *group*; raise ``ValueError`` when the id or name is taken."""
        if group.group_id in self._groups_by_id:
            raise ValueError(f"group id {group.group_id} is already registered")
        if group.identifier in self._groups_by_identifier:
            raise ValueError(f"group identifier {group.identifier!r} is already registered")
        self._groups_by_id[group.group_id] = group
        self._groups_by_identifier[group.identifier] = group

    def add_membership(self, user_id: int, group_id: int) -> None:
        """Record that *user_id* explicitly belongs to *group_id*.

        Raises ``ValueError`` when either id is unknown.
        """
        if user_id not in self._users_by_id:
            raise ValueError(f"unknown user id {user_id}")
        if group_id not in self._groups_by_id:
            raise ValueError(f"unknown group id {group_id}")
        current = self._membership.get(user_id, frozenset())
        self._membership[user_id] = current | {group_id}

    def set_primary_group(self, user_id: int, group_id: int) -> None:
        """Designate *group_id* as *user_id*'s primary group.

        The primary group is a group the user belongs to, so this also
        records the membership. Raises ``ValueError`` when either id is
        unknown.
        """
        if user_id not in self._users_by_id:
            raise ValueError(f"unknown user id {user_id}")
        if group_id not in self._groups_by_id:
            raise ValueError(f"unknown group id {group_id}")
        self.add_membership(user_id, group_id)
        self._primary_groups[user_id] = group_id


class IdentityManager:
    """Semantic operation boundary over an :class:`IdentityState`.

    Provides the operations bootstrap and (future) identity-management
    commands both use: seeding/creating users and groups, establishing
    explicit membership and primary-group relationships, resolving users and
    groups by id or identifier, and producing the current
    ``SNXGroupMembership`` view for ``security/execution``.

    This iteration intentionally implements only these operations. User
    deletion, group deletion, ``usermod``, ``chown``, password management,
    and uid/gid allocation policy are explicit follow-ups — do not add them
    here.
    """

    def __init__(self, state: IdentityState) -> None:
        self._state = state

    # ── Seeding / creation ──────────────────────────────────────────────

    def seed_group(self, group: SNXGroup) -> None:
        """Begin tracking a scenario-local *group*."""
        self._state.register_group(group)

    def seed_user(
        self,
        user: SNXUser,
        *,
        primary_group: SNXGroup | None = None,
        groups: Iterable[SNXGroup] = (),
    ) -> None:
        """Begin tracking a scenario-local *user* with explicit memberships.

        *primary_group* establishes the user's primary-group relationship
        (which implies membership in it); *groups* are additional explicit
        group memberships. Every referenced group must already be seeded via
        :meth:`seed_group` — the bootstrap seeds groups before users — since
        membership is resolved against the group registry.
        """
        self._state.register_user(user)
        for group in groups:
            self._state.add_membership(user.user_id, group.group_id)
        if primary_group is not None:
            self.set_primary_group(user, primary_group)

    def add_user_to_group(self, user: SNXUser, group: SNXGroup) -> None:
        """Establish explicit membership of *user* in *group*."""
        self._state.add_membership(user.user_id, group.group_id)

    def set_primary_group(self, user: SNXUser, group: SNXGroup) -> None:
        """Establish *group* as *user*'s primary group (implies membership)."""
        self._state.set_primary_group(user.user_id, group.group_id)

    # ── Resolution ──────────────────────────────────────────────────────

    def user_by_id(self, user_id: int) -> SNXUser | None:
        """Resolve a user by numeric id, or ``None``."""
        return self._state.user_by_id(user_id)

    def user_by_identifier(self, identifier: str) -> SNXUser | None:
        """Resolve a user by name, or ``None``."""
        return self._state.user_by_identifier(identifier)

    def group_by_id(self, group_id: int) -> SNXGroup | None:
        """Resolve a group by numeric id, or ``None``."""
        return self._state.group_by_id(group_id)

    def group_by_identifier(self, identifier: str) -> SNXGroup | None:
        """Resolve a group by name, or ``None``."""
        return self._state.group_by_identifier(identifier)

    def users(self) -> tuple[SNXUser, ...]:
        """Every tracked user."""
        return self._state.all_users()

    def groups(self) -> tuple[SNXGroup, ...]:
        """Every tracked group."""
        return self._state.all_groups()

    # ── Derived view ────────────────────────────────────────────────────

    def membership_view(self) -> SNXGroupMembership:
        """The current immutable :class:`SNXGroupMembership` view.

        A snapshot: later state mutations do not affect the returned view.
        This is the object the composition root passes to
        ``ExecutionContext.for_user``; ``security/execution`` never sees
        :class:`IdentityState`.
        """
        group_ids_by_user = {
            user.user_id: self._state.member_group_ids(user.user_id)
            for user in self._state.all_users()
        }
        primary_groups: dict[int, SNXGroup] = {}
        for user in self._state.all_users():
            group = self._state.primary_group(user.user_id)
            if group is not None:
                primary_groups[user.user_id] = group
        groups_by_id = {group.group_id: group for group in self._state.all_groups()}
        return SNXGroupMembership.from_membership_maps(
            group_ids_by_user=group_ids_by_user,
            primary_groups=primary_groups,
            groups_by_id=groups_by_id,
        )
