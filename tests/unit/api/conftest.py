"""Shared fixtures for the API unit tests. No database: `api.db.query` is replaced by a fake.

The fake answers by looking for a view name in the SQL, and records every call so tests
can check that request values arrive only as bound parameters.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import db, provenance

UTC = timezone.utc

SYNTHETIC_PROV = {
    "run_id": 7,
    "level": "synthetic",
    "label": "SYNTHETIC: NOT UETCL DATA",
    "synthetic": True,
    "detail": {"inputs": ["ncc_monthly", "network_model"]},
    "code_version": "0.1.0-test",
    "started_at": datetime(2026, 11, 1, 6, 0, tzinfo=UTC),
    "finished_at": datetime(2026, 11, 1, 6, 5, tzinfo=UTC),
}


class FakeDB:
    """Stands in for `api.db.query`. `frames` maps a view name to the DataFrame it returns."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        self.calls.append((sql, dict(params or {})))
        if "SELECT 1" in sql:
            return pd.DataFrame({"ok": [1]})
        for view, frame in self.frames.items():
            if view in sql:
                return frame.copy()
        raise AssertionError(f"unexpected SQL in test: {sql}")


def default_frames(prov: dict[str, Any] | None = None) -> dict[str, pd.DataFrame]:
    """Small DataFrames for the core views."""
    return {
        "api.v_provenance": pd.DataFrame([prov or SYNTHETIC_PROV]),
        "api.v_runs": pd.DataFrame([
            {"run_id": 7, "status": "ok", "started_at": datetime(2026, 11, 1, 6, 0, tzinfo=UTC),
             "finished_at": datetime(2026, 11, 1, 6, 5, tzinfo=UTC), "provenance_level": "synthetic",
             "code_version": "0.1.0-test", "stages": ["network", "losses"], "is_current": True, "message": None,
             "duration_s": 300.0, "n_inputs": 4, "is_pinned": False},
        ]),
        "api.v_months": pd.DataFrame([
            {"month": "2025-09", "label": "Sep 2025", "is_forecast": False},
            {"month": "2025-10", "label": "Oct 2025", "is_forecast": False},
        ]),
        "api.v_import_batches": pd.DataFrame([
            {"batch_id": 3, "dataset": "ncc_monthly", "template": "T03", "root": "synthetic",
             "received_from": "engine/synthetic", "received_on": "2026-11-01",
             "status": "ok", "started_at": datetime(2026, 11, 1, 5, 0, tzinfo=UTC), "rows_read": 120,
             "rows_loaded": 118, "rows_rejected": 2, "n_errors": 2, "n_warnings": 5, "message": "",
             "adapter": "template", "n_info": 0, "in_current_run": True},
        ]),
        "api.v_import_issues": pd.DataFrame([
            {"issue_id": 1, "batch_id": 3, "dataset": "ncc_monthly", "sheet": "system_summary", "row_num": 4,
             "column_name": "sent_out_mwh", "severity": "error", "rule": "min", "message": "below 0",
             "raw_value": "-5", "suggestion": None, "template": "T03", "rejected": True},
        ]),
        "api.v_substations": pd.DataFrame([
            {"ss_code": "KAW", "name": "Kawanda", "kv_levels": "132/33", "district": "Wakiso",
             "in_central": True, "lon": 32.5, "lat": 0.42},
            {"ss_code": "MUT", "name": "Mutundwe", "kv_levels": [132, 33], "district": "Kampala",
             "in_central": True, "lon": None, "lat": None},
        ]),
        "api.v_elements": pd.DataFrame([
            {"element_type": "line", "element_id": "L-KAW-MUT-132-1", "name": "Kawanda - Mutundwe 1",
             "ss_from": "KAW", "ss_to": "MUT", "kv": 132.0, "length_km": 12.3456, "in_central": True,
             "rate_mva": 120.04, "commissioning_year": 1998, "age_years": 28.0, "status": "existing",
             "geojson": '{"type": "LineString", "coordinates": [[32.5, 0.42], [32.55, 0.30]]}'},
            {"element_type": "trafo", "element_id": "T-KAW-1", "name": "Kawanda T1",
             "ss_from": "KAW", "ss_to": "KAW", "kv": 132.0, "length_km": None, "in_central": True,
             "rate_mva": 60.0, "commissioning_year": 2010, "age_years": 16.0, "status": "existing",
             "geojson": None},
        ]),
    }


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDB:
    """Replace the database with small frames and clear the provenance cache."""
    fake = FakeDB(default_frames())
    monkeypatch.setattr(db, "query", fake)
    provenance.clear_cache()
    yield fake
    provenance.clear_cache()


@pytest.fixture
def client(fake_db: FakeDB) -> TestClient:
    """A test client for the full app, backed by the fake database."""
    from api.main import app

    return TestClient(app)


def eat(dt: datetime) -> str:
    """How the API prints a date-time: 'YYYY-MM-DD HH:MM' in EAT."""
    return dt.astimezone(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M")
