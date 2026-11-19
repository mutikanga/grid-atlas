"""The Grid Atlas API application (FastAPI, GET only).

Run inside the api container:  uvicorn api.main:app --host 0.0.0.0 --port 8000

- Every router in `api/routers/` is included automatically (see `api.routers.discover`).
- `/api/docs` is Swagger UI served from our own copy in `web/vendor/swagger-ui/`
  (Nginx serves it at `/vendor/swagger-ui/`), because the server has no internet and
  FastAPI's default docs page loads Swagger from a CDN.
- `/api/openapi.json` is the machine-readable description of every endpoint.
- There are no POST, PUT or DELETE routes anywhere: the Atlas only reads.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from api.routers import discover

SWAGGER_JS = "/vendor/swagger-ui/swagger-ui-bundle.js"
SWAGGER_CSS = "/vendor/swagger-ui/swagger-ui.css"
FAVICON = "/favicon.svg"


def code_version() -> str:
    """The code version: $CODE_VERSION, else the VERSION file at the repo root, else 'dev'."""
    env = os.environ.get("CODE_VERSION")
    if env:
        return env
    path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return path.read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


def create_app() -> FastAPI:
    """Build the app and include every router found in api/routers/."""
    app = FastAPI(
        title="UETCL Grid Atlas API",
        version=code_version(),
        description=(
            "Read-only API of the Grid Atlas. Every response carries `provenance`: "
            "check it before using any number. Units are in each column's `unit` and in "
            "the column-name suffix (`_mw`, `_mwh`, `_pct`, ...)."
        ),
        docs_url=None,  # replaced below by the self-hosted page
        redoc_url=None,
        openapi_url="/api/openapi.json",
        swagger_ui_oauth2_redirect_url=None,
    )
    for _name, router in discover():
        app.include_router(router)

    @app.get("/api/docs", include_in_schema=False, response_class=HTMLResponse)
    def swagger_docs() -> HTMLResponse:
        """Swagger UI using the vendored assets, never a CDN."""
        return get_swagger_ui_html(
            openapi_url="/api/openapi.json",
            title="Grid Atlas API",
            swagger_js_url=SWAGGER_JS,
            swagger_css_url=SWAGGER_CSS,
            swagger_favicon_url=FAVICON,
        )

    return app


app = create_app()
