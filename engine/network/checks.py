"""Sanity checks on a built network, before anyone trusts its load flows.

Converted models carry mistakes that a load flow either hides or turns into a cryptic
non-convergence: an island with no source, a zero-impedance branch, a line typed in ohms
instead of ohms per km, a 132 kV transformer winding on a 33 kV bus. check_net() lists
them in plain words so a trainee can fix the source data, not the symptoms.
"""

from __future__ import annotations

import math

import networkx as nx
import pandas as pd
import pandapower.topology as top

CHECK_COLUMNS = ["severity", "element_type", "element_id", "message"]


def issue(severity: str, element_type: str, element_id, message: str) -> dict:
    """One row of check output. severity is error, warning or info."""
    return {"severity": severity, "element_type": element_type, "element_id": str(element_id),
            "message": message}


def check_islands(net) -> list[dict]:
    """Groups of in-service buses with no slack. Load there is not supplied in any load flow."""
    out = []
    graph = top.create_nxgraph(net, respect_switches=True, include_out_of_service=False)
    slacks = set(net.ext_grid[net.ext_grid.in_service].bus) | set(net.gen[net.gen.in_service & net.gen.slack].bus)
    components = list(nx.connected_components(graph))
    for comp in components:
        if comp & slacks:
            continue
        names = sorted(str(net.bus.at[b, "name"]) for b in comp)
        load = net.load[net.load.in_service & net.load.bus.isin(comp)]
        mw = float((load.p_mw * load.scaling).sum())
        shown = ", ".join(names[:6]) + (" ..." if len(names) > 6 else "")
        out.append(issue("warning", "bus", names[0],
                         f"island of {len(names)} bus(es) with no slack ({shown}); load {mw:.1f} MW unsupplied"))
    if not slacks:
        out.append(issue("error", "network", net.name, "no slack: add a slack generator or boundary"))
    elif len(components) > 1:
        out.append(issue("info", "network", net.name, f"{len(components)} separate electrical islands"))
    return out


def check_line_impedance(net, xr_min: float, xr_max: float) -> list[dict]:
    """Zero or negative R, X or length, and X/R outside the usual overhead-line range."""
    out = []
    for row in net.line.itertuples():
        lid = row.name
        if not row.length_km > 0:
            out.append(issue("error", "line", lid, f"length {row.length_km} km is not positive"))
        if row.x_ohm_per_km <= 0 or math.isnan(row.x_ohm_per_km):
            out.append(issue("error", "line", lid, f"reactance {row.x_ohm_per_km} ohm/km is not positive"))
        if row.r_ohm_per_km < 0 or math.isnan(row.r_ohm_per_km):
            out.append(issue("error", "line", lid, f"resistance {row.r_ohm_per_km} ohm/km is negative or blank"))
        elif row.r_ohm_per_km == 0:
            out.append(issue("warning", "line", lid, "resistance is zero, so the line has no losses"))
        elif row.x_ohm_per_km > 0:
            xr = row.x_ohm_per_km / row.r_ohm_per_km
            if not xr_min <= xr <= xr_max:
                out.append(issue("warning", "line", lid,
                                 f"X/R {xr:.2f} outside {xr_min}-{xr_max}; check R and X units"))
    return out


def check_trafo_impedance(net) -> list[dict]:
    """Transformer vk must be positive and vkr between 0 and vk."""
    out = []
    for row in net.trafo.itertuples():
        if not row.vk_percent > 0:
            out.append(issue("error", "trafo", row.name, f"vk {row.vk_percent} % is not positive"))
        elif row.vkr_percent < 0 or row.vkr_percent >= row.vk_percent:
            out.append(issue("error", "trafo", row.name,
                             f"vkr {row.vkr_percent} % must be between 0 and vk {row.vk_percent} %"))
        if not row.sn_mva > 0:
            out.append(issue("error", "trafo", row.name, f"rated power {row.sn_mva} MVA is not positive"))
    for row in net.trafo3w.itertuples():
        for w in ("hv", "mv", "lv"):
            if not getattr(row, f"vk_{w}_percent") > 0:
                out.append(issue("error", "trafo3w", row.name, f"vk_{w} is not positive"))
    return out


def check_ratings(net) -> list[dict]:
    """Lines and transformers without a usable rating cannot report loading."""
    out = []
    for row in net.line.itertuples():
        rate = getattr(row, "rate_mva", math.nan)
        if not (row.max_i_ka > 0) or rate is None or not (float(rate) > 0):
            out.append(issue("warning", "line", row.name, "no rating: loading cannot be reported"))
    for table in ("trafo", "trafo3w"):
        for row in net[table].itertuples():
            rate = getattr(row, "rate_mva", math.nan)
            if rate is None or not (float(rate) > 0):
                out.append(issue("warning", table, row.name, "no rating: loading uses the nameplate MVA"))
    return out


def connected_buses(net) -> set:
    """Buses touched by at least one branch or bus-bus switch."""
    used = set(net.line.from_bus) | set(net.line.to_bus)
    used |= set(net.trafo.hv_bus) | set(net.trafo.lv_bus)
    used |= set(net.trafo3w.hv_bus) | set(net.trafo3w.mv_bus) | set(net.trafo3w.lv_bus)
    bb = net.switch[net.switch.et == "b"]
    used |= set(bb.bus) | set(bb.element)
    if "impedance" in net:
        used |= set(net.impedance.from_bus) | set(net.impedance.to_bus)
    return used


def check_unconnected(net) -> list[dict]:
    """Buses with no line, transformer or bus switch at all."""
    used = connected_buses(net)
    return [issue("warning", "bus", net.bus.at[b, "name"], "bus has no connection to any branch")
            for b in net.bus.index if b not in used and len(net.bus) > 1]


def check_voltages(net, tolerance: float) -> list[dict]:
    """Transformer winding kV that do not match their buses, and lines joining two voltages."""
    out = []
    vn = net.bus.vn_kv
    windings = [("trafo", ("hv", "lv")), ("trafo3w", ("hv", "mv", "lv"))]
    for table, sides in windings:
        for row in net[table].itertuples():
            for side in sides:
                bus_kv = vn.at[getattr(row, f"{side}_bus")]
                wind_kv = getattr(row, f"vn_{side}_kv")
                if bus_kv > 0 and abs(wind_kv - bus_kv) / bus_kv > tolerance:
                    out.append(issue("error", table, row.name,
                                     f"{side.upper()} winding {wind_kv} kV on a {bus_kv} kV bus"))
    for row in net.line.itertuples():
        a, b = vn.at[row.from_bus], vn.at[row.to_bus]
        if not math.isclose(a, b, rel_tol=1e-3):
            out.append(issue("error", "line", row.name, f"ends at different voltages: {a} kV and {b} kV"))
    return out


def check_build_warnings(net) -> list[dict]:
    """Problems noted while building (skipped rows, typical values used)."""
    return [issue("warning", "build", net.name, w) for w in net.get("atlas_warnings", []) or []]


def check_net(net, *, xr_min: float = 1.5, xr_max: float = 15.0,
              trafo_kv_tolerance: float = 0.10) -> pd.DataFrame:
    """Run every check and return DataFrame(severity, element_type, element_id, message).

    errors: the model is wrong and results on it are not trustworthy.
    warnings: worth a look; often fine for cables or equivalents.
    info: facts about the model, such as the number of islands.
    """
    rows = (check_build_warnings(net) + check_islands(net) + check_line_impedance(net, xr_min, xr_max)
            + check_trafo_impedance(net) + check_ratings(net) + check_unconnected(net)
            + check_voltages(net, trafo_kv_tolerance))
    return pd.DataFrame(rows, columns=CHECK_COLUMNS)
