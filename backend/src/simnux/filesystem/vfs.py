"""
Virtual layered filesystem for SIMNUX.

Implements a two-layer model:
- base_layer: immutable scenario state
- delta_layer: session mutations (overlay)
Copies-on-write: delta layer shadows (never mutates) base_layer on read.
"""

from __future__ import annotations

import logging
import posixpath

from simnux.runtime.models import ExitCode
from simnux.commands.errors import CommandError
from .models import FSResult, SNXNode, ContentMode, PermissionPresets


class SNXFileSystem:
    """Two-layer overlay filesystem.

    ``base_layer`` is immutable (scenario-defined); ``delta_layer`` captures
    per-session mutations. Reads merge both layers with delta taking priority.
    Writes always target ``delta_layer``. This enables session isolation
    without copying the entire filesystem tree.
    """

    def __init__(
        self,
        base_layer: dict[str, SNXNode],
        logger: logging.Logger | None = None,
    ) -> None:

        self.base_layer = base_layer
        self.delta_layer: dict[str, SNXNode] = {}
        self.logger = logger

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger.info(message)

    def normalize_path(self, path: str) -> str:
        """Normalize an absolute path.

        Precondition: path must be absolute (starts with '/').
        Raises ValueError otherwise. Normalizes '/../' and duplicate
        slashes via posixpath.normpath.
        """
        if not path.startswith("/"):
            raise ValueError(f"absolute path required: {path!r}")
        return posixpath.normpath(path)

    def resolve_path(
        self,
        current_directory: str,
        target_path: str,
        home_directory: str,
    ) -> str:
        """Resolve shell-style paths to absolute canonical paths.

        Handles ~ expansion (home_directory), relative path resolution, and
        posixpath.normpath normalization. Guaranteed to return '/' or a path
        starting with '/'. Precondition: ``current_directory`` must be
        absolute.
        """

        if target_path.startswith("~"):
            target_path = target_path.replace("~", home_directory, 1)

        if not target_path.startswith("/"):
            target_path = posixpath.join(current_directory, target_path)

        normalized = posixpath.normpath(target_path)

        return normalized if normalized.startswith("/") else "/"

    def validate_directory(self, path: str) -> FSResult:
        """Validate that a path exists and resolves to a directory."""

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

        return FSResult(exit_code=ExitCode.SUCCESS)

    def _all_nodes(self) -> dict[str, SNXNode]:
        """Merge of base_layer and delta_layer with delta taking priority.

        Excludes nodes marked as deleted. The merge is materialized per-call
        — no caching.
        """
        merged = dict(self.base_layer)
        merged.update(self.delta_layer)

        return {
            path: node
            for path, node in merged.items()
            if not node.deleted
        }

    def get_node(self, path: str) -> SNXNode | None:
        """Look up a node in delta_layer first, then base_layer.

        Delta layer is checked first; base_layer is queried only if delta has
        no entry (not even a deleted tombstone). Returns None for deleted
        nodes.
        """
        path = self.normalize_path(path)

        node = self.delta_layer.get(path)
        if node:
            return None if node.deleted else node

        return self.base_layer.get(path)

    def exists(self, path: str) -> bool:
        return self.get_node(path) is not None

    def is_directory(self, path: str) -> bool:
        node = self.get_node(path)
        return bool(node and node.is_directory)

    def read(self, path: str) -> FSResult:
        """Return file content for a given absolute path.

        Returns FSResult with is-directory error if path points to a
        directory. Returns not-found error if path does not exist in either
        layer.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if not node:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if node.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.IS_A_DIRECTORY,
            )

        return FSResult(
            exit_code=ExitCode.SUCCESS,
            node=node,
        )

    def write(
        self,
        path: str,
        *,
        content: str = "",
        content_mode: ContentMode = ContentMode.OVERWRITE,
        create_if_missing: bool = True,
        is_directory: bool = False,
    ) -> FSResult:
        """Write content to a file at the given absolute path.

        Always writes to delta_layer (never base_layer).
        Supports OVERWRITE, APPEND, and NONE content modes.
        Creates intermediate parent directories implicitly.
        On update: preserves existing owner/group/permissions.
        On create: defaults to root:root with FILE_DEFAULT permissions.
        Precondition: path must be absolute.
        """
        path = self.normalize_path(path)
        existing = self.get_node(path)

        if not existing and not create_if_missing:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        if existing and existing.is_directory:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.IS_A_DIRECTORY,
            )

        if existing:
            if content_mode == ContentMode.APPEND:
                content = (existing.content or "") + content
            elif content_mode == ContentMode.NONE:
                content = existing.content or ""

        node = SNXNode(
            path=path,
            content=content,
            is_directory=is_directory,
            owner=getattr(existing, "owner", "root"),
            group=getattr(existing, "group", "root"),
            permissions=getattr(
                existing,
                "permissions",
                PermissionPresets.FILE_DEFAULT,
            ),
        )

        self.delta_layer[path] = node

        return FSResult(
            exit_code=ExitCode.SUCCESS,
            node=node,
        )

    def append(self, path: str, content: str) -> FSResult:
        return self.write(path, content=content, content_mode=ContentMode.APPEND)

    def touch(self, path: str) -> FSResult:
        """Idempotent file creation.

        If the file exists, it is a no-op (no timestamp update — POSIX
        divergence). If it does not exist, creates an empty file in
        delta_layer.
        """
        path = self.normalize_path(path)
        node = self.get_node(path)

        if not node:
            node = SNXNode(path=path, content="", is_directory=False)
            self.delta_layer[path] = node

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def delete(self, path: str) -> FSResult:
        """Marks a node as deleted in delta_layer.

        Does NOT remove the underlying base_layer node — deletion is a
        tombstone in the overlay. Returns error for non-existent paths.
        """
        path = self.normalize_path(path)

        if not self.exists(path):
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.NOT_FOUND,
            )

        self.delta_layer[path] = SNXNode(path=path, deleted=True)
        self._log(f"delete: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS)

    def list_paths(self) -> list[str]:
        return sorted(self._all_nodes().keys())

    def list_directory(self, path: str) -> list[SNXNode]:
        """Returns immediate children of the given directory path.

        Scans merged node set, returns one level deep only. Results are
        deduplicated and sorted by path.
        Precondition: path must be absolute and normalized.
        """
        path = self.normalize_path(path)
        nodes = self._all_nodes()

        results: dict[str, SNXNode] = {}
        prefix = "/" if path == "/" else f"{path}/"

        for node_path in nodes:
            if not node_path.startswith(prefix):
                continue

            relative = node_path[len(prefix):]
            if not relative:
                continue

            first = relative.split("/")[0]
            child_path = "/" + first if path == "/" else f"{path}/{first}"

            child = self.get_node(child_path)
            if child:
                results[child_path] = child

        return sorted(results.values(), key=lambda n: n.path)
