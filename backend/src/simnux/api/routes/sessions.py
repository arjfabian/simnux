"""Session introspection endpoint for SIMNUX.

Returns a snapshot of an active shell session for UI rendering and debugging.
This is a read-only view over runtime state and does not allow mutation.
"""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request


router = APIRouter()


@router.get("/sessions/{session_id}")
async def session_snapshot(
    session_id: str,
    request: Request,
):
    """Provides the frontend with a flattened view of session internals.

    Rejects 404 for unknown sessions.
    Read-only by construction — no mutators are exposed.
    """

    runtime = request.app.state.runtime

    # Guard against access to unknown session_id. Session isolation is enforced
    # at this single check point.
    if not runtime.exists(session_id):
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    shell = runtime.get_session(session_id)

    # Frontend contract: flatten internal runtime structures into a single
    # response shape to decouple UI from internal representation.
    return {
        "session_id": shell.session.session_id,
        "scenario_name": shell.session.scenario.name,
        "loaded_commands": shell.registry.list_commands(),
        "filesystem": shell.filesystem.list_paths(),
        "current_path": shell.session.current_directory,
    }
