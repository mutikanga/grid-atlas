"""Load-flow tests: the retry ladder, DC fallback, islanding and result tables."""

from __future__ import annotations

import pandas as pd
import pandapower as pp
import pytest

import engine.loadflow as lf
from engine.loadflow import bus_results, element_results, islanded_load_mw, run_pf
from engine.network.build import build_net
from network_helpers import CASE, two_bus_tables


def radial_three_bus():
    """EXA (slack) - EXB - EXC in a line, 10 MW at EXB and 20 MW at EXC."""
    tables, subs = two_bus_tables(load_mw=10.0)
    tables["net_bus"] = pd.concat([tables["net_bus"], pd.DataFrame([{
        "case_id": CASE, "bus_id": "EXC-132-1", "name": "Example C", "substation": "Example C",
        "vn_kv": 132.0, "in_service": "Y"}])], ignore_index=True)
    line2 = tables["net_line"].iloc[0].to_dict() | {"line_id": "L-EXB-EXC-132-1", "from_bus": "EXB-132-1",
                                                    "to_bus": "EXC-132-1"}
    tables["net_line"] = pd.concat([tables["net_line"], pd.DataFrame([line2])], ignore_index=True)
    tables["net_load"] = pd.concat([tables["net_load"], pd.DataFrame([{
        "case_id": CASE, "load_id": "D-EXC-1", "bus": "EXC-132-1", "substation": "Example C",
        "p_mw": 20.0, "q_mvar": 5.0, "in_service": "Y"}])], ignore_index=True)
    subs = pd.concat([subs, pd.DataFrame([{"ss_code": "EXC", "name": "Example C", "in_central": "Y"}])])
    return build_net(tables, CASE, subs)


def test_converges_and_second_run_starts_from_results():
    net = radial_three_bus()
    first = run_pf(net)
    assert first.converged and first.method == "ac-dc"  # no results yet, so 'results' is skipped
    second = run_pf(net)
    assert second.converged and second.method == "ac-results"


def test_ill_conditioned_net_falls_back_to_dc_without_raising():
    # 2000 MW over 300 km of 132 kV line is far beyond the transfer limit: no AC solution.
    tables, subs = two_bus_tables(load_mw=2000.0, length_km=300.0)
    net = build_net(tables, CASE, subs)
    result = run_pf(net)
    assert not result.converged
    assert result.method == "dc" and result.has_results
    assert "init=dc" in result.message and "init=flat" in result.message
    er = element_results(net)
    assert er.loc[0, "p_from_mw"] == pytest.approx(2000.0, rel=1e-6)


def test_ladder_order_with_mocked_solver(monkeypatch):
    calls = []

    def fake_runpp(net, init, max_iteration, **kwargs):
        calls.append((init, max_iteration))
        if init != "flat":
            raise pp.LoadflowNotConverged("mock")
        net["converged"] = True

    monkeypatch.setattr(lf.pp, "runpp", fake_runpp)
    monkeypatch.setattr(lf, "has_previous_results", lambda net: True)
    result = run_pf(radial_three_bus(), max_iteration=30)
    assert calls == [("results", 30), ("dc", 30), ("flat", 60)]
    assert result.converged and result.method == "ac-flat"


def test_dc_failure_reports_none(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("mock failure")

    monkeypatch.setattr(lf.pp, "runpp", boom)
    monkeypatch.setattr(lf.pp, "rundcpp", boom)
    result = run_pf(radial_three_bus())
    assert result.method == "none" and not result.has_results and not result.converged


def test_islanded_load_with_open_line():
    net = radial_three_bus()
    assert islanded_load_mw(net) == 0.0
    net.line.loc[net.line.name == "L-EXB-EXC-132-1", "in_service"] = False
    assert islanded_load_mw(net) == pytest.approx(20.0)
    result = run_pf(net)
    assert result.converged
    br = bus_results(net).set_index("bus_id")
    assert pd.isna(br.loc["EXC-132-1", "vm_pu"])


def test_islanded_load_with_open_switch():
    net = radial_three_bus()
    line = net.line.index[net.line.name == "L-EXA-EXB-132-1"][0]
    pp.create_switch(net, bus=net.line.at[line, "from_bus"], element=line, et="l", closed=False)
    assert islanded_load_mw(net) == pytest.approx(30.0)


def test_result_tables_shape():
    net = radial_three_bus()
    run_pf(net)
    er = element_results(net)
    assert list(er.columns) == ["element_type", "element_id", "p_from_mw", "q_from_mvar", "p_to_mw",
                                "q_to_mvar", "pl_mw", "ql_mvar", "i_ka", "loading_pct"]
    assert set(er.element_id) == {"L-EXA-EXB-132-1", "L-EXB-EXC-132-1"}
    assert (er.pl_mw > 0).all()
    br = bus_results(net)
    assert list(br.columns) == ["bus_id", "vm_pu", "va_deg", "p_mw", "q_mvar"]
    load, gen = lf.totals(net)
    assert load == pytest.approx(30.0) and gen == pytest.approx(30.0 + er.pl_mw.sum(), rel=1e-6)
