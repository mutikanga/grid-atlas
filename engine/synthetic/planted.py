"""Checks of the planted outcomes on the truth model, recorded in truth.json.

- N-1 at each month's peak hour: KAW-MUT circuit trips and Kawanda 220/132 kV unit trips.
- KAP is radial: tripping Kapeeka - Kawanda islands Kapeeka's load.
- A miniature Kawanda load sweep that says which element type binds first.
"""
from __future__ import annotations

import numpy as np
import pandapower as pp

from engine.synthetic.network import CENTRAL
from engine.synthetic.timeseries import MONTHS
from engine.synthetic.truth import n1_loading, snapshot_net
from engine.synthetic.world import World, ss_name

TRIPS = [  # (kind, tripped element, watched element)
    ("line", "L-KAW-MUT-132-1", "L-KAW-MUT-132-2"),
    ("line", "L-KAW-MUT-132-2", "L-KAW-MUT-132-1"),
    ("trafo", "T-KAW-1", "T-KAW-2"),
    ("trafo", "T-KAW-2", "T-KAW-1"),
]
RADIAL_TRIP = ("line", "L-KAP-KAW-132-1")


def n1_by_month(w: World) -> dict[str, dict]:
    """Post-contingency loading of the watched element at every month's peak hour."""
    out = {}
    for month in MONTHS:
        t = w.peak_hour(month)
        tn = snapshot_net(w.nw, w.ts, t)
        base_l = dict(zip(tn.net.line["name"], tn.net.res_line["loading_percent"]))
        base_t = dict(zip(tn.net.trafo["name"], tn.net.res_trafo["loading_percent"]))
        rec = {"peak_at": w.cal.hours[t].strftime("%Y-%m-%d %H:%M"), "trips": {}}
        for kind, trip, watch in TRIPS:
            ok, lines, trafos, _ = n1_loading(tn, (kind, trip))
            post = (lines if kind == "line" else trafos)[watch]
            base = (base_l if kind == "line" else base_t)[watch]
            rec["trips"][trip] = {"watched": watch, "base_pct": round(float(base), 1), "post_pct": round(float(post), 1),
                                  "converged": ok}
        ok, _, _, isl = n1_loading(tn, RADIAL_TRIP)
        rec["radial_islanded_mw"] = round(isl, 2)
        rec["kap_load_mw"] = round(float(w.ts.load_p[t, w.load_col["D-KAP-1"]]), 2)
        out[month] = rec
    return out


def kawanda_elements(w: World) -> list[tuple[str, str]]:
    """Kawanda's transformers (H1) and the lines ending at Kawanda (H2), existing only."""
    trafos = w.nw.trafos
    lines = w.nw.lines
    k = [("trafo", t) for t in trafos.loc[(trafos.ss_code == "KAW") & (trafos.status == "existing"), "trafo_id"]]
    k += [("line", l) for l in lines.loc[((lines.ss_a == "KAW") | (lines.ss_b == "KAW")) & (lines.status == "existing"), "line_id"]]
    return k


def _worst_k(net, kset) -> tuple[float, str]:
    """Highest loading % among the Kawanda elements, and which one."""
    worst, which = -1.0, ""
    for kind, eid in kset:
        tab, res = (net.line, net.res_line) if kind == "line" else (net.trafo, net.res_trafo)
        row = tab.index[tab["name"] == eid][0]
        if not tab.at[row, "in_service"]:
            continue
        v = float(res.at[row, "loading_percent"])
        if v > worst:
            worst, which = v, eid
    return worst, which


def kawanda_sweep(w: World, month: str = "2026-09") -> dict:
    """Scale Central loads by lambda and find where a Kawanda element first exceeds 100 % under N-1.

    A miniature of the engine's sweep (which searches lambda >= 1); here lambda may go below 1
    because the planted overloads already exist at the peak. The binding element's type
    decides the expected verdict: transformer -> H1, line -> H2.
    """
    t = w.peak_hour(month)
    tn = snapshot_net(w.nw, w.ts, t)
    kset = kawanda_elements(w)
    p0 = tn.net.load["p_mw"].to_numpy(copy=True)
    q0 = tn.net.load["q_mvar"].to_numpy(copy=True)
    central = tn.net.load["name"].isin([f"D-{c}-1" for c in CENTRAL]).to_numpy()

    def check(lam: float) -> tuple[bool, str, str]:
        net = tn.net
        net.load["p_mw"] = np.where(central, p0 * lam, p0)
        net.load["q_mvar"] = np.where(central, q0 * lam, q0)
        pp.runpp(net, numba=False)
        worst, which = _worst_k(net, kset)
        if worst > 100:
            return False, which, "base"
        for kind, eid in kset:
            tab = net.line if kind == "line" else net.trafo
            row = tab.index[tab["name"] == eid][0]
            tab.at[row, "in_service"] = False
            try:
                pp.runpp(net, numba=False)
                worst, which = _worst_k(net, kset)
            except pp.LoadflowNotConverged:
                worst, which = 999.0, eid
            tab.at[row, "in_service"] = True
            if worst > 100:
                return False, which, eid
        return True, "", ""

    lo, hi = 0.3, 1.5
    binding = ("", "")
    for _ in range(14):
        mid = (lo + hi) / 2
        ok, el, cont = check(mid)
        if ok:
            lo = mid
        else:
            hi, binding = mid, (el, cont)
    net = tn.net
    net.load["p_mw"], net.load["q_mvar"] = p0, q0
    el = binding[0]
    hyp = "H1_transformers" if el.startswith("T-") else "H2_lines"
    return {"month": month, "lambda_star": round(lo, 3), "binding_element": el, "binding_contingency": binding[1],
            "expected_binding_hypothesis": hyp,
            "note": "Miniature sweep on the truth model (60 C); lambda below 1 means the limit is already exceeded at the peak."}


def t13_contingency_rows(w: World) -> list[dict]:
    """Planning-style benchmark violations at the SYNTH-PEAK hour (only real violations are listed)."""
    t = w.peak_hour("2026-09")
    tn = snapshot_net(w.nw, w.ts, t)
    base_l = dict(zip(tn.net.line["name"], tn.net.res_line["loading_percent"]))
    base_t = dict(zip(tn.net.trafo["name"], tn.net.res_trafo["loading_percent"]))
    rows = []
    title = {"L-KAW-MUT-132-1": "Kawanda - Mutundwe 132 kV circuit 1", "L-KAW-MUT-132-2": "Kawanda - Mutundwe 132 kV circuit 2",
             "T-KAW-1": "Kawanda transformer 1 220/132 kV", "T-KAW-2": "Kawanda transformer 2 220/132 kV"}
    for kind, trip, watch in TRIPS:
        ok, lines, trafos, _ = n1_loading(tn, (kind, trip))
        post = float((lines if kind == "line" else trafos)[watch])
        if post <= 100:
            continue
        base = float((base_l if kind == "line" else base_t)[watch])
        rows.append({"contingency": title[trip], "contingency_ref": trip, "violation_type": "overload",
                     "element": title[watch], "element_ref": watch, "base_value": round(base, 1),
                     "value": round(post, 1), "limit": 100.0, "value_unit": "percent", "rating_basis": "continuous",
                     "mitigation": "SP-01" if kind == "trafo" else "SP-02",
                     "remark": "SYNTHETIC benchmark (truth model at 60 C)"})
    ok, _, _, isl = n1_loading(tn, RADIAL_TRIP)
    rows.append({"contingency": "Kapeeka - Kawanda 132 kV line", "contingency_ref": RADIAL_TRIP[1],
                 "violation_type": "loss_of_supply", "element": ss_name("KAP"), "element_ref": "KAP-33-1",
                 "base_value": None, "value": round(isl, 1), "limit": 0.0, "value_unit": "MW",
                 "rating_basis": None, "mitigation": None, "remark": "SYNTHETIC: radial supply"})
    return rows
