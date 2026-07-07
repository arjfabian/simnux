"""Virtual layered filesystem: immutable base_layer + per-session delta_layer overlay."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
import posixpath

from simnux.commands.errors import CommandError
from simnux.filesystem.models import FSResult
from simnux.filesystem.models import PermissionPresets
from simnux.filesystem.models import SNXNode
from simnux.runtime.models import ExitCode


class SNXFileSystem:
    """Two-layer overlay filesystem with copy-on-write delta isolation."""

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

    def validate_directory(self, path: str) -> FSResult:
        """Check path exists and is a directory."""
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

    def create_file(self, path: str) -> FSResult:
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

        node = SNXNode(
            path=path,
            content="",
            is_directory=False,
            owner="root",
            group="root",
            permissions=PermissionPresets.FILE_DEFAULT,
        )

        self.delta_layer[path] = node
        self._log(f"create_file: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def create_directory(self, path: str) -> FSResult:
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

        node = SNXNode(
            path=path,
            content="",
            is_directory=True,
            owner="root",
            group="root",
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        )

        self.delta_layer[path] = node
        self._log(f"create_directory: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def read(self, path: str) -> FSResult:
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

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def write(self, path: str, content: str) -> FSResult:
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

        node = SNXNode(
            path=path,
            content=content,
            is_directory=False,
            owner=existing.owner,
            group=existing.group,
            permissions=existing.permissions,
        )

        self.delta_layer[path] = node
        self._log(f"write: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def append(self, path: str, content: str) -> FSResult:
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

        node = SNXNode(
            path=path,
            content=(existing.content or "") + content,
            is_directory=False,
            owner=existing.owner,
            group=existing.group,
            permissions=existing.permissions,
        )

        self.delta_layer[path] = node
        self._log(f"append: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def delete_file(self, path: str) -> FSResult:
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

        self.delta_layer[path] = SNXNode(path=path, deleted=True)
        self._log(f"delete_file: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS)

    def delete_directory(self, path: str) -> FSResult:
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

        children = self.list_directory(path)

        if children:
            return FSResult(
                exit_code=ExitCode.ERROR,
                message=CommandError.DIRECTORY_NOT_EMPTY,
            )

        self.delta_layer[path] = SNXNode(path=path, deleted=True)
        self._log(f"delete_directory: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS)

    def touch(self, path: str) -> FSResult:
        """Idempotent file creation (POSIX divergence: no timestamp update)."""
        path = self.normalize_path(path)
        node = self.get_node(path)

        if not node:
            node = SNXNode(path=path, content="", is_directory=False)
            self.delta_layer[path] = node

        return FSResult(exit_code=ExitCode.SUCCESS, node=node)

    def delete(self, path: str, delete_dir: bool = False) -> FSResult:
        """Mark node as deleted in delta_layer (tombstone). By default, dirs cannot be deleted."""
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

            children = self.list_directory(path)

            if children:
                return FSResult(
                    exit_code=ExitCode.ERROR,
                    message=CommandError.DIRECTORY_NOT_EMPTY,
                )

        self.delta_layer[path] = SNXNode(path=path, deleted=True)
        self._log(f"delete: {path}")

        return FSResult(exit_code=ExitCode.SUCCESS)

    def list_paths(self) -> list[str]:
        return sorted(self._all_nodes().keys())

    def list_directory(self, path: str) -> list[SNXNode]:
        """Return immediate children of the given directory, sorted by path."""
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
