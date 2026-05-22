"""Session-start endpoint for SIMNUX.

Responsible for either creating a new session or resuming an existing one.
Session identity is always controlled by the backend unless explicitly resumed.
"""

import uuid

from fastapi import APIRouter, Request

from simnux.api.models.contracts import ShellResponse

router = APIRouter()

DEFAULT_SCENARIO = "hello"


@router.get("/start")
async def start(
    request: Request,
    session_id: str | None = None,
    scenario_name: str = DEFAULT_SCENARIO,
) -> ShellResponse:
    """Entry point for new and resumed sessions.

    Resume path: returns existing session unchanged if a valid session_id is
    provided. Create path: backend generates UUID v4 session_id, loads the
    named scenario, and returns MOTD as the initial stdout. The session_id is
    the only identity token; the frontend must retain it.
    """
    runtime = request.app.state.runtime

    # Resume: if session_id maps to an active shell, return it without
    # modification. Sessions are immutable after creation from the API
    # perspective.
    if session_id:
        shell = runtime.get_session(session_id)

        if shell:
            session = shell.session

            return ShellResponse(
                session_id=session_id,
                scenario_name=session.scenario.name,
                stdout=[],
                stderr=[],
                prompt=shell.render_prompt(),
                status="ok",
            )

        # TODO: return 404 for invalid resume session_id instead of silently
        # falling through to create.

    # Session_id is always backend-generated (never client-supplied) to
    # prevent session fixation and ID collision. The frontend receives and
    # stores the opaque token.
    session_id = str(uuid.uuid4())

    shell = runtime.create_session(
        scenario_name=scenario_name,
        session_id=session_id,
    )

    session = shell.session

    return ShellResponse(
        session_id=session_id,
        scenario_name=session.scenario.name,
        stdout=[session.motd],
        stderr=[],
        prompt=shell.render_prompt(),
        status="ok",
    )
