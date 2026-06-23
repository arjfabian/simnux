"""System health endpoint for SIMNUX.

Provides a lightweight runtime status view for monitoring and frontend bootstrap.
"""

from typing import Any

from fastapi import APIRouter
from fastapi import Request


router = APIRouter()


@router.get("/")
async def root(request: Request) -> dict[str, Any]:
    """Health-check endpoint for monitoring and frontend bootstrap.

    Returns count of active/total sessions, not a full session dump
    (use /sessions/{id} for that). Status is always 'online' when the
    process is running — no dependency checks are performed.
    """

    runtime = request.app.state.runtime
    snapshot = runtime.get_snapshot()

    return {
        "status": "online",
        "runtime": "SIMNUX v0.2.0",
        "active_sessions": snapshot.active_sessions,
        "total_sessions": snapshot.total_sessions,
    }
