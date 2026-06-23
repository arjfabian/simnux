"""Integration tests for SNXFileSystem overlay integrity.

Verifies the core copy-on-write invariant: writes, deletes, and touches
never mutate ``base_layer``. Also validates delta-layer shadowing,
tombstone semantics (idempotency, recreation), and cross-session isolation.
"""

from simnux.commands.errors import CommandError
from simnux.filesystem.vfs import SNXFileSystem
from tests.helpers import assert_not_success


def listed_paths(fs, path: str) -> list[str]:
    """Helper: return sorted list of immediate child paths for a directory."""
    return [node.path for node in fs.list_directory(path)]


class TestBaseLayerImmutability:
    """Base layer must never be mutated by any write/delete/touch operation.

    Uses the ``fs`` fixture (``base_layer_rich`` with passwd/shadow/secret).
    """

    def test_base_layer_unchanged_after_write(self, fs):
        """Writing to a base-layer path does not alter the original node."""
        fs.write("/etc/passwd", content="hacked:...")
        assert fs.base_layer["/etc/passwd"].content == "root:x:0:0:root:/root:/bin/bash"

    def test_base_layer_unchanged_after_delete(self, fs):
        """Deleting a path creates a tombstone in delta but leaves base_layer intact."""
        fs.delete("/home/user/secret.txt")
        assert "/home/user/secret.txt" in fs.base_layer
        assert fs.base_layer["/home/user/secret.txt"].deleted is False

    def test_base_layer_unchanged_after_touch(self, fs):
        """Touch on a new path only affects delta_layer."""
        fs.touch("/newfile.txt")
        assert "/newfile.txt" not in fs.base_layer

    def test_base_layer_immutable_multiple_operations(self, fs):
        """Repeated writes to the same path never leak into base_layer."""
        fs.write("/etc/passwd", content="v1")
        fs.write("/etc/passwd", content="v2")
        fs.write("/etc/passwd", content="v3")
        assert fs.base_layer["/etc/passwd"].content == "root:x:0:0:root:/root:/bin/bash"


class TestDeltaLayerOverrides:
    """Delta layer shadows base_layer on read and does not affect unrelated nodes."""

    def test_delta_overrides_base_on_read(self, fs):
        """Delta-layer content is returned in preference to base_layer on read."""
        fs.write("/etc/passwd", content="overridden")
        node = fs.get_node("/etc/passwd")
        assert node.content == "overridden"

    def test_delta_shadow_in_listing(self, fs):
        """Overwritten base-layer files appear in listings with delta content."""
        fs.write("/home/user/secret.txt", content="overridden")
        assert "/home/user/secret.txt" in listed_paths(
            fs,
            "/home/user",
        )

    def test_delta_additions_visible(self, fs):
        """New files created in delta are immediately visible via ``exists()``."""
        fs.create_file("/home/user/new.txt")
        fs.write("/home/user/new.txt", content="new")
        assert fs.exists("/home/user/new.txt")

    def test_delta_does_not_affect_other_base_nodes(self, fs):
        """Writing to one base-layer path does not alter sibling nodes."""
        fs.write("/etc/passwd", content="changed")
        assert fs.base_layer["/etc/shadow"].content == "root:!:20000:0:99999:7:::"


class TestDeleteTombstone:
    """Tombstone semantics: delete is idempotent, hides from all reads,
    supports recreation, and is isolated between filesystem instances."""

    def test_delete_twice_is_idempotent(self, fs):
        """Deleting an already-deleted node is a no-op (second delete succeeds)."""
        fs.delete("/etc/passwd")
        fs.delete("/etc/passwd")

        assert fs.get_node("/etc/passwd") is None

    def test_deleted_node_hidden_from_get(self, fs):
        """A deleted node is not accessible via ``get_node()``."""
        fs.delete("/home/user/secret.txt")
        assert fs.get_node("/home/user/secret.txt") is None

    def test_deleted_node_hidden_from_listing(self, fs):
        """A deleted node is excluded from directory listings."""
        fs.delete("/home/user/secret.txt")
        assert "/home/user/secret.txt" not in listed_paths(
            fs,
            "/home/user",
        )

    def test_deleted_node_hidden_from_list_paths(self, fs):
        """A deleted node is excluded from the full path listing."""
        fs.delete("/home/user/secret.txt")
        paths = fs.list_paths()
        assert "/home/user/secret.txt" not in paths

    def test_delete_of_delta_added_node(self, fs):
        """Deleting a delta-layer-added node works correctly."""
        fs.create_file("/home/user/new.txt")
        fs.write("/home/user/new.txt", content="temp")
        fs.delete("/home/user/new.txt")
        assert fs.get_node("/home/user/new.txt") is None

    def test_delete_then_recreate(self, fs):
        """A deleted node can be recreated via write (tombstone replaced)."""
        fs.delete("/etc/passwd")
        fs.write("/etc/passwd", content="recreated")
        node = fs.get_node("/etc/passwd")
        assert node is not None
        assert node.content == "recreated"

    def test_delete_directory_without_flag_returns_error(self, fs):
        """Trying to delete a directory fails because delete."""
        result = fs.delete("/home")

        assert_not_success(result)
        assert CommandError.IS_A_DIRECTORY in result.message

        assert fs.get_node("/home") is not None

    def test_delete_isolation_between_sessions(self, base):
        """Deleting a node in one filesystem does not affect another (session isolation)."""
        fs1 = SNXFileSystem(base_layer=dict(base))
        fs2 = SNXFileSystem(base_layer=dict(base))
        fs1.delete("/etc/passwd")
        node = fs2.get_node("/etc/passwd")

        assert node is not None


class TestOverlayConsistency:
    """Cross-operation consistency: append-after-write, delete-after-write,
    delta creation via append, and metadata preservation."""

    def test_append_after_write_uses_delta_version(self, fs):
        """Append after write uses the delta-layer version (not the base original)."""
        fs.write("/etc/passwd", content="override")
        fs.append("/etc/passwd", "\nextra")

        node = fs.get_node("/etc/passwd")

        assert node.content == "override\nextra"

    def test_delete_hides_overridden_node(self, fs):
        """Deleting a delta-overridden node hides it completely."""
        fs.write("/etc/passwd", content="delta-version")
        fs.delete("/etc/passwd")
        assert fs.get_node("/etc/passwd") is None

    def test_append_to_base_file_creates_delta(self, fs):
        """Appending to a base-layer file creates a delta entry with merged content."""
        fs.append("/etc/passwd", "\nnewline")
        node = fs.get_node("/etc/passwd")
        assert node.content == "root:x:0:0:root:/root:/bin/bash\nnewline"
        assert "/etc/passwd" in fs.delta_layer

    def test_base_node_metadata_preserved_in_delta(self, fs):
        """Writing to a base node preserves the original owner and group metadata."""
        original = fs.get_node("/etc/passwd")
        fs.write("/etc/passwd", content="new")
        delta_node = fs.get_node("/etc/passwd")
        assert delta_node.owner == original.owner
        assert delta_node.group == original.group
