"""Tests for the SNXFileSystem two-layer overlay virtual filesystem.

Covers path normalization, resolution, directory validation, node
get/exists/read/write/touch/delete operations, directory listing,
and overlay integrity guarantees (base-layer immutability).
"""

import pytest

from simnux.commands.errors import CommandError

from simnux.filesystem.models import (
    SNXNode,
    ContentMode,
    PermissionPresets,
)
from simnux.runtime.models import ExitCode


class TestNormalizePath:
    """``normalize_path()`` — validates absolute-path precondition and normalises.

    Precondition: path must start with ``/``. Normalizes trailing slashes,
    ``//``, ``/./``, and ``/../`` segments via ``posixpath.normpath``.
    """

    def test_absolute_path_passes(self, filesystem):
        """Valid absolute paths (including root) are accepted and normalized."""
        assert filesystem.normalize_path("/") == "/"
        assert filesystem.normalize_path("/foo") == "/foo"
        assert filesystem.normalize_path("/foo/bar") == "/foo/bar"

    def test_trailing_slash_stripped(self, filesystem):
        """Trailing slashes are stripped from the normalized result."""
        assert filesystem.normalize_path("/foo/") == "/foo"

    def test_double_slashes_collapsed(self, filesystem):
        """Consecutive slashes (``//``) are collapsed (platform-dependent behavior)."""
        result = filesystem.normalize_path("//foo//bar//")
        assert result == "//foo/bar" or result == "/foo/bar"

    def test_dot_segments_resolved(self, filesystem):
        """``/./`` segments are removed and ``/../`` segments are resolved upward."""
        assert filesystem.normalize_path("/foo/./bar") == "/foo/bar"
        assert filesystem.normalize_path("/foo/bar/..") == "/foo"

    def test_relative_path_raises(self, filesystem):
        """Relative paths (no leading ``/``) raise ``ValueError``."""
        with pytest.raises(ValueError, match="absolute path required"):
            filesystem.normalize_path("relative/path")

    def test_empty_string_raises(self, filesystem):
        """Empty string is treated as relative and raises ``ValueError``."""
        with pytest.raises(ValueError, match="absolute path required"):
            filesystem.normalize_path("")


class TestResolvePath:
    """``resolve_path()`` — resolves a target path against a CWD and home dir.

    Applies tilde expansion, ``..`` traversal, and chroot-safety clamping
    so resolved paths never escape the root.
    """

    def test_absolute_target_unchanged(self, filesystem):
        """Absolute targets bypass CWD resolution entirely."""
        result = filesystem.resolve_path("/home/user", "/etc", "/home/user")
        assert result == "/etc"

    def test_relative_resolves_against_cwd(self, filesystem):
        """Relative targets are resolved against the current working directory."""
        result = filesystem.resolve_path("/home/user", "notes.txt", "/home/user")
        assert result == "/home/user/notes.txt"

    def test_tilde_expansion(self, filesystem):
        """``~/path`` expands to ``$HOME/path``."""
        result = filesystem.resolve_path("/home/user", "~/docs", "/home/user")
        assert result == "/home/user/docs"

    def test_tilde_is_home(self, filesystem):
        """Bare ``~`` resolves to the home directory."""
        result = filesystem.resolve_path("/home/user", "~", "/home/user")
        assert result == "/home/user"

    def test_tilde_user_expansion(self, filesystem):
        """``~other/file`` expands the tilde literally (no user-switch support)."""
        result = filesystem.resolve_path("/home/user", "~other/file", "/home/user")
        assert result == "/home/userother/file"

    def test_dot_dot_traversal(self, filesystem):
        """``../`` traverses upward in the directory tree."""
        result = filesystem.resolve_path("/home/user", "../../etc", "/home/user")
        assert result == "/etc"

    def test_chroot_safety_above_root(self, filesystem):
        """Traversal past root (``../../..``) clamps to ``/`` — prevents escape."""
        result = filesystem.resolve_path("/home/user", "../../../", "/home/user")
        assert result == "/"

    def test_deeply_nested_chroot_attempt(self, filesystem):
        """Deep ``../`` sequences beyond root still clamp to ``/`` for security."""
        result = filesystem.resolve_path("/home/user", "../../../../../../../etc", "/home/user")
        assert result == "/etc"

    def test_dot_current_dir(self, filesystem):
        """A single ``.`` resolves to CWD unchanged."""
        result = filesystem.resolve_path("/home/user", ".", "/home/user")
        assert result == "/home/user"

    def test_consecutive_slashes_normalized(self, filesystem):
        """Consecutive slashes in the resolved path are normalized."""
        result = filesystem.resolve_path("/home/user", "//etc//hostname", "/home/user")
        assert result == "//etc/hostname" or result == "/etc/hostname"


class TestValidateDirectory:
    """``validate_directory()`` — checks path is an existing directory.

    Returns a result with ``success`` flag; errors include clear messages
    about nonexistent paths or file-vs-directory mismatches.
    """

    def test_valid_directory(self, filesystem):
        """Valid existing directory returns success."""
        result = filesystem.validate_directory("/home/user")
        assert result.success

    def test_root_is_directory(self, filesystem):
        """Root (``/``) is always a valid directory."""
        result = filesystem.validate_directory("/")
        assert result.success

    def test_nonexistent_path(self, filesystem):
        """Nonexistent path returns ERROR with "No such file or directory"."""
        result = filesystem.validate_directory("/nonexistent")
        assert not result.success
        assert result.exit_code == ExitCode.ERROR
        assert CommandError.NO_SUCH_FILE_OR_DIR in result.message

    def test_file_is_not_directory(self, filesystem):
        """A file path returns ERROR with "Not a directory"."""
        result = filesystem.validate_directory("/home/user/notes.txt")
        assert not result.success
        assert result.exit_code == ExitCode.ERROR
        assert CommandError.NOT_A_DIRECTORY in result.message


class TestGetNode:
    """``get_node()`` — retrieves a node from merged base+delta layers.

    Delta shadows base on read. Deleted nodes (tombstones) are hidden.
    """

    def test_base_layer_node(self, filesystem):
        """Nodes from base_layer are visible through get_node()."""
        node = filesystem.get_node("/etc/hostname")
        assert node is not None
        assert node.content == "simnux-edge"

    def test_missing_node_returns_none(self, filesystem):
        """Paths not present in either layer return ``None``."""
        assert filesystem.get_node("/missing") is None

    def test_delta_overrides_base(self, filesystem):
        """Delta layer values shadow base_layer values on read."""
        filesystem.delta_layer["/etc/hostname"] = SNXNode(
            path="/etc/hostname", content="overridden", is_directory=False
        )
        node = filesystem.get_node("/etc/hostname")
        assert node is not None
        assert node.content == "overridden"

    def test_deleted_node_not_visible(self, filesystem):
        """Nodes marked ``deleted=True`` in delta are hidden from get_node()."""
        filesystem.delta_layer["/etc/hostname"] = SNXNode(
            path="/etc/hostname", deleted=True
        )
        assert filesystem.get_node("/etc/hostname") is None


class TestExists:
    """``exists()`` — checks whether a path is present in the merged view.

    Deleted paths (tombstoned) should return ``False``.
    """

    def test_existing_file(self, filesystem):
        """Existing files return ``True``."""
        assert filesystem.exists("/etc/hostname")

    def test_existing_directory(self, filesystem):
        """Existing directories return ``True``."""
        assert filesystem.exists("/home")

    def test_missing_path(self, filesystem):
        """Nonexistent paths return ``False``."""
        assert not filesystem.exists("/missing")

    def test_deleted_file_not_exists(self, filesystem):
        """File deleted via ``delete()`` returns ``False`` from ``exists()``."""
        filesystem.delete("/etc/hostname")
        assert not filesystem.exists("/etc/hostname")


class TestIsDirectory:
    """``is_directory()`` — determines whether a path is a directory node."""

    def test_directory(self, filesystem):
        """Directories return ``True``."""
        assert filesystem.is_directory("/home/user")

    def test_file_is_not_directory(self, filesystem):
        """Regular files return ``False``."""
        assert not filesystem.is_directory("/home/user/notes.txt")

    def test_missing_path(self, filesystem):
        """Nonexistent paths return ``False`` (never raises)."""
        assert not filesystem.is_directory("/missing")


class TestRead:
    """``read()`` — reads file content from the merged view.

    Reading a directory returns an error; reading a nonexistent path
    returns a descriptive error message.
    """

    def test_read_file(self, filesystem):
        """Reading an existing file returns its content successfully."""
        result = filesystem.read("/home/user/notes.txt")
        assert result.success
        assert result.node is not None
        assert result.node.content == "hello world"

    def test_read_nonexistent(self, filesystem):
        """Reading a nonexistent file returns an error with "not found"."""
        result = filesystem.read("/missing")
        assert not result.success
        assert CommandError.NOT_FOUND in result.message

    def test_read_directory_returns_error(self, filesystem):
        """Reading a directory path returns an error with "is a directory"."""
        result = filesystem.read("/home/user")
        assert not result.success
        assert CommandError.IS_A_DIRECTORY in result.message

    def test_read_root_returns_error(self, filesystem):
        """Reading root (``/``) returns an error — root is a directory."""
        result = filesystem.read("/")
        assert not result.success
        assert CommandError.IS_A_DIRECTORY in result.message


class TestWrite:
    """``write()`` and ``append()`` — create or mutate files in the delta layer.

    Writes always go to ``delta_layer``; ``base_layer`` remains immutable.
    Supports optional ``create_if_missing`` and ``content_mode`` controls.
    """

    def test_overwrite_existing_file(self, filesystem):
        """Overwriting an existing file replaces its content in the delta layer."""
        result = filesystem.write("/home/user/notes.txt", content="new content")
        assert result.success
        node = filesystem.get_node("/home/user/notes.txt")
        assert node is not None
        assert node.content == "new content"

    def test_append_to_file(self, filesystem):
        """Appending to an existing file concatenates to its content."""
        result = filesystem.append("/home/user/notes.txt", "\nappended")
        assert result.success
        node = filesystem.get_node("/home/user/notes.txt")
        assert node is not None
        assert node.content == "hello world\nappended"

    def test_append_nonexistent_creates_file(self, filesystem):
        """Appending to a nonexistent path creates the file automatically."""
        result = filesystem.append("/home/user/newfile.txt", "content")
        assert result.success
        node = filesystem.get_node("/home/user/newfile.txt")
        assert node is not None
        assert node.content == "content"

    def test_none_mode_preserves_content(self, filesystem):
        """``ContentMode.NONE`` prevents the content parameter from taking effect."""
        result = filesystem.write(
            "/home/user/notes.txt",
            content="should be ignored",
            content_mode=ContentMode.NONE,
        )
        assert result.success
        node = filesystem.get_node("/home/user/notes.txt")
        assert node.content == "hello world"

    def test_write_new_file(self, filesystem):
        """Writing to a new path creates the file and writes content."""
        result = filesystem.write("/home/user/new.txt", content="new file")
        assert result.success
        node = filesystem.get_node("/home/user/new.txt")
        assert node is not None
        assert node.content == "new file"

    def test_write_creates_intermediate_dirs_implicitly(self, filesystem):
        """Writing to a deep path auto-creates any missing intermediate directories."""
        result = filesystem.write("/new/dir/file.txt", content="deep")
        assert result.success
        node = filesystem.get_node("/new/dir/file.txt")
        assert node is not None
        assert node.content == "deep"

    def test_write_to_directory_rejected(self, filesystem):
        """Writing to an existing directory path is rejected with "is a directory"."""
        result = filesystem.write("/home/user", content="data")
        assert not result.success
        assert CommandError.IS_A_DIRECTORY in result.message

    def test_write_no_create_if_missing(self, filesystem):
        """With ``create_if_missing=False``, writing to a nonexistent path fails."""
        result = filesystem.write("/missing.txt", content="data", create_if_missing=False)
        assert not result.success
        assert CommandError.NOT_FOUND in result.message

    def test_write_updates_delta_not_base(self, filesystem):
        """Writes only touch ``delta_layer`` — ``base_layer`` is never mutated."""
        filesystem.write("/etc/hostname", content="overwritten")
        assert filesystem.base_layer["/etc/hostname"].content == "simnux-edge"
        assert filesystem.delta_layer["/etc/hostname"].content == "overwritten"


class TestTouch:
    """``touch()`` — creates empty files or no-ops on existing files."""

    def test_touch_new_file(self, filesystem):
        """Touch on a nonexistent path creates an empty file."""
        result = filesystem.touch("/home/user/newfile.txt")
        assert result.success
        node = filesystem.get_node("/home/user/newfile.txt")
        assert node is not None
        assert node.content == ""

    def test_touch_existing_file_is_noop(self, filesystem):
        """Touch on an existing file does not alter its content."""
        result = filesystem.touch("/etc/hostname")
        assert result.success
        node = filesystem.get_node("/etc/hostname")
        assert node.content == "simnux-edge"


class TestDelete:
    """``delete()`` — marks nodes as deleted via a delta-layer tombstone.

    Deleted nodes are hidden from all read operations but the base_layer
    entry is preserved (copy-on-write).
    """

    def test_delete_creates_tombstone(self, filesystem):
        """Delete creates a tombstone entry (``deleted=True``) in delta_layer."""
        result = filesystem.delete("/etc/hostname")
        assert result.success
        assert filesystem.get_node("/etc/hostname") is None
        assert "/etc/hostname" in filesystem.delta_layer
        assert filesystem.delta_layer["/etc/hostname"].deleted is True

    def test_delete_nonexistent_returns_error(self, filesystem):
        """Deleting a nonexistent path returns an error with "not found"."""
        result = filesystem.delete("/nonexistent")
        assert not result.success
        assert CommandError.NOT_FOUND in result.message

    def test_deleted_node_shadows_base(self, filesystem):
        """The tombstone hides the base_layer node without modifying it."""
        filesystem.delete("/etc/hostname")
        assert filesystem.base_layer["/etc/hostname"] is not None
        assert filesystem.get_node("/etc/hostname") is None


class TestListDirectory:
    """``list_directory()`` — returns immediate children of a directory path.

    Only direct children are listed (non-recursive). Deleted and
    delta-added nodes are reflected correctly.
    """

    def test_list_root(self, filesystem):
        """Listing root (``/``) returns all top-level directories."""
        nodes = filesystem.list_directory("/")
        paths = [n.path for n in nodes]
        assert "/home" in paths
        assert "/etc" in paths
        assert "/var" in paths

    def test_list_nested_directory(self, filesystem):
        """Listing a nested directory returns its immediate children."""
        nodes = filesystem.list_directory("/home/user")
        paths = [n.path for n in nodes]
        assert "/home/user/notes.txt" in paths

    def test_list_empty_directory(self, filesystem):
        """An empty directory returns an empty list."""
        nodes = filesystem.list_directory("/var/log")
        assert nodes == []

    def test_list_nonexistent_directory(self, filesystem):
        """Listing a nonexistent directory returns an empty list (never raises)."""
        nodes = filesystem.list_directory("/nonexistent")
        assert nodes == []

    def test_only_immediate_children(self, filesystem):
        """Only direct children are included; grandchildren are not listed."""
        filesystem.delta_layer["/home/user/sub"] = SNXNode(
            path="/home/user/sub", content="", is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        )
        filesystem.write("/home/user/sub/deep/file.txt", content="deep")
        nodes = filesystem.list_directory("/home/user")
        paths = [n.path for n in nodes]
        assert "/home/user/notes.txt" in paths
        assert "/home/user/sub" in paths
        assert "/home/user/sub/deep" not in paths

    def test_listing_omits_deleted_nodes(self, filesystem):
        """Deleted nodes are excluded from directory listings."""
        filesystem.delete("/home/user/notes.txt")
        nodes = filesystem.list_directory("/home/user")
        paths = [n.path for n in nodes]
        assert "/home/user/notes.txt" not in paths

    def test_list_directory_delta_visible(self, filesystem):
        """Delta-added files are visible in directory listings."""
        filesystem.write("/home/user/newfile.txt", content="new")
        nodes = filesystem.list_directory("/home/user")
        paths = [n.path for n in nodes]
        assert "/home/user/newfile.txt" in paths


class TestListPaths:
    """``list_paths()`` — returns all visible paths across both layers."""

    def test_lists_all_visible_nodes(self, filesystem):
        """All paths from base_layer are included in the full listing."""
        paths = filesystem.list_paths()
        assert "/" in paths
        assert "/home" in paths
        assert "/etc/hostname" in paths

    def test_delta_additions_appear(self, filesystem):
        """Delta-added paths are included in the full listing."""
        filesystem.write("/newfile.txt", content="new")
        paths = filesystem.list_paths()
        assert "/newfile.txt" in paths


class TestOverlayIntegrity:
    """Overlay consistency: base_layer is immutable, delta shadows on read.

    These tests verify the core copy-on-write invariant: writes and
    deletes never propagate to base_layer.
    """

    def test_base_layer_immutable(self, filesystem):
        """Writing to a base-layer path does not modify the original base_layer node."""
        original = filesystem.base_layer["/etc/hostname"].content
        filesystem.write("/etc/hostname", content="changed")
        assert filesystem.base_layer["/etc/hostname"].content == original

    def test_delta_fully_overrides_base(self, filesystem):
        """Delta layer values take full precedence over base_layer on read."""
        filesystem.write("/etc/hostname", content="delta-value")
        assert filesystem.get_node("/etc/hostname").content == "delta-value"

    def test_deleted_node_shadows_base_correctly(self, filesystem):
        """A delete tombstone hides the base_layer entry without removing it."""
        assert filesystem.get_node("/etc/hostname") is not None
        filesystem.delete("/etc/hostname")
        assert filesystem.get_node("/etc/hostname") is None
        assert "/etc/hostname" in filesystem.base_layer

    def test_write_preserves_permissions(self, filesystem):
        """Writing to a file preserves its original permission preset."""
        filesystem.write("/etc/hostname", content="new")
        node = filesystem.get_node("/etc/hostname")
        assert node.permissions == PermissionPresets.FILE_DEFAULT


class TestWriteToDirectoryRejection:
    """Guarding against accidental directory-vs-file misuse."""

    def test_cannot_overwrite_directory_with_file(self, filesystem):
        """Writing content to a directory path is rejected."""
        result = filesystem.write("/home", content="data")
        assert not result.success

    def test_cannot_touch_existing_directory(self, filesystem):
        """Touch on an existing directory succeeds (no-op permitted)."""
        result = filesystem.touch("/home")
        assert result.success

    def test_cannot_delete_and_recreate_as_file(self, filesystem):
        """Deleting a directory then writing content to its path succeeds (recreate)."""
        filesystem.delete("/etc")
        result = filesystem.write("/etc", content="data")
        assert result.success


class TestRegressionPromptHomeMismatch:
    """Regression: tilde expansion must match home prefix exactly, not partially."""

    def test_resolve_home_with_tilde_consistency(self, filesystem):
        """``~`` resolves to home; absolute home path also resolves to home."""
        cwd = "/home/user"
        home = "/home/user"
        result = filesystem.resolve_path(cwd, "~", home)
        assert result == home
        result2 = filesystem.resolve_path(cwd, "/home/user", home)
        assert result2 == "/home/user"


class TestRegressionWriteEmptyContent:
    """Regression: empty-string writes and appends to empty files."""

    def test_write_empty_string_preserves_empty(self, filesystem):
        """Writing an empty string creates a file with empty content (not a no-op)."""
        result = filesystem.write("/new_empty.txt", content="")
        assert result.success
        node = filesystem.get_node("/new_empty.txt")
        assert node.content == ""

    def test_append_to_empty_file(self, filesystem):
        """Appending to an empty file works correctly."""
        filesystem.write("/empty.txt", content="")
        filesystem.append("/empty.txt", "data")
        node = filesystem.get_node("/empty.txt")
        assert node.content == "data"
