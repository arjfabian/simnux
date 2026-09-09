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
    """Unix r/w/x flags enforced by the VFS permission evaluator."""

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


def permissions_from_mode(mode: int) -> SNXPermissions:
    """Decode a numeric permission mode (0..0o777) into three rwx tiers.

    Follows Unix octal encoding: read=4, write=2, execute=1, applied to the
    owner (first digit), group (second), and other (third) classes.

    Raises ``ValueError`` when *mode* carries setuid/setgid/sticky or other
    out-of-range bits (not representable by :class:`SNXPermissions`).
    """
    if mode < 0 or mode > 0o777:
        raise ValueError(f"invalid mode: {mode:o}")

    def _flags(value: int) -> PermissionFlags:
        return PermissionFlags(
            read=bool(value & 0o4),
            write=bool(value & 0o2),
            execute=bool(value & 0o1),
        )

    return SNXPermissions(
        user=_flags((mode >> 6) & 0o7),
        group=_flags((mode >> 3) & 0o7),
        other=_flags(mode & 0o7),
    )


def mode_from_permissions(permissions: SNXPermissions) -> int:
    """Encode an :class:`SNXPermissions` back into a numeric mode."""

    def _oct(flags: PermissionFlags) -> int:
        return (
            (0o4 if flags.read else 0) | (0o2 if flags.write else 0) | (0o1 if flags.execute else 0)
        )

    return (_oct(permissions.user) << 6) | (_oct(permissions.group) << 3) | _oct(permissions.other)


def permissions_symbolic(permissions: SNXPermissions) -> str:
    """Render :class:`SNXPermissions` as the nine-character Unix string.

    Three ``r``/``w``/``x`` triples for the user, group, and other classes,
    each bit shown as its letter or ``-`` when unset. Matches ``ls -l``
    rendering (without the leading file-type column).
    """

    def _triple(flags: PermissionFlags) -> str:
        return (
            ("r" if flags.read else "-")
            + ("w" if flags.write else "-")
            + ("x" if flags.execute else "-")
        )

    return _triple(permissions.user) + _triple(permissions.group) + _triple(permissions.other)


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

    @property
    def size(self) -> int:
        """Byte length of the regular file's UTF-8 encoded content.

        Derived live from ``content`` so it can never go stale: any mutation
        rebuilds the node with new content, and readers always see the current
        state. Empty files, directories, and tombstones (``content`` is
        ``None`` or ``""``) report 0 — directory sizes are not simulated yet.
        """
        if not self.content:
            return 0
        return len(self.content.encode("utf-8"))


@dataclass
class FSResult:
    """VFS operation result contract — exit_code, message, optional node(s)."""

    exit_code: ExitCode = ExitCode.SUCCESS
    message: str = ""

    metadata: dict = field(default_factory=dict)

    node: SNXNode | None = None

    nodes: list[SNXNode] = field(default_factory=list)


class ContentMode(str, Enum):
    """Write mode for VFS write operations: NONE, OVERWRITE, APPEND."""

    NONE = "none"
    OVERWRITE = "overwrite"
    APPEND = "append"
