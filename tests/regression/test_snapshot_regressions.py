"""Regression tests for snapshot identity consistency and filesystem visibility.

Ensures snapshot session IDs match the owning session and that filesystem
mutations are reflected in snapshots.
"""

from simnux.core.filesystem.vfs import SNXFileSystem
from tests.helpers import make_shell


class TestRegressionSnapshotUUIDConsistency:
    """Snapshot identity and filesystem visibility after mutations.

    Uses factory fixtures (``create_filesystem``, ``create_scenario``)
    combined with ``make_shell`` from helpers.
    """

    def test_snapshot_matches_session_id(
        self,
        create_filesystem,
        create_scenario,
        test_logger,
    ):
        """Snapshot's ``session_id`` matches the owning session's ID."""
        fs = create_filesystem()
        scenario = create_scenario()
        shell = make_shell(
            filesystem=fs,
            logger=test_logger,
            scenario=scenario,
            identifier="fixed-snap-id",
        )
        snap = shell.get_snapshot("fixed-snap-id")
        assert snap.session_id == "fixed-snap-id"

    def test_snapshot_after_command_execution(
        self,
        create_scenario,
        test_logger,
        fs_with_home,
    ):
        """Filesystem mutations (write) are visible in the snapshot."""
        fs = SNXFileSystem(base_layer=fs_with_home)
        scenario = create_scenario()
        shell = make_shell(
            filesystem=fs,
            logger=test_logger,
            scenario=scenario,
            identifier="exec-test",
        )
        fs.create_file("/home/user/new.txt")
        fs.write("/home/user/new.txt", content="test")
        snap = shell.get_snapshot("exec-test")
        assert "/home/user/new.txt" in snap.filesystem
