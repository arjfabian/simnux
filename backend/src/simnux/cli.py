"""SIMNUX runtime entrypoint.

Exposes CLI startup via `simnux` console script or `python -m simnux`.
"""

import os

import uvicorn


def main() -> None:
    """Start the FastAPI server using uvicorn."""

    uvicorn.run(
        "simnux.boot.app_factory:create_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        factory=True,
        reload=_is_dev_reload_enabled(),
    )


def _is_dev_reload_enabled() -> bool:
    """Enable uvicorn hot reload via SIMNUX_RELOAD env var."""
    return os.getenv("SIMNUX_RELOAD", "false").lower() == "true"
