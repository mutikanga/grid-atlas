"""Tests for engine/cases.py: weights, energy scaling, peak and minimum hours, applying to a net."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn
import pytest

from conftest import MONTH, base_inputs, scada_hour_value
from engine import cases as cs

LOAD_SS = {"D-EXA-1": "EXA", "D-EXA-2": "EXA", "D-EXB-1": "EXB"}


def weighted_energy(snaps: list[cs.Snapshot]) -> dict[str, float]:
    """Sum of weight_h x load MW per substation over the snapshots."""
    out: dict[str, float] = {}
    for s in snaps:
        for load_id, p in zip(s.loads["load_id"], s.loads["p_mw"]):
            ss = LOAD_SS[load_id]
            out[ss] = out.get(ss, 0.0) + s.weight_h * p
    return out


def test_normalise_shares():
    s = cs.normalise_shares(pd.Series([0.6, np.nan]))
    assert list(s) == pytest.approx([0.6, 0.4])
    assert list(cs.normalise_shares(pd.Series([np.nan, np.nan, np.nan]))) == pytest.approx([1 / 3] * 3)
    assert list(cs.normalise_shares(pd.Series([2.0, 2.0]))) == pytest.approx([0.5, 0.5])


def test_case_loads_use_base_case_and_shares(inputs):
    loads = cs.case_loads(inputs).set_index("load_id")
    assert set(loads.index) == {"D-EXA-1", "D-EXA-2", "D-EXB-1"}
    assert loads.loc["D-EXA-2", "share"] == pytest.approx(0.4)
    assert loads.loc["D-EXB-1", "share"] == pytest.approx(1.0)


def test_weights_sum_to_24_times_days(inputs):
    snaps = cs.month_snapshots(inputs, MONTH, {})
    assert len(snaps) == 48
    assert sum(s.weight_h for s in snaps) == 24 * 31
    wd = [s for s in snaps if s.day_type == "WD"]
    assert {s.weight_h for s in wd} == {21.0}
    assert snaps[0].case_key == f"{MONTH}|WD|0"


@pytest.mark.parametrize("fixture", ["inputs", "scada_inputs"])
def test_weighted_energy_equals_ncc(fixture, request):
    inputs = request.getfixturevalue(fixture)
    energy = weighted_energy(cs.month_snapshots(inputs, MONTH, {}))
    assert energy["EXA"] == pytest.approx(30000.0)
    assert energy["EXB"] == pytest.approx(15000.0)


def test_snapshot_records_sources(scada_inputs):
    snaps = cs.month_snapshots(scada_inputs, MONTH, {})
    assert snaps[0].profile_source == "standard"  # worst of scada (EXA) and standard (EXB)
    assert "scada 1" in snaps[0].note and "standard 1" in snaps[0].note


def test_scale_factor_warning(scada_inputs, caplog):
    # SCADA gives EXA about 28,000 MWh; doubling the NCC figure puts k near 2.
    sm = scada_inputs.substation_monthly
    scada_inputs.substation_monthly = sm.assign(energy_mwh=sm["energy_mwh"].where(sm["substation_code"] != "EXA", 60000.0))
    with caplog.at_level("WARNING"):
        snaps = cs.month_snapshots(scada_inputs, MONTH, {})
    assert "scale outside band: EXA" in snaps[0].note
    assert any("EXA" in r.message for r in caplog.records)


def test_gens_in_snapshots(inputs):
    snaps = {s.case_key: s for s in cs.month_snapshots(inputs, MONTH, {})}
    noon, night = snaps[f"{MONTH}|WD|12"], snaps[f"{MONTH}|WD|2"]
    assert list(noon.gens["gen_id"]) == ["G-SOL-1"]
    assert noon.total_gen_mw > 0 and night.total_gen_mw == 0


def test_peak_from_ncc_uses_coincident_and_factor(inputs):
    inputs.system_monthly = pd.DataFrame({"month": [MONTH], "peak_mw": [80.0],
                                          "peak_at": [pd.Timestamp("2026-03-10 20:00")]})
    snap = cs.peak_snapshot(inputs, MONTH, {})
    assert snap.case_key == f"{MONTH}|peak" and snap.kind == "peak"
    assert (snap.day_type, snap.hour) == ("WD", 20)
    p = snap.loads.set_index("load_id")["p_mw"]
    assert p["D-EXB-1"] == pytest.approx(25.0)                   # coincident_mw
    assert p["D-EXA-1"] + p["D-EXA-2"] == pytest.approx(60.0 * 80.0 / 90.0)  # peak x factor
    q = snap.loads.set_index("load_id")["q_mvar"]
    assert q["D-EXB-1"] == pytest.approx(25.0 * 9.0 / 30.0)


def test_peak_without_system_figure_picks_profile_peak_hour(inputs):
    snaps = cs.month_snapshots(inputs, MONTH, {})
    best = max(snaps, key=lambda s: s.total_load_mw)
    snap = cs.peak_snapshot(inputs, MONTH, {})
    assert (snap.day_type, snap.hour) == (best.day_type, best.hour)


def test_min_without_scada_picks_lowest_profile_hour(inputs):
    snaps = cs.month_snapshots(inputs, MONTH, {})
    low = min(snaps, key=lambda s: s.total_load_mw)
    snap = cs.min_snapshot(inputs, MONTH, {})
    assert snap.case_key == f"{MONTH}|min"
    assert (snap.day_type, snap.hour) == (low.day_type, low.hour)
    assert snap.total_load_mw == pytest.approx(low.total_load_mw)


def test_peak_and_min_from_scada(scada_inputs):
    peak = cs.peak_snapshot(scada_inputs, MONTH, {})
    assert peak.profile_source == "scada"
    assert (peak.day_type, peak.hour) == ("WD", 23)  # 20 + 23 + 10 MW on 10 March
    p = peak.loads.set_index("load_id")["p_mw"]
    assert p["D-EXA-1"] + p["D-EXA-2"] == pytest.approx(scada_hour_value("2026-03-10", 23))
    low = cs.min_snapshot(scada_inputs, MONTH, {})
    assert (low.day_type, low.hour) == ("NWD", 0)    # 20 MW at midnight on Sunday 15 March


def test_hour_snapshot(scada_inputs):
    snap = cs.hour_snapshot(scada_inputs, datetime(2026, 3, 15, 8, 0), {})
    assert snap is not None and snap.kind == "hour"
    assert snap.case_key == "2026-03|2026-03-15 08:00"
    p = snap.loads.set_index("load_id")["p_mw"]
    assert p["D-EXA-1"] == pytest.approx(0.6 * scada_hour_value("2026-03-15", 8))
    assert "D-EXB-1" in p.index  # not measured: filled from its profile
    assert cs.hour_snapshot(scada_inputs, datetime(2026, 3, 16, 8, 0), {}) is None
    assert cs.hour_snapshot(base_inputs(), datetime(2026, 3, 15, 8, 0), {}) is None


def make_net():
    """pandapower's example_simple with identity columns like build_net adds, and a second load."""
    net = pn.example_simple()
    pp.create_load(net, bus=net.load.bus.iloc[0], p_mw=1.0, q_mvar=0.5, name="second")
    net.load["load_id"] = ["D-EXA-1", "D-EXB-1"]
    net.load["ss_code"] = ["EXA", "EXB"]
    net.gen["gen_id"] = ["G-SLK-1"] * len(net.gen)
    net.sgen["gen_id"] = ["G-SOL-1"] * len(net.sgen)
    return net


def test_apply_snapshot_sets_named_loads_only():
    net = make_net()
    before_exb = net.load.loc[1, ["p_mw", "q_mvar"]].tolist()
    snap = cs.Snapshot(
        case_key="x", kind="snapshot", month=MONTH, day_type="WD", hour=1, weight_h=1.0,
        loads=pd.DataFrame({"load_id": ["D-EXA-1", "D-ZZZ-9"], "p_mw": [7.0, 3.0], "q_mvar": [2.0, 1.0]}),
        gens=pd.DataFrame({"gen_id": ["G-SOL-1"], "p_mw": [4.5]}),
    )
    n = cs.apply_snapshot(net, snap)
    assert n == 2
    assert net.load.loc[0, ["p_mw", "q_mvar"]].tolist() == [7.0, 2.0]
    assert net.load.loc[1, ["p_mw", "q_mvar"]].tolist() == before_exb
    assert (net.sgen["p_mw"] == 4.5).all()
    pp.runpp(net)
    assert net.converged


def test_apply_month_snapshot_end_to_end(inputs):
    net = make_net()
    snap = cs.month_snapshots(inputs, MONTH, {})[20]
    cs.apply_snapshot(net, snap)
    expected = snap.loads.set_index("load_id").loc["D-EXB-1", "p_mw"]
    assert net.load.loc[1, "p_mw"] == pytest.approx(expected)


def test_scale_loads():
    net = make_net()
    p0 = net.load["p_mw"].copy()
    cs.scale_loads(net, 2.0, ss_codes=["EXB"])
    assert net.load.loc[0, "p_mw"] == p0[0]
    assert net.load.loc[1, "p_mw"] == pytest.approx(2 * p0[1])
    cs.scale_loads(net, 0.5)
    assert net.load.loc[1, "p_mw"] == pytest.approx(p0[1])
