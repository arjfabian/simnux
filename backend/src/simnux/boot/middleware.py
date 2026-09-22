"""FastAPI middleware configuration for SIMNUX."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])


def configure_middleware(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Enable proxy header inspection for accurate client IP resolution behind a reverse proxy
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
    app.add_middleware(SlowAPIMiddleware)

    raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8001,http://127.0.0.1:8001")
    allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
