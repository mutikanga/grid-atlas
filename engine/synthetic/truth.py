"""Simulate the synthetic year hour by hour with the truth model (R at 60 C).

About 9,500 AC load flows. pandapower's ``recycle`` option reuses the admittance
matrix between hours (only injections change), which makes each run a few ms.
The 5-day outage of Kawanda - Kampala North runs on a separate copy of the net,
because recycling assumes the topology does not change.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandapower as pp

from engine.synthetic.network import Network, TruthNet, build_truth_net, central_element_mask
from engine.synthetic.timeseries import OUTAGE_END, OUTAGE_LINE, OUTAGE_START, TruthSeries

RECYCLE = dict(trafo=False, gen=True, bus_pq=True)


@dataclass
class TruthResult:
    """Hourly results of the truth simulation (arrays are hours x elements, in net row order)."""

    tn: TruthNet
    line_names: list[str]
    trafo_names: list[str]
    bus_names: list[str]
    line_p_from: np.ndarray
    line_q_from: np.ndarray
    line_p_to: np.ndarray
    line_q_to: np.ndarray
    line_pl: np.ndarray
    line_loading: np.ndarray
    trafo_p_hv: np.ndarray
    trafo_q_hv: np.ndarray
    trafo_p_lv: np.ndarray
    trafo_q_lv: np.ndarray
    trafo_pl: np.ndarray
    trafo_loading: np.ndarray
    bus_vm: np.ndarray
    slack_p: np.ndarray
    central_loss: np.ndarray     # MW per hour inside the Central meter perimeter
    total_loss: np.ndarray       # MW per hour, whole model
    outage_hours: np.ndarray     # bool per hour: OUTAGE_LINE out of service


def _apply_hour(tn: TruthNet, ts: TruthSeries, t: int, load_rows: np.ndarray, gen_rows: list) -> None:
    """Write hour t's injections into the net (vectorised assignment)."""
    net = tn.net
    p = net.load["p_mw"].to_numpy(copy=True)
    q = net.load["q_mvar"].to_numpy(copy=True)
    p[load_rows] = ts.load_p[t]
    q[load_rows] = ts.load_q[t]
    net.load["p_mw"] = p
    net.load["q_mvar"] = q
    gp = net.gen["p_mw"].to_numpy(copy=True)
    sp = net.sgen["p_mw"].to_numpy(copy=True)
    for k, (table, row) in enumerate(gen_rows):
        if table == "gen":
            gp[row] = ts.gen_p[t, k]
        else:
            sp[row] = ts.gen_p[t, k]
    net.gen["p_mw"] = gp
    net.sgen["p_mw"] = sp


def simulate(nw: Network, ts: TruthSeries, *, r_temp_c: float = 60.0, hours: np.ndarray | None = None,
             with_outage: bool = True) -> TruthResult:
    """Run the truth load flow for every hour (or only the given hour positions).

    with_outage=False ignores the planned outage (the engine's model does not know about it).

    Raises RuntimeError if any hour fails to converge: the synthetic world must be solvable.
    """
    tn = build_truth_net(nw, r_temp_c=r_temp_c)
    out_tn = copy.deepcopy(tn)
    out_tn.net.line.at[out_tn.line[OUTAGE_LINE], "in_service"] = False

    load_rows = np.array([tn.load[i] for i in ts.load_ids])
    gen_rows = [("gen", tn.gen[g]) if g in tn.gen else ("sgen", tn.sgen[g]) for g in ts.gen_ids]
    idx = np.arange(len(ts.cal.hours)) if hours is None else np.asarray(hours)
    stamps = ts.cal.hours
    outage = (stamps >= pd.Timestamp(OUTAGE_START)) & (stamps < pd.Timestamp(OUTAGE_END)) & with_outage

    n, nl, nt, nb = len(idx), len(tn.net.line), len(tn.net.trafo), len(tn.net.bus)
    arrays = {k: np.zeros((n, nl)) for k in ("lpf", "lqf", "lpt", "lqt", "lpl", "lld")}
    arrays.update({k: np.zeros((n, nt)) for k in ("tph", "tqh", "tpl_", "tql", "tpl", "tld")})
    vm = np.zeros((n, nb))
    slack = np.zeros(n)
    first = {id(tn): True, id(out_tn): True}

    for k, t in enumerate(idx):
        cur = out_tn if outage[t] else tn
        _apply_hour(cur, ts, t, load_rows, gen_rows)
        if first[id(cur)]:
            pp.runpp(cur.net, numba=False, init="flat")
            first[id(cur)] = False
        else:
            pp.runpp(cur.net, numba=False, init="results", recycle=RECYCLE)
        if not cur.net.converged:
            raise RuntimeError(f"truth load flow did not converge at {stamps[t]}")
        rl, rt = cur.net.res_line, cur.net.res_trafo
        arrays["lpf"][k] = rl["p_from_mw"].to_numpy()
        arrays["lqf"][k] = rl["q_from_mvar"].to_numpy()
        arrays["lpt"][k] = rl["p_to_mw"].to_numpy()
        arrays["lqt"][k] = rl["q_to_mvar"].to_numpy()
        arrays["lpl"][k] = rl["pl_mw"].to_numpy()
        arrays["lld"][k] = rl["loading_percent"].to_numpy()
        arrays["tph"][k] = rt["p_hv_mw"].to_numpy()
        arrays["tqh"][k] = rt["q_hv_mvar"].to_numpy()
        arrays["tpl_"][k] = rt["p_lv_mw"].to_numpy()
        arrays["tql"][k] = rt["q_lv_mvar"].to_numpy()
        arrays["tpl"][k] = rt["pl_mw"].to_numpy()
        arrays["tld"][k] = rt["loading_percent"].to_numpy()
        vm[k] = cur.net.res_bus["vm_pu"].to_numpy()
        slack[k] = cur.net.res_ext_grid["p_mw"].sum()
    for key in arrays:
        arrays[key] = np.nan_to_num(arrays[key])

    lmask, tmask = central_element_mask(nw, tn)
    central = arrays["lpl"][:, lmask].sum(axis=1) + arrays["tpl"][:, tmask].sum(axis=1)
    total = arrays["lpl"].sum(axis=1) + arrays["tpl"].sum(axis=1)
    return TruthResult(
        tn=tn,
        line_names=tn.net.line["name"].tolist(),
        trafo_names=tn.net.trafo["name"].tolist(),
        bus_names=tn.net.bus["name"].tolist(),
        line_p_from=arrays["lpf"], line_q_from=arrays["lqf"], line_p_to=arrays["lpt"], line_q_to=arrays["lqt"],
        line_pl=arrays["lpl"], line_loading=arrays["lld"],
        trafo_p_hv=arrays["tph"], trafo_q_hv=arrays["tqh"], trafo_p_lv=arrays["tpl_"], trafo_q_lv=arrays["tql"],
        trafo_pl=arrays["tpl"], trafo_loading=arrays["tld"],
        bus_vm=vm, slack_p=slack, central_loss=central, total_loss=total, outage_hours=outage[idx],
    )


def snapshot_net(nw: Network, ts: TruthSeries, t: int, *, r_temp_c: float = 60.0,
                 include_planned: bool = False) -> TruthNet:
    """A solved truth net for one hour position t (used for the peak case, N-1 checks and T01)."""
    tn = build_truth_net(nw, r_temp_c=r_temp_c, include_planned=include_planned)
    load_rows = np.array([tn.load[i] for i in ts.load_ids])
    gen_rows = [("gen", tn.gen[g]) if g in tn.gen else ("sgen", tn.sgen[g]) for g in ts.gen_ids]
    _apply_hour(tn, ts, t, load_rows, gen_rows)
    pp.runpp(tn.net, numba=False)
    return tn


def n1_loading(tn: TruthNet, trip: tuple[str, str]) -> tuple[bool, pd.Series, pd.Series, float]:
    """Trip one element ('line' or 'trafo', id) on a copy and re-solve.

    Returns (converged, line loading % by id, trafo loading % by id, islanded load MW).
    Islanded load is the load on buses left without a voltage solution.
    """
    net = copy.deepcopy(tn.net)
    kind, eid = trip
    table = net.line if kind == "line" else net.trafo
    table.at[(tn.line if kind == "line" else tn.trafo)[eid], "in_service"] = False
    try:
        pp.runpp(net, numba=False)
    except pp.LoadflowNotConverged:
        return False, pd.Series(dtype=float), pd.Series(dtype=float), float("nan")
    dead = net.res_bus["vm_pu"].isna()
    islanded = float(net.load.loc[net.load["bus"].map(dead) & net.load["in_service"], "p_mw"].sum())
    lines = pd.Series(net.res_line["loading_percent"].to_numpy(), index=net.line["name"])
    trafos = pd.Series(net.res_trafo["loading_percent"].to_numpy(), index=net.trafo["name"])
    return True, lines, trafos, islanded
