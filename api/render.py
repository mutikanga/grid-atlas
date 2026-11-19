"""One path from a registered table to JSON, CSV and XLSX.

Why one path: the acceptance tests demand that a download shows exactly the numbers on
the screen. So the screen and both downloads all go through `fetch` (same view, same
filters, same order) and are rounded by the same column spec:

- JSON and CSV values are rounded to each column's `decimals`.
- XLSX keeps full precision, but its cells use a number format with the same decimals,
  so Excel displays the same figures and a user can still compute with them.

Provenance travels with every output: a `provenance` object in JSON, and in the
downloads a first column `provenance`, a file-name prefix (SYNTHETIC_ / APPROXIMATE_)
and, in Excel, a README sheet and a red banner row.

Safety: table and column names come only from the registry (`api/tables.py`). Request
values reach SQL only as bound parameters (`:f0`, `:f1`, ...).
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import xlsxwriter
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from api import db, provenance, tables
from api.tables import TableSpec

EAT = timezone(timedelta(hours=3), "EAT")  # East Africa Time, no daylight saving
MAX_FILTER_LENGTH = 200

# Yes/no columns are stored as Y/N text in the input tables but as booleans in most
# views, and a boolean cast to text reads 'true'/'false'. A filter value of Y also
# matches 'true' (and so on), so `?in_central=Y` works whatever the column type.
YES_NO_ALIASES = {"Y": "true", "N": "false", "true": "Y", "false": "N"}

# A CSV text cell starting with one of these is run as a formula by Excel. Imported
# raw values come from files outside our control, so such cells get a leading quote.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
PLAIN_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
UNDEFINED_TABLE = "42P01"  # Postgres SQLSTATE: the view does not exist (yet)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MIME = "text/csv; charset=utf-8"


# ---------------------------------------------------------------- filters and SQL


def allowed_filters(spec: TableSpec, params: Mapping[str, Any]) -> dict[str, str]:
    """Keep only the request parameters this table declares as filters, and drop blanks.

    Unknown parameters are silently ignored, so a page can pass its whole query string.
    """
    out: dict[str, str] = {}
    for param in spec.filters:
        value = params.get(param)
        if value is None:
            continue
        value = str(value).strip()
        if value == "":
            continue
        if len(value) > MAX_FILTER_LENGTH:
            raise HTTPException(400, f"filter {param} is too long")
        out[param] = value
    return out


def select_sql(spec: TableSpec, filters: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """Build the SELECT for a table. Returns the SQL text and its bound parameters.

    Each filter compares the column as text (`col::text = :fN`), so '2026-03' and
    '132' work whatever the column type, and the value is never part of the SQL
    string. Y/N and true/false are treated as the same answer (see YES_NO_ALIASES).
    """
    cols = ", ".join(spec.column_keys)
    sql = f"SELECT {cols} FROM {spec.view}"
    bind: dict[str, str] = {}
    where = []
    for i, (param, value) in enumerate(filters.items()):
        name = f"f{i}"
        column = spec.filters[param]
        alias = YES_NO_ALIASES.get(value)
        if alias is None:
            where.append(f"{column}::text = :{name}")
        else:
            where.append(f"{column}::text IN (:{name}, :{name}a)")
            bind[f"{name}a"] = alias
        bind[name] = value
    if where:
        sql += " WHERE " + " AND ".join(where)
    if spec.order_by:
        sql += f" ORDER BY {spec.order_by}"
    return sql, bind


def query_view(sql: str, bind: Mapping[str, Any], name: str, view: str) -> pd.DataFrame:
    """Run `db.query`, turning "view does not exist yet" into a 404 instead of a 500."""
    try:
        return db.query(sql, bind)
    except Exception as exc:  # the driver error type depends on the backend
        if getattr(getattr(exc, "orig", None), "sqlstate", None) == UNDEFINED_TABLE:
            raise HTTPException(404, f"{name}: not available yet ({view} does not exist)") from None
        raise


def fetch(spec: TableSpec, filters: Mapping[str, str]) -> pd.DataFrame:
    """Read a registered table. A view that does not exist yet becomes a 404, not a 500."""
    sql, bind = select_sql(spec, filters)
    df = query_view(sql, bind, spec.name, spec.view)
    # A view may return extra columns; keep the registered ones, in order.
    missing = [k for k in spec.column_keys if k not in df.columns]
    for key in missing:
        df[key] = None
    return df[spec.column_keys]


# ---------------------------------------------------------------- value conversion


def plain(value: Any) -> Any:
    """Convert one database value to a plain JSON value (None, bool, int, float, str, list, dict).

    Date-times are shown as 'YYYY-MM-DD HH:MM' in EAT, dates as 'YYYY-MM-DD' (contracts §2).
    """
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, np.datetime64):
        value = pd.Timestamp(value)
        if value is pd.NaT:
            return None
    if isinstance(value, datetime):  # also pandas Timestamp
        if value.tzinfo is not None:
            value = value.astimezone(EAT)
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (np.ndarray, np.generic)):  # numpy array or scalar
        return plain(value.tolist())
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def is_number(value: Any) -> bool:
    """True for int and float values, but not for booleans (a bool is an int in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def round_value(value: Any, decimals: int | None) -> Any:
    """Round a number to the column's decimals; whole numbers become ints. Others pass through.

    Halves round away from zero (2.5 -> 3, 0.125 -> 0.13), as Excel displays them, so
    the screen, the CSV and the Excel cell format all show the same figure. Python's
    own round() would give 2 and 0.12 (banker's rounding and binary floats).
    """
    if decimals is None or not is_number(value):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return value
    step = Decimal(1).scaleb(-decimals)  # 0.01 for 2 decimals
    try:
        rounded = Decimal(repr(value)).quantize(step, rounding=ROUND_HALF_UP)
    except InvalidOperation:  # more digits than Decimal's 28: far beyond any grid figure
        return round(value, decimals) if decimals else int(round(value))
    if decimals == 0:
        return int(rounded)
    return float(rounded) + 0.0  # + 0.0 turns -0.0 into 0.0


def json_rows(spec: TableSpec, df: pd.DataFrame) -> list[dict[str, Any]]:
    """The rows for the JSON response: plain values, rounded per column."""
    rows = []
    for record in df.to_dict(orient="records"):
        rows.append({c.key: round_value(plain(record.get(c.key)), c.decimals) for c in spec.columns})
    return rows


def text_cell(value: Any, decimals: int | None) -> str:
    """Format one value for CSV: rounded numbers with fixed decimals, Y/N for yes/no."""
    value = plain(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    if is_number(value):
        if decimals is None:
            # An id or year read from a column with blanks arrives as a float (12.0).
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value)
        return f"{round_value(value, decimals):.{decimals}f}"
    if isinstance(value, list):
        return "; ".join(text_cell(v, None) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def csv_safe(text: str) -> str:
    """Stop Excel from running a text cell as a formula (CSV injection).

    Numbers never pass through here, and text that is just a number ('-5', a raw value
    from an import) is left alone because Excel reads it as a number, not a formula.
    A text cell such as '=HYPERLINK(...)' becomes "'=HYPERLINK(...)".
    """
    if text.startswith(FORMULA_START) and not PLAIN_NUMBER.match(text):
        return "'" + text
    return text


def csv_cell(value: Any, decimals: int | None) -> str:
    """One CSV cell: `text_cell`, plus formula protection for text values."""
    plain_value = plain(value)
    text = text_cell(plain_value, decimals)
    if isinstance(plain_value, (str, list, dict)):
        return csv_safe(text)
    return text


def excel_cell(value: Any) -> Any:
    """Prepare one value for XlsxWriter: full-precision numbers, text for everything else."""
    value = plain(value)
    if value is None or is_number(value):
        return value
    return text_cell(value, None)


def number_format(decimals: int | None) -> str | None:
    """The Excel number format matching the screen: thousands separator plus fixed decimals."""
    if decimals is None:
        return None
    return "#,##0" + ("." + "0" * decimals if decimals else "")


# ---------------------------------------------------------------- outputs


def export_links(spec: TableSpec, filters: Mapping[str, str]) -> dict[str, str]:
    """Relative download links carrying the same filters as the screen."""
    query = ("?" + urlencode(filters)) if filters else ""
    return {
        "csv": f"/export/{spec.name}.csv{query}",
        "xlsx": f"/export/{spec.name}.xlsx{query}",
    }


def columns_meta(spec: TableSpec) -> list[dict[str, Any]]:
    """Column descriptions for the browser: key, label, unit, decimals."""
    return [{"key": c.key, "label": c.label, "unit": c.unit, "decimals": c.decimals} for c in spec.columns]


def get_spec(name: str) -> TableSpec:
    """Look up a registered table, turning an unknown name into a 404."""
    try:
        return tables.get(name)
    except KeyError:
        raise HTTPException(404, f"no table called {name!r}") from None


def table_payload(name: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """The JSON table response (contracts section 10)."""
    spec = get_spec(name)
    filters = allowed_filters(spec, params)
    df = fetch(spec, filters)
    return {
        "table": spec.name,
        "title": spec.title,
        "provenance": provenance.current(),
        "columns": columns_meta(spec),
        "rows": json_rows(spec, df),
        "filters": filters,
        "export": export_links(spec, filters),
    }


def export_filename(spec: TableSpec, prov: Mapping[str, Any], ext: str) -> str:
    """For example SYNTHETIC_loss_monthly_run12.csv. The prefix is empty for real data."""
    run = f"_run{prov['run_id']}" if prov.get("run_id") is not None else ""
    return f"{provenance.file_prefix(dict(prov))}{spec.name}{run}.{ext}"


def csv_bytes(spec: TableSpec, df: pd.DataFrame, prov: Mapping[str, Any]) -> bytes:
    """CSV in UTF-8 with a BOM (so Excel reads µ and Ω correctly), provenance column first.

    Headers are the column keys: their suffix already carries the unit (`loss_mwh`).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(["provenance", *spec.column_keys])
    label = prov.get("label") or prov.get("level") or ""
    for record in df.to_dict(orient="records"):
        writer.writerow([label, *(csv_cell(record.get(c.key), c.decimals) for c in spec.columns)])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def banner_text(prov: Mapping[str, Any]) -> str:
    """The warning written in red across the top of every data sheet when not real."""
    return (
        f"{prov.get('watermark') or prov.get('label')}. Run {prov.get('run_id')}. "
        "Do not use these numbers in any slide, paper or ERA material."
    )


def readme_rows(spec: TableSpec, prov: Mapping[str, Any], filters: Mapping[str, str]) -> list[tuple[str, Any]]:
    """Key/value lines for the README sheet: what this is, where it came from, how it was cut."""
    generated = datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")
    rows: list[tuple[str, Any]] = [
        ("Table", f"{spec.title} ({spec.name})"),
        ("Provenance", prov.get("label") or prov.get("level")),
        ("Provenance level", prov.get("level")),
        ("Real data", "Y" if prov.get("is_real") else "N"),
        ("Run id", prov.get("run_id")),
        ("Code version", prov.get("code_version")),
        ("Run started", plain(prov.get("started_at"))),
        ("Run finished", plain(prov.get("finished_at"))),
        ("Filters", "; ".join(f"{k}={v}" for k, v in filters.items()) or "none"),
        ("Generated", generated),
        ("Source view", spec.view),
        ("Precision", "Full precision; the cell format shows the same decimals as the screen."),
    ]
    if not prov.get("is_real"):
        rows.append(("Warning", banner_text(prov)))
    detail = prov.get("detail")
    if isinstance(detail, dict):
        for key, value in detail.items():
            rows.append((f"Detail: {key}", text_cell(value, None)))
    return rows


def xlsx_bytes(spec: TableSpec, df: pd.DataFrame, prov: Mapping[str, Any], filters: Mapping[str, str]) -> bytes:
    """An Excel workbook: README sheet first, then the data sheet (opened by default)."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    real = bool(prov.get("is_real"))
    kind = str(prov.get("kind") or "unknown")
    keywords = [f"gridatlas-{kind}"]
    if "synthetic" in kind:
        keywords.append("gridatlas-synthetic")  # the same marker the synthetic inputs carry
    wb.set_properties(
        {
            "title": spec.title,
            "subject": str(prov.get("label") or ""),
            "keywords": ", ".join(keywords),
            "comments": f"Grid Atlas export, run {prov.get('run_id')}, provenance {prov.get('label')}",
        }
    )
    bold = wb.add_format({"bold": True})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    header = wb.add_format({"bold": True, "bg_color": "#E8EDF3", "border": 1, "text_wrap": True, "valign": "top"})
    red = wb.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": "#B00020", "font_size": 13, "valign": "vcenter"}
    )

    readme = wb.add_worksheet("README")
    data = wb.add_worksheet(spec.name[:31])
    if not real:
        readme.set_tab_color("#B00020")
        data.set_tab_color("#B00020")

    # README: banner, key/value lines, then the column dictionary.
    r = 0
    if not real:
        readme.merge_range(r, 0, r, 4, banner_text(prov), red)
        readme.set_row(r, 30)
        r += 2
    for key, value in readme_rows(spec, prov, filters):
        readme.write(r, 0, key, bold)
        readme.write(r, 1, excel_cell(value), wrap)
        r += 1
    r += 1
    for c, title in enumerate(("Column", "Label", "Unit", "Decimals")):
        readme.write(r, c, title, header)
    for col in spec.columns:
        r += 1
        readme.write_row(r, 0, [col.key, col.label, col.unit, "" if col.decimals is None else col.decimals])
    readme.set_column(0, 0, 22)
    readme.set_column(1, 1, 70)
    readme.set_column(2, 3, 10)

    # Data sheet: optional banner row, header with units, then the rows.
    formats = [wb.add_format({"num_format": number_format(c.decimals)}) if c.decimals is not None else None
               for c in spec.columns]
    r = 0
    if not real:
        data.merge_range(r, 0, r, max(len(spec.columns), 1), banner_text(prov), red)
        data.set_row(r, 30)
        r += 1
    data.write(r, 0, "provenance", header)
    for c, col in enumerate(spec.columns, start=1):
        data.write(r, c, f"{col.label} ({col.unit})" if col.unit else col.label, header)
    data.freeze_panes(r + 1, 1)
    label = str(prov.get("label") or prov.get("level") or "")
    for record in df.to_dict(orient="records"):
        r += 1
        data.write(r, 0, label)
        for c, col in enumerate(spec.columns, start=1):
            value = excel_cell(record.get(col.key))
            if value is None:
                continue
            if formats[c - 1] is not None and is_number(value):
                data.write_number(r, c, value, formats[c - 1])
            elif is_number(value):
                data.write_number(r, c, value)
            else:
                data.write_string(r, c, str(value))
    data.set_column(0, 0, 18)
    data.set_column(1, len(spec.columns), 16)
    data.activate()
    wb.close()
    return buf.getvalue()


def download(name: str, params: Mapping[str, Any], ext: str) -> Response:
    """Serve a registered table as a CSV or XLSX attachment, with the screen's filters."""
    spec = get_spec(name)
    filters = allowed_filters(spec, params)
    df = fetch(spec, filters)
    prov = provenance.current()
    if ext == "csv":
        body, mime = csv_bytes(spec, df, prov), CSV_MIME
    elif ext == "xlsx":
        body, mime = xlsx_bytes(spec, df, prov, filters), XLSX_MIME
    else:
        raise HTTPException(404, f"unknown export format {ext!r}")
    filename = export_filename(spec, prov, ext)
    return Response(
        content=body,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Atlas-Provenance": str(prov.get("kind") or ""),
        },
    )


# ---------------------------------------------------------------- router helper


def table_route(router: APIRouter, path: str, name: str, summary: str | None = None) -> None:
    """Add a GET endpoint at `path` that serves registered table `name` as a table response.

    Saves each router from repeating the same five lines:

        register(TableSpec(name="loss_monthly", ...))
        table_route(router, "/monthly", "loss_monthly", "Modelled losses by month")
    """
    spec = get_spec(name)
    filt = ", ".join(f"`{p}`" for p in spec.filters) or "none"
    units = "; ".join(f"{c.key} [{c.unit}]" for c in spec.columns if c.unit)
    description = (
        f"Table `{spec.name}` from `{spec.view}`. Filters (query parameters): {filt}. "
        f"Units: {units or 'none'}. Downloads: `/export/{spec.name}.csv` and `.xlsx` with the same filters."
    )

    def endpoint(request: Request) -> dict[str, Any]:
        return table_payload(name, request.query_params)

    endpoint.__name__ = f"table_{name}"
    router.add_api_route(path, endpoint, methods=["GET"], summary=summary or spec.title, description=description)
