"""SIMNUX application lifecycle hooks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan context manager.

    Currently logs startup/shutdown events. Future expansion: connection pool
    teardown, scenario cache invalidation, session cleanup.
    """

    logger = app.state.logger

    logger.info("SIMNUX runtime starting")

    yield

    logger.info("SIMNUX runtime shutting down")
