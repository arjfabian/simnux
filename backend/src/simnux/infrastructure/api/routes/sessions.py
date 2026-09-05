"""Session management endpoints for SIMNUX.

Provides read-only introspection and session destruction for the frontend.
"""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request


router = APIRouter()


@router.get("/api/sessions/{session_id}")
async def session_snapshot(
    request: Request,
    session_id: str,
):
    """Provides the frontend with a flattened view of session internals.

    Rejects 404 for unknown sessions.
    Read-only by construction — no mutators are exposed.
    """

    runtime = request.app.state.runtime
    session = runtime.get_session(session_id)

    if session is None or not session.shells:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    shell = session.active_shells[0]

    return {
        "session_id": session.session_id,
        "scenario_name": shell.scenario.name,
        "loaded_commands": shell.registry.list_commands(),
        "filesystem": shell.filesystem.list_paths(),
        "current_path": shell.current_directory,
    }


@router.delete("/sessions/{session_id}")
async def destroy_session(
    session_id: str,
    request: Request,
):
    """Destroy an active session, freeing its runtime resources.

    Idempotent — returns 200 even if the session was already removed.
    Used by the frontend when switching scenarios to prevent session leaks.
    """

    runtime = request.app.state.runtime
    runtime.destroy_session(session_id)

    return {"status": "ok", "session_id": session_id}
