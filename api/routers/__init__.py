"""API routers: one module per area, discovered automatically.

Each module in this folder exposes `router = APIRouter(prefix="/api/<area>")` and
registers its tables with `api.tables.register(...)` at import time. `api/main.py`
calls `discover()` so a new slice only has to drop its file here.

A module that fails to import is skipped and its error is kept in `LOAD_ERRORS`, so one
unfinished slice cannot take the whole API down. `/api/health` reports these errors.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import traceback

from fastapi import APIRouter

log = logging.getLogger("atlas.api")

# module name -> the last line of its import error
LOAD_ERRORS: dict[str, str] = {}


def discover() -> list[tuple[str, APIRouter]]:
    """Import every router module in this package and return (module name, router) pairs.

    Modules are imported in name order, so the result is the same on every start.
    """
    found: list[tuple[str, APIRouter]] = []
    LOAD_ERRORS.clear()
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        full = f"{__name__}.{info.name}"
        try:
            module = importlib.import_module(full)
        except Exception as exc:  # keep the API up; report the broken router instead
            LOAD_ERRORS[info.name] = f"{type(exc).__name__}: {exc}"
            log.error("router %s failed to import:\n%s", full, traceback.format_exc())
            continue
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            found.append((info.name, router))
        else:
            LOAD_ERRORS[info.name] = "module has no `router = APIRouter(...)`"
    return found
