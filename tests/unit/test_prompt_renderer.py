"""Tests for the PromptRenderer — shell prompt generation.

Verifies that prompts correctly render ``user@hostname:path$ `` with
tilde abbreviation for the home directory, ``$`` vs ``#`` for root,
and correct hostname/username display.
"""

import logging

from simnux.core.commands.registry import CommandRegistry
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.core.scenarios.models import SNXScenario
from simnux.core.shell.prompt import PromptRenderer
from simnux.core.shell.runtime import SNXShell
from simnux.security.execution.models import ExecutionContext
from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


def _make_session(
    username="user",
    hostname="simnux",
    starting_dir="/home/user",
    current_directory=None,
):
    """Create a minimal SNXShell for prompt-rendering tests.

    Builds a scratch scenario with a single root node so the shell
    constructor is satisfied, then returns a shell ready for render.

    Returns:
        SNXShell: Shell with the given username/hostname/paths.
    """
    scenario = SNXScenario(
        name="Test",
        difficulty="Easy",
        hostname=hostname,
        users={
            "root": SNXUser(0, "root"),
            username: SNXUser(1001, username),
        },
        groups={
            "root": SNXGroup(0, "root"),
            username: SNXGroup(1001, username),
        },
        starting_dir=starting_dir,
        filesystem={
            "/": SNXNode(
                path="/",
                owner=SNXUser(0, "root"),
                group=SNXGroup(0, "root"),
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            )
        },
    )
    return SNXShell(
        scenario=scenario,
        execution_context=ExecutionContext.for_user(
            scenario.users[username],
            SNXGroupMembership.from_identities(
                scenario.users,
                scenario.groups,
            ),
        ),
        current_directory=current_directory or starting_dir,
        filesystem=SNXFileSystem(base_layer={}),
        registry=CommandRegistry(),
        logger=logging.getLogger("test_prompt_renderer"),
        identifier="Test",
    )


class TestPromptRenderer:
    """Shell prompt rendering: ``user@hostname:path$ `` format.

    Covers tilde abbreviation, root-user ``#`` vs normal ``$``,
    hostname/username insertion, and prefix-matching edge cases
    where a path starts with the same prefix as home but is not
    actually under home.
    """

    def test_home_directory_shows_tilde(self):
        """CWD matching home displays a bare ``~``."""
        session = _make_session(current_directory="/home/user")
        prompt = PromptRenderer.render(session)
        assert "~" in prompt

    def test_normal_user_prompt(self):
        """Full format: ``user@hostname:~$ `` for normal users at home."""
        session = _make_session(
            username="alice",
            starting_dir="/home/alice",
            current_directory="/home/alice",
        )
        prompt = PromptRenderer.render(session)
        assert prompt.startswith("alice@simnux:~$ ")

    def test_root_user_shows_hash(self):
        """Root user gets ``# `` instead of ``$ ``."""
        session = _make_session(username="root", starting_dir="/root", current_directory="/root")
        prompt = PromptRenderer.render(session)
        assert prompt.endswith("# ")

    def test_normal_user_shows_dollar(self):
        """Non-root users get ``$ `` as the prompt suffix."""
        session = _make_session(
            username="bob", starting_dir="/home/bob", current_directory="/home/bob"
        )
        prompt = PromptRenderer.render(session)
        assert prompt.endswith("$ ")

    def test_nested_path_under_home_shows_tilde_prefix(self):
        """Subdirectory under home shows ``~/subdir``."""
        session = _make_session(current_directory="/home/user/docs")
        prompt = PromptRenderer.render(session)
        assert "~/docs" in prompt

    def test_path_outside_home_shows_full(self):
        """Path outside home shows the full absolute path."""
        session = _make_session(current_directory="/etc")
        prompt = PromptRenderer.render(session)
        assert "user@simnux:/etc$ " in prompt

    def test_root_in_non_home_directory(self):
        """Root user outside home shows full path with ``# `` suffix."""
        session = _make_session(username="root", starting_dir="/root", current_directory="/var/log")
        prompt = PromptRenderer.render(session)
        assert prompt.startswith("root@simnux:/var/log# ")

    def test_non_standard_home_directory(self):
        """Non-standard home paths (not ``/home/``) still get tilde abbreviation."""
        session = _make_session(starting_dir="/opt/app", current_directory="/opt/app")
        prompt = PromptRenderer.render(session)
        assert "~" in prompt

    def test_non_standard_home_nested_path(self):
        """Nested path under non-standard home shows ``~/sub``."""
        session = _make_session(starting_dir="/opt/app", current_directory="/opt/app/config")
        prompt = PromptRenderer.render(session)
        assert "~/config" in prompt

    def test_path_prefix_matches_home_but_not_subpath(self):
        """Path that only shares a prefix with home is not abbreviated (prevents false matches)."""
        session = _make_session(starting_dir="/home/user", current_directory="/home/user2")
        prompt = PromptRenderer.render(session)
        assert "~" not in prompt
        assert "/home/user2" in prompt

    def test_root_prompt_when_cwd_is_root(self):
        """Root user at ``/`` shows ``root@simnux:/# ``."""
        session = _make_session(username="root", starting_dir="/root", current_directory="/")
        prompt = PromptRenderer.render(session)
        assert prompt.startswith("root@simnux:/# ")

    def test_hostname_appears_in_prompt(self):
        """Custom hostname is rendered in the prompt."""
        session = _make_session(hostname="custom-host", current_directory="/home/user")
        prompt = PromptRenderer.render(session)
        assert "custom-host" in prompt

    def test_username_appears_in_prompt(self):
        """Custom username is rendered in the prompt."""
        session = _make_session(username="john", current_directory="/home/user")
        prompt = PromptRenderer.render(session)
        assert "john" in prompt
