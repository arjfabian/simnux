"""Tests for SNXRuntime — session lifecycle management.

Covers session creation, retrieval, overwrite semantics, snapshot
generation, command loading, filesystem population, and session
isolation.
"""

from tests.helpers import assert_success


class TestSNXRuntime:
    """Runtime session lifecycle: create, retrieve, snapshot, isolate.

    Uses the ``runtime`` fixture which provides a fresh ``SNXRuntime``
    with the ``"hello"`` scenario. Sessions created via
    ``runtime.create_session()`` get a full shell with loaded commands.
    """

    def test_create_session(self, runtime):
        """Creating a session returns a shell and registers it in the runtime."""
        shell = runtime.create_session(
            scenario_name="hello",
            session_id="session-1",
        )
        assert shell is not None
        assert shell.session.session_id == "session-1"
        assert runtime.exists("session-1")

    def test_session_retrieval(self, runtime):
        """Created sessions can be retrieved by ID via ``get_session()``."""
        runtime.create_session(scenario_name="hello", session_id="session-2")
        shell = runtime.get_session("session-2")
        assert shell is not None
        assert shell.session.session_id == "session-2"

    def test_get_nonexistent_session(self, runtime):
        """Retrieving a nonexistent session ID returns ``None``."""
        shell = runtime.get_session("nonexistent")
        assert shell is None

    def test_duplicate_session_id_overwrites(self, runtime):
        """Creating a session with an existing ID replaces the old one (last-wins)."""
        shell1 = runtime.create_session(scenario_name="hello", session_id="dup")
        shell2 = runtime.create_session(scenario_name="hello", session_id="dup")
        assert shell1 is not shell2
        assert runtime.get_session("dup") is shell2
        assert runtime.exists("dup")

    def test_session_not_exists(self, runtime):
        """An unregistered session ID returns ``False`` from ``exists()``."""
        assert not runtime.exists("nonexistent")

    def test_empty_runtime_snapshot(self, runtime):
        """A fresh runtime has zero sessions in its snapshot."""
        snapshot = runtime.get_snapshot()
        assert snapshot.total_sessions == 0
        assert snapshot.active_sessions == []

    def test_runtime_snapshot_after_create(self, runtime):
        """After creating sessions, the snapshot reflects the correct count."""
        runtime.create_session(scenario_name="hello", session_id="s1")
        runtime.create_session(scenario_name="hello", session_id="s2")
        snapshot = runtime.get_snapshot()
        assert snapshot.total_sessions == 2
        assert len(snapshot.active_sessions) == 2

    def test_session_scenario_name_in_snapshot(self, runtime):
        """Snapshot entries include the human-readable scenario name."""
        runtime.create_session(scenario_name="hello", session_id="s1")
        snapshot = runtime.get_snapshot()
        shell_snap = snapshot.active_sessions[0]
        assert shell_snap.scenario_name == "Hello SIMNUX"

    def test_session_commands_loaded(self, runtime):
        """Sessions come with standard commands (ls, cd, cat, touch, pwd, echo) pre-loaded."""
        shell = runtime.create_session(scenario_name="hello", session_id="cmd-test")
        commands = shell.registry.list_commands()
        assert "ls" in commands
        assert "cd" in commands
        assert "cat" in commands
        assert "touch" in commands
        assert "pwd" in commands
        assert "echo" in commands
        assert len(commands) >= 6

    def test_session_filesystem_populated(self, runtime):
        """Sessions have a populated filesystem with expected directories and files."""
        shell = runtime.create_session(scenario_name="hello", session_id="fs-test")
        assert shell.filesystem.exists("/home/user")
        assert shell.filesystem.exists("/etc/hostname")
        assert shell.filesystem.exists("/etc/motd")

    def test_multiple_sessions_isolated(self, runtime):
        """Filesystem mutations in one session do not affect another."""

        s1 = runtime.create_session(
            scenario_name="hello",
            session_id="isolation-1",
        )

        s2 = runtime.create_session(
            scenario_name="hello",
            session_id="isolation-2",
        )

        result = s1.filesystem.create_file("/unique.txt")

        assert_success(result)

        result = s1.filesystem.write(
            "/unique.txt",
            content="s1-only",
        )

        assert_success(result)

        assert s1.filesystem.exists("/unique.txt") is True
        assert s2.filesystem.exists("/unique.txt") is False

    def test_session_current_directory_set(self, runtime):
        """New sessions start in the scenario's configured starting directory."""
        shell = runtime.create_session(scenario_name="hello", session_id="cwd-test")
        assert shell.session.current_directory == "/home/user"

    def test_destroy_session(self, runtime):
        """``destroy_session`` removes the session and returns True."""
        runtime.create_session(scenario_name="hello", session_id="doomed")
        assert runtime.exists("doomed")
        assert runtime.destroy_session("doomed") is True
        assert not runtime.exists("doomed")
        assert runtime.get_session("doomed") is None

    def test_destroy_nonexistent_session(self, runtime):
        """``destroy_session`` returns False for an unknown session_id."""
        assert runtime.destroy_session("ghost") is False

    def test_destroy_prevents_leak(self, runtime):
        """After destroying a session, the snapshot no longer includes it."""
        runtime.create_session(scenario_name="hello", session_id="s1")
        runtime.create_session(scenario_name="hello", session_id="s2")
        assert runtime.get_snapshot().total_sessions == 2

        runtime.destroy_session("s1")
        snapshot = runtime.get_snapshot()
        assert snapshot.total_sessions == 1
        assert all(s.session_id != "s1" for s in snapshot.active_sessions)
