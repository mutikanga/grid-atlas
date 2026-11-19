"""Test helpers: export a pandapower net to T01-shaped tables, and small example data.

The round-trip tests export pandapower's own example networks to T01 tables, rebuild them
with engine.network.build_net, and check the load flow gives the same answer. That proves
the builder reads every T01 column the way the template describes it.
"""

from __future__ import annotations

import math

import pandas as pd

CASE = "RT"


def bus_label(net, b: int) -> str:
    """A T01 bus id for pandapower bus index b."""
    return f"B{b}"


def export_t01(net, case_id: str = CASE) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return (T01 tables, substations register) for a pandapower net.

    Each bus gets its own substation (code S<n>). Values are written exactly, with
    r_temp_c = 20, so build_net(..., r_temp_c=20) must reproduce the original net.
    """
    f_hz = float(net.f_hz)
    buses = pd.DataFrame([{
        "case_id": case_id, "bus_id": bus_label(net, b), "name": str(r["name"]), "substation": f"Sub {b}",
        "vn_kv": float(r.vn_kv), "zone": None, "in_service": "Y" if r.in_service else "N",
        "v_min_pu": None, "v_max_pu": None} for b, r in net.bus.iterrows()])
    subs = pd.DataFrame({"ss_code": [f"S{b}" for b in net.bus.index],
                         "name": [f"Sub {b}" for b in net.bus.index],
                         "in_central": ["Y" if b % 2 == 0 else "N" for b in net.bus.index]})
    lines = pd.DataFrame([{
        "case_id": case_id, "line_id": f"L{i}", "name": str(r["name"]), "from_bus": bus_label(net, r.from_bus),
        "to_bus": bus_label(net, r.to_bus), "circuit": 1, "length_km": float(r.length_km),
        "r_ohm_per_km": float(r.r_ohm_per_km), "x_ohm_per_km": float(r.x_ohm_per_km),
        "b_us_per_km": float(r.c_nf_per_km) * 2 * math.pi * f_hz * 1e-3, "r_temp_c": 20.0,
        "rate_cont_mva": math.sqrt(3) * float(net.bus.vn_kv[r.from_bus]) * float(r.max_i_ka),
        "status": "existing", "in_service": "Y" if r.in_service else "N"} for i, r in net.line.iterrows()])
    trafos = pd.DataFrame([{
        "case_id": case_id, "trafo_id": f"T{i}", "substation": f"Sub {r.hv_bus}", "hv_bus": bus_label(net, r.hv_bus),
        "lv_bus": bus_label(net, r.lv_bus), "sn_mva": float(r.sn_mva), "vn_hv_kv": float(r.vn_hv_kv),
        "vn_lv_kv": float(r.vn_lv_kv), "vk_percent": float(r.vk_percent), "vkr_percent": float(r.vkr_percent),
        "pfe_kw": float(r.pfe_kw), "i0_percent": float(r.i0_percent), "vector_group": r.vector_group,
        "tap_side": r.tap_side, "tap_neutral": r.tap_neutral, "tap_min": r.tap_min, "tap_max": r.tap_max,
        "tap_step_percent": r.tap_step_percent, "tap_pos": r.tap_pos, "rate_cont_mva": float(r.sn_mva),
        "status": "existing", "in_service": "Y" if r.in_service else "N"} for i, r in net.trafo.iterrows()])
    gens = []
    for i, r in net.ext_grid.iterrows():
        gens.append({"gen_id": f"X{i}", "bus": bus_label(net, r.bus), "control": "slack", "p_mw": 0.0,
                     "vm_pu": float(r.vm_pu), "p_max_mw": 999.0, "q_min_mvar": None, "q_max_mvar": None})
    for i, r in net.gen.iterrows():
        gens.append({"gen_id": f"G{i}", "bus": bus_label(net, r.bus), "control": "PV",
                     "p_mw": float(r.p_mw * r.scaling), "vm_pu": float(r.vm_pu), "p_max_mw": float(r.p_mw),
                     "q_min_mvar": r.min_q_mvar, "q_max_mvar": r.max_q_mvar})
    for i, r in net.sgen.iterrows():
        q = float(r.q_mvar * r.scaling)
        gens.append({"gen_id": f"P{i}", "bus": bus_label(net, r.bus), "control": "PQ",
                     "p_mw": float(r.p_mw * r.scaling), "vm_pu": None, "p_max_mw": float(r.p_mw),
                     "q_min_mvar": q, "q_max_mvar": q})
    gens = pd.DataFrame([{**g, "case_id": case_id, "plant": f"Plant {g['gen_id']}", "technology": "hydro",
                          "in_service": "Y"} for g in gens])
    loads = pd.DataFrame([{
        "case_id": case_id, "load_id": f"D{i}", "bus": bus_label(net, r.bus), "substation": f"Sub {r.bus}",
        "share": None, "p_mw": float(r.p_mw * r.scaling), "q_mvar": float(r.q_mvar * r.scaling),
        "in_service": "Y" if r.in_service else "N"} for i, r in net.load.iterrows()])
    shunts = pd.DataFrame([{
        "case_id": case_id, "shunt_id": f"C{i}", "bus": bus_label(net, r.bus),
        "q_mvar": float(r.q_mvar * r.step) * (float(net.bus.vn_kv[r.bus]) / float(r.vn_kv)) ** 2,
        "steps": 1, "in_service": "Y" if r.in_service else "N"} for i, r in net.shunt.iterrows()])
    names = {"l": ("line", lambda e: f"L{e}"), "t": ("trafo", lambda e: f"T{e}"),
             "b": ("bus", lambda e: bus_label(net, e))}
    switches = pd.DataFrame([{
        "case_id": case_id, "switch_id": f"SW{i}", "bus": bus_label(net, r.bus), "element_type": names[r.et][0],
        "element_id": names[r.et][1](r.element), "closed": "Y" if r.closed else "N"}
        for i, r in net.switch.iterrows()])
    case = pd.DataFrame([{"case_id": case_id, "case_type": "other", "case_date": "2026-09-30",
                          "source_tool": "other", "base_mva": float(net.sn_mva), "frequency_hz": f_hz,
                          "perimeter": "other"}])
    tables = {"net_case": case, "net_bus": buses, "net_line": lines, "net_trafo": trafos, "net_gen": gens,
              "net_load": loads, "net_shunt": shunts, "net_switch": switches}
    return tables, subs


def two_bus_tables(*, load_mw: float = 50.0, rate_cont: float = 100.0, rate_ncc=None, rate_emerg=None,
                   r_ohm_per_km: float = 0.1, r_temp_c=20.0, length_km: float = 20.0,
                   x_ohm_per_km: float = 0.4) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """A 132 kV slack bus feeding one load bus over one line: the smallest useful case."""
    buses = pd.DataFrame([
        {"case_id": CASE, "bus_id": "EXA-132-1", "name": "Example A 132", "substation": "Example A",
         "vn_kv": 132.0, "in_service": "Y"},
        {"case_id": CASE, "bus_id": "EXB-132-1", "name": "Example B 132", "substation": "Example B S/S",
         "vn_kv": 132.0, "in_service": "Y"}])
    lines = pd.DataFrame([{
        "case_id": CASE, "line_id": "L-EXA-EXB-132-1", "from_bus": "EXA-132-1", "to_bus": "EXB-132-1",
        "circuit": 1, "length_km": length_km, "r_ohm_per_km": r_ohm_per_km, "x_ohm_per_km": x_ohm_per_km,
        "b_us_per_km": 2.8, "r_temp_c": r_temp_c, "rate_cont_mva": rate_cont, "rate_emerg_mva": rate_emerg,
        "rate_ncc_mva": rate_ncc, "status": "existing", "in_service": "Y", "commissioning_year": 2003,
        "tower_group": "EXA-EXB-132"}])
    gens = pd.DataFrame([{"case_id": CASE, "gen_id": "G-EXA-1", "bus": "EXA-132-1", "plant": "Example Hydro",
                          "technology": "hydro", "p_mw": 0.0, "p_max_mw": 500.0, "control": "slack",
                          "vm_pu": 1.0, "in_service": "Y"}])
    loads = pd.DataFrame([{"case_id": CASE, "load_id": "D-EXB-1", "bus": "EXB-132-1", "substation": "Example B",
                           "share": 1.0, "p_mw": load_mw, "q_mvar": load_mw * 0.3, "in_service": "Y"}])
    subs = pd.DataFrame({"ss_code": ["EXA", "EXB"], "name": ["Example A", "Example B"], "in_central": ["N", "Y"]})
    return {"net_bus": buses, "net_line": lines, "net_gen": gens, "net_load": loads}, subs


def four_substation_t12() -> dict[str, pd.DataFrame]:
    """A 4-substation T12 example: EXA 220/132/33 with the slack at 220 kV, three 132/33
    substations on a 132 kV ring, one hydro and one solar plant."""
    subs = pd.DataFrame([
        {"ss_code": "EXA", "name": "Example A", "kv_levels": "220/132/33", "lat": 0.40, "lon": 32.50, "in_central": "Y"},
        {"ss_code": "EXB", "name": "Example B", "kv_levels": "132/33", "lat": 0.33, "lon": 32.58, "in_central": "Y"},
        {"ss_code": "EXC", "name": "Example C", "kv_levels": "132/33", "lat": 0.30, "lon": 32.45, "in_central": "Y"},
        {"ss_code": "EXD", "name": "Example D", "kv_levels": "220/132/33", "lat": 0.45, "lon": 33.10, "in_central": "N"},
    ])
    lines = pd.DataFrame([
        {"from_ss": "EXD", "to_ss": "EXA", "kv": 220, "circuit": 1, "length_km": None, "conductor": "ACSR Twin Bear",
         "conductors_per_phase": None, "status": "existing", "commissioning_year": 2008, "tower_group": "EXA-EXD-220"},
        {"from_ss": "EXD", "to_ss": "EXA", "kv": 220, "circuit": 2, "length_km": None, "conductor": "ACSR Bear",
         "conductors_per_phase": 2, "status": "existing", "commissioning_year": 2008, "tower_group": "EXA-EXD-220"},
        {"from_ss": "EXA", "to_ss": "EXB", "kv": 132, "circuit": 1, "length_km": 16.4, "conductor": "ACSR Bear",
         "conductors_per_phase": 1, "status": "existing", "commissioning_year": 2003},
        {"from_ss": "EXB", "to_ss": "EXC", "kv": 132, "circuit": 1, "length_km": None, "conductor": "ACSR Lynx",
         "conductors_per_phase": None, "status": "existing", "commissioning_year": 1995},
        {"from_ss": "EXC", "to_ss": "EXA", "kv": 132, "circuit": 1, "length_km": 14.0, "conductor": "ACSR Wolf",
         "conductors_per_phase": None, "status": "existing", "commissioning_year": 1990},
        {"from_ss": "EXA", "to_ss": "EXC", "kv": 132, "circuit": 2, "length_km": 14.0, "conductor": "ACCC Wolf-size",
         "conductors_per_phase": None, "status": "planned", "commissioning_year": 2029},
    ])
    trafos = pd.DataFrame([
        {"substation": "EXA", "unit": 1, "mva": 250, "hv_kv": 220, "lv_kv": 132, "vk_percent": None, "status": "existing"},
        {"substation": "EXA", "unit": 1, "mva": 60, "hv_kv": 132, "lv_kv": 33, "vk_percent": 12.0, "status": "existing"},
        {"substation": "EXB", "unit": 1, "mva": 60, "hv_kv": 132, "lv_kv": 33, "vk_percent": None, "status": "existing"},
        {"substation": "EXB", "unit": 2, "mva": 60, "hv_kv": 132, "lv_kv": 33, "vk_percent": None, "status": "existing"},
        {"substation": "EXC", "unit": 1, "mva": 40, "hv_kv": 132, "lv_kv": 33, "vk_percent": None, "status": "existing"},
        {"substation": "EXD", "unit": 1, "mva": 125, "hv_kv": 220, "lv_kv": 132, "vk_percent": None, "status": "existing"},
    ])
    gens = pd.DataFrame([
        {"plant": "Example Hydro", "unit": 1, "substation": "EXB", "connection_kv": 132, "technology": "hydro",
         "p_max_mw": 50, "q_min_mvar": -20, "q_max_mvar": 30, "status": "existing"},
        {"plant": "Example Solar", "unit": 1, "substation": "EXC", "connection_kv": 33, "technology": "solar",
         "p_max_mw": 20, "status": "existing"},
    ])
    boundary = pd.DataFrame([{"substation": "EXD", "kv": 220, "kind": "slack", "vm_pu": 1.02, "p_mw": None,
                              "note": "Example: Nile infeed"}])
    return {"hb_substation": subs, "hb_line": lines, "hb_trafo": trafos, "hb_gen": gens, "hb_boundary": boundary}
