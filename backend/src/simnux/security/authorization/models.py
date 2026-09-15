"""Authorization domain models: access rights, permission profiles, and the
neutral protected-resource descriptor used in access requests.

These types are filesystem-independent: they describe *what* is protected and
*what right* is being requested, never how a filesystem stores or resolves a
node. The VFS builds :class:`ProtectedResource` objects from ``SNXNode`` state
so the policy below stays decoupled from any one resource implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum

from simnux.security.execution.models import ExecutionContext
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


class Access(Enum):
    """Kinds of access the protection system can gate on."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


@dataclass(frozen=True)
class PermissionFlags:
    """Unix r/w/x flags enforced by the authorization policy."""

    read: bool = False
    write: bool = False
    execute: bool = False

    @classmethod
    def rw(cls) -> PermissionFlags:
        return cls(read=True, write=True)

    @classmethod
    def r(cls) -> PermissionFlags:
        return cls(read=True)

    @classmethod
    def rwx(cls) -> PermissionFlags:
        return cls(read=True, write=True, execute=True)

    @classmethod
    def rx(cls) -> PermissionFlags:
        return cls(read=True, execute=True)


@dataclass(frozen=True)
class SNXPermissions:
    """Three-tier (user/group/other) permission set for a protected resource."""

    user: PermissionFlags = field(default_factory=PermissionFlags)
    group: PermissionFlags = field(default_factory=PermissionFlags)
    other: PermissionFlags = field(default_factory=PermissionFlags)


@dataclass(frozen=True)
class ProtectedResource:
    """Abstract protected resource: owner/group identities plus a
    class-based permission profile.

    The VFS constructs these from ``SNXNode``; authorization never sees node
    types, filesystem paths, or commands.
    """

    owner: SNXUser
    group: SNXGroup
    permissions: SNXPermissions


@dataclass(frozen=True)
class AccessRequest:
    """The query authorization answers: may *subject* perform *right* on
    *resource*?"""

    subject: ExecutionContext
    resource: ProtectedResource
    right: Access
