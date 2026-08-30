"""Regression tests for snapshot UUID consistency and filesystem visibility.

Ensures snapshot session IDs match the source session and that filesystem
mutations are reflected in snapshots.
"""

from simnux.core.filesystem.vfs import SNXFileSystem
from tests.helpers import make_shell


class TestRegressionSnapshotUUIDConsistency:
    """Snapshot identity and filesystem visibility after mutations.

    Uses factory fixtures (``create_filesystem``, ``create_session``)
    combined with ``make_shell`` from helpers.
    """

    def test_snapshot_matches_session_id(self, create_filesystem, create_session, test_logger):
        """Snapshot's ``session_id`` matches the source session's ID."""
        fs = create_filesystem()
        session = create_session(session_id="fixed-snap-id")
        shell = make_shell(
            session=session,
            filesystem=fs,
            logger=test_logger,
        )
        snap = shell.get_snapshot()
        assert snap.session_id == "fixed-snap-id"

    def test_snapshot_after_command_execution(self, create_session, test_logger, fs_with_home):
        """Filesystem mutations (write) are visible in the snapshot."""
        fs = SNXFileSystem(base_layer=fs_with_home)
        session = create_session(
            session_id="exec-test",
        )
        shell = make_shell(
            session=session,
            filesystem=fs,
            logger=test_logger,
        )
        fs.create_file("/home/user/new.txt")
        fs.write("/home/user/new.txt", content="test")
        snap = shell.get_snapshot()
        assert "/home/user/new.txt" in snap.filesystem
