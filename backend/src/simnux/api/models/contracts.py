"""Request/response models for the SIMNUX command API.

Defines the public HTTP contract exposed by the runtime API.
Transport models remain isolated from internal runtime structures.
"""

from typing import Literal

from pydantic import BaseModel


class CommandRequest(BaseModel):
    """Shell execution request bound to an active session."""

    command: str
    session_id: str


class ShellResponse(BaseModel):
    """Standard shell execution response envelope."""

    session_id: str
    scenario_name: str | None = None

    stdout: list[str] = []
    stderr: list[str] = []

    prompt: str = ""

    # Frontend side-effect signals.
    action_type: int = 0
    action_message: str | None = None

    # Interactive input bridge.
    awaiting_input: bool = False

    # Transport-level execution state.
    status: Literal["ok", "error"] = "ok"
