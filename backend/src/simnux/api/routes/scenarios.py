"""Scenario listing endpoint for SIMNUX.

Exposes the set of available scenario choices to the frontend
via a simple GET endpoint.
"""

from fastapi import APIRouter

from simnux.scenarios.loader import ScenarioLoader


router = APIRouter()


@router.get("/api/scenarios")
async def list_scenarios():
    """Return all available scenario names."""
    return {"scenarios": ScenarioLoader.list_available()}
