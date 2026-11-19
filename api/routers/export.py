"""Downloads: any registered table as CSV or Excel, with the same filters as the screen.

    /export/<name>.csv?month=2026-03
    /export/<name>.xlsx?month=2026-03

`<name>` must be in the registry (`api/tables.py`); anything else is a 404, so a request
can never choose a view or column that a developer did not list. `/export/` alone lists
the available tables.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api import render, tables

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/", summary="List the tables that can be downloaded")
def list_exports() -> dict[str, Any]:
    """Every registered table with its filters and download links."""
    return {
        "tables": [
            {
                "name": spec.name,
                "title": spec.title,
                "filters": sorted(spec.filters),
                "export": render.export_links(spec, {}),
            }
            for spec in tables.all()
        ]
    }


@router.get("/{name}.csv", summary="Download a table as CSV")
def export_csv(name: str, request: Request) -> Response:
    """CSV in UTF-8 with BOM, values rounded as on screen, `provenance` as the first column.

    The file name starts with SYNTHETIC_ or APPROXIMATE_ when the data is not real.
    """
    return render.download(name, request.query_params, "csv")


@router.get("/{name}.xlsx", summary="Download a table as Excel")
def export_xlsx(name: str, request: Request) -> Response:
    """Excel workbook: README sheet (provenance, run, filters, time), then the data at full
    precision with the screen's number format, `provenance` first, and a red banner row
    when the data is not real."""
    return render.download(name, request.query_params, "xlsx")
