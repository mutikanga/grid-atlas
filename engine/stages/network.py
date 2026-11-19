"""Stage 'network': register the model's elements and prove it solves.

Writes results.element and results.bus (the register every later stage and the map join
on), logs the model checks, and runs one base-case load flow as a sanity check, stored in
results.case (kind 'base') with its element and bus results. All the numeric work is in
engine.network and engine.loadflow; this file only reads ctx and writes tables.
"""

from __future__ import annotations

import pandas as pd

from engine.loadflow import bus_results, element_results, islanded_load_mw, run_pf, totals
from engine.network import bus_register, check_net, element_register
from engine.network.build import get_table

BASE_CASE_KEY = "base"
# The [checks] settings check_net() accepts; any other key in the config is ignored.
CHECK_SETTINGS = ("xr_min", "xr_max", "trafo_kv_tolerance")


def log_checks(ctx, issues: pd.DataFrame) -> None:
    """Log check results: each error and warning, then a one-line count."""
    for row in issues.itertuples():
        if row.severity in ("error", "warning"):
            ctx.log.warning("check %s %s %s: %s", row.severity, row.element_type, row.element_id, row.message)
    counts = issues.severity.value_counts().to_dict() if len(issues) else {}
    ctx.log.info("network checks: %s", counts or "no issues")


def case_hour(inputs, case_id: str):
    """The hour the case represents, from net_case.case_hour, or None."""
    case = get_table(getattr(inputs, "net_tables", {}) or {}, "net_case")
    if case.empty or "case_hour" not in case.columns:
        return None
    rows = case[case["case_id"].astype(str) == str(case_id)] if "case_id" in case.columns else case
    hour = pd.to_numeric(rows["case_hour"], errors="coerce").iloc[0] if len(rows) else None
    # results.case.hour must be 0-23; a 1-24 style or mistyped hour is left blank, not fatal.
    if hour is None or pd.isna(hour) or not 0 <= hour <= 23:
        return None
    return int(hour)


def base_case_row(net, result, inputs, case_id: str) -> pd.DataFrame:
    """The results.case row for the sanity load flow."""
    total_load, total_gen = totals(net)
    note = result.message
    lost = islanded_load_mw(net)
    if lost > 0:
        note += f"; {lost:.1f} MW on islanded buses"
    return pd.DataFrame([{
        "case_key": BASE_CASE_KEY, "kind": "base", "month": None, "day_type": None,
        "hour": case_hour(inputs, case_id), "weight_h": None, "scenario": "base",
        "total_load_mw": total_load, "total_gen_mw": total_gen, "converged": result.converged,
        "method": result.method, "profile_source": "model case", "note": f"case {case_id}: {note}",
    }])


def run(ctx) -> None:
    """Register the network, check it, and solve the model's own case once."""
    inputs = ctx.inputs
    net = ctx.net()
    case_id = inputs.case_id
    ctx.log.info("network: case %s, %d buses, %d lines, %d transformers", case_id, len(net.bus),
                 len(net.line), len(net.trafo) + len(net.trafo3w))

    ctx.write("element", element_register(net))
    ctx.write("bus", bus_register(net))

    checks_cfg = (ctx.cfg.get("network", {}) or {}).get("checks", {}) or {}
    log_checks(ctx, check_net(net, **{k: float(v) for k, v in checks_cfg.items() if k in CHECK_SETTINGS}))

    lf_cfg = (ctx.cfg.get("network", {}) or {}).get("loadflow", {}) or {}
    result = run_pf(net, ladder=tuple(lf_cfg.get("ladder", ("results", "dc", "flat"))),
                    max_iteration=int(lf_cfg.get("max_iteration", 30)),
                    flat_max_iteration=lf_cfg.get("flat_max_iteration"))
    ctx.log.info("base case: converged=%s method=%s %s", result.converged, result.method, result.message)

    ctx.write("case", base_case_row(net, result, inputs, case_id))
    if result.has_results:
        er = element_results(net)
        er.insert(0, "case_key", BASE_CASE_KEY)
        ctx.write("element_result", er)
        br = bus_results(net)
        br.insert(0, "case_key", BASE_CASE_KEY)
        ctx.write("bus_result", br)
