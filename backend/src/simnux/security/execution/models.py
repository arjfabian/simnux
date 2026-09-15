"""Execution identity facsimile: the credentials and context a workload runs as.

Distinguishes *identity* (which scenario-local ``SNXUser``/``SNXGroup`` exist)
from *execution* (the credential set under which a specific piece of work is
performed). The authorization layer consumes these; nothing here references
filesystems, commands, sessions, or clients.

These types are intentionally minimal:

* ``ExecutionCredentials`` — who the work is performed as (real/effective
  identity, group credentials, reserved privilege information).
* ``ExecutionContext`` — the security state under which a piece of simulated
  work is performed. Future mechanisms that transform or constrain execution
  (privilege elevation, a restricted execution view) will derive new contexts
  from this one; none of those mechanisms are implemented yet.

The ``SNXShell`` owns the current execution context; commands and the filesystem
receive it as the authorization subject. An execution context never identifies
a SIMNUX session or client.
"""

from __future__ import annotations

from dataclasses import dataclass

from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


@dataclass(frozen=True)
class ExecutionCredentials:
    """The real/effective identities and group credentials for a workload.

    * ``real_user`` — the identity that initiated the interaction. Today it
      always equals ``effective_user``; no real/effective split exists yet,
      but the model can represent one.
    * ``effective_user`` — the identity whose permissions gate operations.
    * ``primary_group`` — the group used to own newly created resources.
      ``None`` means the execution carries no primary group (the identity has
      no designated native group). It never means "root member": membership
      for authorization is exactly the ``groups`` tuple below, and carrying no
      primary group never grants root-group membership or root privilege.
    * ``supplementary_groups`` — additional scenario-local groups the acting
      identity belongs to; permission evaluation consults these.
    * ``privileges`` — reserved. No privilege mechanism exists yet; kept so the
      model can later represent granted privileges without a type change.

    ``groups`` exposes primary + supplementary in a single membership tuple.
    """

    real_user: SNXUser
    effective_user: SNXUser
    primary_group: SNXGroup | None = None
    supplementary_groups: tuple[SNXGroup, ...] = ()
    privileges: frozenset[str] = frozenset()

    @property
    def groups(self) -> tuple[SNXGroup, ...]:
        """Every scenario-local group this execution belongs to.

        With ``primary_group`` unset the tuple is exactly
        ``supplementary_groups``; an identity without group membership (or
        without a membership view) is in no group, never in the root group.
        """
        if self.primary_group is None:
            return self.supplementary_groups
        return (self.primary_group, *self.supplementary_groups)

    @classmethod
    def for_user(
        cls,
        user: SNXUser,
        membership: SNXGroupMembership | None = None,
    ) -> ExecutionCredentials:
        """Build credentials for *user*, deriving the primary and any
        supplementary groups from a scenario membership view.

        When a membership view is supplied, the user's primary group becomes
        ``primary_group`` and every other group the user belongs to is carried
        as ``supplementary_groups`` (distinct from the primary). Without a
        membership view the user has no group memberships — in no group other
        than ownership would imply, and never a root-group member.
        """
        if membership is None:
            return cls(
                real_user=user,
                effective_user=user,
            )

        primary_group = membership.primary_group(user)
        primary_group_id = primary_group.group_id if primary_group is not None else None

        supplementary_groups: list[SNXGroup] = []
        for group_id in sorted(membership.group_ids_of(user)):
            if group_id == primary_group_id:
                continue
            group = membership.group_of(group_id)
            if group is None:
                raise ValueError(
                    f"membership for {user.identifier!r} references group id "
                    f"{group_id} that cannot be resolved to an SNXGroup"
                )
            supplementary_groups.append(group)

        return cls(
            real_user=user,
            effective_user=user,
            primary_group=primary_group,
            supplementary_groups=tuple(supplementary_groups),
        )


@dataclass(frozen=True)
class ExecutionContext:
    """The security state under which a piece of simulated work is performed.

    Wraps the current :class:`ExecutionCredentials`. This is the abstraction a
    future privilege/execution-view mechanism will transform or constrain; for
    now it simply carries the credentials of the current interaction.

    The shell owns the current execution context and hands it to commands; the
    filesystem optionally receives it as the authorization subject. It never
    identifies a SIMNUX session or client.
    """

    credentials: ExecutionCredentials

    @property
    def effective_user(self) -> SNXUser:
        """The identity whose permissions gate the current work."""
        return self.credentials.effective_user

    @classmethod
    def for_user(
        cls,
        user: SNXUser,
        membership: SNXGroupMembership | None = None,
    ) -> ExecutionContext:
        return cls(credentials=ExecutionCredentials.for_user(user, membership))

    @classmethod
    def root(cls) -> ExecutionContext:
        """A privileged system context (``user_id == 0``), for tooling/tests
        that perform system-level work with no scenario actor.
        """
        return cls.for_user(SNXUser(0, "root"))
