"""Regression tests for bugs found in review: each test names the problem it guards against."""

from __future__ import annotations

import math
import types

import pandas as pd
import pytest

from engine.loadflow import element_results, run_pf
from engine.network import element_register
from engine.network.build import build_net
from engine.stages import network as stage
from loaders import network_handbuilt as hb
from loaders.adapters import load_adapter
from network_helpers import CASE, four_substation_t12, two_bus_tables


def add_bus(tables: dict, bus_id: str, kv: float = 132.0, substation: str = "Example C") -> None:
    """Append one bus row to the T01 tables."""
    tables["net_bus"] = pd.concat([tables["net_bus"], pd.DataFrame([{
        "case_id": CASE, "bus_id": bus_id, "substation": substation, "vn_kv": kv, "in_service": "Y"}])],
        ignore_index=True)


def test_switch_at_a_bus_the_line_does_not_touch_is_skipped_not_fatal():
    # pandapower raises for such a switch; one bad switch row must not stop the whole build.
    tables, subs = two_bus_tables()
    add_bus(tables, "EXC-132-1")
    tables["net_switch"] = pd.DataFrame([
        {"case_id": CASE, "switch_id": "SW-BAD", "bus": "EXC-132-1", "element_type": "line",
         "element_id": "L-EXA-EXB-132-1", "closed": "Y"},
        {"case_id": CASE, "switch_id": "SW-OK", "bus": "EXB-132-1", "element_type": "line",
         "element_id": "L-EXA-EXB-132-1", "closed": "Y"}])
    net = build_net(tables, CASE, subs)
    assert list(net.switch.name) == ["SW-OK"]
    assert any("SW-BAD" in w and "not an end" in w for w in net["atlas_warnings"])


def test_slack_is_never_given_to_an_out_of_service_unit():
    tables, subs = two_bus_tables()
    tables["net_gen"] = pd.DataFrame([
        {"case_id": CASE, "gen_id": "G-BIG-1", "bus": "EXA-132-1", "control": "PV", "p_mw": 0.0,
         "p_max_mw": 900.0, "in_service": "N"},
        {"case_id": CASE, "gen_id": "G-SMALL-1", "bus": "EXA-132-1", "control": "PV", "p_mw": 0.0,
         "p_max_mw": 100.0, "in_service": "Y"}])
    net = build_net(tables, CASE, subs)
    slack = net.gen[net.gen.slack]
    assert list(slack.name) == ["G-SMALL-1"]
    assert run_pf(net).converged


def test_line_without_rating_reports_unknown_loading_not_infinite():
    tables, subs = two_bus_tables(rate_cont=None)
    net = build_net(tables, CASE, subs)
    assert run_pf(net).converged
    loading = element_results(net).loading_pct.iloc[0]
    assert math.isnan(loading)


def test_extra_element_with_an_existing_id_replaces_it():
    # An uprating project re-states a line under its own id: one line, the new rating,
    # and the element register still has unique ids (results.element primary key).
    tables, subs = two_bus_tables()
    upgraded = tables["net_line"].iloc[0].to_dict() | {"rate_cont_mva": 250.0}
    net = build_net(tables, CASE, subs, extra={"net_line": pd.DataFrame([upgraded])})
    assert len(net.line) == 1 and net.line.rate_mva.iloc[0] == 250.0
    assert not element_register(net).element_id.duplicated().any()
    assert any("given more than once" in w for w in net["atlas_warnings"])


def test_duplicate_bus_rows_give_one_bus():
    tables, subs = two_bus_tables()
    tables["net_bus"] = pd.concat([tables["net_bus"], tables["net_bus"].iloc[[1]]], ignore_index=True)
    net = build_net(tables, CASE, subs)
    assert list(net.bus.name) == ["EXA-132-1", "EXB-132-1"]
    assert run_pf(net).converged


def test_trafo3w_with_blank_vk_gets_typical_values_and_solves():
    tables, subs = two_bus_tables()
    add_bus(tables, "EXB-33-1", 33.0, "Example B")
    add_bus(tables, "EXB-11-1", 11.0, "Example B")
    tables["net_trafo3w"] = pd.DataFrame([{
        "case_id": CASE, "trafo_id": "T-EXB-9", "hv_bus": "EXB-132-1", "mv_bus": "EXB-33-1",
        "lv_bus": "EXB-11-1", "sn_hv_mva": 60.0, "sn_mv_mva": 60.0, "sn_lv_mva": 20.0,
        "vn_hv_kv": 132.0, "vn_mv_kv": 33.0, "vn_lv_kv": 11.0, "vk_hv_percent": None,
        "vk_mv_percent": None, "vk_lv_percent": None, "rate_cont_mva": 60.0, "status": "existing"}])
    net = build_net(tables, CASE, subs)
    assert (net.trafo3w[["vk_hv_percent", "vk_mv_percent", "vk_lv_percent"]] > 0).all(axis=None)
    assert any("T-EXB-9" in w and "vk_hv_percent" in w for w in net["atlas_warnings"])
    assert run_pf(net).converged


def test_handbuilt_in_central_comes_from_t12_when_register_lacks_the_substation():
    # ref.substation holds the canonical list; a hand-built substation outside it still
    # keeps the in_central flag the team gave it in hb_substation.
    t01 = hb.to_net_tables(four_substation_t12())
    empty_register = pd.DataFrame(columns=["ss_code", "name", "in_central"])
    net = build_net(t01, "HANDBUILT", empty_register)
    central = dict(zip(net.bus.name, net.bus.in_central))
    assert central["EXA-132-1"] and not central["EXD-220-1"]
    trafo = dict(zip(net.trafo.name, net.trafo.in_central))
    assert trafo["T-EXA-1"] and not trafo["T-EXD-1"]
    load = dict(zip(net.load.name, net.load.in_central))
    assert load["D-EXB-1"] and not load["D-EXD-1"]


def test_register_wins_over_the_bus_row_in_central():
    tables, subs = two_bus_tables()
    tables["net_bus"]["in_central"] = ["Y", "N"]  # register says EXA N, EXB Y
    net = build_net(tables, CASE, subs)
    assert list(net.bus.in_central) == [False, True]


def test_every_unit_of_a_plant_keeps_one_plant_code():
    gens = pd.DataFrame([
        {"plant": "Zetz Hydro", "unit": 1, "substation": "EXB", "connection_kv": 132, "technology": "hydro",
         "p_max_mw": 50, "status": "existing"},
        {"plant": "Zeta Hydro", "unit": 1, "substation": "EXB", "connection_kv": 132, "technology": "hydro",
         "p_max_mw": 50, "status": "existing"},
        {"plant": "Zetz Hydro", "unit": 2, "substation": "EXB", "connection_kv": 132, "technology": "hydro",
         "p_max_mw": 50, "status": "existing"}])
    out = hb.build_gens(gens, None, hb.DEFAULT_HB_CFG)
    codes = out.groupby("plant").plant_code.unique()
    assert list(codes["Zetz Hydro"]) == ["ZETH"]
    assert list(codes["Zeta Hydro"]) == ["ZETH2"]
    assert list(out.gen_id) == ["G-ZETH-1", "G-ZETH2-1", "G-ZETH-2"]


def test_two_names_of_one_registered_plant_share_its_code():
    plants = pd.DataFrame({"plant_code": ["KII"], "name": ["Kiira"]})
    gens = pd.DataFrame([
        {"plant": "Kiira", "unit": 1, "substation": "EXB", "connection_kv": 132, "technology": "hydro",
         "p_max_mw": 50, "status": "existing"},
        {"plant": "KII", "unit": 2, "substation": "EXB", "connection_kv": 132, "technology": "hydro",
         "p_max_mw": 50, "status": "existing"}])
    out = hb.build_gens(gens, plants, hb.DEFAULT_HB_CFG)
    assert list(out.gen_id) == ["G-KII-1", "G-KII-2"]


def test_blank_length_to_a_substation_without_coordinates_is_a_clear_error():
    tables = four_substation_t12()
    tables["hb_line"] = pd.concat([tables["hb_line"], pd.DataFrame([{
        "from_ss": "EXA", "to_ss": "EXZ", "kv": 132, "circuit": 1, "length_km": float("nan"),
        "conductor": "ACSR Bear", "conductors_per_phase": 1.0, "status": "existing",
        "commissioning_year": 2000.0}])], ignore_index=True)
    with pytest.raises(ValueError, match="EXA-EXZ 132 kV.*lat/lon"):
        hb.to_net_tables(tables)


def test_adapter_name_from_a_manifest_cannot_leave_the_adapters_package():
    with pytest.raises(ValueError, match="plain module name"):
        load_adapter("..network_handbuilt")
    with pytest.raises(ValueError, match="plain module name"):
        load_adapter("os.path")


@pytest.mark.parametrize("hour,expected", [(20, 20), (24, None), (None, None), (-1, None)])
def test_case_hour_outside_0_23_is_left_blank(hour, expected):
    # results.case has CHECK (hour BETWEEN 0 AND 23): a bad hour must not fail the stage.
    inputs = types.SimpleNamespace(net_tables={"net_case": pd.DataFrame([{"case_id": CASE, "case_hour": hour}])})
    assert stage.case_hour(inputs, CASE) == expected


class FakeCtx:
    """The parts of RunContext the network stage uses, writing to a dict instead of the DB."""

    def __init__(self, tables, subs, cfg):
        import logging
        self.inputs = types.SimpleNamespace(net_tables=tables, case_id=CASE, substations=subs)
        self.cfg, self.log, self.written = cfg, logging.getLogger("test"), {}
        self._net = build_net(tables, CASE, subs)

    def net(self):
        import copy
        return copy.deepcopy(self._net)

    def write(self, table, df):
        self.written[table] = df.copy()
        return len(df)


def test_stage_ignores_unknown_check_settings_and_writes_unique_rows():
    tables, subs = two_bus_tables()
    cfg = {"network": {"checks": {"xr_min": 1.5, "xr_max": 15, "new_threshold": 3}}}
    ctx = FakeCtx(tables, subs, cfg)
    stage.run(ctx)
    assert set(ctx.written) == {"element", "bus", "case", "element_result", "bus_result"}
    assert ctx.written["case"].method.iloc[0].startswith("ac-")
    assert not ctx.written["element"].duplicated(["element_type", "element_id"]).any()


def test_pypowsybl_buses_of_an_unsolved_case_stay_in_service():
    # A CGMES file without its SV profile has no bus voltages; that must not switch every
    # bus off. A stand-in for the pypowsybl network gives the three frames bus_frame reads.
    from loaders import network_pypowsybl as conv

    class FakeNet:
        def get_voltage_levels(self):
            return pd.DataFrame({"substation_id": ["S1"], "nominal_v": [132.0], "name": ["VL1"],
                                 "low_voltage_limit": [float("nan")], "high_voltage_limit": [145.2]},
                                index=pd.Index(["VL1"], name="id"))

        def get_substations(self):
            return pd.DataFrame({"name": ["Example A"]}, index=pd.Index(["S1"], name="id"))

        def get_bus_breaker_view_buses(self):
            return pd.DataFrame({"name": ["B1"], "v_mag": [float("nan")], "v_angle": [float("nan")],
                                 "voltage_level_id": ["VL1"]}, index=pd.Index(["B1"], name="id"))

    buses, nominal = conv.bus_frame(FakeNet(), "C1")
    assert buses.in_service.tolist() == ["Y"]
    assert buses.substation.iloc[0] == "Example A" and nominal == {"VL1": 132.0}
    assert buses.v_max_pu.iloc[0] == pytest.approx(1.1)
