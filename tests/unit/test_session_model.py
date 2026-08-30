"""Tests for SNXSession model — status tracking, property passthroughs,
CWD mutation, and session identity.

Covers the session data model that combines scenario metadata with
per-session mutable state (current directory, task progress).
"""

import pytest

from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.scenarios.models import SNXScenario
from simnux.core.sessions.runtime import SNXSession


@pytest.fixture
def scenario():
    """Scratch scenario with hacker-themed metadata and minimal root-only filesystem."""
    return SNXScenario(
        name="ScenarioX",
        difficulty="Hard",
        username="hacker",
        hostname="pwnbox",
        starting_dir="/home/hacker",
        filesystem={
            "/": SNXNode(
                path="/",
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/etc/motd": SNXNode(
                path="/etc/motd",
                content="Solve the puzzle",
                is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        },
    )


@pytest.fixture
def session(scenario):
    """Standard session using the hacker scenario, starting at ``/home/hacker``."""
    return SNXSession(
        session_id="session-01",
        scenario=scenario,
        current_directory=scenario.starting_dir,
    )


class TestSessionStatus:
    """``get_status()`` — computed task-completion state for the scenario."""

    def test_default_status_no_tasks(self, session):
        """A fresh session with no tasks is not solved."""
        status = session.get_status()
        assert status["tasks_total"] == 0
        assert status["tasks_completed"] == 0
        assert status["scenario_solved"] is False

    def test_status_not_solved_when_tasks_remain(self, session):
        """Partial task completion does not mark the scenario as solved."""
        session.tasks_total = 3
        session.tasks_completed = 1
        status = session.get_status()
        assert status["scenario_solved"] is False

    def test_status_solved_when_all_tasks_done(self, session):
        """All tasks completed marks the scenario as solved."""
        session.tasks_total = 3
        session.tasks_completed = 3
        status = session.get_status()
        assert status["scenario_solved"] is True

    def test_status_solved_exceeds_tasks(self, session):
        """Completed tasks exceeding total still reports solved (overflow tolerance)."""
        session.tasks_total = 3
        session.tasks_completed = 5
        status = session.get_status()
        assert status["scenario_solved"] is True

    def test_status_zero_tasks_not_solved(self, session):
        """Zero tasks count means the scenario is not solvable (no objectives defined)."""
        session.tasks_total = 0
        session.tasks_completed = 0
        status = session.get_status()
        assert status["scenario_solved"] is False


class TestPropertyPassthroughs:
    """Property proxies from SNXSession to the underlying SNXScenario."""

    def test_motd_passthrough(self, session):
        """``session.motd`` delegates to the scenario's motd."""
        assert session.motd == "Solve the puzzle"

    def test_home_directory_passthrough(self, session):
        """``session.home_directory`` delegates to scenario's starting_dir."""
        assert session.home_directory == "/home/hacker"

    def test_username_passthrough(self, session):
        """``session.username`` delegates to the scenario's username."""
        assert session.username == "hacker"

    def test_hostname_passthrough(self, session):
        """``session.hostname`` delegates to the scenario's hostname."""
        assert session.hostname == "pwnbox"

    def test_metadata_default(self, session):
        """Default metadata is an empty dict."""
        assert session.metadata == {}

    def test_metadata_passthrough(self, session, scenario):
        """Custom metadata passed to SNXSession is stored and retrievable."""
        session2 = SNXSession(
            session_id="s2",
            scenario=scenario,
            current_directory="/home/hacker",
            metadata={"progress": 0.5, "flags": ["flag1"]},
        )
        assert session2.metadata == {"progress": 0.5, "flags": ["flag1"]}


class TestCwdMutation:
    """``set_cwd()`` — updates the session's current working directory."""

    def test_set_cwd_updates_directory(self, session):
        """Setting an absolute path updates current_directory."""
        session.set_cwd("/tmp")
        assert session.current_directory == "/tmp"

    def test_set_cwd_with_tilde_char(self, session):
        """Setting ``"~"`` stores it literally (expansion happens in the shell, not session)."""
        session.set_cwd("~")
        assert session.current_directory == "~"

    def test_set_cwd_nested_path(self, session):
        """Setting a nested absolute path updates current_directory."""
        session.set_cwd("/var/log")
        assert session.current_directory == "/var/log"


class TestSessionId:
    """Session identity — each session has a unique string ID."""

    def test_session_id_stored(self, session):
        """The session ID passed at construction is stored."""
        assert session.session_id == "session-01"

    def test_different_sessions_have_different_ids(self, scenario):
        """Two sessions created with different IDs are distinct."""
        s1 = SNXSession(session_id="a", scenario=scenario, current_directory="/")
        s2 = SNXSession(session_id="b", scenario=scenario, current_directory="/")
        assert s1.session_id != s2.session_id
