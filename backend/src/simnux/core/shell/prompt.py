"""Prompt rendering utilities for SIMNUX shell UI."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from simnux.core.shell.runtime import SNXShell


class PromptRenderer:
    """Builds a ``user@hostname:cwd$`` prompt string matching PS1 convention.

    Condenses home_directory to '~' for display. Renders '#' for root,
    '$' for regular users — mirroring real shell UX.
    """

    @staticmethod
    def render(shell: SNXShell) -> str:
        """Build CLI prompt from current shell interaction state."""

        path = shell.current_directory
        home_prefix = shell.home_directory.rstrip("/") + "/"

        if path == shell.home_directory:
            path = "~"

        elif home_prefix == "/" and path != "/":
            path = "~" + path

        elif path.startswith(home_prefix):
            path = path.replace(shell.home_directory, "~", 1)

        tail = "#" if shell.user.identifier == "root" else "$"

        return f"{shell.user.identifier}@{shell.hostname}:{path}{tail} "
