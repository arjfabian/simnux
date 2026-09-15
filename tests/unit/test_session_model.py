"""Tests for SNXSession (shell router) and SNXShell (interaction state).

Covers the session's shell set/dispatch behavior and the shell-owned
scenario interaction state (current directory, task progress, property
passthroughs).
"""

import logging

import pytest

from simnux.core.commands.registry import CommandRegistry
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.core.scenarios.models import SNXScenario
from simnux.core.sessions.runtime import SNXSession
from simnux.core.shell.runtime import SNXShell
from simnux.security.execution.models import ExecutionContext
from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


@pytest.fixture
def scenario():
    """Scratch scenario with hacker-themed metadata and minimal root-only filesystem."""
    return SNXScenario(
        name="ScenarioX",
        difficulty="Hard",
        hostname="pwnbox",
        users={
            "root": SNXUser(0, "root"),
            "hacker": SNXUser(1001, "hacker"),
        },
        groups={
            "root": SNXGroup(0, "root"),
            "hacker": SNXGroup(1001, "hacker"),
        },
        starting_dir="/home/hacker",
        filesystem={
            "/": SNXNode(
                path="/",
                owner=SNXUser(0, "root"),
                group=SNXGroup(0, "root"),
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/etc/motd": SNXNode(
                path="/etc/motd",
                owner=SNXUser(0, "root"),
                group=SNXGroup(0, "root"),
                content="Solve the puzzle",
                is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        },
    )


def make_shell(
    scenario,
    *,
    identifier=None,
    current_directory=None,
    metadata=None,
):
    """Build an SNXShell over *scenario* with a scratch filesystem/registry."""
    return SNXShell(
        scenario=scenario,
        execution_context=ExecutionContext.for_user(
            scenario.users["hacker"],
            SNXGroupMembership.from_identities(
                scenario.users,
                scenario.groups,
            ),
        ),
        current_directory=current_directory or scenario.starting_dir,
        filesystem=SNXFileSystem(base_layer=dict(scenario.filesystem)),
        registry=CommandRegistry(),
        logger=logging.getLogger("test_session_model"),
        identifier=identifier or scenario.name,
        metadata=metadata,
    )


@pytest.fixture
def session(scenario):
    """Session hosting one shell over the hacker scenario at ``/home/hacker``."""
    session = SNXSession(session_id="session-01")
    session.add_shell(make_shell(scenario))
    return session


class TestShellStatus:
    """``get_status()`` — computed task-completion state for the scenario."""

    def test_default_status_no_tasks(self, session):
        """A fresh shell with no tasks is not solved."""
        shell = session.active_shells[0]
        status = shell.get_status()
        assert status["tasks_total"] == 0
        assert status["tasks_completed"] == 0
        assert status["scenario_solved"] is False

    def test_status_not_solved_when_tasks_remain(self, session):
        """Partial task completion does not mark the scenario as solved."""
        shell = session.active_shells[0]
        shell.tasks_total = 3
        shell.tasks_completed = 1
        status = shell.get_status()
        assert status["scenario_solved"] is False

    def test_status_solved_when_all_tasks_done(self, session):
        """All tasks completed marks the scenario as solved."""
        shell = session.active_shells[0]
        shell.tasks_total = 3
        shell.tasks_completed = 3
        status = shell.get_status()
        assert status["scenario_solved"] is True

    def test_status_solved_exceeds_tasks(self, session):
        """Completed tasks exceeding total still reports solved (overflow tolerance)."""
        shell = session.active_shells[0]
        shell.tasks_total = 3
        shell.tasks_completed = 5
        status = shell.get_status()
        assert status["scenario_solved"] is True

    def test_status_zero_tasks_not_solved(self, session):
        """Zero tasks count means the scenario is not solvable (no objectives defined)."""
        shell = session.active_shells[0]
        shell.tasks_total = 0
        shell.tasks_completed = 0
        status = shell.get_status()
        assert status["scenario_solved"] is False


class TestPropertyPassthroughs:
    """Property proxies from SNXShell to the underlying SNXScenario."""

    def test_motd_passthrough(self, session):
        """``shell.motd`` delegates to the scenario's motd."""
        shell = session.active_shells[0]
        assert shell.motd == "Solve the puzzle"

    def test_home_directory_passthrough(self, session):
        """``shell.home_directory`` delegates to scenario's starting_dir."""
        shell = session.active_shells[0]
        assert shell.home_directory == "/home/hacker"

    def test_username_passthrough(self, session):
        """``shell.user.identifier`` reflects the shell's current user."""
        shell = session.active_shells[0]
        assert shell.user.identifier == "hacker"

    def test_hostname_passthrough(self, session):
        """``shell.hostname`` delegates to the scenario's hostname."""
        shell = session.active_shells[0]
        assert shell.hostname == "pwnbox"

    def test_metadata_default(self, session):
        """Default metadata is an empty dict."""
        shell = session.active_shells[0]
        assert shell.metadata == {}

    def test_metadata_passthrough(self, scenario):
        """Custom metadata passed to SNXShell is stored and retrievable."""
        shell = make_shell(
            scenario,
            identifier="s2",
            metadata={"progress": 0.5, "flags": ["flag1"]},
        )
        assert shell.metadata == {"progress": 0.5, "flags": ["flag1"]}


class TestCwdMutation:
    """``set_cwd()`` — updates the shell's current working directory."""

    def test_set_cwd_updates_directory(self, session):
        """Setting an absolute path updates current_directory."""
        shell = session.active_shells[0]
        shell.set_cwd("/tmp")
        assert shell.current_directory == "/tmp"

    def test_set_cwd_with_tilde_char(self, session):
        """Setting ``"~"`` stores it literally (expansion happens elsewhere)."""
        shell = session.active_shells[0]
        shell.set_cwd("~")
        assert shell.current_directory == "~"

    def test_set_cwd_nested_path(self, session):
        """Setting a nested absolute path updates current_directory."""
        shell = session.active_shells[0]
        shell.set_cwd("/var/log")
        assert shell.current_directory == "/var/log"


class TestShellDispatch:
    """A session owns a set of shells keyed by identifier."""

    def test_session_id_stored(self, session):
        """The session ID passed at construction is stored."""
        assert session.session_id == "session-01"

    def test_add_and_retrieve_shell(self, scenario):
        """A shell added to a session is retrievable by identifier."""
        session = SNXSession(session_id="a")
        shell = make_shell(scenario, identifier="hello")
        session.add_shell(shell)
        assert session.get_shell("hello") is shell
        assert session.active_shells == [shell]

    def test_multiple_shells_per_session(self, scenario):
        """A session hosts multiple shells, one per scenario identifier."""
        session = SNXSession(session_id="a")
        shell1 = make_shell(scenario, identifier="hello")
        shell2 = make_shell(scenario, identifier="mission-1")
        session.add_shell(shell1)
        session.add_shell(shell2)
        assert session.get_shell("hello") is shell1
        assert session.get_shell("mission-1") is shell2
        assert len(session.active_shells) == 2

    def test_missing_shell_returns_none(self, scenario):
        """Requesting an unknown shell identifier returns ``None``."""
        session = SNXSession(session_id="a")
        session.add_shell(make_shell(scenario, identifier="hello"))
        assert session.get_shell("nope") is None

    def test_replace_shell_last_wins(self, scenario):
        """Adding a shell with an existing identifier replaces it (last-wins)."""
        session = SNXSession(session_id="a")
        shell1 = make_shell(scenario, identifier="hello")
        shell2 = make_shell(scenario, identifier="hello")
        session.add_shell(shell1)
        session.add_shell(shell2)
        assert session.get_shell("hello") is shell2
        assert session.active_shells == [shell2]

    def test_session_does_not_own_interaction_state(self, scenario):
        """SNXSession exposes no scenario-bound interaction state of its own."""
        session = SNXSession(session_id="a")
        session.add_shell(make_shell(scenario, identifier="hello"))

        assert not hasattr(session, "scenario")
        assert not hasattr(session, "user")
        assert not hasattr(session, "current_directory")
        assert not hasattr(session, "history")
        assert not hasattr(session, "environment")

        session.shells["hello"].set_cwd("/etc")
        assert session.shells["hello"].current_directory == "/etc"

    def test_remove_shell(self, scenario):
        """Removing a shell detaches it; others remain."""
        session = SNXSession(session_id="a")
        session.add_shell(make_shell(scenario, identifier="hello"))
        session.add_shell(make_shell(scenario, identifier="mission-1"))
        session.remove_shell("hello")
        assert session.get_shell("hello") is None
        assert len(session.active_shells) == 1

    def test_different_sessions_have_different_ids(self, scenario):
        """Two sessions created with different IDs are distinct."""
        s1 = SNXSession(session_id="a")
        s2 = SNXSession(session_id="b")
        assert s1.session_id != s2.session_id
        assert s1.shells is not s2.shells

    def test_shells_in_one_session_own_independent_cwd(self, scenario):
        """Two shells in the same session keep independent current directories."""
        session = SNXSession(session_id="a")
        shell1 = make_shell(scenario, identifier="hello")
        shell2 = make_shell(scenario, identifier="mission-1")
        session.add_shell(shell1)
        session.add_shell(shell2)

        shell1.set_cwd("/etc")

        assert shell1.current_directory == "/etc"
        assert session.get_shell("hello").current_directory == "/etc"
        assert session.get_shell("mission-1").current_directory == "/home/hacker"

    def test_shells_in_one_session_own_independent_history(self, scenario):
        """Two shells in the same session keep independent command histories."""
        session = SNXSession(session_id="a")
        session.add_shell(make_shell(scenario, identifier="hello"))
        session.add_shell(make_shell(scenario, identifier="mission-1"))

        session.get_shell("hello").add_history("echo hi")

        assert session.get_shell("hello").history == ["echo hi"]
        assert session.get_shell("mission-1").history == []

    def test_shells_in_one_session_own_independent_environment(self, scenario):
        """Two shells in the same session keep independent environments."""
        session = SNXSession(session_id="a")
        session.add_shell(make_shell(scenario, identifier="hello"))
        session.add_shell(make_shell(scenario, identifier="mission-1"))

        session.get_shell("hello").environment["FOO"] = "bar"

        assert session.get_shell("hello").environment.get("FOO") == "bar"
        assert session.get_shell("mission-1").environment.get("FOO") is None

    def test_shells_in_one_session_own_independent_pending_state(self, scenario):
        """Two shells in the same session keep independent pending input state."""
        session = SNXSession(session_id="a")
        session.add_shell(make_shell(scenario, identifier="hello"))
        session.add_shell(make_shell(scenario, identifier="mission-1"))

        session.get_shell("hello").awaiting_input = True
        session.get_shell("hello").pending_command = "read -p Input:"

        assert session.get_shell("hello").awaiting_input is True
        assert session.get_shell("hello").pending_command == "read -p Input:"
        assert session.get_shell("mission-1").awaiting_input is False
        assert session.get_shell("mission-1").pending_command is None

    def test_shells_in_one_session_own_independent_progress(self, scenario):
        """Two shells in the same session keep independent task progress."""
        session = SNXSession(session_id="a")
        session.add_shell(make_shell(scenario, identifier="hello"))
        session.add_shell(make_shell(scenario, identifier="mission-1"))

        session.get_shell("hello").tasks_total = 2
        session.get_shell("hello").tasks_completed = 2

        assert session.get_shell("hello").get_status()["scenario_solved"] is True
        assert session.get_shell("mission-1").get_status()["scenario_solved"] is False
