"""Regression tests for prompt rendering edge cases.

Ensures tilde abbreviation works correctly for home, nested subpaths,
and paths completely outside the home directory.
"""

from simnux.shell.prompt import PromptRenderer


class TestRegressionPromptHomeMismatch:
    """Tilde abbreviation: correct behavior for home, subpaths, and outside-home paths.

    Uses the ``create_session`` factory fixture.
    """

    def test_home_directory_shows_tilde(self, create_session):
        """CWD matching home shows a bare ``~``."""
        session = create_session(
            cwd="/home/user",
        )
        prompt = PromptRenderer.render(session)
        assert "~" in prompt

    def test_root_home_directory_shows_tilde_prefix(self, create_session):
        """Root home directory abbreviates paths correctly."""
        session = create_session(
            starting_dir="/",
            cwd="/etc",
        )

        prompt = PromptRenderer.render(session)

        assert "~/etc" in prompt

    def test_root_home_directory_root_path_shows_bare_tilde(self, create_session):
        """Root path renders as bare ``~`` when home is root."""
        session = create_session(
            starting_dir="/",
            cwd="/",
        )

        prompt = PromptRenderer.render(session)

        assert ":~" in prompt

    def test_nested_home_path_shows_tilde_prefix(self, create_session):
        """Subdirectory under home shows ``~/docs``."""
        session = create_session(
            cwd="/home/user/docs",
        )
        prompt = PromptRenderer.render(session)
        assert "~/docs" in prompt

    def test_path_outside_home_shows_full_path(self, create_session):
        """Path outside home shows full absolute path with no tilde."""
        session = create_session(
            cwd="/var/log",
        )
        prompt = PromptRenderer.render(session)
        assert "~" not in prompt
        assert "/var/log" in prompt
