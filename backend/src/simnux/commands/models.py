"""
Shared execution context injected into all SIMNUX commands.

Provides controlled access to session state and the virtual filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import re
from typing import TYPE_CHECKING

from simnux.filesystem.vfs import SNXFileSystem
from simnux.sessions.runtime import SNXSession


if TYPE_CHECKING:
    from simnux.commands.dispatcher import CommandDispatcher


@dataclass
class CommandContext:
    """Per-session injection container for command execution.

    Contains references to the mutable session state and filesystem;
    commands share the same context object for their lifetime.
    """

    session: SNXSession
    filesystem: SNXFileSystem
    dispatcher: CommandDispatcher | None = None

    # Terminal height in text lines, reported per-request by the
    # frontend. ``None`` means unknown — commands fall back to defaults.
    viewport_height: int | None = None


_DEFAULT_PAGER_VIEWPORT = 24

# Maximum byte size of a file that ``less`` (and file-inspection commands) will
# read for client-side paging. Files larger than this are rejected with an
# explicit error rather than being spooled into memory/returned in full.
MAX_PAGER_FILE_SIZE = 1_000_000  # bytes (~1MB)


@dataclass
class PagerState:
    """Full-screen pager state owned by ``less``/``more`` command instances.

    Stored on ``session.pending_state`` while a pager is suspended.
    Encapsulates all viewport slicing, navigation clamping, and regex
    search bookkeeping so commands stay thin and the API layer can
    project fields without knowing pager internals.
    """

    content: list[str]
    filename: str | None = None
    position: int = 0
    viewport: int = _DEFAULT_PAGER_VIEWPORT

    # Owning pager program ("less" / "more") — drives status-bar
    # formatting differences (e.g. more's POSIX "--More--(N%)" indicator).
    program: str = "less"

    search_pattern: str | None = None
    search_positions: list[int] = field(default_factory=list)
    search_index: int = -1

    def __post_init__(self) -> None:
        self.clamp()

    # ── Projection helpers ────────────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self.content)

    def current_page(self) -> list[str]:
        """Return the visible slice of content."""
        end = min(self.position + self.viewport, self.total)
        return self.content[self.position : end]

    def at_bottom(self) -> bool:
        """True when the last page is displayed."""
        return self.position + self.viewport >= self.total

    def percent_shown(self) -> int:
        """Percentage of the file visible (100 when past end)."""
        if not self.total:
            return 100
        shown = min(self.position + self.viewport, self.total)
        return round(shown * 100 / self.total)

    # ── Navigation ────────────────────────────────────────────────────

    def clamp(self) -> None:
        """Constrain position to valid bounds [0, total - viewport]."""
        self.position = max(0, min(self.position, max(0, self.total - self.viewport)))

    def advance(self, lines: int | None = None) -> None:
        """Move forward one page (or ``lines``). Clamps to bottom."""
        step = self.viewport if lines is None else lines
        self.position += step
        self.clamp()

    def rewind(self, lines: int | None = None) -> None:
        """Move backward one page (or ``lines``). Clamps to top."""
        step = self.viewport if lines is None else lines
        self.position -= step
        self.clamp()

    def jump_top(self) -> None:
        self.position = 0

    def jump_bottom(self) -> None:
        self.position = max(0, self.total - self.viewport)

    # ── Search ────────────────────────────────────────────────────────

    def search_forward(self, pattern: str) -> bool:
        """Compile ``pattern``, collect matches, jump to first at/after position.

        Returns False on invalid regex or zero matches (state untouched
        except ``search_pattern``/``search_positions`` on success).
        """
        try:
            regex = re.compile(pattern)
        except re.error:
            return False

        positions = [i for i, line in enumerate(self.content) if regex.search(line)]
        if not positions:
            return False

        self.search_pattern = pattern
        self.search_positions = positions
        start = next((p for p in positions if p > self.position), positions[0])
        self.search_index = positions.index(start)
        self.jump_to_match()
        return True

    def search_next(self) -> bool:
        """Jump to next match. False when no active matches."""
        if not self.search_positions:
            return False
        self.search_index = (self.search_index + 1) % len(self.search_positions)
        self.jump_to_match()
        return True

    def search_prev(self) -> bool:
        """Jump to previous match. False when no active matches."""
        if not self.search_positions:
            return False
        self.search_index = (self.search_index - 1) % len(self.search_positions)
        self.jump_to_match()
        return True

    def jump_to_match(self) -> None:
        """Scroll so the current match line is visible (near viewport top)."""
        target = self.search_positions[self.search_index]
        self.position = target
        self.clamp()
