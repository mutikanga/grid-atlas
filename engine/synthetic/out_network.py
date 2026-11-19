"""T01 (network model), T12 (hand-built schedules) and T02 (GIS) from the synthetic network.

T01 holds two cases:
- SYNTH-PEAK, as_operated_peak: the September 2026 Central peak hour, solved with the truth model;
- SYNTH-2030, planning_2030: September 2026 peak loads grown at 7 % a year to 2030, plus
  committed loads, with the planned Kawanda third transformer and second KAW-KNO circuit.
Planned elements appear in SYNTH-PEAK too, with status 'planned', so the engine's
status filter (not the case) decides whether they are built.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pandapower as pp

from engine.synthetic.network import MBR_LOAD_ID, TRUTH_R_TEMP_C, Network, build_truth_net
from engine.synthetic.timeseries import rng_for
from engine.synthetic.world import World, ss_name

PEAK_CASE = "SYNTH-PEAK"
PLAN_CASE = "SYNTH-2030"
GROWTH_TO_2030 = 1.07 ** 4
# Loads committed before 2030 that the 2030 case includes (also in T08 committed_loads).
COMMITTED_2030 = {"KAW": 20.0, "NMV": 15.0, "KAP": 10.0}
PLANNED_PROJECT = {"L-KAW-KNO-132-2": "SP-02", "L-KAP-KAW-132-2": "SP-03"}
RATING_NOTE = ("SYNTHETIC: rate_cont is a typical ACSR rating at 30 C ambient and 75 C conductor; "
               "rate_emerg = 1.1 x cont for lines and 1.2 x for transformers.")


def bus_name(bus: str) -> str:
    """Display name of a bus, for example 'Kawanda 132 kV bus 1'."""
    ss, kv, n = bus.split("-")
    return f"{ss_name(ss)} {kv} kV bus {n}"


def line_title(r) -> str:
    return f"{ss_name(r.ss_a)} - {ss_name(r.ss_b)} {r.kv} kV circuit {r.circuit}"


# --------------------------------------------------------------------------- snapshots
def solve_peak(w: World, t: int) -> pp.pandapowerNet:
    """The truth net solved at hour position t (planned elements left out)."""
    from engine.synthetic.truth import snapshot_net

    return snapshot_net(w.nw, w.ts, t).net


def solve_2030(w: World, t: int) -> tuple[pp.pandapowerNet, dict[str, float], dict[str, float]]:
    """The 2030 planning case: grown loads, committed loads and planned elements in service.

    Returns the solved net, load P by id and generator P by id.
    """
    tn = build_truth_net(w.nw, r_temp_c=TRUTH_R_TEMP_C, include_planned=True)
    net = tn.net
    load_p, gen_p = {}, {}
    for lid, row in tn.load.items():
        k = w.load_col[lid]
        ss = lid.split("-")[1]
        grow = GROWTH_TO_2030 if lid != MBR_LOAD_ID else 1.07 ** 2
        p = w.ts.load_p[t, k] * grow + COMMITTED_2030.get(ss, 0.0)
        q = p * (w.ts.load_q[t, k] / w.ts.load_p[t, k])
        net.load.at[row, "p_mw"], net.load.at[row, "q_mvar"] = p, q
        load_p[lid] = p
    dispatch = {"G-NALH-1": 190.0, "G-KARH-1": 420.0, "G-NMVT-1": 45.0,
                "G-KBSS-1": 0.0, "G-NKGS-1": 0.0, "G-KAPS-1": 0.0}
    for gid, p in dispatch.items():
        if gid in tn.gen:
            net.gen.at[tn.gen[gid], "p_mw"] = p
        else:
            net.sgen.at[tn.sgen[gid], "p_mw"] = p
        gen_p[gid] = p
    pp.runpp(net, numba=False)
    gen_p["G-BUJH-1"] = float(net.res_ext_grid["p_mw"].sum())
    return net, load_p, gen_p


# --------------------------------------------------------------------------- T01
def t01_tables(w: World) -> tuple[dict[str, pd.DataFrame], dict]:
    """All T01 sheets for both cases, plus facts for truth.json."""
    nw = w.nw
    t_peak = w.peak_hour("2026-09")
    when = w.cal.hours[t_peak]
    peak_net = solve_peak(w, t_peak)
    plan_net, plan_load, plan_gen = solve_2030(w, t_peak)
    peak_load = {lid: float(w.ts.load_p[t_peak, w.load_col[lid]]) for lid in w.ts.load_ids}
    peak_q = {lid: float(w.ts.load_q[t_peak, w.load_col[lid]]) for lid in w.ts.load_ids}
    peak_gen = {g: float(w.ts.gen_p[t_peak, w.gen_col[g]]) for g in w.ts.gen_ids}
    peak_gen["G-BUJH-1"] = float(peak_net.res_ext_grid["p_mw"].sum())

    cases = pd.DataFrame([
        {"case_id": PEAK_CASE, "case_type": "as_operated_peak", "case_date": when.date(), "case_hour": when.hour,
         "description": "SYNTHETIC: Central evening peak, September 2026, all units available",
         "source_tool": "synthetic", "tool_version": "engine/synthetic 1", "base_mva": 100.0, "frequency_hz": 50.0,
         "perimeter": "central", "rating_note": RATING_NOTE, "contact": "[synthetic]"},
        {"case_id": PLAN_CASE, "case_type": "planning_2030", "case_date": date(2030, 9, 15), "case_hour": when.hour,
         "description": "SYNTHETIC: 2030 peak, 7 % a year growth plus committed loads, planned projects in service",
         "source_tool": "synthetic", "tool_version": "engine/synthetic 1", "base_mva": 100.0, "frequency_hz": 50.0,
         "perimeter": "central", "rating_note": RATING_NOTE, "contact": "[synthetic]"},
    ])
    sheets: dict[str, list[pd.DataFrame]] = {k: [] for k in (
        "buses", "lines", "transformers", "generators", "loads", "shunts", "boundary",
        "solved_buses", "solved_branches")}
    for case_id, net, lp, gp in ((PEAK_CASE, peak_net, peak_load, peak_gen), (PLAN_CASE, plan_net, plan_load, plan_gen)):
        planned_in = case_id == PLAN_CASE
        sheets["buses"].append(pd.DataFrame([
            {"case_id": case_id, "bus_id": r.bus_id, "name": bus_name(r.bus_id), "substation": ss_name(r.ss_code),
             "vn_kv": r.vn_kv, "zone": "Central" if r.in_central else "External", "in_service": "Y",
             "v_min_pu": 0.95 if r.vn_kv >= 132 else 0.90, "v_max_pu": 1.05 if r.vn_kv >= 220 else 1.10}
            for r in nw.buses.itertuples()]))
        sheets["lines"].append(pd.DataFrame([
            {"case_id": case_id, "line_id": r.line_id, "name": line_title(r), "from_bus": r.from_bus, "to_bus": r.to_bus,
             "circuit": r.circuit, "length_km": r.length_km, "conductor": r.conductor, "conductors_per_phase": r.bundle,
             "r_ohm_per_km": r.r20_ohm_per_km, "x_ohm_per_km": r.x_ohm_per_km, "b_us_per_km": r.b_us_per_km,
             "r_temp_c": 20.0, "rate_cont_mva": r.rate_cont_mva, "rate_emerg_mva": r.rate_emerg_mva,
             "rate_ncc_mva": None, "rate_ncc_basis": None, "commissioning_year": r.commissioning_year,
             "status": r.status, "in_service": "Y", "tower_group": r.tower_group,
             "notes": "SYNTHETIC" + (f"; planned (T08 {PLANNED_PROJECT.get(r.line_id, '')})" if r.status == "planned" else "")}
            for r in nw.lines.itertuples()]))
        sheets["transformers"].append(pd.DataFrame([
            {"case_id": case_id, "trafo_id": r.trafo_id,
             "name": f"{ss_name(r.ss_code)} transformer {r.trafo_id.split('-')[-1]} {int(r.vn_hv_kv)}/{int(r.vn_lv_kv)} kV",
             "substation": ss_name(r.ss_code), "hv_bus": r.hv_bus, "lv_bus": r.lv_bus, "sn_mva": r.sn_mva,
             "vn_hv_kv": r.vn_hv_kv, "vn_lv_kv": r.vn_lv_kv, "vk_percent": r.vk_percent, "vkr_percent": r.vkr_percent,
             "load_loss_kw": round(r.vkr_percent / 100 * r.sn_mva * 1000, 1), "pfe_kw": r.pfe_kw,
             "i0_percent": r.i0_percent, "vector_group": "YNyn0" if r.vn_lv_kv >= 132 else "YNd1", "tap_side": "hv",
             "tap_neutral": 0, "tap_min": -10, "tap_max": 10, "tap_step_percent": 1.25, "tap_pos": int(r.tap_pos),
             "rate_cont_mva": r.rate_cont_mva, "rate_emerg_mva": r.rate_emerg_mva, "rate_ncc_mva": None,
             "rate_ncc_basis": None, "commissioning_year": r.commissioning_year, "status": r.status,
             "in_service": "Y", "notes": "SYNTHETIC" + ("; planned (T08 SP-01)" if r.status == "planned" else "")}
            for r in nw.trafos.itertuples()]))
        sheets["generators"].append(pd.DataFrame([
            {"case_id": case_id, "gen_id": r.gen_id, "name": f"{r.plant} unit 1", "bus": r.bus, "plant": r.plant,
             "technology": r.technology, "p_mw": round(gp[r.gen_id], 3), "p_max_mw": r.p_max_mw, "p_min_mw": r.p_min_mw,
             "q_min_mvar": r.q_min_mvar, "q_max_mvar": r.q_max_mvar, "vm_pu": r.vm_pu, "control": r.control,
             "connection_kv": r.connection_kv, "in_service": "Y"}
            for r in nw.gens.itertuples()]))
        sheets["loads"].append(pd.DataFrame([
            {"case_id": case_id, "load_id": r.load_id, "bus": r.bus, "substation": ss_name(r.ss_code),
             "bsp_name": f"{ss_name(r.ss_code)} 33 kV" if r.load_id != MBR_LOAD_ID else "Mbarara tie (export)",
             "share": 1.0, "p_mw": round(lp[r.load_id], 3),
             "q_mvar": round(lp[r.load_id] * (peak_q[r.load_id] / peak_load[r.load_id]), 3), "in_service": "Y"}
            for r in nw.loads.itertuples()]))
        sheets["shunts"].append(pd.DataFrame([
            {"case_id": case_id, "shunt_id": r.shunt_id, "bus": r.bus, "q_mvar": r.q_mvar, "steps": 1, "in_service": "Y"}
            for r in nw.shunts.itertuples()]))
        sheets["boundary"].append(pd.DataFrame([
            {"case_id": case_id, "bus": "BUJ-220-1", "kind": "slack", "vm_pu": 1.04, "p_mw": None,
             "note": "SYNTHETIC: Nile infeed at Bujagali, the slack"},
            {"case_id": case_id, "bus": "NAL-132-1", "kind": "pv", "vm_pu": 1.03, "p_mw": round(gp["G-NALH-1"], 3),
             "note": "SYNTHETIC: Nalubaale/Kiira injection (generator G-NALH-1)"},
            {"case_id": case_id, "bus": "KAR-400-1", "kind": "pv", "vm_pu": 1.04, "p_mw": round(gp["G-KARH-1"], 3),
             "note": "SYNTHETIC: Karuma 400 kV infeed to Kawanda (generator G-KARH-1)"},
            {"case_id": case_id, "bus": "MBR-220-1", "kind": "fixed_p", "vm_pu": None, "p_mw": None,
             "note": "SYNTHETIC: export tie to Mbarara, already modelled as load D-MBR-1 (positive = leaving Central)"},
        ]))
        sheets["solved_buses"].append(pd.DataFrame({
            "case_id": case_id, "bus_id": net.bus["name"].to_numpy(),
            "vm_pu": net.res_bus["vm_pu"].round(5).to_numpy(), "va_deg": net.res_bus["va_degree"].round(4).to_numpy()}))
        lr = pd.DataFrame({"case_id": case_id, "branch_id": net.line["name"].to_numpy(),
                           "p_from_mw": net.res_line["p_from_mw"].to_numpy(), "q_from_mvar": net.res_line["q_from_mvar"].to_numpy(),
                           "p_to_mw": net.res_line["p_to_mw"].to_numpy(), "q_to_mvar": net.res_line["q_to_mvar"].to_numpy(),
                           "loading_pct": net.res_line["loading_percent"].to_numpy()})
        trr = pd.DataFrame({"case_id": case_id, "branch_id": net.trafo["name"].to_numpy(),
                            "p_from_mw": net.res_trafo["p_hv_mw"].to_numpy(), "q_from_mvar": net.res_trafo["q_hv_mvar"].to_numpy(),
                            "p_to_mw": net.res_trafo["p_lv_mw"].to_numpy(), "q_to_mvar": net.res_trafo["q_lv_mvar"].to_numpy(),
                            "loading_pct": net.res_trafo["loading_percent"].to_numpy()})
        sheets["solved_branches"].append(pd.concat([lr, trr]).round(4))
    out = {k: pd.concat(v, ignore_index=True) for k, v in sheets.items()}
    out["cases"] = cases
    out["switches"] = pd.DataFrame()
    out["transformers_3w"] = pd.DataFrame()
    out["changes"] = pd.DataFrame([
        {"change_date": date(2024, 3, 15), "element_id": "T-KAW-4", "element_type": "trafo", "change": "commissioned",
         "detail": "SYNTHETIC: first 400/220 kV unit for the Karuma infeed"},
        {"change_date": date(2024, 3, 15), "element_id": "T-KAW-5", "element_type": "trafo", "change": "commissioned",
         "detail": "SYNTHETIC: second 400/220 kV unit for the Karuma infeed"},
        {"change_date": date(2024, 3, 15), "element_id": "L-KAR-KAW-400-1", "element_type": "line",
         "change": "commissioned", "detail": "SYNTHETIC: Karuma - Kawanda 400 kV line"},
    ])
    facts = {
        "peak_case": {"case_id": PEAK_CASE, "timestamp": when.strftime("%Y-%m-%d %H:%M"),
                      "central_load_mw": round(sum(v for k, v in peak_load.items() if k != MBR_LOAD_ID), 2),
                      "converged": bool(peak_net.converged)},
        "plan_case": {"case_id": PLAN_CASE, "central_load_mw": round(sum(v for k, v in plan_load.items() if k != MBR_LOAD_ID), 2),
                      "converged": bool(plan_net.converged),
                      "max_line_loading_pct": round(float(plan_net.res_line["loading_percent"].max()), 1),
                      "max_trafo_loading_pct": round(float(plan_net.res_trafo["loading_percent"].max()), 1)},
    }
    return out, facts


# --------------------------------------------------------------------------- T12
def t12_tables(nw: Network) -> dict[str, pd.DataFrame]:
    """The same network as T01, written as hand-built schedules (the fallback path)."""
    subs = pd.DataFrame([
        {"ss_code": r.ss_code, "name": r.name, "kv_levels": r.kv_levels, "lat": r.lat, "lon": r.lon,
         "district": r.district, "in_central": r.in_central, "source": "SYNTHETIC substation list"}
        for r in nw.substations.itertuples()])
    lines = pd.DataFrame([
        {"from_ss": r.ss_a, "to_ss": r.ss_b, "kv": float(r.kv), "circuit": r.circuit, "length_km": r.length_km,
         "conductor": r.conductor, "conductors_per_phase": r.bundle, "commissioning_year": r.commissioning_year,
         "tower_group": r.tower_group, "status": r.status, "source": "SYNTHETIC line schedule"}
        for r in nw.lines.itertuples()])
    trafos = pd.DataFrame([
        {"substation": r.ss_code, "unit": int(r.trafo_id.split("-")[-1]), "mva": r.sn_mva, "hv_kv": r.vn_hv_kv,
         "lv_kv": r.vn_lv_kv, "vk_percent": r.vk_percent, "commissioning_year": r.commissioning_year,
         "status": r.status, "source": "SYNTHETIC nameplate"}
        for r in nw.trafos.itertuples()])
    gens = pd.DataFrame([
        {"plant": r.plant, "unit": 1, "substation": r.ss_code, "connection_kv": r.connection_kv,
         "technology": r.technology, "p_max_mw": r.p_max_mw, "p_min_mw": r.p_min_mw, "q_min_mvar": r.q_min_mvar,
         "q_max_mvar": r.q_max_mvar, "status": "existing", "source": "SYNTHETIC licence register"}
        for r in nw.gens.itertuples()])
    boundary = pd.DataFrame([
        {"substation": "BUJ", "kv": 220.0, "kind": "slack", "vm_pu": 1.04, "p_mw": None, "note": "SYNTHETIC: Nile infeed"},
        {"substation": "NAL", "kv": 132.0, "kind": "pv", "vm_pu": 1.03, "p_mw": 150.0, "note": "SYNTHETIC: Nalubaale/Kiira"},
        {"substation": "KAR", "kv": 400.0, "kind": "pv", "vm_pu": 1.04, "p_mw": 220.0, "note": "SYNTHETIC: Karuma 400 kV infeed"},
        {"substation": "MBR", "kv": 220.0, "kind": "fixed_p", "vm_pu": None, "p_mw": 40.0,
         "note": "SYNTHETIC: export to the west; positive p_mw = power leaving Central"},
    ])
    return {"substations": subs, "line_schedule": lines, "transformer_schedule": trafos,
            "generators": gens, "boundary": boundary}


# --------------------------------------------------------------------------- T02 GIS
def _jittered_route(a: tuple[float, float], b: tuple[float, float], rng: np.random.Generator,
                    n: int = 6, offset: float = 0.0) -> list[list[float]]:
    """A gently wiggling LineString from a to b (lon, lat), optionally shifted sideways."""
    (lat1, lon1), (lat2, lon2) = a, b
    dlat, dlon = lat2 - lat1, lon2 - lon1
    length = math.hypot(dlat, dlon) or 1.0
    nlat, nlon = -dlon / length, dlat / length  # unit normal
    pts = []
    for i in range(n + 1):
        f = i / n
        wiggle = 0.0 if i in (0, n) else rng.normal(0, 0.012 * length)
        side = offset * (0 if i in (0, n) else 1)
        pts.append([lon1 + f * dlon + (wiggle + side) * nlon, lat1 + f * dlat + (wiggle + side) * nlat])
    return pts


def site_year(nw: Network, ss: str) -> int:
    """Commissioning year of a site: its oldest transformer, else its oldest plant, else 2000."""
    years = nw.trafos.loc[(nw.trafos.ss_code == ss) & (nw.trafos.status == "existing"), "commissioning_year"].tolist()
    years += nw.gens.loc[nw.gens.ss_code == ss, "cod_year"].tolist()
    lines = nw.lines[(nw.lines.status == "existing") & ((nw.lines.ss_a == ss) | (nw.lines.ss_b == ss))]
    if not years and len(lines):
        years = lines["commissioning_year"].tolist()
    return int(min(years)) if years else 2000


def t02_features(nw: Network, seed: int) -> tuple[list[dict], list[dict], pd.DataFrame]:
    """Substation points, circuit LineStrings and the crosswalk sheet."""
    rng = rng_for(seed, "gis")
    pts = []
    for i, r in enumerate(nw.substations.itertuples(), start=1):
        kind = "power_station" if r.ss_code in ("BUJ", "NAL", "KAR") else "substation"
        bus_ids = ";".join(nw.buses.loc[nw.buses["ss_code"] == r.ss_code, "bus_id"])
        pts.append({
            "geometry": {"type": "Point", "coordinates": [r.lon + rng.normal(0, 0.0004), r.lat + rng.normal(0, 0.0004)]},
            "properties": {"source_id": f"SYN-SS-{i:03d}", "name": r.name, "ss_code": r.ss_code, "facility_type": kind,
                           "kv_levels": r.kv_levels, "model_bus_ids": bus_ids, "status": "existing",
                           "commissioning_year": site_year(nw, r.ss_code),
                           "district": r.district, "capture_method": "approximate", "notes": "SYNTHETIC location"}})
    circuits, cross = [], []
    loc = {r.ss_code: (r.lat, r.lon) for r in nw.substations.itertuples()}
    routes: dict[str, list] = {}
    for i, r in enumerate(nw.lines[nw.lines["status"] != "planned"].itertuples(), start=1):
        base = routes.get(r.tower_group)
        if base is None:
            base = _jittered_route(loc[r.ss_a], loc[r.ss_b], rng)
            routes[r.tower_group] = base
        coords = [[p[0] + (r.circuit - 1) * 0.0003, p[1]] for p in base]  # double circuits sit side by side
        cid = f"SYN-CCT-{i:03d}"
        twin = nw.lines[(nw.lines["tower_group"] == r.tower_group) & (nw.lines["line_id"] != r.line_id)]
        circuits.append({
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"circuit_id": cid, "model_branch_id": r.line_id,
                           "name": f"{ss_name(r.ss_a)} - {ss_name(r.ss_b)} {r.circuit}", "from_substation": ss_name(r.ss_a),
                           "to_substation": ss_name(r.ss_b), "kv": float(r.kv), "design_kv": float(r.kv),
                           "circuit_no": r.circuit, "double_circuit_with": None,
                           "conductor": r.conductor, "route_length_km": round(r.length_km * (1 + rng.normal(0, 0.02)), 2),
                           "commissioning_year": r.commissioning_year, "reconductored_year": None, "status": "existing",
                           "capture_method": "approximate", "notes": "SYNTHETIC route",
                           "_twin": twin["line_id"].tolist()}})
        cross.append({"entity_type": "circuit", "planning_model_id": r.line_id, "gis_feature_id": cid,
                      "ncc_report_name": f"{ss_name(r.ss_a)}-{ss_name(r.ss_b)} {r.kv} kV {r.circuit}",
                      "scada_name": f"{r.ss_a} LINE {r.ss_b} {r.circuit}",
                      "commercial_name": f"{ss_name(r.ss_a)} - {ss_name(r.ss_b)}", "notes": "SYNTHETIC"})
    by_line = {c["properties"]["model_branch_id"]: c["properties"]["circuit_id"] for c in circuits}
    for c in circuits:
        twins = c["properties"].pop("_twin")
        if twins and twins[0] in by_line:
            c["properties"]["double_circuit_with"] = by_line[twins[0]]
    for p in pts:
        cross.append({"entity_type": "substation", "planning_model_id": p["properties"]["ss_code"],
                      "gis_feature_id": p["properties"]["source_id"], "ncc_report_name": p["properties"]["name"],
                      "scada_name": p["properties"]["ss_code"], "commercial_name": p["properties"]["name"],
                      "notes": "SYNTHETIC"})
    return pts, circuits, pd.DataFrame(cross)


def asset_age_rows(nw: Network) -> pd.DataFrame:
    """T13 commissioning_years: one row per existing line circuit and transformer."""
    rows = []
    for r in nw.lines[nw.lines["status"] == "existing"].itertuples():
        rows.append({"element_type": "line", "element_ref": r.line_id, "name": line_title(r),
                     "from_substation": ss_name(r.ss_a), "to_substation": ss_name(r.ss_b), "kv": float(r.kv),
                     "commissioning_year": r.commissioning_year, "source": "SYNTHETIC line schedule"})
    for r in nw.trafos[nw.trafos["status"] == "existing"].itertuples():
        rows.append({"element_type": "transformer", "element_ref": r.trafo_id,
                     "name": f"{ss_name(r.ss_code)} transformer {r.trafo_id.split('-')[-1]}",
                     "from_substation": ss_name(r.ss_code), "kv": r.vn_hv_kv,
                     "commissioning_year": r.commissioning_year, "source": "SYNTHETIC nameplate"})
    return pd.DataFrame(rows)
