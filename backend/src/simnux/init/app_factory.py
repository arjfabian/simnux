"""
Application factory for SIMNUX.

Bootstraps FastAPI, wiring runtime, logging, middleware, and routes.
This is the single entrypoint for assembling the HTTP application.
All dependencies (logger, runtime, middleware, routes) are wired here,
making dependency flow traceable from one location.
"""

from fastapi import FastAPI

from simnux.observability.logging import setup_simnux_logger
from simnux.runtime.runtime import SNXRuntime

from .config import RuntimeConfig
from .lifecycle import lifespan
from .middleware import configure_middleware
from .routes import register_routes


def create_app() -> FastAPI:
    """Assemble the full FastAPI application: logging, SNXRuntime, CORS
    middleware, and auto-discovered routes. Called once by uvicorn via the
    factory protocol.
    """

    config = RuntimeConfig()

    logger = setup_simnux_logger(config.log_path)
    logger.info("Initializing SIMNUX API")

    app = FastAPI(
        title="SIMNUX Runtime",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.state.logger = logger
    app.state.runtime = SNXRuntime(
        logger=logger,
        config=config,
    )

    logger.info("SNXRuntime initialized")

    configure_middleware(app)
    logger.info("CORS middleware configured")

    register_routes(app)
    logger.info("Routes registered")

    return app
