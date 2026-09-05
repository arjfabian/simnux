"""Session-start endpoint for SIMNUX.

Responsible for either creating a new session (plus its first shell) or
resuming an existing one. Session identity is always controlled by the
backend unless explicitly resumed.
"""

import uuid

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request

from simnux.core.scenarios.loader import ScenarioNotFoundError
from simnux.infrastructure.api.models.contracts import ShellResponse


router = APIRouter()

DEFAULT_SCENARIO = "hello"


@router.get("/start")
async def start(
    request: Request,
    session_id: str | None = None,
    scenario_name: str = DEFAULT_SCENARIO,
) -> ShellResponse:
    """Entry point for new and resumed sessions.

    Resume path: returns an existing shell unchanged if a valid session_id is
    provided (selecting the shell by *scenario_name*, falling back to the
    session's first shell). Create path: backend generates UUID v4 session_id,
    loads the named scenario, and returns MOTD as the initial stdout. The
    session_id is the identity token; the frontend must retain it.
    """
    runtime = request.app.state.runtime

    # Resume: if session_id maps to an active session, return the matching
    # shell without modification. Sessions are immutable after creation from
    # the API perspective.
    if session_id:
        session = runtime.get_session(session_id)

        if session:
            shell = session.get_shell(scenario_name)
            if shell is None and session.shells:
                shell = session.active_shells[0]

            if shell:
                return ShellResponse(
                    session_id=session_id,
                    scenario_name=shell.scenario.name,
                    stdout=[],
                    stderr=[],
                    prompt=shell.render_prompt(),
                    status="ok",
                )

        raise HTTPException(
            status_code=404,
            detail="Session not found or expired",
        )

    # Session_id is always backend-generated (never client-supplied) to
    # prevent session fixation and ID collision. The frontend receives and
    # stores the opaque token.
    session_id = str(uuid.uuid4())

    try:
        shell = runtime.create_session(
            scenario_name=scenario_name,
            session_id=session_id,
        )
    except ScenarioNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{scenario_name}' not found",
        ) from None

    return ShellResponse(
        session_id=session_id,
        scenario_name=shell.scenario.name,
        stdout=[shell.motd],
        stderr=[],
        prompt=shell.render_prompt(),
        status="ok",
    )
