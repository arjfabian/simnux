"""FastAPI middleware configuration for SIMNUX."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def configure_middleware(app: FastAPI) -> None:
    """Configure CORS middleware for the development frontend.

    Enables browser-based access from the local dev server.
    CORS origins are hardcoded to localhost:8001 (the frontend dev server).
    Widen this list for production deployments.
    """

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8001",
            "http://127.0.0.1:8001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
