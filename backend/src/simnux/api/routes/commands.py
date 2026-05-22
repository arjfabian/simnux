"""Command execution endpoint for SIMNUX.

Bridges HTTP requests to the internal shell runtime.
This layer is intentionally thin to keep protocol logic separate from execution
logic.
"""

from fastapi import APIRouter, HTTPException, Request

from simnux.api.models.contracts import CommandRequest, ShellResponse

router = APIRouter()


@router.post("/execute_command", response_model=ShellResponse)
async def execute(
    request: CommandRequest,
    http_request: Request,
) -> ShellResponse:
    """Dispatch raw shell input to the session-bound shell runtime.

    Rejects with 404 if session_id is unknown.
    Returns structured stdout/stderr, not raw HTTP strings.
    """

    runtime = http_request.app.state.runtime

    # Rejects requests for unknown session_id. Sessions are the security
    # boundary; no command executes without a valid session reference.
    if not runtime.exists(request.session_id):
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    shell = runtime.get_session(request.session_id)
    result = shell.execute(request.command)

    return ShellResponse(
        session_id=request.session_id,
        scenario_name=shell.session.scenario.name,
        stdout=result.stdout,
        stderr=result.stderr,
        prompt=shell.render_prompt(),
        status="ok",
    )
