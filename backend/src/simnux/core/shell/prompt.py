"""Prompt rendering utilities for SIMNUX shell UI."""

from simnux.core.sessions.runtime import SNXSession


class PromptRenderer:
    """Builds a ``user@hostname:cwd$`` prompt string matching PS1 convention.

    Condenses home_directory to '~' for display. Renders '#' for root,
    '$' for regular users — mirroring real shell UX.
    """

    @staticmethod
    def render(session: SNXSession) -> str:
        """Build CLI prompt from current session context."""

        path = session.current_directory
        home_prefix = session.home_directory.rstrip("/") + "/"

        if path == session.home_directory:
            path = "~"

        elif home_prefix == "/" and path != "/":
            path = "~" + path

        elif path.startswith(home_prefix):
            path = path.replace(session.home_directory, "~", 1)

        tail = "#" if session.username == "root" else "$"

        return f"{session.username}@{session.hostname}:{path}{tail} "
