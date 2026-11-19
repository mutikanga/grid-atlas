"""Regression tests for the bugs found in review of the F3b profile and snapshot code.

Each test names the problem it guards against.
"""
from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from conftest import MONTH, base_inputs, net_tables
from engine import cases as cs
from engine import inputs as inp
from engine import profiles as pr


# --------------------------------------------------------------------------- in service as Y/N text


def test_in_service_text_n_is_out_of_service():
    """The hand-built converter writes 'Y'/'N'; bool('N') is True, so 'N' used to count as in service."""
    tables = net_tables()
    tables["net_load"] = tables["net_load"].assign(in_service=["Y", "N", "Y", "Y"])
    tables["net_gen"] = tables["net_gen"].assign(in_service=["N", "Y"])
    inputs = base_inputs(net_tables=tables)
    assert set(cs.case_loads(inputs)["load_id"]) == {"D-EXA-1", "D-EXB-1"}
    assert pr.case_gens(inputs).empty  # the solar unit is out, the other is the slack


def test_in_service_blank_counts_as_in_service():
    df = pd.DataFrame({"in_service": [True, False, None, np.nan, "Y", "n"]})
    assert list(pr.in_service_mask(df)) == [True, False, True, True, True, False]


# --------------------------------------------------------------------------- substation of a load


def test_case_loads_use_substation_code_with_numeric_bus_ids():
    """Real T01 bus ids are numbers ('3301'); the substation must come from substation_code."""
    tables = net_tables()
    tables["net_load"] = tables["net_load"].assign(bus=["3301", "3302", "3401", "3301"])
    loads = cs.case_loads(base_inputs(net_tables=tables)).set_index("load_id")
    assert loads["ss_code"].to_dict() == {"D-EXA-1": "EXA", "D-EXA-2": "EXA", "D-EXB-1": "EXB"}


# --------------------------------------------------------------------------- base case and hand-built path


def test_configured_base_case_missing_falls_back():
    cases = pd.DataFrame({"case_id": ["HANDBUILT"], "case_type": ["as_operated_peak"]})
    assert inp.choose_base_case(cases, "PLANNING-PEAK") == "HANDBUILT"
    assert inp.choose_base_case(cases, "HANDBUILT") == "HANDBUILT"


def test_handbuilt_converter_gets_the_plants_register(monkeypatch):
    """Without the register the converter guesses plant codes, which then miss NCC's figures."""
    seen = {}

    def to_net_tables(hb, *, plants=None):
        seen["plants"] = plants
        return {}

    monkeypatch.setattr(inp.importlib, "import_module", lambda name: types.SimpleNamespace(to_net_tables=to_net_tables))
    plants = pd.DataFrame({"plant_code": ["SOL"], "name": ["Example solar"]})
    inp.handbuilt_net_tables({"hb_substation": pd.DataFrame()}, plants)
    assert seen["plants"] is plants

    # A converter without a plants parameter is still called.
    monkeypatch.setattr(inp.importlib, "import_module", lambda name: types.SimpleNamespace(convert=lambda hb: {"ok": hb}))
    assert "ok" in inp.handbuilt_net_tables({}, plants)


def test_real_handbuilt_converter_accepts_plants():
    import inspect

    from loaders import network_handbuilt

    assert "plants" in inspect.signature(network_handbuilt.to_net_tables).parameters


# --------------------------------------------------------------------------- time zones


def test_mixed_utc_offsets_are_converted_to_eat():
    values = pd.Series([datetime(2026, 3, 10, 17, tzinfo=timezone.utc),
                        datetime(2026, 3, 10, 20, tzinfo=timezone(timedelta(hours=3)))], dtype=object)
    out = inp.to_eat_naive(values)
    assert list(out) == [pd.Timestamp("2026-03-10 20:00")] * 2


def test_min_at_is_normalised():
    df = pd.DataFrame({"month": ["2026-03-01"], "min_at": [pd.Timestamp("2026-03-15 00:00", tz="UTC")]})
    assert inp.normalise(df)["min_at"].iloc[0] == pd.Timestamp("2026-03-15 03:00")


# --------------------------------------------------------------------------- minimum snapshot


def with_minima(inputs, sys_min, min_at=None):
    sm = inputs.substation_monthly
    inputs.substation_monthly = sm.assign(min_mw=[20.0, 10.0])
    inputs.system_monthly = pd.DataFrame({"month": [MONTH], "peak_mw": [80.0], "min_mw": [sys_min],
                                          "min_at": [min_at]})
    return inputs


def test_min_scaled_to_system_minimum(inputs):
    snap = cs.min_snapshot(with_minima(inputs, 36.0), MONTH, {})
    p = snap.loads.set_index("load_id")["p_mw"]
    assert p.sum() == pytest.approx(36.0)
    assert p["D-EXB-1"] == pytest.approx(12.0)


def test_min_not_scaled_when_system_perimeter_is_wider(inputs, caplog):
    """A national minimum of 500 MW must not be forced onto two substations that peak at 90 MW."""
    with caplog.at_level("WARNING"):
        snap = cs.min_snapshot(with_minima(inputs, 500.0), MONTH, {})
    p = snap.loads.set_index("load_id")["p_mw"]
    assert p.sum() == pytest.approx(30.0)
    assert "not scaled" in snap.note
    assert any("perimeters differ" in r.message for r in caplog.records)


def test_min_hour_from_system_min_at(inputs):
    snap = cs.min_snapshot(with_minima(inputs, 36.0, pd.Timestamp("2026-03-15 03:00")), MONTH, {})
    assert (snap.day_type, snap.hour) == ("NWD", 3)


# --------------------------------------------------------------------------- generators


def test_partly_measured_plant_gives_only_the_rest_to_other_units():
    """Units without SCADA used to get the whole plant energy on top of the measured unit."""
    tables = net_tables()
    tables["net_gen"] = pd.DataFrame({
        "case_id": ["C1", "C1", "C1"], "gen_id": ["G-HYD-1", "G-HYD-2", "G-SLK-1"],
        "plant_code": ["HYD", "HYD", "SLK"], "technology": ["hydro", "hydro", "hydro"],
        "p_max_mw": [50.0, 50.0, 200.0], "control": ["PV", "PV", "slack"], "in_service": [True] * 3,
    })
    points = pd.DataFrame({"point_id": ["G1.P"], "substation_code": ["EXA"], "element_type": ["generator"],
                           "element_ref": ["G-HYD-1"], "quantity": ["P"], "unit": ["MW"],
                           "sign_convention": ["+ = from the busbar into the bay"]})
    stamps = pd.date_range("2026-03-01", "2026-03-31 23:00", freq="h")
    scada = pd.DataFrame({"timestamp": stamps, "point_id": "G1.P", "value": -30.0, "unit": "MW", "quality": "good"})
    inputs = base_inputs(
        net_tables=tables, scada_points=points, scada_frames={MONTH: scada},
        generation_monthly=pd.DataFrame({"month": [MONTH], "plant_code": ["HYD"], "technology": ["hydro"],
                                         "sent_out_mwh": [40000.0]}),
    )
    gp = pr.gen_profiles(inputs, MONTH).set_index(["gen_id", "day_type", "hour"])["p_mw"]
    assert gp[("G-HYD-1", "WD", 12)] == pytest.approx(30.0)
    assert gp[("G-HYD-2", "WD", 12)] == pytest.approx((40000.0 - 30.0 * 744) / 744)


# --------------------------------------------------------------------------- applying and signs


def test_apply_snapshot_never_writes_nan():
    import pandapower.networks as pn

    net = pn.example_simple()
    net.load["load_id"] = ["D-EXA-1"]
    p0 = float(net.load.at[0, "p_mw"])
    snap = cs.Snapshot("x", "snapshot", MONTH, "WD", 0, 1.0,
                       loads=pd.DataFrame({"load_id": ["D-EXA-1"], "p_mw": [np.nan], "q_mvar": [1.5]}))
    cs.apply_snapshot(net, snap)
    assert net.load.at[0, "p_mw"] == p0
    assert net.load.at[0, "q_mvar"] == 1.5


@pytest.mark.parametrize("text, sign", [
    ("+ = from the busbar into the feeder; - = to the busbar", 1.0),
    ("positive = flow to the busbar, negative = from the busbar", -1.0),
    ("Positive into the bus bar", -1.0),
    ("+ = from the transformer to the busbar", -1.0),
    (None, 1.0),
    ("export positive", 1.0),
])
def test_point_sign_reads_the_first_direction_named(text, sign):
    assert pr.point_sign(text) == sign
