"""Provenance of the current run: is this data synthetic, approximate or real?

Every API response carries this object, every page shows it in a banner, and every
export carries it in a column, a file-name prefix and a README sheet. It comes from
`api.v_provenance` (one row: the current run), cached for a few seconds because almost
every request needs it.

The API adds three derived fields so the browser does not have to interpret levels:
- `kind`: one of synthetic, approximate, open, real, none
- `is_real`: True only for open and real (numbers from the real world, though still
  model estimates until a method note is signed: the label says so)
- `watermark`: the text drawn over charts and the map when the data is not real
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from api import db

CACHE_SECONDS = 5.0
EAT = timezone(timedelta(hours=3), "EAT")

_cache: dict[str, Any] = {"at": 0.0, "value": None}

WATERMARKS = {
    "synthetic": "SYNTHETIC: NOT UETCL DATA",
    "approximate": "APPROXIMATE: NOT AN OFFICIAL UETCL FIGURE",
    "none": "NO MODEL RUN YET",
}

# Kinds whose numbers come from the real world (UETCL data or open data). Everything
# else gets a watermark and a file-name prefix.
REAL_KINDS = ("open", "real")

# The level used when there is no run, or the database cannot say. Treat it as not real.
NO_RUN: dict[str, Any] = {
    "run_id": None,
    "level": "none",
    "label": "NO MODEL RUN YET",
    "synthetic": True,
    "detail": {},
    "code_version": None,
    "started_at": None,
    "finished_at": None,
}


def classify(level: str | None, synthetic: bool | None) -> str:
    """Turn the stored level into one of the kinds: synthetic, approximate, open, real, none.

    The engine writes the levels of `engine/provenance.py` (real, open, approximate,
    synthetic). Case, spaces and dashes do not matter. A level that mentions
    "synthetic" (for example "partly synthetic"), a row flagged synthetic, or any
    unrecognised level is treated as synthetic: the safe side.
    """
    norm = "_".join((level or "").lower().replace("-", " ").replace("\u2013", " ").split())
    if norm in ("", "none", "no_run"):
        return "none"
    if "synthetic" in norm or synthetic:
        return "synthetic"
    if "approx" in norm:
        return "approximate"
    if norm == "open":
        return "open"
    if norm.startswith("real"):
        return "real"
    return "synthetic"


def file_prefix(prov: dict[str, Any]) -> str:
    """The prefix for export file names: APPROXIMATE_ or SYNTHETIC_, or none when real."""
    kind = prov.get("kind") or classify(prov.get("level"), prov.get("synthetic"))
    if kind in REAL_KINDS:
        return ""
    if kind == "approximate":
        return "APPROXIMATE_"
    return "SYNTHETIC_"


def enrich(row: dict[str, Any]) -> dict[str, Any]:
    """Add kind, is_real and watermark to a raw provenance row, and make it JSON-safe."""
    out = {k: _plain(v) for k, v in row.items()}
    if isinstance(out.get("detail"), str):
        try:
            out["detail"] = json.loads(out["detail"])
        except ValueError:
            pass
    kind = classify(out.get("level"), out.get("synthetic"))
    out["kind"] = kind
    out["is_real"] = kind in REAL_KINDS
    out["watermark"] = WATERMARKS.get(kind, "")
    if not out.get("label"):
        out["label"] = str(out.get("level") or "").upper()
    return out


def _plain(value: Any) -> Any:
    """Convert database values (timestamps, numpy numbers, NaN) to plain JSON values."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, datetime):  # same 'YYYY-MM-DD HH:MM' EAT form as api.render.plain
        if value.tzinfo is not None:
            value = value.astimezone(EAT)
        return value.strftime("%Y-%m-%d %H:%M")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


def load() -> dict[str, Any]:
    """Read the current provenance from the database (no cache).

    Before the first migration the view does not exist; that counts as "no run".
    """
    try:
        df = db.query(
            "SELECT run_id, level, label, synthetic, detail, code_version, started_at, finished_at "
            "FROM api.v_provenance LIMIT 1"
        )
    except Exception as exc:  # the driver error type depends on the backend
        if getattr(getattr(exc, "orig", None), "sqlstate", None) == "42P01":
            return enrich(dict(NO_RUN))
        raise
    if df.empty:
        return enrich(dict(NO_RUN))
    return enrich(df.iloc[0].to_dict())


def current() -> dict[str, Any]:
    """The current provenance, cached for CACHE_SECONDS. Returns a fresh copy each time."""
    now = time.monotonic()
    if _cache["value"] is None or now - _cache["at"] > CACHE_SECONDS:
        _cache["value"] = load()
        _cache["at"] = now
    return dict(_cache["value"])


def clear_cache() -> None:
    """Forget the cached value (used by tests, and handy after pinning a run)."""
    _cache["value"] = None
    _cache["at"] = 0.0
