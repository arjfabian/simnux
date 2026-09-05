"""Core filesystem models: nodes, permissions, and operation results."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum

from simnux.core.runtime.models import ExitCode
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


@dataclass
class PermissionFlags:
    """Unix r/w/x flags (NOTE: not enforced by VFS, present for display/future use)."""

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


@dataclass
class SNXPermissions:
    """Three-tier (user/group/other) permission set per node."""

    user: PermissionFlags = field(default_factory=PermissionFlags)
    group: PermissionFlags = field(default_factory=PermissionFlags)
    other: PermissionFlags = field(default_factory=PermissionFlags)


class PermissionPresets:
    """Default permission profiles (Linux umask 022)."""

    FILE_DEFAULT = SNXPermissions(
        user=PermissionFlags.rw(),
        group=PermissionFlags.r(),
        other=PermissionFlags.r(),
    )

    DIRECTORY_DEFAULT = SNXPermissions(
        user=PermissionFlags.rwx(),
        group=PermissionFlags.rx(),
        other=PermissionFlags.rx(),
    )


@dataclass
class SNXNode:
    """File or directory node. Path must be absolute and normalized."""

    path: str

    owner: SNXUser
    group: SNXGroup

    content: str | None = None

    is_directory: bool = False
    deleted: bool = False

    permissions: SNXPermissions = field(default_factory=SNXPermissions)


@dataclass
class FSResult:
    """VFS operation result contract — exit_code, message, optional node."""

    exit_code: ExitCode = ExitCode.SUCCESS
    message: str = ""

    metadata: dict = field(default_factory=dict)

    node: SNXNode | None = None


class ContentMode(str, Enum):
    """Write mode for VFS write operations: NONE, OVERWRITE, APPEND."""

    NONE = "none"
    OVERWRITE = "overwrite"
    APPEND = "append"
