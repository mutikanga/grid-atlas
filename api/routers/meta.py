"""Meta endpoints: health, provenance, runs, months and the import log.

- `/api/health`: is the API up and can it reach the database?
- `/api/meta/provenance`: the current run's provenance (also inside every response).
- `/api/meta/runs`: the model runs, newest first.
- `/api/meta/months`: the 13 study months plus '2030', for the map slider.
- `/api/meta/imports` and `/api/meta/imports/issues`: what was loaded, and the quarantine
  (a row with any `error` issue was rejected).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api import db, provenance, render
from api.routers import LOAD_ERRORS
from api.tables import Col, TableSpec, register

# The prefix is /api rather than /api/meta because /api/health lives here too.
router = APIRouter(prefix="/api", tags=["meta"])

# The study period (contracts section 5) and the forecast year. Used only when the
# months view is empty, so the slider still works on a fresh database.
STUDY_MONTHS = [f"2025-{m:02d}" for m in range(9, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]
FORECAST_YEAR = "2030"

register(TableSpec(
    name="runs",
    title="Model runs",
    view="api.v_runs",
    columns=[
        Col("run_id", "Run"),
        Col("status", "Status"),
        Col("started_at", "Started (EAT)"),
        Col("finished_at", "Finished (EAT)"),
        Col("duration_s", "Duration", "s", 0),
        Col("provenance_level", "Provenance"),
        Col("code_version", "Code version"),
        Col("stages", "Stages"),
        Col("n_inputs", "Input batches", "", 0),
        Col("is_current", "Current"),
        Col("is_pinned", "Pinned"),
        Col("message", "Message"),
    ],
    filters={"status": "status", "run_id": "run_id"},
    order_by="run_id desc",
))

register(TableSpec(
    name="months",
    title="Study months",
    view="api.v_months",
    columns=[
        Col("month", "Month"),
        Col("label", "Label"),
        Col("is_forecast", "Forecast"),
    ],
    filters={},
    order_by="month",
))

register(TableSpec(
    name="import_batches",
    title="Import batches",
    view="api.v_import_batches",
    columns=[
        Col("batch_id", "Batch"),
        Col("dataset", "Dataset"),
        Col("template", "Template"),
        Col("root", "Data root (synthetic, real, open)"),
        Col("received_from", "Received from"),
        Col("received_on", "Received on"),
        Col("adapter", "Adapter"),
        Col("status", "Status"),
        Col("started_at", "Loaded at (EAT)"),
        Col("rows_read", "Rows read", "", 0),
        Col("rows_loaded", "Rows loaded", "", 0),
        Col("rows_rejected", "Rows rejected", "", 0),
        Col("n_errors", "Errors", "", 0),
        Col("n_warnings", "Warnings", "", 0),
        Col("n_info", "Info", "", 0),
        Col("in_current_run", "In current run"),
        Col("message", "Message"),
    ],
    filters={"dataset": "dataset", "status": "status", "root": "root", "batch_id": "batch_id",
             "in_current_run": "in_current_run"},
    order_by="batch_id desc",
))

register(TableSpec(
    name="import_issues",
    title="Import issues (quarantine)",
    view="api.v_import_issues",
    columns=[
        Col("issue_id", "Issue"),
        Col("batch_id", "Batch"),
        Col("dataset", "Dataset"),
        Col("template", "Template"),
        Col("sheet", "Sheet"),
        Col("row_num", "Row"),
        Col("column_name", "Column"),
        Col("severity", "Severity"),
        Col("rule", "Rule"),
        Col("message", "Message"),
        Col("raw_value", "Value received"),
        Col("suggestion", "Suggestion"),
        Col("rejected", "Row rejected"),
    ],
    filters={
        "batch_id": "batch_id",
        "dataset": "dataset",
        "severity": "severity",
        "sheet": "sheet",
        "rule": "rule",
        "rejected": "rejected",
    },
    order_by="batch_id desc, sheet, row_num, issue_id",
))


@router.get("/health", summary="API and database health")
def health() -> JSONResponse:
    """200 when the database answers a trivial query, 503 otherwise.

    `routers_failed` lists router modules that could not be imported (an unfinished slice).
    """
    body: dict[str, Any] = {"status": "ok", "database": "ok", "routers_failed": dict(LOAD_ERRORS)}
    try:
        db.query("SELECT 1 AS ok")
    except Exception as exc:  # any failure means "not healthy"; say why
        body.update(status="error", database=f"{type(exc).__name__}: {exc}"[:300])
        return JSONResponse(body, status_code=503)
    return JSONResponse(body)


@router.get("/meta/provenance", summary="Provenance of the current run")
def current_provenance() -> dict[str, Any]:
    """The current run's provenance: level, label, whether it is real, the watermark text."""
    return provenance.current()


render.table_route(router, "/meta/runs", "runs", "Model runs, newest first")
render.table_route(router, "/meta/imports", "import_batches", "Import batches (the import log)")
render.table_route(router, "/meta/imports/issues", "import_issues", "Import issues and the quarantine")


@router.get("/meta/months", summary="The 13 study months plus 2030")
def months(request: Request) -> dict[str, Any]:
    """The months for the map slider, oldest first, always ending with '2030'.

    Rows come from `api.v_months` (forecast years appear there as 'YYYY'). If the view has
    no study months yet the contract's study period is used, and '2030' is added when
    missing, so the slider always has its 14 stops.
    """
    payload = render.table_payload("months", request.query_params)
    study = [r for r in payload["rows"] if not r.get("is_forecast")]
    forecast = [r for r in payload["rows"] if r.get("month") == FORECAST_YEAR]
    if not study:
        study = [{"month": m, "label": m, "is_forecast": False} for m in STUDY_MONTHS]
    if not forecast:
        forecast = [{"month": FORECAST_YEAR, "label": f"{FORECAST_YEAR} (forecast)", "is_forecast": True}]
    payload["rows"] = study + forecast[:1]
    return payload
