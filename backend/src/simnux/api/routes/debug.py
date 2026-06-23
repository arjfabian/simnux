"""Debug introspection endpoints for SIMNUX.

Exposes internal runtime state for development and inspection purposes.
These endpoints are not part of the stable public API.
"""

from fastapi import APIRouter
from fastapi import Request

from simnux.observability.snapshots import RuntimeSnapshot


router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/runtime")
async def runtime_snapshot(request: Request) -> RuntimeSnapshot:
    """Exposes the full runtime object graph for development inspection.

    Intentionally unfiltered; not suitable for production consumption.
    """

    # Endpoint delivers unredacted runtime state by design. Remove or gate
    # this router in production deployments.
    return request.app.state.runtime.get_snapshot()
