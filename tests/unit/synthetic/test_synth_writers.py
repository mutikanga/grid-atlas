"""The writers: value formats, repeatable workbooks, manifests, and the dirty injections."""
from __future__ import annotations

import csv
import hashlib
import tomllib
from datetime import date, datetime

import openpyxl
import pandas as pd
import pytest

from engine.synthetic import dirty
from engine.synthetic.generate import safe_out
from engine.synthetic.writers import (Manifest, ManifestFile, format_value, load_specs, write_manifest,
                                      write_workbook)


def test_format_value_uses_contract_forms():
    assert format_value(date(2026, 3, 1), "month") == "2026-03"
    assert format_value(date(2026, 3, 12), "date") == "2026-03-12"
    assert format_value(pd.Timestamp("2026-03-12 20:00"), "datetime") == "2026-03-12 20:00"
    assert format_value(True, "yn") == "Y"
    assert format_value(3.0, "int") == 3
    assert format_value(float("nan"), "number") is None
    assert format_value("", "number") is None


def test_workbook_is_byte_repeatable(tmp_path):
    spec = load_specs()["growth"]
    df = pd.DataFrame([{"scope": "central", "year_from": 2026, "year_to": 2030, "rate_pct_per_yr": 7.0,
                        "scenario": "base", "source": "SYNTHETIC"}])
    a, b = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    write_workbook(a, spec, {"growth_rates": df})
    write_workbook(b, spec, {"growth_rates": df})
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    wb = openpyxl.load_workbook(a)
    assert wb.properties.keywords == "gridatlas-synthetic"
    assert wb.sheetnames[0] == "README"
    rows = list(wb["growth_rates"].iter_rows(values_only=True))
    assert list(rows[0]) == [c["name"] for c in spec["sheets"][0]["columns"]]
    assert rows[1][0] == "central"


def test_manifest_round_trip(tmp_path):
    (tmp_path / "SYNTHETIC_x.csv").write_text("a\n1\n")
    write_manifest(tmp_path, Manifest("scada", "T04", [ManifestFile("SYNTHETIC_x.csv", sheet="hourly_data")]))
    with (tmp_path / "manifest.toml").open("rb") as fh:
        m = tomllib.load(fh)
    assert m["provenance"] == "synthetic" and m["received_on"] == date(2026, 11, 1)
    assert m["files"][0]["sheet"] == "hourly_data"
    assert m["files"][0]["sha256"] == hashlib.sha256(b"a\n1\n").hexdigest()


def test_output_must_stay_under_data_synthetic():
    with pytest.raises(SystemExit):
        safe_out("/tmp/elsewhere")
    with pytest.raises(SystemExit):
        safe_out("data/real")


def _rows(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True)
    rows = list(wb[sheet].iter_rows(values_only=True))
    return pd.DataFrame([r for r in rows[1:]], columns=rows[0])


def test_dirty_injections_on_the_base_files(syn_root, clean_files):
    """Run the dirty injector over the base files read back from disk; every fault lands as recorded."""
    t03 = syn_root / "ncc_monthly" / "SYNTHETIC_T03_ncc_monthly.xlsx"
    sheets = {
        "ncc_monthly": {s: _rows(t03, s) for s in ("substation_monthly", "boundary_meters", "generation_monthly")},
        "ncc_operations": {"events": _rows(syn_root / "ncc_operations" / "SYNTHETIC_T05_ncc_operations.xlsx", "events")},
        "commercial": {"bsp_sales": _rows(syn_root / "commercial" / "SYNTHETIC_T06_commercial.xlsx", "bsp_sales")},
    }
    with (syn_root / "scada" / "SYNTHETIC_scada_2026-08.csv").open(newline="") as fh:
        rows = list(csv.reader(fh))
    scada = {"2026-08": pd.DataFrame(rows[1:], columns=rows[0])}
    n_sub = len(sheets["ncc_monthly"]["substation_monthly"])
    log = dirty.inject(sheets, scada)
    kinds = {i["kind"] for i in log}
    assert {"misspelled_name", "kwh_entered_as_mwh", "duplicate_key", "missing_required", "bad_enum"} <= kinds
    sub = sheets["ncc_monthly"]["substation_monthly"]
    assert len(sub) == n_sub + 1
    for inj in log:
        if inj["dataset"] == "ncc_monthly" and inj["sheet"] == "substation_monthly" and inj["kind"] == "misspelled_name":
            assert sub.at[inj["data_index"], "substation"] == inj["value"]
    assert all(i["excel_row"] == i["data_index"] + 2 for i in log)
    assert scada["2026-08"].duplicated(["timestamp", "point_id"]).sum() == 3
