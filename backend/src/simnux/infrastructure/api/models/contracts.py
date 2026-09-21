"""Request/response models for the SIMNUX command API.

Defines the public HTTP contract exposed by the runtime API.
Transport models remain isolated from internal runtime structures.
"""

from typing import Literal

from pydantic import BaseModel
from pydantic import Field


class CommandRequest(BaseModel):
    """Shell execution request bound to an active session."""

    command: str
    session_id: str

    # Optional shell selector: when the session hosts multiple shells, the
    # request may target one by its identifier (scenario name). When absent,
    # the session's first (default) shell is used.
    scenario_name: str | None = None

    # Terminal geometry reported by the frontend (lines visible in the
    # output pane). Drives dynamic full-screen pager viewports.
    viewport_height: int | None = Field(default=None, ge=1, le=200)


class ShellResponse(BaseModel):
    """Standard shell execution response envelope."""

    session_id: str
    scenario_name: str | None = None

    # Stable scenario identifier (directory slug, e.g. "hello"), distinct from
    # scenario_name (the human-readable display name, e.g. "Hello SIMNUX").
    # Lets the frontend compare resume results against URL-derived slugs.
    scenario_identifier: str | None = None

    stdout: list[str] = []
    stderr: list[str] = []

    prompt: str = ""

    # Frontend side-effect signals.
    action_type: int = 0
    action_message: str | None = None

    # Interactive input bridge.
    awaiting_input: bool = False

    # Full-screen pager projection (populated when pending_state is PagerState —
    # legacy suspended ``more`` protocol).
    pager_lines: list[str] | None = None
    pager_position: int | None = None
    pager_total: int | None = None
    pager_eof: bool | None = None
    pager_filename: str | None = None
    # Preformatted status bar (e.g. more's "--More--(42%)"); the frontend
    # composes its own interactive status when this is absent.
    pager_status: str | None = None

    # Client-side pager signal (non-suspended ``less``): when ``is_pager`` is
    # True, ``pager_content`` carries the full file lines so the frontend can
    # page locally without further execute_command roundtrips.
    is_pager: bool = False
    pager_content: list[str] | None = None

    # Transport-level execution state.
    status: Literal["ok", "error"] = "ok"
