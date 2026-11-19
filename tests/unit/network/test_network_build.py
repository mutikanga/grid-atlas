"""Builder tests: round trips through T01 tables, R temperature, ratings, filters, registers."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn
import pytest

from engine.loadflow import element_results, run_pf
from engine.network import build_from_inputs, bus_register, check_net, element_register
from engine.network.build import build_net, pick_rating, resistance_at, shift_from_vector_group
from network_helpers import CASE, export_t01, two_bus_tables


def solve_original(net) -> None:
    """Solve the original pandapower example the same way run_pf does."""
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=False)


def compare(original, rebuilt) -> None:
    """Bus voltages within 1e-6 pu, angles (relative to the first bus) within 1e-6 degrees,
    and line flows within 1e-6 MW."""
    vm_o = original.res_bus.vm_pu.to_numpy()
    vm_r = rebuilt.res_bus.vm_pu.to_numpy()
    assert np.allclose(vm_o, vm_r, atol=1e-6, equal_nan=True)
    va_o = original.res_bus.va_degree.to_numpy() - original.res_bus.va_degree.iloc[0]
    va_r = rebuilt.res_bus.va_degree.to_numpy() - rebuilt.res_bus.va_degree.iloc[0]
    assert np.allclose(va_o, va_r, atol=1e-6, equal_nan=True)
    assert np.allclose(original.res_line.p_from_mw.to_numpy(), rebuilt.res_line.p_from_mw.to_numpy(),
                       atol=1e-6, equal_nan=True)


@pytest.mark.parametrize("factory", [pn.case9, pn.example_simple])
def test_round_trip_matches_original(factory):
    original = factory()
    tables, subs = export_t01(original)
    rebuilt = build_net(tables, CASE, subs, r_temp_c=20.0)
    assert len(rebuilt.bus) == len(original.bus)
    solve_original(original)
    result = run_pf(rebuilt)
    assert result.converged and result.method.startswith("ac-")
    compare(original, rebuilt)


def test_round_trip_example_simple_keeps_switches_and_shift():
    original = pn.example_simple()
    tables, subs = export_t01(original)
    rebuilt = build_net(tables, CASE, subs, r_temp_c=20.0)
    assert len(rebuilt.switch) == len(original.switch)
    assert (~rebuilt.switch.closed).sum() == 1
    assert rebuilt.trafo.shift_degree.iloc[0] == 150.0
    assert rebuilt.sgen.q_mvar.iloc[0] == pytest.approx(-0.5)


def test_identity_columns_and_in_central():
    tables, subs = two_bus_tables()
    net = build_net(tables, CASE, subs)
    assert list(net.bus.name) == ["EXA-132-1", "EXB-132-1"]
    # EXB's substation is named "Example B S/S": matched by normalised name.
    assert list(net.bus.ss_code) == ["EXA", "EXB"]
    assert list(net.bus.in_central) == [False, True]
    line = net.line.iloc[0]
    assert line["name"] == "L-EXA-EXB-132-1"
    assert (line.ss_from, line.ss_to, line.in_central) == ("EXA", "EXB", True)
    assert line.tower_group == "EXA-EXB-132"
    assert net.ext_grid.gen_id.iloc[0] == "G-EXA-1"
    assert net.load.load_id.iloc[0] == "D-EXB-1" and net.load.ss_code.iloc[0] == "EXB"


def test_substation_code_column_wins_over_name():
    tables, subs = two_bus_tables()
    tables["net_bus"]["substation_code"] = ["EXB", "EXA"]
    net = build_net(tables, CASE, subs)
    assert list(net.bus.ss_code) == ["EXB", "EXA"]


def test_line_in_central_both_ends():
    tables, subs = two_bus_tables()
    net = build_net(tables, CASE, subs, line_in_central="both")
    assert not net.line.in_central.iloc[0]


def test_resistance_temperature_correction():
    assert resistance_at(0.1, 20.0, 50.0) == pytest.approx(0.1 * (1 + 0.00403 * 30))
    tables, subs = two_bus_tables(r_ohm_per_km=0.1, r_temp_c=None)
    net = build_net(tables, CASE, subs, r_temp_c=50.0)
    assert net.line.r_ohm_per_km.iloc[0] == pytest.approx(0.1 * 1.1209)
    tables, subs = two_bus_tables(r_ohm_per_km=0.12, r_temp_c=75.0)
    net = build_net(tables, CASE, subs, r_temp_c=50.0)
    assert net.line.r_ohm_per_km.iloc[0] == pytest.approx(0.12 * (1 - 0.00403 * 25))


def test_rating_set_changes_loading():
    tables, subs = two_bus_tables(load_mw=60.0, rate_cont=100.0, rate_ncc=50.0, rate_emerg=120.0)
    loading = {}
    for rating_set in ("cont", "ncc", "emerg", "min"):
        net = build_net(tables, CASE, subs, rating_set=rating_set)
        assert run_pf(net).converged
        loading[rating_set] = element_results(net).set_index("element_id").loc["L-EXA-EXB-132-1", "loading_pct"]
        assert net.line.max_i_ka.iloc[0] == pytest.approx(net.line.rate_mva.iloc[0] / (math.sqrt(3) * 132))
    assert loading["ncc"] == pytest.approx(2 * loading["cont"], rel=1e-9)
    assert loading["emerg"] == pytest.approx(loading["cont"] * 100 / 120, rel=1e-9)
    assert loading["min"] == pytest.approx(loading["ncc"], rel=1e-9)


def test_pick_rating_falls_back_to_continuous():
    assert pick_rating({"rate_cont_mva": 100, "rate_ncc_mva": None}, "ncc") == (100.0, "cont")
    assert pick_rating({"rate_cont_mva": None}, "cont")[1] == "missing"
    with pytest.raises(ValueError):
        pick_rating({"rate_cont_mva": 1}, "summer")


def test_trafo_loading_is_against_rate_mva_and_vkr_from_load_loss():
    tables, subs = two_bus_tables()
    tables["net_bus"] = pd.concat([tables["net_bus"], pd.DataFrame([{
        "case_id": CASE, "bus_id": "EXB-33-1", "name": "Example B 33", "substation": "Example B",
        "vn_kv": 33.0, "in_service": "Y"}])], ignore_index=True)
    tables["net_trafo"] = pd.DataFrame([{
        "case_id": CASE, "trafo_id": "T-EXB-1", "substation": "Example B", "hv_bus": "EXB-132-1",
        "lv_bus": "EXB-33-1", "sn_mva": 60.0, "vn_hv_kv": 132.0, "vn_lv_kv": 33.0, "vk_percent": 12.0,
        "vkr_percent": None, "load_loss_kw": 240.0, "pfe_kw": 30.0, "i0_percent": 0.05,
        "vector_group": "YNd11", "rate_cont_mva": 60.0, "rate_ncc_mva": 30.0, "status": "existing",
        "in_service": "Y"}])
    tables["net_load"].loc[0, "bus"] = "EXB-33-1"
    net = build_net(tables, CASE, subs, rating_set="ncc")
    assert net.trafo.vkr_percent.iloc[0] == pytest.approx(0.4)
    assert net.trafo.shift_degree.iloc[0] == 330.0
    assert run_pf(net).converged
    er = element_results(net).set_index("element_id")
    assert er.loc["T-EXB-1", "loading_pct"] == pytest.approx(2 * net.res_trafo.loading_percent.iloc[0])


def test_status_and_as_of_filter():
    tables, subs = two_bus_tables()
    extra_line = tables["net_line"].iloc[0].to_dict() | {
        "line_id": "L-EXA-EXB-132-2", "status": "planned", "commissioning_year": 2028}
    tables["net_line"] = pd.concat([tables["net_line"], pd.DataFrame([extra_line])], ignore_index=True)
    assert len(build_net(tables, CASE, subs).line) == 1
    planned = ("existing", "committed", "planned")
    assert len(build_net(tables, CASE, subs, statuses=planned, as_of=date(2027, 1, 1)).line) == 1
    assert len(build_net(tables, CASE, subs, statuses=planned, as_of=date(2030, 12, 31)).line) == 2


def test_extra_elements_are_added():
    tables, subs = two_bus_tables()
    extra_line = tables["net_line"].iloc[0].to_dict() | {"line_id": "L-EXA-EXB-132-2", "status": "planned"}
    extra = {"net_line": pd.DataFrame([extra_line]).drop(columns=["case_id"])}
    net = build_net(tables, CASE, subs, statuses=("existing", "planned"), extra=extra)
    assert sorted(net.line.name) == ["L-EXA-EXB-132-1", "L-EXA-EXB-132-2"]


def test_boundary_rows_and_missing_slack():
    tables, subs = two_bus_tables()
    tables["net_gen"].loc[0, "control"] = "PV"
    tables["net_boundary"] = pd.DataFrame([{"case_id": CASE, "bus": "EXB-132-1", "kind": "fixed_p",
                                            "p_mw": 10.0, "note": "Example tie"}])
    net = build_net(tables, CASE, subs)
    # The only PV unit was promoted to slack, and the build says so.
    assert net.gen.slack.iloc[0]
    assert any("made the slack" in w for w in net["atlas_warnings"])
    assert net.sgen.gen_id.iloc[0] == "B-EXB-132-1" and bool(net.sgen.is_equivalent.iloc[0])
    assert run_pf(net).converged


def test_registers_have_contract_columns():
    tables, subs = two_bus_tables()
    net = build_net(tables, CASE, subs)
    reg = element_register(net)
    assert list(reg.columns) == ["element_type", "element_id", "name", "ss_from", "ss_to", "kv", "length_km",
                                 "in_central", "is_equivalent", "rate_mva", "rate_basis", "commissioning_year",
                                 "tower_group", "status"]
    line = reg.set_index("element_id").loc["L-EXA-EXB-132-1"]
    assert line.rate_mva == 100.0 and line.kv == 132.0 and line.commissioning_year == 2003
    assert set(reg.element_type) == {"line", "gen", "load"}
    buses = bus_register(net)
    assert list(buses.columns) == ["bus_id", "ss_code", "vn_kv", "in_central"]


def test_check_net_finds_planted_problems():
    tables, subs = two_bus_tables(x_ohm_per_km=0.0)
    tables["net_bus"] = pd.concat([tables["net_bus"], pd.DataFrame([{
        "case_id": CASE, "bus_id": "EXC-33-1", "name": "lonely", "substation": "Nowhere", "vn_kv": 33.0,
        "in_service": "Y"}])], ignore_index=True)
    tables["net_line"] = pd.concat([tables["net_line"], pd.DataFrame([{
        "case_id": CASE, "line_id": "L-BAD", "from_bus": "EXB-132-1", "to_bus": "EXC-33-1", "circuit": 1,
        "length_km": 5.0, "r_ohm_per_km": 0.1, "x_ohm_per_km": 3.0, "rate_cont_mva": None,
        "status": "existing", "in_service": "N"}])], ignore_index=True)
    issues = check_net(build_net(tables, CASE, subs))
    text = " | ".join(issues.message)
    assert "reactance 0.0 ohm/km is not positive" in text
    assert "different voltages" in text
    assert "no rating" in text
    assert "X/R 26.76 outside 1.5-15.0" in text  # 3.0 / (0.1 corrected to 50 C)
    assert "not in the register" in text  # 'Nowhere' substation
    assert "island" in text


def test_build_from_inputs_uses_scenario():
    tables, subs = two_bus_tables()
    extra_line = tables["net_line"].iloc[0].to_dict() | {
        "line_id": "L-EXA-EXB-132-2", "status": "planned", "commissioning_year": 2029}
    tables["net_line"] = pd.concat([tables["net_line"], pd.DataFrame([extra_line])], ignore_index=True)

    class Inputs:
        net_tables, case_id, substations = tables, CASE, subs

    cfg = {"network": {"r_temp_c": 50.0, "scenarios": {
        "2030": {"as_of": "2030-12-31", "statuses": ["existing", "committed", "planned"]}}}}
    assert len(build_from_inputs(Inputs, cfg).line) == 1
    assert len(build_from_inputs(Inputs, cfg, scenario="2030").line) == 2


def test_vector_group_shift():
    assert shift_from_vector_group("YNd5") == 150.0
    assert shift_from_vector_group("Dyn11") == 330.0
    assert shift_from_vector_group(None) == 0.0
