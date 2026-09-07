"""Virtual layered filesystem: immutable base_layer + per-session delta_layer overlay.

Permission enforcement: every permission-sensitive VFS mutation/access gates
on the acting scenario-local user through ``PermissionEvaluator`` — read
(``read``), write (``write``/``append``/``touch`` of an existing file),
execute (``validate_directory``/``check_access``), directory read
(``list_directory``), owner-or-root (``chmod``), and parent-directory
``WRITE + EXECUTE`` for entry creation/removal (``create_file`` /
``create_directory`` / ``touch`` of a missing path / ``delete`` /
``delete_file`` / ``delete_directory``).

Creation and deletion follow Unix directory-entry semantics: they authorize
on the *containing directory* (write+execute there), never on the target
file's own permission bits. Root (``user_id == 0``) bypasses every gate per
the documented root policy.

Intentional simplifications / gaps: ``exists``/``is_directory``/
``list_paths``/``get_node``/``resolve_path`` are informational and
unenforced; ``list_directory``/``validate_directory`` check only the target
directory (no ancestor-path traversal audit); sticky-bit / world-writable
``/tmp`` semantics are not modeled, so only the directory owner (or an
explicitly writable directory) may create/delete entries there.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
import posixpath

from simnux.core.commands.errors import CommandError
from simnux.core.filesystem.models import FSResult
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.models import SNXPermissions
from simnux.core.filesystem.models import permissions_from_mode
from simnux.core.filesystem.permissions import Access
from simnux.core.filesystem.permissions import PermissionEvaluator
from simnux.core.runtime.config import VfsLimits
from simnux.core.runtime.models import ExitCode
from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


_ROOT_USER = SNXUser(0, "root")
_ROOT_GROUP = SNXGroup(0, "root")


class SNXFileSystem:
    """Two-layer overlay filesystem with copy-on-write delta isolation."""

    def __init__(
        self,
        base_layer: dict[str, SNXNode],
        logger: logging.Logger | None = None,
        *,
        vfs_limits: VfsLimits | None = None,
        max_file_bytes: int = 0,
        max_total_bytes: int = 0,
        membership: SNXGroupMembership | None = None,
    ) -> None:
        self.base_layer = base_layer
        self.delta_layer: dict[str, SNXNode] = {}
        self.logger = logger
        if vfs_limits is not None:
            self.max_file_bytes = vfs_limits.max_file_bytes
            self.max_total_bytes = vfs_limits.max_total_bytes
        else:
            self.max_file_bytes = max_file_bytes
            self.max_total_bytes = max_total_bytes

        self._membership = membership or SNXGroupMembership()
        self.permissions = PermissionEvaluator(self._membership)

        self._total_bytes_initialized = False
        self._current_total_bytes = 0

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger.info(message)

    # ── Permission helpers ─────────────────────────────────────────────

    def _denied(self) -> FSResult:
        """FSResult for a permission denial."""
        return FSResult(
            exit_code=ExitCode.ERROR,
            message=CommandError.PERMISSION_DENIED,
        )

    def _owner_group(self, user: SNXUser) -> SNXGroup:
        """Primary group for a newly created node, falling back to root."""
        primary = self._membership.primary_group(user)
        return primary if primary is not None else _ROOT_GROUP

    def _deny_without_parent_access(
        self, parent: SNXNode | None, acting_user: SNXUser
    ) -> FSResult | None:
        """Return a denied FSResult when *acting_user* may not change *parent* entries.

        Unix create/delete semantics authorize on the containing directory:
        the acting user needs BOTH write and execute there. Returns ``None``
        when the mutation is permitted. A missing parent (orphan node) is
        never modifiable, so its absence also denies.
        """
        if parent is None:
            return self._denied()
        can_write = self.permissions.check(acting_user, parent, Access.WRITE)
        can_search = self.permissions.check(acting_user, parent, Access.EXECUTE)
        if can_write and can_search:
            return None
        return self._denied()

    def _parent_node(self, path: str) -> SNXNode | None:
        """The node containing *path* (``/`` is its own parent)."""
        parent_path = str(PurePosixPath(path).parent)
        return self.get_node(parent_path)

    # ── Byte cap helpers ──────────────────────────────────────────────

    def _ensure_total_bytes_initialized(self) -> None:
        """Lazily compute the total byte count across all effective files."""
        if self._total_bytes_initialized:
            return
        for _path, node in self._all_nodes().items():
            if not node.is_directory and node.content:
                self._current_total_bytes += len(node.content.encode("utf-8"))
        self._total_bytes_initialized = True

    def _effective_content_bytes(self, path: str) -> int:
        """Return the byte count of the current effective content for *path*."""
        node = self.get_node(path)
        if node is None or node.is_directory or not node.content:
            return 0
        return len(node.content.encode("utf-8"))

    def _check_write_limit(self, path: str, new_content: str) -> str | None:
        """Return an error string if the write would exceed byte caps, else None."""
        new_bytes = len(new_content.encode("utf-8"))

        if self.max_file_bytes > 0 and new_bytes > self.max_file_bytes:
            return str(CommandError.DISK_QUOTA_EXCEEDED)

        if self.max_total_bytes > 0:
            self._ensure_total_bytes_initialized()
            old_bytes = self._effective_content_bytes(path)
            projected = self._current_total_bytes - old_bytes + new_bytes
            if projected > self.max_total_bytes:
                return str(CommandError.DISK_QUOTA_EXCEEDED)

        return None

    def _apply_byte_delta(self, path: str, old_bytes: int, new_bytes: int) -> None:
        """Update the running total byte counter after a successful write."""
        if self.max_total_bytes <= 0:
            return
        self._current_total_bytes += new_bytes - old_bytes

    # ── Path utilities ────────────────────────────────────────────────

    def normalize_path(self, path: str) -> str:
        """Normalize an absolute path via posixpath.normpath."""
        if not path.startswith("/"):
            raise ValueError(f"absolute path required: {path!r}")
        return posixpath.normpath(path)

    def resolve_path(
        self,
        current_directory: str,
        target_path: str,
        home_directory: str,
    ) -> str:
        """Resolve shell paths to absolute canonical paths (~, relative, .)."""
        if target_path.startswith("~"):
            target_path = target_path.replace("~", home_directory, 1)

        if not target_path.startswith("/"):
            target_path = posixpath.join(current_directory, target_path)

        normalized = posixpath.normpath(target_path)

        return normalized if normalized.startswith("/") else "/"

    def validate_directory(self, path: str, acting_user: SNXUser) -> FSResult:
        """Check path exists, is a directory, and may be entered by *acting_user*.

        Directory traversal is gated on ``EXECUTE`` (Unix-like): the target
        directory only; ancestor-path traversal is a documented v0.5.0 gap.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if not node:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NO_SUCH_FILE_OR_DIR,
            )

        if not node.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_A_DIRECTORY,
            )

        if not self.permissions.check(acting_user, node, Access.EXECUTE):
            return self._denied()

        return FSResult(exit_code=ExitCode.SUCCESS)

    def check_access(self, path: str, access: Access, acting_user: SNXUser) -> FSResult:
        """Check whether *acting_user* may perform *access* on *path*.

        Public entry point for execute/other access needs (e.g. script
        execution). Preserves the read-style diagnostics for missing paths
        and directories so callers keep consistent error messages.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if node is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if access is Access.EXECUTE and node.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.IS_A_DIRECTORY,
            )

        if not self.permissions.check(acting_user, node, access):
            return self._denied()

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def _all_nodes(self) -> dict[str, SNXNode]:
        """Merged view of base_layer + delta_layer (delta wins, tombstones excluded)."""
        merged = dict(self.base_layer)
        merged.update(self.delta_layer)

        return {path: node for path, node in merged.items() if not node.deleted}

    def get_node(self, path: str) -> SNXNode | None:
        """Look up node: delta_layer first, then base_layer. Returns None for tombstones."""
        path = self.normalize_path(path)

        node = self.delta_layer.get(path)
        if node is not None:
            return None if node.deleted else node

        return self.base_layer.get(path)

    def exists(self, path: str) -> bool:
        return self.get_node(path) is not None

    def is_directory(self, path: str) -> bool:
        node = self.get_node(path)
        return bool(node and node.is_directory)

    def create_file(self, path: str, acting_user: SNXUser = _ROOT_USER) -> FSResult:
        """Create an empty regular file owned by *acting_user*.

        Creating an entry requires ``WRITE + EXECUTE`` on the containing
        directory (Unix directory-entry semantics).
        """
        path = self.normalize_path(path)

        if self.exists(path):
            if self.is_directory(path):
                return FSResult(
                    exit_code=ExitCode.ERROR,
                    message=CommandError.IS_A_DIRECTORY,
                )
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.FILE_EXISTS,
            )

        parent_path = str(PurePosixPath(path).parent)
        parent = self.get_node(parent_path)

        if parent is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if not parent.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_A_DIRECTORY,
            )

        denied = self._deny_without_parent_access(parent, acting_user)
        if denied is not None:
            return denied

        node = SNXNode(
            path=path,
            content="",
            is_directory=False,
            owner=acting_user,
            group=self._owner_group(acting_user),
            permissions=PermissionPresets.FILE_DEFAULT,
        )

        self.delta_layer[path] = node
        self._log(f"create_file: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def create_directory(self, path: str, acting_user: SNXUser = _ROOT_USER) -> FSResult:
        """Create an empty directory owned by *acting_user*.

        Creating an entry requires ``WRITE + EXECUTE`` on the containing
        directory (Unix directory-entry semantics).
        """
        path = self.normalize_path(path)

        if self.exists(path):
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.FILE_EXISTS,
            )

        parent_path = str(PurePosixPath(path).parent)
        parent = self.get_node(parent_path)

        if parent is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if not parent.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_A_DIRECTORY,
            )

        denied = self._deny_without_parent_access(parent, acting_user)
        if denied is not None:
            return denied

        node = SNXNode(
            path=path,
            content="",
            is_directory=True,
            owner=acting_user,
            group=self._owner_group(acting_user),
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        )

        self.delta_layer[path] = node
        self._log(f"create_directory: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def read(self, path: str, acting_user: SNXUser) -> FSResult:
        path = self.normalize_path(path)
        node = self.get_node(path)

        if node is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if node.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.IS_A_DIRECTORY,
            )

        if not self.permissions.check(acting_user, node, Access.READ):
            return self._denied()

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def write(self, path: str, content: str, acting_user: SNXUser) -> FSResult:
        path = self.normalize_path(path)
        existing = self.get_node(path)

        if existing is None:
            existing = self.delta_layer.get(path)
            if existing is None:
                existing = self.base_layer.get(path)
            if existing is None:
                return FSResult(
                    exit_code=ExitCode.ERROR,
                    message=CommandError.NOT_FOUND,
                )

        if existing.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.IS_A_DIRECTORY,
            )

        if not self.permissions.check(acting_user, existing, Access.WRITE):
            return self._denied()

        err = self._check_write_limit(path, content)
        if err is not None:
            return FSResult(exit_code=ExitCode.ERROR, message=err)

        old_bytes = self._effective_content_bytes(path)
        new_bytes = len(content.encode("utf-8"))

        node = SNXNode(
            path=path,
            content=content,
            is_directory=False,
            owner=existing.owner,
            group=existing.group,
            permissions=existing.permissions,
        )

        self.delta_layer[path] = node
        self._apply_byte_delta(path, old_bytes, new_bytes)
        self._log(f"write: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def append(self, path: str, content: str, acting_user: SNXUser) -> FSResult:
        path = self.normalize_path(path)
        existing = self.get_node(path)

        if existing is None:
            existing = self.delta_layer.get(path)
            if existing is None:
                existing = self.base_layer.get(path)
            if existing is None:
                return FSResult(
                    exit_code=ExitCode.ERROR,
                    message=CommandError.NOT_FOUND,
                )

        if existing.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.IS_A_DIRECTORY,
            )

        if not self.permissions.check(acting_user, existing, Access.WRITE):
            return self._denied()

        new_content = (existing.content or "") + content
        err = self._check_write_limit(path, new_content)
        if err is not None:
            return FSResult(exit_code=ExitCode.ERROR, message=err)

        old_bytes = self._effective_content_bytes(path)
        new_bytes = len(new_content.encode("utf-8"))

        node = SNXNode(
            path=path,
            content=new_content,
            is_directory=False,
            owner=existing.owner,
            group=existing.group,
            permissions=existing.permissions,
        )

        self.delta_layer[path] = node
        self._apply_byte_delta(path, old_bytes, new_bytes)
        self._log(f"append: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def delete_file(self, path: str, acting_user: SNXUser = _ROOT_USER) -> FSResult:
        """Remove a regular file from its containing directory.

        Removing an entry requires ``WRITE + EXECUTE`` on the parent
        directory — never the target file's own permission bits.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if node is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if node.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.IS_A_DIRECTORY,
            )

        parent = self._parent_node(path)
        denied = self._deny_without_parent_access(parent, acting_user)
        if denied is not None:
            return denied

        self.delta_layer[path] = SNXNode(
            path=path,
            owner=_ROOT_USER,
            group=_ROOT_GROUP,
            deleted=True,
        )
        self._log(f"delete_file: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS)

    def delete_directory(self, path: str, acting_user: SNXUser = _ROOT_USER) -> FSResult:
        """Remove an empty directory from its containing directory.

        Removing an entry requires ``WRITE + EXECUTE`` on the parent
        directory — never the target directory's own permission bits.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if node is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if not node.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_A_DIRECTORY,
            )

        children = self._directory_children(path)

        if children:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.DIRECTORY_NOT_EMPTY,
            )

        parent = self._parent_node(path)
        denied = self._deny_without_parent_access(parent, acting_user)
        if denied is not None:
            return denied

        self.delta_layer[path] = SNXNode(
            path=path,
            owner=_ROOT_USER,
            group=_ROOT_GROUP,
            deleted=True,
        )
        self._log(f"delete_directory: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS)

    def touch(self, path: str, acting_user: SNXUser) -> FSResult:
        """Idempotent file creation (POSIX divergence: no timestamp update).

        Creating a missing file assigns ownership to *acting_user* with
        ``FILE_DEFAULT`` permissions and requires ``WRITE + EXECUTE`` on the
        containing directory. On an existing regular file the modifying
        write permission is required.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if not node:
            parent = self._parent_node(path)
            if parent is None:
                return FSResult(
                    exit_code=ExitCode.ERROR,
                    message=CommandError.NOT_FOUND,
                )

            denied = self._deny_without_parent_access(parent, acting_user)
            if denied is not None:
                return denied

            node = SNXNode(
                path=path,
                owner=acting_user,
                group=self._owner_group(acting_user),
                content="",
                is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            )
            self.delta_layer[path] = node

        if node.is_directory:
            return FSResult(exit_code=ExitCode.SUCCESS, node=node)

        if not self.permissions.check(acting_user, node, Access.WRITE):
            return self._denied()

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def delete(
        self, path: str, delete_dir: bool = False, acting_user: SNXUser = _ROOT_USER
    ) -> FSResult:
        """Mark node as deleted in delta_layer (tombstone). By default, dirs cannot be deleted.

        Removing an entry requires ``WRITE + EXECUTE`` on the parent
        directory (Unix directory-entry semantics).
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if node is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if node.is_directory:
            if not delete_dir:
                return FSResult(
                    exit_code=ExitCode.ERROR,
                    message=CommandError.IS_A_DIRECTORY,
                )

            children = self._directory_children(path)

            if children:
                return FSResult(
                    exit_code=ExitCode.ERROR,
                    message=CommandError.DIRECTORY_NOT_EMPTY,
                )

        parent = self._parent_node(path)
        denied = self._deny_without_parent_access(parent, acting_user)
        if denied is not None:
            return denied

        self.delta_layer[path] = SNXNode(
            path=path,
            owner=_ROOT_USER,
            group=_ROOT_GROUP,
            deleted=True,
        )
        self._log(f"delete: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS)

    def list_paths(self) -> list[str]:
        return sorted(self._all_nodes().keys())

    def list_directory(self, path: str, acting_user: SNXUser) -> FSResult:
        """Read the immediate children of *path* for *acting_user*.

        Listing a directory is gated on ``READ``; on success the children are
        returned in ``FSResult.nodes``. Target-directory only; ancestor
        traversal checks are a documented v0.5.0 gap.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if node is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if not node.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_A_DIRECTORY,
            )

        if not self.permissions.check(acting_user, node, Access.READ):
            return self._denied()

        return FSResult(
            exit_code=ExitCode.SUCCESS,
            nodes=self._directory_children(path),
        )

    def _directory_children(self, path: str) -> list[SNXNode]:
        """Immediate children of *path* (UI tooling / deletion checks only)."""
        path = self.normalize_path(path)
        nodes = self._all_nodes()

        results: dict[str, SNXNode] = {}
        prefix = "/" if path == "/" else f"{path}/"

        for node_path in nodes:
            if not node_path.startswith(prefix):
                continue

            relative = node_path[len(prefix) :]
            if not relative:
                continue

            first = relative.split("/")[0]
            child_path = "/" + first if path == "/" else f"{path}/{first}"

            child = self.get_node(child_path)
            if child:
                results[child_path] = child

        return sorted(results.values(), key=lambda n: n.path)

    def chmod(self, path: str, mode: int, acting_user: SNXUser) -> FSResult:
        """Change the permission bits of an existing node.

        Only *mode* is mutated: path, owner, group, content, directory state,
        and deleted state are preserved. The node owner (or root) may chmod;
        any other user is denied. Files are never created here.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if node is None:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if acting_user.user_id != node.owner.user_id and acting_user.user_id != 0:
            return self._denied()

        permissions: SNXPermissions = permissions_from_mode(mode)

        new_node = SNXNode(
            path=node.path,
            owner=node.owner,
            group=node.group,
            content=node.content,
            is_directory=node.is_directory,
            deleted=node.deleted,
            permissions=permissions,
        )

        self.delta_layer[path] = new_node
        self._log(f"chmod: {path} {mode:o}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=new_node)
