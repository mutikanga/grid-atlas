"""Tests for engine/inputs.py: base-case choice, normalisation, lazy SCADA, loading through a fake ctx."""
from __future__ import annotations

import logging

import pandas as pd

from engine import inputs as inp


def test_choose_base_case():
    cases = pd.DataFrame({"case_id": ["A", "B", "C"], "case_type": ["light_load", "as_operated_peak", "as_operated_peak"]})
    assert inp.choose_base_case(cases) == "B"
    assert inp.choose_base_case(cases, "C") == "C"
    assert inp.choose_base_case(cases[cases.case_id == "A"]) == "A"
    assert inp.choose_base_case(pd.DataFrame()) == ""


def test_normalise_months_and_times():
    df = pd.DataFrame({
        "month": [pd.Timestamp("2026-03-01").date()],
        "peak_at": [pd.Timestamp("2026-03-10 17:00", tz="UTC")],
    })
    out = inp.normalise(df)
    assert out["month"].iloc[0] == "2026-03"
    assert out["peak_at"].iloc[0] == pd.Timestamp("2026-03-10 20:00")


def test_scada_is_loaded_lazily_once():
    calls = []

    def loader(month):
        calls.append(month)
        return pd.DataFrame({"timestamp": [pd.Timestamp("2026-03-01")], "point_id": ["P1"],
                             "value": [1.0], "unit": ["MW"], "quality": ["good"]})

    inputs = inp.Inputs(scada_loader=loader)
    assert calls == []
    assert len(inputs.scada("2026-03")) == 1
    inputs.scada("2026-03")
    assert calls == ["2026-03"]
    assert inp.Inputs().scada("2026-04").empty


class FakeCtx:
    """Stands in for RunContext: tables come from a dict, missing ones are empty."""

    def __init__(self, tables, cfg=None):
        self.tables = tables
        self.cfg = cfg or {}
        self.log = logging.getLogger("fake")

    def table(self, name, where="", params=None):
        return self.tables.get(name, pd.DataFrame())

    def read(self, sql, params=None):
        return pd.DataFrame(columns=inp.SCADA_COLUMNS)


def test_load_inputs_from_t01():
    ctx = FakeCtx({
        "ts.net_case": pd.DataFrame({"case_id": ["X", "PK"], "case_type": ["other", "as_operated_peak"]}),
        "ts.ncc_substation_monthly": pd.DataFrame({"month": [pd.Timestamp("2026-03-01")], "substation_code": ["EXA"],
                                                   "energy_mwh": [1.0]}),
    })
    inputs = inp.load_inputs(ctx)
    assert inputs.case_id == "PK"
    assert not inputs.is_handbuilt
    assert inputs.substation_monthly["month"].iloc[0] == "2026-03"
    assert inputs.scada("2026-03").empty
    assert inp.load_inputs(FakeCtx(ctx.tables, {"cases": {"base_case": "X"}})).case_id == "X"


def test_load_inputs_converts_handbuilt(monkeypatch):
    seen = {}

    def fake_convert(hb, plants=None):
        seen.update(hb)
        return {"net_case": pd.DataFrame({"case_id": ["HANDBUILT"], "case_type": ["other"]}),
                "net_load": pd.DataFrame({"case_id": ["HANDBUILT"], "load_id": ["D-EXA-1"]})}

    monkeypatch.setattr(inp, "handbuilt_net_tables", fake_convert)
    ctx = FakeCtx({"ts.hb_substation": pd.DataFrame({"ss_code": ["EXA"]})})
    inputs = inp.load_inputs(ctx)
    assert inputs.is_handbuilt and inputs.case_id == "HANDBUILT"
    assert "hb_substation" in seen and not inputs.net_tables["net_load"].empty
