"""Regression tests for bugs found in the F4 review (one test per bug)."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

from api import provenance, render, tables
from api.tables import Col, TableSpec

ROOT = Path(__file__).resolve().parents[3]

SPEC = TableSpec(
    name="review_table",
    title="Review table",
    view="api.v_review_table",
    columns=[
        Col("batch_id", "Batch"),
        Col("raw_value", "Value received"),
        Col("loss_mwh", "Losses", "MWh", 0),
        Col("loading_pct", "Loading", "%", 2),
        Col("in_central", "In Central"),
    ],
    filters={"in_central": "in_central", "batch_id": "batch_id"},
    order_by="batch_id",
)

# batch_id has a blank, so pandas stores the column as float (3.0): a real case for
# ids, row numbers and commissioning years read from the database.
FRAME = pd.DataFrame([
    {"batch_id": 3, "raw_value": '=HYPERLINK("http://x","click")', "loss_mwh": 2.5,
     "loading_pct": 0.125, "in_central": True},
    {"batch_id": None, "raw_value": "-5", "loss_mwh": -2.5, "loading_pct": 1.005, "in_central": False},
])


@pytest.fixture
def review(fake_db):
    tables.register(SPEC)
    fake_db.frames["api.v_review_table"] = FRAME
    return fake_db


# Bug 1: round() is banker's rounding on binary floats, so the screen and CSV showed
# 2 for 2.5 and 0.12 for 0.125 while Excel's number format shows 3 and 0.13.
@pytest.mark.parametrize("value, decimals, expected", [
    (2.5, 0, 3), (3.5, 0, 4), (-2.5, 0, -3), (0.125, 2, 0.13), (1.005, 2, 1.01),
    (1234.5678, 1, 1234.6), (7, 2, 7.0), (-0.04, 1, 0.0),
])
def test_rounding_matches_excel_half_away_from_zero(value, decimals, expected):
    got = render.round_value(value, decimals)
    assert got == expected
    assert type(got) is (int if decimals == 0 else float)


def test_rounding_never_gives_negative_zero():
    assert math.copysign(1.0, render.round_value(-0.04, 1)) == 1.0


def test_rounding_survives_huge_numbers():
    assert render.round_value(1e40, 10) == pytest.approx(1e40)


def test_json_and_csv_round_halves_the_same_way(review):
    payload = render.table_payload("review_table", {})
    assert payload["rows"][0]["loss_mwh"] == 3 and payload["rows"][0]["loading_pct"] == 0.13
    assert payload["rows"][1]["loss_mwh"] == -3 and payload["rows"][1]["loading_pct"] == 1.01
    lines = render.csv_bytes(SPEC, FRAME, provenance.current()).decode("utf-8-sig").splitlines()
    assert lines[1].split(",")[-3:] == ["3", "0.13", "Y"]
    assert lines[2].split(",")[-3:] == ["-3", "1.01", "N"]


# Bug 2: a boolean column cast to text reads 'true'/'false', so ?in_central=Y (the
# contract's yes/no form) matched nothing.
def test_yes_no_filter_matches_booleans_and_y_n_text():
    sql, bind = render.select_sql(SPEC, {"in_central": "Y", "batch_id": "3"})
    assert "in_central::text IN (:f0, :f0a)" in sql
    assert "batch_id::text = :f1" in sql
    assert bind == {"f0": "Y", "f0a": "true", "f1": "3"}
    _, bind = render.select_sql(SPEC, {"in_central": "false"})
    assert bind == {"f0": "false", "f0a": "N"}


# Bug 3: CSV formula injection. Raw values come from delivered files; a cell such as
# =HYPERLINK(...) ran as a formula when the CSV was opened in Excel.
def test_csv_text_cells_cannot_become_formulas(review):
    body = render.csv_bytes(SPEC, FRAME, provenance.current()).decode("utf-8-sig")
    assert "'=HYPERLINK" in body
    assert ",-5," in body  # a number written as text stays a number
    assert render.csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert render.csv_safe("+1.5e3") == "+1.5e3"
    assert render.csv_safe("Kawanda") == "Kawanda"


# Bug 4: an id column with a blank arrives as float, and the CSV printed '3.0'.
def test_csv_prints_whole_floats_without_decimals_when_column_has_none(review):
    lines = render.csv_bytes(SPEC, FRAME, provenance.current()).decode("utf-8-sig").splitlines()
    assert lines[1].split(",")[1] == "3"
    assert lines[2].split(",")[1] == ""


# Bug 5: /api/network/geo gave a 500 before the views exist; tables give a 404.
def test_network_geo_missing_view_is_404(client, monkeypatch):
    class Orig:
        sqlstate = "42P01"

    class UndefinedTable(Exception):
        orig = Orig()

    real_query = render.db.query

    def boom(sql, params=None):
        if "api.v_substations" in sql:
            raise UndefinedTable("relation api.v_substations does not exist")
        return real_query(sql, params)

    monkeypatch.setattr(render.db, "query", boom)
    resp = client.get("/api/network/geo")
    assert resp.status_code == 404
    assert "v_substations" in resp.json()["detail"]


def test_query_view_reraises_other_errors(fake_db, monkeypatch):
    def boom(sql, params=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(render.db, "query", boom)
    with pytest.raises(RuntimeError):
        render.query_view("SELECT 1", {}, "x", "api.v_x")
    with pytest.raises(HTTPException) as err:
        class Orig:
            sqlstate = "42P01"

        class Missing(Exception):
            orig = Orig()

        def missing(sql, params=None):
            raise Missing("no view")

        monkeypatch.setattr(render.db, "query", missing)
        render.query_view("SELECT 1", {}, "x", "api.v_x")
    assert err.value.status_code == 404


# Bug 6 (web): table cells in columns without decimals (ids, years) were formatted with
# a thousands separator, so a commissioning year showed as '1,998'. The behaviour is
# checked with node in tmp/F4-review/jscheck; this guards that table() uses cellText.
def test_table_cells_use_cell_text_for_ids_and_years():
    js = (ROOT / "web/js/common.js").read_text(encoding="utf-8")
    assert "export function cellText(value, col)" in js
    assert "const text = cellText(row[col.key], col);" in js
    assert "Number.isInteger(value)) return String(value)" in js
