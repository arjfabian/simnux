"""
Core filesystem models for SIMNUX VFS.

Defines nodes, permissions, and filesystem operation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from simnux.runtime.models import ExitCode


@dataclass
class PermissionFlags:
    """Decorative permission flags modeled on Unix r/w/x.

    NOTE: permissions are NOT enforced by the VFS or command layer.
    Currently present for scenario display and future authorization
    integration.
    """

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
    """Three-tier (user/group/other) permission set matching Unix convention.

    Stored per-node but not enforced at read/write time.
    Designed for future enforcement.
    """

    user: PermissionFlags = field(default_factory=PermissionFlags)
    group: PermissionFlags = field(default_factory=PermissionFlags)
    other: PermissionFlags = field(default_factory=PermissionFlags)


class PermissionPresets:
    """Standard permission profiles applied to new nodes.

    Directories get rwxr-xr-x, files get rw-r--r--.
    These mirror Linux defaults (umask 022).
    """

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
    """File or directory node in the virtual filesystem.

    Invariants: ``path`` must be absolute and normalized. ``is_directory``
    and ``deleted`` are mutually non-exclusive but deleted nodes are excluded
    from all read operations.
    """

    path: str
    content: str | None = None

    is_directory: bool = False
    deleted: bool = False

    owner: str = "root"
    group: str = "root"

    # Default permissions are all-False; callers must assign appropriate
    # PermissionPresets. This is intentional — no implicit permissions are
    # assumed on node creation.
    permissions: SNXPermissions = field(default_factory=SNXPermissions)


@dataclass
class FSResult:
    """Result contract for all VFS operations.

    ``success`` property checks ``exit_code == SUCCESS``.
    ``node`` is populated on success; ``message`` carries the error string
    on failure.
    """

    exit_code: ExitCode = ExitCode.SUCCESS
    message: str = ""

    metadata: dict = field(default_factory=dict)

    node: SNXNode | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == ExitCode.SUCCESS


class ContentMode(str, Enum):
    """Write mode selector for VFS write operations.

    NONE: preserve existing content, OVERWRITE: replace, APPEND: concatenate.
    """
    NONE = "none"
    OVERWRITE = "overwrite"
    APPEND = "append"
