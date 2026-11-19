"""The truth model itself: it converges at the peak and carries the planted N-1 features.

These tests build the network and series directly (no files), a few load flows each.
"""
from __future__ import annotations

import re

import numpy as np
import pytest

from engine.synthetic.network import CENTRAL, build_network, build_truth_net
from engine.synthetic.timeseries import make_series
from engine.synthetic.truth import n1_loading, simulate, snapshot_net


@pytest.fixture(scope="module")
def base():
    nw = build_network("base")
    return nw, make_series(nw, 42)


def sep_peak(ts) -> int:
    """Hour position of the September 2026 Central peak."""
    cols = [ts.load_ids.index(f"D-{c}-1") for c in CENTRAL]
    sel = np.where(ts.cal.month == "2026-09")[0]
    return int(sel[ts.load_p[sel][:, cols].sum(axis=1).argmax()])


def test_ids_follow_the_contract(base):
    nw, _ = base
    assert all(re.fullmatch(r"[A-Z]{3}-\d+-\d", b) for b in nw.buses["bus_id"])
    assert all(re.fullmatch(r"L-[A-Z]{3}-[A-Z]{3}-\d+-\d", x) for x in nw.lines["line_id"])
    assert all(re.fullmatch(r"T-[A-Z]{3}-\d", x) for x in nw.trafos["trafo_id"])
    assert all(re.fullmatch(r"G-[A-Z]{4}-\d", x) for x in nw.gens["gen_id"])
    assert len(nw.substations) == 15
    assert (nw.lines.status == "existing").sum() >= 19 and (nw.trafos.status == "existing").sum() >= 22


def test_series_are_deterministic(base):
    nw, ts = base
    again = make_series(nw, 42)
    assert np.array_equal(ts.load_p, again.load_p) and np.array_equal(ts.gen_p, again.gen_p)
    other = make_series(nw, 7)
    assert not np.array_equal(ts.load_p, other.load_p)
    assert len(ts.cal.hours) == 395 * 24


def test_peak_is_about_600_mw(base):
    nw, ts = base
    cols = [ts.load_ids.index(f"D-{c}-1") for c in CENTRAL]
    peak = ts.load_p[:, cols].sum(axis=1).max()
    assert 560 < peak < 660


def test_truth_converges_at_peak_with_sane_voltages(base):
    nw, ts = base
    tn = snapshot_net(nw, ts, sep_peak(ts))
    assert tn.net.converged
    vm = tn.net.res_bus["vm_pu"]
    assert vm.min() > 0.93 and vm.max() < 1.08


def test_kaw_mut_n1_overload(base):
    nw, ts = base
    tn = snapshot_net(nw, ts, sep_peak(ts))
    ok, lines, _, _ = n1_loading(tn, ("line", "L-KAW-MUT-132-1"))
    assert ok and lines["L-KAW-MUT-132-2"] > 100


def test_kawanda_transformer_n1_overload_and_binds_first(base):
    nw, ts = base
    tn = snapshot_net(nw, ts, sep_peak(ts))
    ok, _, trafos, _ = n1_loading(tn, ("trafo", "T-KAW-1"))
    _, lines, _, _ = n1_loading(tn, ("line", "L-KAW-MUT-132-1"))
    assert ok and trafos["T-KAW-2"] > 100
    assert trafos["T-KAW-2"] > lines["L-KAW-MUT-132-2"] + 5, "base variant is transformer-bound"


def test_line_bound_variant_reverses_the_order():
    nw = build_network("line_bound")
    ts = make_series(nw, 42)
    tn = snapshot_net(nw, ts, sep_peak(ts))
    _, _, trafos, _ = n1_loading(tn, ("trafo", "T-KAW-1"))
    _, lines, _, _ = n1_loading(tn, ("line", "L-KAW-MUT-132-1"))
    assert lines["L-KAW-MUT-132-2"] > 100
    assert lines["L-KAW-MUT-132-2"] > trafos["T-KAW-2"] + 10


def test_kap_trip_islands_kapeeka(base):
    nw, ts = base
    t = sep_peak(ts)
    tn = snapshot_net(nw, ts, t)
    ok, _, _, islanded = n1_loading(tn, ("line", "L-KAP-KAW-132-1"))
    assert islanded == pytest.approx(ts.load_p[t, ts.load_ids.index("D-KAP-1")], rel=1e-6)


def test_every_central_contingency_converges(base):
    """No Central line or transformer trip leaves the truth model unsolvable at the peak."""
    nw, ts = base
    tn = snapshot_net(nw, ts, sep_peak(ts))
    for kind, names in (("line", tn.net.line["name"]), ("trafo", tn.net.trafo["name"])):
        for eid in names:
            ok, *_ = n1_loading(tn, (kind, eid))
            assert ok, eid


def test_boundary_balance_equals_central_losses(base):
    """Imports at the Central ends of the ties + Central plants - Central loads = Central element losses."""
    nw, ts = base
    hours = np.arange(sep_peak(ts) - 3, sep_peak(ts) + 1)
    res = simulate(nw, ts, hours=hours)
    tn = res.tn
    net_import = np.zeros(len(hours))
    for r in nw.tie_lines().itertuples():
        k = res.line_names.index(r.line_id)
        p_end = res.line_p_from[:, k] if r.a_central else res.line_p_to[:, k]
        net_import += -p_end
    plants = [ts.gen_ids.index(g) for g in nw.gens.loc[nw.gens.ss_code.isin(CENTRAL), "gen_id"]]
    loads = [ts.load_ids.index(f"D-{c}-1") for c in CENTRAL]
    balance = net_import + ts.gen_p[hours][:, plants].sum(axis=1) - ts.load_p[hours][:, loads].sum(axis=1)
    assert np.allclose(balance, res.central_loss, atol=1e-3)


def test_planned_elements_only_in_the_2030_model(base):
    nw, _ = base
    now = build_truth_net(nw)
    later = build_truth_net(nw, include_planned=True)
    assert "T-KAW-3" not in now.trafo and "T-KAW-3" in later.trafo
    assert "L-KAW-KNO-132-2" not in now.line and "L-KAW-KNO-132-2" in later.line
