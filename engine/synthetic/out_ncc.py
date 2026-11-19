"""T03 (NCC monthly), T04 (SCADA) and T05 (NCC operations) from the synthetic world.

Everything is cut from the truth simulation, so the files agree with each other the way
real NCC data should: energies add up, the boundary balance gives the (planted) loss,
SCADA matches the flows within about 1 %, and the Kawanda constraint shows in the
constraint hours, curtailments and events.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from engine.synthetic.network import CENTRAL, MBR_LOAD_ID, SUBSTATIONS
from engine.synthetic.timeseries import MONTHS, OUTAGE_END, OUTAGE_LINE, OUTAGE_START, rng_for
from engine.synthetic.world import NCC_PLANT_NAMES, PLANTED_ESTIMATED_MONTH, World, ncc_name, ss_name

# SCADA coverage: full months, months with no SCADA at all, and the rest (two sample days).
SCADA_FULL_MONTHS = ("2026-07", "2026-08", "2026-09")
SCADA_MISSING_MONTHS = ("2026-01", "2026-06")
SIGN = "+ = from the busbar into the bay"
KAW_CONSTRAINT = "KAW-1"
KAW_LINES_CONSTRAINT = "KAW-2"
CONSTRAINT_PERCENTILE = 98.5  # hours above this percentile of N-0 loading count as 'constraint bound'


def fmt_ts(t) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M")


# --------------------------------------------------------------------------- Kawanda constraint
def kawanda_elements(w: World) -> tuple[list[str], str]:
    """The elements of the main Kawanda constraint for this variant, and their type."""
    if w.variant == "line_bound":
        return ["L-KAW-MUT-132-1", "L-KAW-MUT-132-2"], "line"
    return ["T-KAW-1", "T-KAW-2"], "transformer"


def kawanda_loading(w: World) -> np.ndarray:
    """Hourly N-0 loading % of the most loaded element of the main Kawanda constraint."""
    ids, kind = kawanda_elements(w)
    if kind == "line":
        return np.max([w.tr.line_loading[:, w.line_col[i]] for i in ids], axis=0)
    return np.max([w.tr.trafo_loading[:, w.trafo_col[i]] for i in ids], axis=0)


def constraint_periods(w: World) -> pd.DataFrame:
    """Contiguous periods when the Kawanda constraint bound (N-0 loading above a high percentile).

    These are the hours NCC would act on: with one unit out, the other would overload.
    """
    load = kawanda_loading(w)
    thr = float(np.percentile(load, CONSTRAINT_PERCENTILE))
    hot = load >= thr
    rows, t = [], 0
    hours = w.cal.hours
    while t < len(hot):
        if not hot[t]:
            t += 1
            continue
        s = t
        while t < len(hot) and hot[t]:
            t += 1
        ids, kind = kawanda_elements(w)
        mw = sum(np.abs(w.tr.trafo_p_hv[s:t, w.trafo_col[i]]) if kind == "transformer"
                 else np.abs(w.tr.line_p_from[s:t, w.line_col[i]]) for i in ids)
        rows.append({"constraint_id": KAW_CONSTRAINT, "start_at": hours[s], "end_at": hours[t - 1] + pd.Timedelta(hours=1),
                     "max_loading_pct": round(float(load[s:t].max()), 1), "max_mw": round(float(np.max(mw)), 1),
                     "n_hours": t - s})
    df = pd.DataFrame(rows)
    df.attrs["threshold_pct"] = thr
    return df


# --------------------------------------------------------------------------- T05
def kawanda_constraint_rows(w: World) -> list[dict]:
    """The two Kawanda constraints: the binding one for this variant first (KAW-1), the other second."""
    tr = w.nw.trafos.set_index("trafo_id").loc["T-KAW-1"]
    ln = w.nw.lines.set_index("line_id").loc["L-KAW-MUT-132-1"]
    trafo = {"element": "Kawanda 220/132 kV transformers T1 and T2", "element_ref": "T-KAW-1;T-KAW-2",
             "element_type": "transformer", "voltage_kv": 220.0, "lv_kv": 132.0,
             "rating_mva": float(tr["rate_cont_mva"]), "emergency_limit_mva": float(tr["rate_emerg_mva"]),
             "triggering_contingency": "Outage of either Kawanda 220/132 kV transformer",
             "relief_project": "Third 220/132 kV transformer at Kawanda (SP-01)", "relief_date": "2027-06"}
    lines = {"element": "Kawanda - Mutundwe 132 kV circuits 1 and 2", "element_ref": "L-KAW-MUT-132-1;L-KAW-MUT-132-2",
             "element_type": "line", "voltage_kv": 132.0, "lv_kv": None,
             "rating_mva": float(ln["rate_cont_mva"]), "emergency_limit_mva": float(ln["rate_emerg_mva"]),
             "triggering_contingency": "Trip of the other Kawanda - Mutundwe circuit",
             "relief_project": "Second Kawanda - Kampala North 132 kV circuit (SP-02)", "relief_date": "2028-06"}
    _, kind = kawanda_elements(w)
    first, second = (trafo, lines) if kind == "transformer" else (lines, trafo)
    rows = []
    for cid, c, seen, scheme, note in (
        (KAW_CONSTRAINT, first, "2025-09", "Operator instruction: curtail DC-1 and DC-2, then shed Kawanda 33 kV feeders",
         "SYNTHETIC: the Kawanda constraint"),
        (KAW_LINES_CONSTRAINT, second, "2026-01", None, "SYNTHETIC: secondary Kawanda constraint"),
    ):
        rows.append({"constraint_id": cid, "substation": ncc_name("KAW"), **c, "limit_mva": c["rating_mva"],
                     "limit_mw": round(c["rating_mva"] * 0.95, 1), "limit_basis": "thermal", "binds_at": "N-1",
                     "special_scheme": scheme, "first_seen": seen, "notes": note})
    return rows


def t05_tables(w: World) -> tuple[dict[str, pd.DataFrame], dict]:
    """Constraints, constraint hours, curtailments, deferred connections and events."""
    rng = rng_for(w.seed, "ops")
    constraints = pd.DataFrame(kawanda_constraint_rows(w))
    periods = constraint_periods(w)
    # NCC acted on about two in three periods: curtail the data centres (on these the action is logged).
    act = rng.random(len(periods)) < 0.65
    curt_rows = []
    for k, (p, acted) in enumerate(zip(periods.itertuples(), act)):
        if not acted:
            continue
        hours = p.n_hours
        for ref, lo, hi in (("DC-1", 5.0, 9.0), ("DC-2", 3.0, 6.0)):
            mw = round(float(rng.uniform(lo, hi)), 1)
            curt_rows.append({"start_at": p.start_at + pd.Timedelta(minutes=10), "end_at": p.end_at - pd.Timedelta(minutes=5),
                              "substation": ncc_name("KAW"), "supply_kv": 33.0, "customer_category": "data_centre",
                              "customer_ref": ref, "mw_curtailed": mw, "mwh_curtailed": round(mw * (hours - 0.25), 2),
                              "action_type": "customer_curtailment", "reason": "kawanda_constraint",
                              "constraint_id": KAW_CONSTRAINT, "instruction_ref": f"SYN-INS-{k + 1:03d}", "notes": "SYNTHETIC"})
    for day, ref, mw in ((date(2026, 2, 24), "DC-1", 6.0), (date(2026, 2, 24), "DC-2", 4.0),
                         (date(2026, 3, 11), "DC-1", 5.0), (date(2026, 3, 11), "DC-2", 3.5)):
        start = datetime.combine(day, datetime.min.time()) + timedelta(hours=19)
        curt_rows.append({"start_at": pd.Timestamp(start), "end_at": pd.Timestamp(start + timedelta(hours=3)),
                          "substation": ncc_name("KAW"), "supply_kv": 33.0, "customer_category": "data_centre",
                          "customer_ref": ref, "mw_curtailed": mw, "mwh_curtailed": mw * 3,
                          "action_type": "customer_curtailment", "reason": "generation_shortfall", "constraint_id": None,
                          "instruction_ref": f"SYN-GEN-{day:%m%d}", "notes": "SYNTHETIC: dry-season generation shortfall"})
    curtailments = pd.DataFrame(curt_rows).sort_values(["start_at", "customer_ref"]).reset_index(drop=True)
    ch = periods.copy()
    acted_idx = set(np.where(act)[0])
    ch["elements_out"] = None
    ch["action"] = ["Curtailed DC-1 and DC-2" if i in acted_idx else "Monitored; no action" for i in range(len(ch))]
    ch["evidence"] = "scada"
    deferred = pd.DataFrame([
        {"application_date": date(2025, 10, 6), "substation_or_area": ncc_name("KAW"), "customer_category": "data_centre",
         "customer_ref": "DC-3", "application_ref": "SYN-APP-101", "requested_mw": 20.0, "wanted_from": "2026-03",
         "firm_or_interruptible": "firm", "status": "deferred", "connection_date": "2027-09",
         "reason": "No firm capacity at Kawanda before the third 220/132 kV transformer", "constraint_id": KAW_CONSTRAINT},
        {"application_date": date(2026, 2, 17), "substation_or_area": ncc_name("KAW"), "customer_category": "industrial",
         "customer_ref": "IND-7", "application_ref": "SYN-APP-117", "requested_mw": 20.0, "wanted_from": "2026-08",
         "firm_or_interruptible": "firm", "status": "deferred", "connection_date": "2027-12",
         "reason": "No firm capacity at Kawanda before the third 220/132 kV transformer", "constraint_id": KAW_CONSTRAINT},
    ])
    events = event_rows(w, periods, rng)
    facts = {"constraint_threshold_pct": round(periods.attrs["threshold_pct"], 1), "n_constraint_periods": len(periods),
             "n_curtailments_kawanda": int((curtailments["reason"] == "kawanda_constraint").sum()),
             "n_curtailments_generation": int((curtailments["reason"] == "generation_shortfall").sum()),
             "curtailed_mwh_kawanda": round(float(curtailments.loc[curtailments.reason == "kawanda_constraint", "mwh_curtailed"].sum()), 1),
             "n_events": len(events), "n_events_constraint_related": int((events["constraint_related"] == "Y").sum())}
    ch = ch.drop(columns=["n_hours"])
    return {"constraints": constraints, "constraint_hours": ch, "curtailments": curtailments,
            "deferred_connections": deferred, "events": events}, facts


def event_rows(w: World, periods: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """About two dozen operational events over the 13 months.

    The planned KAW-KNO outage is in the truth simulation; the short trips and load shedding
    are not (they last minutes to hours and would not change monthly energy materially).
    """
    kap_load = lambda t: float(w.ts.load_p[w.cal.hours.get_loc(pd.Timestamp(t)), w.load_col["D-KAP-1"]])
    rows = [
        {"incident_ref": "SYN-2026-041", "start_at": pd.Timestamp(OUTAGE_START), "end_at": pd.Timestamp(OUTAGE_END),
         "substation": ncc_name("KAW"), "element": "Kawanda - Kampala North 132 kV circuit 1", "element_ref": OUTAGE_LINE,
         "voltage_kv": 132.0, "event_type": "planned_outage", "mw_lost": 0.0, "mwh_unserved": 0.0,
         "cause_code": "equipment", "constraint_related": "N", "constraint_id": None,
         "cause": "Planned maintenance: insulator replacement", "notes": "SYNTHETIC: in the truth simulation"},
        {"incident_ref": "SYN-2025-112", "start_at": pd.Timestamp("2025-11-08 16:40"), "end_at": pd.Timestamp("2025-11-08 18:05"),
         "substation": "Kapeeka", "element": "Kapeeka - Kawanda 132 kV line", "element_ref": "L-KAP-KAW-132-1",
         "voltage_kv": 132.0, "event_type": "forced_trip", "mw_lost": round(kap_load("2025-11-08 16:00"), 1),
         "mwh_unserved": round(kap_load("2025-11-08 16:00") * 1.4, 1), "cause_code": "weather", "constraint_related": "N",
         "constraint_id": None, "cause": "Lightning; radial line, Kapeeka lost supply", "notes": "SYNTHETIC"},
        {"incident_ref": "SYN-2026-007", "start_at": pd.Timestamp("2026-01-14 14:05"), "end_at": pd.Timestamp("2026-01-14 15:20"),
         "substation": "Nkonge", "element": "Kabulasoke - Nkonge 132 kV line", "element_ref": "L-KBS-NKG-132-1",
         "voltage_kv": 132.0, "event_type": "forced_trip", "mw_lost": 0.0, "mwh_unserved": 0.0, "cause_code": "vandalism",
         "constraint_related": "N", "constraint_id": None, "cause": "Tower member theft found on patrol", "notes": "SYNTHETIC"},
        {"incident_ref": "SYN-2026-033", "start_at": pd.Timestamp("2026-03-26 11:20"), "end_at": pd.Timestamp("2026-03-26 12:00"),
         "substation": ncc_name("MUK"), "element": "Mukono - Nalubaale 132 kV line", "element_ref": "L-MUK-NAL-132-1",
         "voltage_kv": 132.0, "event_type": "forced_trip", "mw_lost": 0.0, "mwh_unserved": 0.0, "cause_code": "protection",
         "constraint_related": "N", "constraint_id": None, "cause": "Distance protection mal-operation", "notes": "SYNTHETIC"},
        {"incident_ref": "SYN-2026-058", "start_at": pd.Timestamp("2026-05-19 09:10"), "end_at": pd.Timestamp("2026-05-19 09:55"),
         "substation": "Masaka", "element": "Masaka transformer 3 132/33 kV", "element_ref": "T-MSK-3",
         "voltage_kv": 132.0, "event_type": "forced_trip", "mw_lost": 12.0, "mwh_unserved": 9.0, "cause_code": "human_error",
         "constraint_related": "N", "constraint_id": None, "cause": "Wrong bay switched during maintenance", "notes": "SYNTHETIC"},
        {"incident_ref": "SYN-2026-020", "start_at": pd.Timestamp("2026-02-24 19:00"), "end_at": pd.Timestamp("2026-02-24 22:00"),
         "substation": ncc_name("KAW"), "element": "Kawanda 33 kV feeders", "element_ref": None, "voltage_kv": 33.0,
         "event_type": "load_shedding", "mw_lost": 18.0, "mwh_unserved": 54.0, "cause_code": "generation",
         "constraint_related": "N", "constraint_id": None, "cause": "Dry-season generation shortfall", "notes": "SYNTHETIC"},
        {"incident_ref": "SYN-2026-029", "start_at": pd.Timestamp("2026-03-11 19:00"), "end_at": pd.Timestamp("2026-03-11 22:00"),
         "substation": "Mutundwe", "element": "Mutundwe 33 kV feeders", "element_ref": None, "voltage_kv": 33.0,
         "event_type": "load_shedding", "mw_lost": 15.0, "mwh_unserved": 45.0, "cause_code": "generation",
         "constraint_related": "N", "constraint_id": None, "cause": "Dry-season generation shortfall", "notes": "SYNTHETIC"},
        {"incident_ref": "SYN-2026-087", "start_at": pd.Timestamp("2026-08-03 02:15"), "end_at": pd.Timestamp("2026-08-03 02:40"),
         "substation": None, "element": "System disturbance (frequency dip)", "element_ref": None, "voltage_kv": None,
         "event_type": "disturbance", "mw_lost": 0.0, "mwh_unserved": 0.0, "cause_code": "unknown",
         "constraint_related": "N", "constraint_id": None, "cause": "Under-frequency excursion, cause under review",
         "notes": "SYNTHETIC"},
    ]
    # Constraint-related events: feeder shedding at Kawanda on the hottest constraint periods,
    # and two trips of a Kawanda unit or line that forced shedding.
    top = periods.sort_values("max_loading_pct", ascending=False).head(8)
    ids, kind = kawanda_elements(w)
    for n, p in enumerate(top.itertuples(), start=1):
        start = p.start_at + pd.Timedelta(minutes=25)
        end = min(p.end_at, start + pd.Timedelta(hours=2))
        dur = (end - start).total_seconds() / 3600
        if n <= 2:
            unit = ids[n - 1]
            name = (f"Kawanda transformer {unit.split('-')[-1]} 220/132 kV" if kind == "transformer"
                    else f"Kawanda - Mutundwe 132 kV circuit {unit.split('-')[-1]}")
            rows.append({"incident_ref": f"SYN-KAW-{n:02d}", "start_at": start, "end_at": end,
                         "substation": ncc_name("KAW"), "element": name, "element_ref": unit,
                         "voltage_kv": 220.0 if kind == "transformer" else 132.0, "event_type": "forced_trip",
                         "mw_lost": 22.0, "mwh_unserved": round(22.0 * dur, 1), "cause_code": "constraint",
                         "constraint_related": "Y", "constraint_id": KAW_CONSTRAINT,
                         "cause": "Overload protection tripped the unit; the parallel element then overloaded and feeders were shed",
                         "notes": "SYNTHETIC: not in the truth simulation"})
        else:
            mw = round(float(rng.uniform(8, 16)), 1)
            rows.append({"incident_ref": f"SYN-KAW-{n:02d}", "start_at": start, "end_at": end,
                         "substation": ncc_name("KAW"), "element": "Kawanda 33 kV feeder group B", "element_ref": None,
                         "voltage_kv": 33.0, "event_type": "load_shedding", "mw_lost": mw,
                         "mwh_unserved": round(mw * dur, 1), "cause_code": "constraint", "constraint_related": "Y",
                         "constraint_id": KAW_CONSTRAINT,
                         "cause": "Shed to keep the Kawanda constraint within its N-1 limit",
                         "notes": "SYNTHETIC: not in the truth simulation"})
    return pd.DataFrame(rows).sort_values("start_at").reset_index(drop=True)


# --------------------------------------------------------------------------- T03
def t03_tables(w: World, ops: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict]:
    """NCC monthly sheets, cut from the truth and the reconciliation design."""
    recon = w.recon.set_index("month")
    tr = w.tr
    cl = w.central_load()
    all_gen = {g: w.gen_p(g) for g in w.nw.gens["gen_id"]}
    total_gen = sum(all_gen.values())
    mbr = w.ts.load_p[:, w.load_col[MBR_LOAD_ID]]
    events, curt = ops["events"], ops["curtailments"]
    deemed_rows, sub_rows, gen_rows, sys_rows, lbv_rows, sample_rows, bm_rows = [], [], [], [], [], [], []
    lines = w.nw.lines.set_index("line_id")
    kv_of_line = np.array([lines.loc[n, "kv"] for n in tr.line_names])
    rng = rng_for(w.seed, "t03")
    periods = ops["constraint_hours"]
    for month in MONTHS:
        sel = w.month_mask(month)
        idx = np.where(sel)[0]
        r = recon.loc[month]
        tpk, tmin = w.peak_hour(month), w.min_hour(month)
        # --- substation monthly
        for c in CENTRAL:
            k = w.load_col[f"D-{c}-1"]
            p, q = w.ts.load_p[:, k], w.ts.load_q[:, k]
            ip = idx[p[idx].argmax()]
            embedded = c in ("NMV", "KBS", "NKG", "KAP")
            sub_rows.append({
                "month": month, "substation": ncc_name(c), "metering_point": f"{c} 33 kV feeders (BSP)", "metering_kv": 33.0,
                "energy_mwh": round(r["reported_deliveries"][f"D-{c}-1"], 3), "peak_mw": round(float(p[ip]), 3),
                "peak_at": w.cal.hours[ip], "peak_mvar": round(float(q[ip]), 3), "coincident_mw": round(float(p[tpk]), 3),
                "min_mw": round(float(p[idx].min()), 3), "load_basis": "gross",
                "quality": "actual",
                "notes": "SYNTHETIC" + ("; gross: the 33 kV plant is metered separately" if embedded else "")})
        # --- generation monthly
        demand_hours = len(idx)
        for g in w.nw.gens.itertuples():
            p = all_gen[g.gen_id]
            sent = r["reported_plants"].get(g.gen_id, float(p[idx].sum()))
            avail = 100.0
            if g.gen_id == "G-NMVT-1":
                avail = round(100.0 * (1 - float(((w.cal.hours[idx] >= "2026-05-11") & (w.cal.hours[idx] < "2026-05-21")).sum()) / demand_hours), 1)
            gen_rows.append({
                "month": month, "plant": NCC_PLANT_NAMES[g.plant_code], "technology": g.technology,
                "connection_substation": ncc_name(g.ss_code), "connection_kv": g.connection_kv,
                "sent_out_mwh": round(sent, 3), "peak_mw": round(float(p[idx].max()), 3),
                "availability_pct": avail if g.technology != "solar" else round(float(rng.uniform(96, 100)), 1),
                "metered": "Y", "notes": "SYNTHETIC"})
        # --- boundary meters
        mm = w.meter_month[w.meter_month["month"] == month]
        for m in w.meters:
            lr = lines.loc[m.line_id]
            for direction in ("import", "export"):
                row = mm[(mm["meter_id"] == m.meter_id) & (mm["direction"] == direction)].iloc[0]
                bm_rows.append({
                    "month": month, "meter_id": m.meter_id, "substation": ncc_name(m.ss),
                    "circuit": f"{ss_name(lr.ss_a)} - {ss_name(lr.ss_b)} {lr.kv} kV circuit {lr.circuit}",
                    "far_end_substation": ss_name(m.far), "circuit_kv": float(m.kv), "line_end": ss_name(m.ss),
                    "hv_or_lv": "na", "direction": direction, "energy_mwh": round(float(row["reported_mwh"]), 3),
                    "energy_mvarh": round(float(row["energy_mvarh"]), 3), "accuracy_class": "0.2S",
                    "ct_vt_class": "CT 0.2S, VT 0.2", "main_or_check": "main", "estimated": row["estimated"],
                    "notes": "; ".join(x for x in ("SYNTHETIC", f"model ref {m.line_id}", row["note"]) if x)})
        # --- system summary (the whole synthetic system is the 'national' system)
        gen_mwh = float(total_gen[idx].sum())
        delivered = float(cl[idx].sum())
        exported = float(mbr[idx].sum())
        losses = gen_mwh - delivered - exported
        ev_m = events[events["start_at"].dt.strftime("%Y-%m") == month]
        cu_m = curt[curt["start_at"].dt.strftime("%Y-%m") == month]
        unserved_kaw = float(cu_m.loc[cu_m["reason"] == "kawanda_constraint", "mwh_curtailed"].sum())
        shed = ev_m[ev_m["event_type"] == "load_shedding"]
        deemed_kap = round(float(rng.uniform(5, 40)), 1) if month in ("2025-11", "2026-04", "2026-05") else 0.0
        sys_rows.append({
            "month": month, "generated_mwh": round(gen_mwh, 3), "imported_mwh": 0.0, "exported_mwh": round(exported, 3),
            "sent_out_mwh": round(gen_mwh, 3), "delivered_mwh": round(delivered, 3), "losses_mwh": round(losses, 3),
            "losses_pct": round(100 * losses / gen_mwh, 3), "station_supply_mwh": None,
            "peak_mw": round(float(cl[tpk]), 3), "peak_at": w.cal.hours[tpk], "min_mw": round(float(cl[tmin]), 3),
            "min_at": w.cal.hours[tmin], "deemed_mwh": deemed_kap, "unserved_mwh": round(unserved_kaw + float(shed["mwh_unserved"].sum()), 2),
            "constraint_incidents": int((ev_m["constraint_related"] == "Y").sum()),
            "estimated": "Y" if month == PLANTED_ESTIMATED_MONTH else "N",
            "notes": "SYNTHETIC system = the synthetic model; exported = the Mbarara tie"})
        # --- losses by voltage (national scope: context only, not the Central basis)
        pl_l, pl_t = tr.line_pl[idx], tr.trafo_pl[idx]
        buckets = {"400": float(pl_l[:, kv_of_line == 400].sum()), "220": float(pl_l[:, kv_of_line == 220].sum()),
                   "132": float(pl_l[:, kv_of_line == 132].sum()), "transformation": float(pl_t.sum())}
        buckets["total"] = sum(buckets.values())
        for level, val in buckets.items():
            lbv_rows.append({"month": month, "scope": "national", "voltage_level": level,
                             "losses_mwh": round(val * (1 + 0.01 * rng.standard_normal()), 3),
                             "losses_pct": round(100 * val / gen_mwh, 4), "base_mwh": round(gen_mwh, 3),
                             "method": "estimated", "meters_used": "SYNTHETIC: state estimator by voltage level",
                             "notes": "SYNTHETIC national context; not the Central boundary basis"})
        # --- deemed and unserved
        if deemed_kap:
            deemed_rows.append({"month": month, "category": "deemed", "plant_or_substation": NCC_PLANT_NAMES["KAPS"],
                                "energy_mwh": deemed_kap, "amount_ugx": round(deemed_kap * 1000 * 290.0),
                                "cause": "network_constraint", "constraint_element": "Kapeeka - Kawanda 132 kV line",
                                "notes": "SYNTHETIC"})
        if unserved_kaw:
            deemed_rows.append({"month": month, "category": "unserved", "plant_or_substation": ncc_name("KAW"),
                                "energy_mwh": round(unserved_kaw, 2), "amount_ugx": None, "cause": "network_constraint",
                                "constraint_element": "Kawanda constraint KAW-1", "notes": "SYNTHETIC: data-centre curtailment"})
        for (ss, cause), g in shed.groupby(["substation", "cause_code"]):
            deemed_rows.append({"month": month, "category": "load_shed", "plant_or_substation": ss,
                                "energy_mwh": round(float(g["mwh_unserved"].sum()), 2), "amount_ugx": None,
                                "cause": "network_constraint" if cause == "constraint" else "generation_shortfall",
                                "constraint_element": "Kawanda constraint KAW-1" if cause == "constraint" else None,
                                "notes": "SYNTHETIC"})
        # --- sample days
        pk, lo = w.sample_days(month)
        pm = periods[periods["start_at"].dt.strftime("%Y-%m") == month]
        cday = pm.sort_values("max_loading_pct", ascending=False)["start_at"].iloc[0].date() if len(pm) else None
        sample_rows.append({"month": month, "peak_day": pk, "offpeak_day": lo, "constraint_day": cday,
                            "note": "SYNTHETIC: peak day = day of the monthly Central peak; off-peak = lowest-energy day"})
    facts = {"central_peak_mw": round(float(cl.max()), 2), "central_peak_at": fmt_ts(w.cal.hours[cl.argmax()]),
             "sample_days": {r["month"]: [str(r["peak_day"]), str(r["offpeak_day"])] for r in sample_rows}}
    return {"system_summary": pd.DataFrame(sys_rows), "losses_by_voltage": pd.DataFrame(lbv_rows),
            "substation_monthly": pd.DataFrame(sub_rows), "generation_monthly": pd.DataFrame(gen_rows),
            "boundary_meters": pd.DataFrame(bm_rows), "internal_meters": pd.DataFrame(),
            "deemed_unserved": pd.DataFrame(deemed_rows), "sample_days": pd.DataFrame(sample_rows)}, facts


T03_ANSWERS = {
    "Q1": "SYNTHETIC: the national losses by voltage come from the state estimator.",
    "Q2": "SYNTHETIC: transformation losses are reported separately from line losses.",
    "Q3": "SYNTHETIC: yes. Every Central boundary circuit has a main meter at its Central end (see boundary_meters).",
    "Q4": "SYNTHETIC: BSP meters are on the 33 kV feeders (LV side).",
    "Q5": "SYNTHETIC: substation loads are gross; 33 kV plants at NMV, KBS, NKG and KAP are metered separately.",
    "Q6": "SYNTHETIC: December 2025, Masaka tie export meter MSK-M01 estimated after data loss.",
    "Q7": "SYNTHETIC: EAT, timestamps mark the start of the hour, peaks are hourly averages.",
}


# --------------------------------------------------------------------------- T04
def scada_points(w: World) -> pd.DataFrame:
    """The SCADA point list: Central line ends, 132/33 kV transformer LV bays, Kawanda
    220/132 and 400/220 kV transformer HV bays, BSP totals, generators and bus kV."""
    nw = w.nw
    rows = []

    def add(pid, ss, bay, kv, etype, remote, winding, ref, qty, unit, note=""):
        rows.append({"point_id": pid, "substation": ss_name(ss), "bay": bay, "voltage_kv": float(kv), "element_type": etype,
                     "remote_substation": ss_name(remote) if remote else None, "winding": winding, "element_ref": ref,
                     "quantity": qty, "unit": unit, "sign_convention": SIGN if qty in ("P", "Q") else None,
                     "interval_minutes": 60, "notes": ("SYNTHETIC " + note).strip()})

    for r in nw.lines[nw.lines["status"] == "existing"].itertuples():
        for ss, far in ((r.ss_a, r.ss_b), (r.ss_b, r.ss_a)):
            if not SUBSTATIONS[ss][2]:
                continue
            for qty, unit in (("P", "MW"), ("Q", "MVAr")):
                add(f"{ss}.{r.line_id}.{qty}", ss, f"Line to {ss_name(far)} circuit {r.circuit}", r.kv, "line", far, "na",
                    r.line_id, qty, unit)
    for r in nw.trafos[nw.trafos["status"] == "existing"].itertuples():
        if r.vn_lv_kv == 33:
            for qty, unit in (("P", "MW"), ("Q", "MVAr")):
                add(f"{r.ss_code}.{r.trafo_id}.LV.{qty}", r.ss_code, f"Transformer {r.trafo_id.split('-')[-1]} 33 kV incomer",
                    33, "transformer", None, "lv", r.trafo_id, qty, unit, "(load flows out of this bay: values are negative)")
        elif r.ss_code == "KAW":
            for qty, unit in (("P", "MW"), ("Q", "MVAr")):
                add(f"{r.ss_code}.{r.trafo_id}.HV.{qty}", r.ss_code,
                    f"Transformer {r.trafo_id.split('-')[-1]} {int(r.vn_hv_kv)} kV side", r.vn_hv_kv, "transformer", None,
                    "hv", r.trafo_id, qty, unit)
    for c in CENTRAL:
        for qty, unit in (("P", "MW"), ("Q", "MVAr")):
            add(f"{c}.BSP.{qty}", c, "33 kV feeders (total)", 33, "bsp", None, "na", f"D-{c}-1", qty, unit)
    for g in nw.gens.itertuples():
        add(f"{g.ss_code}.{g.gen_id}.P", g.ss_code, f"{g.plant} generator bay", g.connection_kv, "generator", None, "na",
            g.gen_id, "P", "MW", "(output is negative under this convention)")
    for b in nw.buses.itertuples():
        if b.in_central and b.vn_kv in (132.0, 220.0):
            add(f"{b.ss_code}.{b.bus_id}.V", b.ss_code, f"{int(b.vn_kv)} kV busbar", b.vn_kv, "busbar", None, "na",
                b.bus_id, "V", "kV")
    return pd.DataFrame(rows)


def point_values(w: World, points: pd.DataFrame) -> dict[str, np.ndarray]:
    """True hourly value for every point, under the point's sign convention."""
    out = {}
    for p in points.itertuples():
        if p.element_type == "line":
            ss = p.point_id.split(".")[0]
            pv, qv = w.end_flow(p.element_ref, ss)
            out[p.point_id] = pv if p.quantity == "P" else qv
        elif p.element_type == "transformer":
            k = w.trafo_col[p.element_ref]
            if p.winding == "lv":   # from the 33 kV busbar into the transformer
                out[p.point_id] = w.tr.trafo_p_lv[:, k] if p.quantity == "P" else w.tr.trafo_q_lv[:, k]
            else:                   # from the HV busbar into the transformer
                out[p.point_id] = w.tr.trafo_p_hv[:, k] if p.quantity == "P" else w.tr.trafo_q_hv[:, k]
        elif p.element_type == "bsp":
            k = w.load_col[p.element_ref]
            out[p.point_id] = w.ts.load_p[:, k] if p.quantity == "P" else w.ts.load_q[:, k]
        elif p.element_type == "generator":
            out[p.point_id] = -w.gen_p(p.element_ref)
        else:
            k = w.bus_col[p.element_ref]
            out[p.point_id] = w.tr.bus_vm[:, k] * float(p.voltage_kv)
    return out


def scada_month(w: World, month: str, points: pd.DataFrame, values: dict[str, np.ndarray]) -> pd.DataFrame | None:
    """Hourly SCADA rows for one month: the full month, the two sample days, or None."""
    if month in SCADA_MISSING_MONTHS:
        return None
    sel = w.month_mask(month)
    if month not in SCADA_FULL_MONTHS:
        pk, lo = w.sample_days(month)
        day = w.cal.hours.normalize()
        sel = sel & ((day == pd.Timestamp(pk)) | (day == pd.Timestamp(lo)))
    idx = np.where(sel)[0]
    rng = rng_for(w.seed, f"scada-{month}")
    stamps = w.cal.hours[idx].strftime("%Y-%m-%d %H:%M")
    frames = []
    for p in points.itertuples():
        v = values[p.point_id][idx]
        rel = 0.002 if p.quantity == "V" else 0.01
        noisy = v * (1 + rel * rng.standard_normal(len(idx)))
        if p.quantity in ("P", "Q"):
            noisy = noisy + 0.05 * rng.standard_normal(len(idx))  # a small absolute floor
        quality = np.full(len(idx), "good", dtype=object)
        bad = rng.random(len(idx)) < 0.001
        noisy = np.where(bad, 0.0, noisy)
        quality[bad] = "bad"
        frames.append(pd.DataFrame({"timestamp": stamps, "point_id": p.point_id, "value": np.round(noisy, 3),
                                    "unit": p.unit, "quality": quality}))
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values(["timestamp", "point_id"], kind="stable").reset_index(drop=True)


def breaker_rows(events: pd.DataFrame) -> pd.DataFrame:
    """Breaker open/close records for every event on a line or transformer."""
    rows = []
    for e in events.itertuples():
        if not isinstance(e.element_ref, str) or not e.element_ref:
            continue
        ss = e.substation if isinstance(e.substation, str) else None
        for t, state, why in ((e.start_at, "open", e.cause), (e.end_at, "closed", "Restored")):
            if pd.isna(t):
                continue
            rows.append({"timestamp": t, "substation": ss, "bay": e.element, "breaker_id": f"{e.element_ref}.CB1",
                         "element_ref": e.element_ref, "new_state": state, "reason": f"SYNTHETIC: {why}"})
    return pd.DataFrame(rows)


T04_ANSWERS = {
    "Q1": "SYNTHETIC: hourly averages, timestamped at the start of the hour (EAT).",
    "Q2": "SYNTHETIC: + = from the busbar into the bay, for every P and Q point.",
}
T05_ANSWERS = {
    "Q1": "SYNTHETIC: the Kawanda constraint (KAW-1) binds at N-1 in the evening peak.",
}
