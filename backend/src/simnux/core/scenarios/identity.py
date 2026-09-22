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

    def remove_user(self, user_id: int) -> None:
        """Unregister *user_id* and drop its memberships and primary-group
        designation. Raises ``ValueError`` when the user is unknown."""
        if user_id not in self._users_by_id:
            raise ValueError(f"unknown user id {user_id}")
        user = self._users_by_id[user_id]
        del self._users_by_id[user_id]
        del self._users_by_identifier[user.identifier]
        self._membership.pop(user_id, None)
        self._primary_groups.pop(user_id, None)

    def remove_group(self, group_id: int) -> None:
        """Unregister *group_id* and remove it from every membership and any
        primary-group designation. Raises ``ValueError`` when the group is
        unknown."""
        if group_id not in self._groups_by_id:
            raise ValueError(f"unknown group id {group_id}")
        group = self._groups_by_id[group_id]
        del self._groups_by_id[group_id]
        del self._groups_by_identifier[group.identifier]
        self._membership = {
            user_id: memberships - {group_id} for user_id, memberships in self._membership.items()
        }
        self._primary_groups = {
            user_id: gid for user_id, gid in self._primary_groups.items() if gid != group_id
        }


class IdentityManager:
    """Semantic operation boundary over an :class:`IdentityState`.

    Provides the operations bootstrap and (future) identity-management
    commands both use: seeding/creating users and groups, deleting users,
    establishing explicit membership and primary-group relationships,
    resolving users and groups by id or identifier, and producing the current
    ``SNXGroupMembership`` view for ``security/execution``.

    Deletion and creation are implemented for users (:meth:`delete_user`,
    :meth:`create_user`) and groups (:meth:`delete_group`, :meth:`create_group`).
    ``usermod``, ``chown``, password management, and id reuse policies remain
    explicit follow-ups — do not add them here.
    """

    DEFAULT_UID_START = 1000
    DEFAULT_GID_START = 1000

    def __init__(
        self,
        state: IdentityState,
        *,
        user_id_start: int = DEFAULT_UID_START,
        gid_start: int = DEFAULT_GID_START,
    ) -> None:
        """Create a manager over *state*.

        *user_id_start* / *gid_start* are the lower bounds for automatic
        user-id / group-id allocation (the policy is "first free id at or
        above this bound"), kept explicit and minimal — never a reuse policy.
        """
        self._state = state
        self._uid_start = user_id_start
        self._gid_start = gid_start

    # ── Seeding / creation ──────────────────────────────────────────────

    def create_user(
        self,
        identifier: str,
        *,
        user_id: int | None = None,
        primary_group: SNXGroup | None = None,
        groups: Iterable[SNXGroup] = (),
    ) -> SNXUser:
        """Create and register a scenario-local user.

        This is the single domain operation that the future ``useradd``
        command and system bootstrap both call; it never delegates to the
        command layer and never touches the filesystem, ``/etc`` projections,
        or ``home`` directories — those remain separate concerns.

        * ``identifier`` — the user's name. Must not already be registered.
        * ``user_id`` — explicit numeric id, or ``None`` to auto-allocate the
          first free id at or above ``user_id_start``.
        * ``primary_group`` — an already-registered group the user joins as
          its primary group. When ``None``, the ``useradd`` default is
          applied: a private group with the same identifier and ``gid ==
          uid`` is created (explicitly, never inferred from name matching)
          and becomes the primary group.
        * ``groups`` — additional already-registered groups the user joins.

        Returns the created immutable :class:`SNXUser` (stored in
        :class:`IdentityState`; never mutated afterwards).

        Raises ``ValueError`` when the identifier or uid is already
        registered, when an explicit primary/supplementary group is not
        registered, or when the private group id (``gid == uid``) collides
        with an already-registered group.
        """
        if self._state.user_by_identifier(identifier) is not None:
            raise ValueError(f"user identifier {identifier!r} is already registered")
        if user_id is None:
            user_id = self._allocate_user_id()
        elif self._state.user_by_id(user_id) is not None:
            raise ValueError(f"user id {user_id} is already registered")

        if primary_group is None:
            # useradd default: a private group named like the user with the
            # same numeric id as the user. Registration raises on collision
            # with an existing group id/identifier (explicit failure).
            private_group = SNXGroup(group_id=user_id, identifier=identifier)
            self._state.register_group(private_group)
            primary_group = private_group
        elif self._state.group_by_id(primary_group.group_id) is None:
            raise ValueError(f"unknown group id {primary_group.group_id}")

        user = SNXUser(user_id=user_id, identifier=identifier)
        self._state.register_user(user)
        for group in groups:
            self._state.add_membership(user.user_id, group.group_id)
        self.set_primary_group(user, primary_group)
        return user

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

    def delete_user(self, identifier: str) -> SNXUser:
        """Delete the scenario-local user named *identifier* from the state.

        The single domain operation that the future ``userdel`` command and
        system teardown both call; it never touches the filesystem, ``/etc``
        projections, or ``home`` directories — those remain separate concerns.

        Removes the user together with its explicit memberships and
        primary-group designation. When the user's primary group is the
        private same-named group created by :meth:`create_user` (``gid ==
        uid`` with the user's identifier) and no other registered user is a
        member of it, that group is removed too, keeping the state consistent
        with the loader's one-same-named-group-per-user convention. Shared or
        explicit primary/supplementary groups are never removed.

        The system root user (``user_id == 0``) cannot be deleted: every
        scenario is seeded with it and the account projection renderers
        assume it exists.

        Returns the removed immutable :class:`SNXUser`.

        Raises ``ValueError`` when the identifier is not registered or names
        the root user. Id/identifier reuse after deletion is out of scope.
        """
        user = self._state.user_by_identifier(identifier)
        if user is None:
            raise ValueError(f"user identifier {identifier!r} is not registered")
        if user.user_id == 0:
            raise ValueError("the system root user cannot be deleted")

        primary = self._state.primary_group(user.user_id)

        self._state.remove_user(user.user_id)

        if (
            primary is not None
            and primary.group_id == user.user_id
            and primary.identifier == user.identifier
            and not any(
                primary.group_id in self._state.member_group_ids(member.user_id)
                for member in self._state.all_users()
            )
        ):
            self._state.remove_group(primary.group_id)

        return user

    def create_group(
        self,
        identifier: str,
        *,
        group_id: int | None = None,
    ) -> SNXGroup:
        """Create and register a scenario-local group.

        The single domain operation that the future ``groupadd`` command and
        system bootstrap both call; it never delegates to the command layer
        and never touches the filesystem or the ``/etc`` projections.

        * ``identifier`` — the group's name. Must not already be registered.
        * ``group_id`` — explicit numeric id, or ``None`` to auto-allocate
          the first free id at or above ``gid_start``.

        Returns the created immutable :class:`SNXGroup` (stored in
        :class:`IdentityState`; never mutated afterwards).

        Raises ``ValueError`` when the identifier is already registered or
        when an explicit group id collides with a registered group.
        """
        if self._state.group_by_identifier(identifier) is not None:
            raise ValueError(f"group identifier {identifier!r} is already registered")
        if group_id is None:
            group_id = self._allocate_group_id()
        elif self._state.group_by_id(group_id) is not None:
            raise ValueError(f"group id {group_id} is already registered")

        group = SNXGroup(group_id=group_id, identifier=identifier)
        self._state.register_group(group)
        return group

    def delete_group(self, identifier: str) -> SNXGroup:
        """Delete the scenario-local group named *identifier* from the state.

        The single domain operation that the future ``groupdel`` command and
        system teardown both call; it never touches the filesystem or the
        ``/etc`` projections.

        Refuses deletion when the group is the primary group of any
        registered user — the relationship is resolved from the state's
        explicit primary-group designations, never inferred from identifier
        equality between the group and a user. Otherwise the group is removed
        together with every membership referencing it (secondary references
        are scrubbed, never inferred).

        Returns the removed immutable :class:`SNXGroup`.

        Raises ``ValueError`` when the identifier is not registered or when
        the group is the primary group of a registered user.
        """
        group = self._state.group_by_identifier(identifier)
        if group is None:
            raise ValueError(f"group identifier {identifier!r} is not registered")

        for user in self._state.all_users():
            primary = self._state.primary_group(user.user_id)
            if primary is not None and primary.group_id == group.group_id:
                raise ValueError(
                    f"group identifier {identifier!r} is the primary group of "
                    f"user {user.identifier!r} and cannot be deleted"
                )

        self._state.remove_group(group.group_id)
        return group

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

    def _allocate_user_id(self) -> int:
        """The first free user id at or above the configured start.

        Minimal and explicit: ids are never reused while registered; reuse
        after deletion is out of scope.
        """
        user_id = self._uid_start
        while self._state.user_by_id(user_id) is not None:
            user_id += 1
        return user_id

    def _allocate_group_id(self) -> int:
        """The first free group id at or above the configured start.

        Minimal and explicit: ids are never reused while registered; reuse
        after deletion is out of scope.
        """
        group_id = self._gid_start
        while self._state.group_by_id(group_id) is not None:
            group_id += 1
        return group_id
