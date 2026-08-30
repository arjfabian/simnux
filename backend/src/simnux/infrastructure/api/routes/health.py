from fastapi import APIRouter
from fastapi import Request

from simnux import __version__


router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    """Lightweight operational check for load balancers and orchestrators."""
    return {"status": "ok", "version": __version__}
