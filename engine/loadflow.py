"""Run load flows that never crash a stage, and read their results into tidy tables.

Real network data often fails to converge on the first try (a bad tap, a far-off start
point, a weak tie). run_pf() therefore walks a retry ladder and, if the AC load flow still
fails, falls back to a DC load flow so a thermal estimate still exists. It never raises on
non-convergence: callers read PFResult.converged and PFResult.method instead.

The same functions serve the batch stages and the API's live trip, so keep them pure: a
pandapower net in, DataFrames out, no database.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.topology as top

log = logging.getLogger(__name__)

ELEMENT_RESULT_COLUMNS = ["element_type", "element_id", "p_from_mw", "q_from_mvar", "p_to_mw",
                          "q_to_mvar", "pl_mw", "ql_mvar", "i_ka", "loading_pct"]
BUS_RESULT_COLUMNS = ["bus_id", "vm_pu", "va_deg", "p_mw", "q_mvar"]


@dataclass
class PFResult:
    """Outcome of run_pf.

    converged: True only when an AC load flow converged.
    method: which step gave the results: 'ac-results', 'ac-dc', 'ac-flat', or 'dc' (a DC
        estimate after every AC step failed: flows only, no voltages or reactive power),
        or 'none' when even the DC load flow failed.
    message: what happened, for logs and results.case.note.
    """

    converged: bool
    method: str
    message: str = ""

    @property
    def has_results(self) -> bool:
        """True when the net's res_* tables hold usable results (AC or DC)."""
        return self.method != "none"


def has_previous_results(net) -> bool:
    """True when the net holds a finished AC solution that can seed the next one."""
    return (len(net.res_bus) == len(net.bus) and len(net.bus) > 0
            and bool(net.res_bus.vm_pu.notna().any()) and bool(net.get("converged", False)))


def try_ac(net, init: str, max_iteration: int) -> str | None:
    """Run one AC Newton-Raphson load flow. Returns None on success, else the error text."""
    try:
        pp.runpp(net, algorithm="nr", init=init, max_iteration=max_iteration,
                 calculate_voltage_angles=True, numba=False)
        return None if net.converged else "did not converge"
    except pp.LoadflowNotConverged:
        return "did not converge"
    except Exception as exc:  # singular matrix, bad data: we still want the next rung
        return f"{type(exc).__name__}: {exc}"


def run_pf(net, *, ladder=("results", "dc", "flat"), max_iteration: int = 30,
           flat_max_iteration: int | None = None) -> PFResult:
    """Solve the net, trying each start in the ladder, then a DC estimate.

    ladder: 'results' starts from the previous solution (fast for snapshot series; skipped
        when there is none), 'dc' starts from a DC solution, 'flat' from 1.0 pu with more
        iterations (flat_max_iteration, default twice max_iteration and at least 50).
    The net's res_* tables hold the results of whichever step succeeded.
    """
    flat_iter = flat_max_iteration or max(50, 2 * max_iteration)
    errors = []
    for init in ladder:
        if init == "results" and not has_previous_results(net):
            continue
        err = try_ac(net, init, flat_iter if init == "flat" else max_iteration)
        if err is None:
            note = f"AC converged from init={init}" + (f" after: {'; '.join(errors)}" if errors else "")
            return PFResult(True, f"ac-{init}", note)
        errors.append(f"init={init}: {err}")
    try:
        pp.rundcpp(net)
        msg = "AC failed (" + "; ".join(errors) + "); DC estimate: flows only"
        log.warning("load flow %s: %s", net.name, msg)
        return PFResult(False, "dc", msg)
    except Exception as exc:
        msg = "AC failed (" + "; ".join(errors) + f"); DC failed: {type(exc).__name__}: {exc}"
        log.warning("load flow %s: %s", net.name, msg)
        return PFResult(False, "none", msg)


def rate_scaled_loading(loading_pct: pd.Series, sn_mva: pd.Series, rate_mva: pd.Series) -> pd.Series:
    """pandapower measures transformer loading against sn_mva; re-base it on rate_mva (the
    chosen rating set) where a rating is known."""
    rate = pd.to_numeric(rate_mva, errors="coerce")
    factor = (sn_mva / rate).where(rate > 0, 1.0)
    return loading_pct * factor


def frame_rows(element_type: str, names: pd.Series, **cols) -> pd.DataFrame:
    """Build result rows for one element table in the shared column order."""
    out = pd.DataFrame({"element_type": element_type, "element_id": names.astype(str).values})
    for c in ELEMENT_RESULT_COLUMNS[2:]:
        out[c] = np.asarray(cols[c], dtype=float) if c in cols else np.nan
    return out


def element_results(net) -> pd.DataFrame:
    """Line, transformer and three-winding transformer results in one long table.

    Columns are those of results.element_result minus run_id and case_key. For transformers
    'from' is the HV side and 'to' the LV side (for 3-winding units, MV plus LV), and
    loading_pct is against rate_mva, the chosen rating set. Out-of-service or islanded
    elements carry NaN or zero, as pandapower leaves them.
    """
    parts = []
    if len(net.line) and len(net.res_line) == len(net.line):
        r = net.res_line.reindex(net.line.index)
        # A line with no rating is built with max_i_ka = 0, and pandapower then reports an
        # infinite loading. Report it as unknown (NaN) instead, so it never looks overloaded.
        loading = r.loading_percent.where(net.line.max_i_ka > 0)
        parts.append(frame_rows("line", net.line["name"], p_from_mw=r.p_from_mw, q_from_mvar=r.q_from_mvar,
                                p_to_mw=r.p_to_mw, q_to_mvar=r.q_to_mvar, pl_mw=r.pl_mw,
                                ql_mvar=r.ql_mvar, i_ka=r.i_ka, loading_pct=loading))
    if len(net.trafo) and len(net.res_trafo) == len(net.trafo):
        t, r = net.trafo, net.res_trafo.reindex(net.trafo.index)
        rate = t["rate_mva"] if "rate_mva" in t else t.sn_mva
        parts.append(frame_rows("trafo", t["name"], p_from_mw=r.p_hv_mw, q_from_mvar=r.q_hv_mvar,
                                p_to_mw=r.p_lv_mw, q_to_mvar=r.q_lv_mvar, pl_mw=r.pl_mw,
                                ql_mvar=r.ql_mvar, i_ka=r.i_hv_ka,
                                loading_pct=rate_scaled_loading(r.loading_percent, t.sn_mva, rate)))
    if len(net.trafo3w) and len(net.res_trafo3w) == len(net.trafo3w):
        t, r = net.trafo3w, net.res_trafo3w.reindex(net.trafo3w.index)
        rate = t["rate_mva"] if "rate_mva" in t else t.sn_hv_mva
        parts.append(frame_rows("trafo3w", t["name"], p_from_mw=r.p_hv_mw, q_from_mvar=r.q_hv_mvar,
                                p_to_mw=r.p_mv_mw + r.p_lv_mw, q_to_mvar=r.q_mv_mvar + r.q_lv_mvar,
                                pl_mw=r.pl_mw, ql_mvar=r.ql_mvar, i_ka=r.i_hv_ka,
                                loading_pct=rate_scaled_loading(r.loading_percent, t.sn_hv_mva, rate)))
    if not parts:
        return pd.DataFrame(columns=ELEMENT_RESULT_COLUMNS)
    return pd.concat(parts, ignore_index=True)[ELEMENT_RESULT_COLUMNS]


def bus_results(net) -> pd.DataFrame:
    """Bus voltage, angle and net injection, keyed by bus_id (the T01 id).
    Islanded buses have NaN voltage."""
    if len(net.res_bus) != len(net.bus):
        return pd.DataFrame(columns=BUS_RESULT_COLUMNS)
    r = net.res_bus.reindex(net.bus.index)
    return pd.DataFrame({"bus_id": net.bus["name"].astype(str).values,
                         "vm_pu": r.vm_pu.astype(float).values,
                         "va_deg": r.va_degree.astype(float).values,
                         "p_mw": r.p_mw.astype(float).values,
                         "q_mvar": r.q_mvar.astype(float).values})


def slack_buses(net) -> set:
    """Buses that hold a slack: in-service ext_grids and slack generators."""
    eg = net.ext_grid[net.ext_grid.in_service].bus
    sg = net.gen[net.gen.in_service & net.gen.slack].bus
    return set(eg) | set(sg)


def islanded_buses(net) -> set:
    """In-service buses with no path to a slack (open switches and out-of-service
    branches respected). This is topology only, so it works without a load flow."""
    unsupplied = top.unsupplied_buses(net, slacks=slack_buses(net), respect_switches=True)
    return set(unsupplied) | set(net.bus.index[~net.bus.in_service])


def islanded_load_mw(net) -> float:
    """Load (MW, after scaling) on buses cut off from every slack: the loss of supply."""
    if net.load.empty:
        return 0.0
    cut = islanded_buses(net)
    loads = net.load[net.load.in_service & net.load.bus.isin(cut)]
    total = float((loads.p_mw * loads.scaling).sum())
    return 0.0 if math.isnan(total) else total


def solved_sum(res: pd.DataFrame, n: int) -> float | None:
    """Sum of p_mw in a result table, or None when it does not match the element table."""
    if n == 0:
        return 0.0
    if len(res) != n:
        return None
    return float(res.p_mw.fillna(0.0).sum())


def totals(net) -> tuple[float, float]:
    """Total in-service load and generation in MW.

    Generation is the solved output (slack included) when results exist, otherwise the
    set-points without the slack.
    """
    load = net.load[net.load.in_service]
    total_load = float((load.p_mw * load.scaling).sum())
    solved = [solved_sum(net[f"res_{t}"], len(net[t])) for t in ("ext_grid", "gen", "sgen")]
    if all(s is not None for s in solved) and len(net.res_bus) == len(net.bus):
        return total_load, float(sum(solved))
    set_points = 0.0
    for t in ("gen", "sgen"):
        g = net[t][net[t].in_service]
        set_points += float((g.p_mw * g.scaling).sum())
    return total_load, set_points
