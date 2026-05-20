"""Auto-discover and register API routes for SIMNUX.

Uses pkgutil.iter_modules to find all modules under simnux.api.routes.
Every module with an ``APIRouter`` attribute named ``router`` is automatically
included. New routes only need a new module in that package — no manual
wiring.
"""

import importlib
import pkgutil

from fastapi import FastAPI
from fastapi.routing import APIRouter

import simnux.api.routes as routes_pkg


def register_routes(app: FastAPI) -> None:
    """Auto-discover and mount all submodules of simnux.api.routes that
    export an ``APIRouter`` instance. Skips modules starting with '_'.
    New API routes require no registration code beyond creating the module.
    """

    for _, module_name, _ in pkgutil.iter_modules(routes_pkg.__path__):
        if module_name.startswith("_"):
            continue

        module = importlib.import_module(f"simnux.api.routes.{module_name}")
        router = getattr(module, "router", None)

        if isinstance(router, APIRouter):
            app.include_router(router)
