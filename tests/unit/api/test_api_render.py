"""Tests for the one render path: SQL building, rounding, CSV and XLSX outputs."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import numpy as np
import openpyxl
import pandas as pd
import pytest
from fastapi import HTTPException

from api import provenance, render, tables
from api.tables import Col, TableSpec

SPEC = TableSpec(
    name="test_losses",
    title="Test losses",
    view="api.v_test_losses",
    columns=[
        Col("month", "Month"),
        Col("element_id", "Element"),
        Col("loss_mwh", "Losses", "MWh", 1),
        Col("loading_pct", "Loading", "%", 0),
        Col("in_central", "In Central"),
    ],
    filters={"month": "month", "element": "element_id"},
    order_by="month, element_id desc",
)

FRAME = pd.DataFrame([
    {"month": "2026-03", "element_id": "L-KAW-MUT-132-1", "loss_mwh": 1234.5678,
     "loading_pct": 87.6, "in_central": True},
    {"month": "2026-03", "element_id": "T-KAW-1", "loss_mwh": np.nan, "loading_pct": np.float64(101.49),
     "in_central": False},
])


def view_call(fake, view):
    """The last SQL call that read `view`, with its bound parameters."""
    return [c for c in fake.calls if view in c[0]][-1]


@pytest.fixture
def losses(fake_db):
    """Register the test table and serve FRAME for its view."""
    tables.register(SPEC)
    fake_db.frames["api.v_test_losses"] = FRAME
    return fake_db


def test_select_sql_binds_values_and_never_formats_them():
    sql, bind = render.select_sql(SPEC, {"month": "2026-03'; DROP TABLE x; --", "element": "T-KAW-1"})
    assert "DROP" not in sql
    assert sql == (
        "SELECT month, element_id, loss_mwh, loading_pct, in_central FROM api.v_test_losses "
        "WHERE month::text = :f0 AND element_id::text = :f1 ORDER BY month, element_id desc"
    )
    assert bind == {"f0": "2026-03'; DROP TABLE x; --", "f1": "T-KAW-1"}


def test_unknown_and_blank_filters_are_ignored():
    got = render.allowed_filters(SPEC, {"month": "2026-03", "element": "", "view": "meta.run", "x": "1"})
    assert got == {"month": "2026-03"}


def test_overlong_filter_is_refused():
    with pytest.raises(HTTPException) as err:
        render.allowed_filters(SPEC, {"month": "x" * 500})
    assert err.value.status_code == 400


def test_table_payload_shape_and_rounding(losses):
    payload = render.table_payload("test_losses", {"month": "2026-03", "bogus": "1"})
    assert set(payload) >= {"table", "title", "provenance", "columns", "rows", "export"}
    assert payload["table"] == "test_losses"
    assert payload["columns"][2] == {"key": "loss_mwh", "label": "Losses", "unit": "MWh", "decimals": 1}
    assert payload["rows"][0] == {"month": "2026-03", "element_id": "L-KAW-MUT-132-1", "loss_mwh": 1234.6,
                                  "loading_pct": 88, "in_central": True}
    assert payload["rows"][1]["loss_mwh"] is None  # NaN becomes null
    assert payload["rows"][1]["loading_pct"] == 101 and isinstance(payload["rows"][1]["loading_pct"], int)
    assert payload["export"] == {"csv": "/export/test_losses.csv?month=2026-03",
                                 "xlsx": "/export/test_losses.xlsx?month=2026-03"}
    assert payload["provenance"]["kind"] == "synthetic"
    sql, params = view_call(losses, "api.v_test_losses")
    assert "2026-03" not in sql and params == {"f0": "2026-03"}


def test_unknown_table_is_404(fake_db):
    with pytest.raises(HTTPException) as err:
        render.table_payload("no_such_table", {})
    assert err.value.status_code == 404


def test_missing_view_is_404_not_500(fake_db, monkeypatch):
    class Orig:
        sqlstate = "42P01"

    class UndefinedTable(Exception):
        orig = Orig()

    def boom(sql, params=None):
        raise UndefinedTable("relation does not exist")

    tables.register(SPEC)
    monkeypatch.setattr(render.db, "query", boom)
    with pytest.raises(HTTPException) as err:
        render.fetch(SPEC, {})
    assert err.value.status_code == 404


def test_plain_formats_datetimes_in_eat():
    assert render.plain(datetime(2026, 3, 1, 17, 0, tzinfo=timezone.utc)) == "2026-03-01 20:00"
    assert render.plain(pd.Timestamp("2026-03-01")) == "2026-03-01 00:00"
    assert render.plain(np.int64(5)) == 5 and isinstance(render.plain(np.int64(5)), int)
    assert render.plain(pd.NaT) is None


def test_csv_has_bom_provenance_first_and_rounded_values(losses):
    prov = provenance.current()
    body = render.csv_bytes(SPEC, FRAME, prov)
    assert body.startswith("﻿".encode("utf-8"))
    lines = body.decode("utf-8-sig").splitlines()
    assert lines[0] == "provenance,month,element_id,loss_mwh,loading_pct,in_central"
    assert lines[1] == "SYNTHETIC: NOT UETCL DATA,2026-03,L-KAW-MUT-132-1,1234.6,88,Y"
    assert lines[2] == "SYNTHETIC: NOT UETCL DATA,2026-03,T-KAW-1,,101,N"


def test_csv_export_matches_json(client, losses):
    json_rows = client.get("/api/meta/runs").json()  # warm the provenance cache
    assert json_rows["rows"]
    payload = render.table_payload("test_losses", {})
    resp = client.get("/export/test_losses.csv")
    lines = resp.content.decode("utf-8-sig").splitlines()[1:]
    for row, line in zip(payload["rows"], lines):
        cells = line.split(",")[1:]
        assert cells[2] == ("" if row["loss_mwh"] is None else f"{row['loss_mwh']:.1f}")
        assert cells[3] == str(row["loading_pct"])


def test_export_filename_prefix(losses):
    synthetic = provenance.enrich({"run_id": 7, "level": "synthetic", "synthetic": True})
    approximate = provenance.enrich({"run_id": 7, "level": "approximate", "synthetic": False})
    real = provenance.enrich({"run_id": 7, "level": "real", "synthetic": False})
    assert render.export_filename(SPEC, synthetic, "csv") == "SYNTHETIC_test_losses_run7.csv"
    assert render.export_filename(SPEC, approximate, "xlsx") == "APPROXIMATE_test_losses_run7.xlsx"
    assert render.export_filename(SPEC, real, "csv") == "test_losses_run7.csv"


def test_csv_download_response(client, losses):
    resp = client.get("/export/test_losses.csv", params={"month": "2026-03", "nope": "x"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="SYNTHETIC_test_losses_run7.csv"' in resp.headers["content-disposition"]
    sql, params = view_call(losses, "api.v_test_losses")
    assert params == {"f0": "2026-03"} and "nope" not in sql


def test_xlsx_readme_banner_precision_and_format(client, losses):
    resp = client.get("/export/test_losses.xlsx", params={"month": "2026-03"})
    assert resp.status_code == 200
    assert 'filename="SYNTHETIC_test_losses_run7.xlsx"' in resp.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["README", "test_losses"]
    readme = {row[0]: row[1] for row in wb["README"].iter_rows(values_only=True) if row and row[0]}
    assert readme["Run id"] == 7
    assert readme["Provenance"] == "SYNTHETIC: NOT UETCL DATA"
    assert readme["Filters"] == "month=2026-03"
    assert "Generated" in readme
    assert "gridatlas-synthetic" in (wb.properties.keywords or "")
    data = wb["test_losses"]
    assert "SYNTHETIC" in str(data["A1"].value)  # red banner row
    assert data["A1"].fill.fgColor.rgb.endswith("B00020")
    assert [c.value for c in data[2]] == ["provenance", "Month", "Element", "Losses (MWh)", "Loading (%)",
                                          "In Central"]
    assert data["A3"].value == "SYNTHETIC: NOT UETCL DATA"
    assert data["D3"].value == pytest.approx(1234.5678)  # full precision kept
    assert data["D3"].number_format == "#,##0.0"
    assert data["E3"].number_format == "#,##0"


def test_xlsx_has_no_banner_when_real(losses, monkeypatch):
    real = provenance.enrich({"run_id": 9, "level": "real", "label": "TRAINEE SHOWCASE", "synthetic": False})
    body = render.xlsx_bytes(SPEC, FRAME, real, {})
    wb = openpyxl.load_workbook(io.BytesIO(body))
    assert wb["test_losses"]["A1"].value == "provenance"
