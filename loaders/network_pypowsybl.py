"""Convert a PSS/E RAW (v33/v35), CGMES or PowerFactory DGS case into T01-shaped tables.

pandapower has no PSS/E reader, so native cases go through pypowsybl: it reads the file
into its IIDM model and hands back pandas DataFrames, which this module maps onto the
T01 columns (templates/spec/T01_network_model.toml). The result goes through the same
builder as every other network source.

pypowsybl publishes Linux wheels for x86_64 only. It is installed in the amd64 server
image and NOT in the arm64 development image, so it is imported lazily and a clear error
is raised when it is missing. This module was written from the pypowsybl documentation
and has not been run on the development Mac: test it on the server image first
(docs/dev/implementation-design.md section 5, "Validation of any converted model").

Conversion rules:
- Ohm and siemens values become per-km values on a notional 1 km length (IIDM has no line
  length); the real length comes from the GIS or Planning, and the notes say so.
- Transformer r, x, g, b (IIDM: in ohms and siemens at side 2) become vk %, vkr %, pfe kW
  and i0 % on the rated power. Taps are fixed at the case position.
- Permanent current limits become continuous MVA ratings (sqrt(3) * kV * A / 1000); the
  longest temporary limit becomes the emergency rating.
- Branches with an impedance below LOW_Z_PU (on 100 MVA) become closed bus-bus switches.
"""

from __future__ import annotations

import math
import platform
from pathlib import Path

import pandas as pd

LOW_Z_PU = 1e-4
BASE_MVA = 100.0
TECHNOLOGY = {"HYDRO": "hydro", "THERMAL": "thermal", "SOLAR": "solar", "WIND": "wind",
              "NUCLEAR": "other", "OTHER": "other"}


def import_pypowsybl():
    """Import pypowsybl.network, or raise a clear error where it is not installed."""
    try:
        import pypowsybl.network as pn  # noqa: PLC0415 - optional, amd64-only dependency
    except ImportError as exc:
        machine = platform.machine()
        raise RuntimeError(
            "pypowsybl is not installed in this image "
            f"(machine {machine}). It ships Linux x86_64 wheels only, so PSS/E, CGMES and DGS "
            "conversion runs in the amd64 server image. On Apple Silicon, run the conversion "
            "on the server, or ask Planning for the T01 workbook instead.") from exc
    return pn


def yn(flag) -> str:
    """Boolean to the T01 'Y'/'N'."""
    return "Y" if bool(flag) else "N"


def fnum(value, default: float = math.nan) -> float:
    """value as a float, or the default when blank or NaN."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(f) else f


def first_col(df: pd.DataFrame, *names: str) -> pd.Series:
    """The first of the named columns present in df (pypowsybl versions differ slightly)."""
    for n in names:
        if n in df.columns:
            return df[n]
    return pd.Series([None] * len(df), index=df.index, dtype=object)


# ---------------------------------------------------------------------------
# Buses and substations
# ---------------------------------------------------------------------------

def bus_frame(net, case_id: str) -> tuple[pd.DataFrame, dict[str, float]]:
    """net_bus rows from the bus-breaker view, plus a map voltage_level_id -> nominal kV."""
    vls = net.get_voltage_levels()
    subs = net.get_substations()
    nominal = vls["nominal_v"].astype(float).to_dict()
    sub_name = {sid: (row.get("name") or sid) for sid, row in subs.to_dict("index").items()}
    buses = net.get_bus_breaker_view_buses()
    rows = []
    for bid, b in buses.iterrows():
        vl = b["voltage_level_id"]
        vlrow = vls.loc[vl]
        sid = vlrow.get("substation_id")
        rows.append({
            "case_id": case_id, "bus_id": str(bid), "name": b.get("name") or str(bid),
            "substation": sub_name.get(sid) or vlrow.get("name") or str(bid), "vn_kv": float(vlrow["nominal_v"]),
            # Always in service: an unsolved case (a CGMES file without its SV profile) has
            # no voltages at all, and treating that as "dead" would switch off every bus.
            # Disconnected equipment is out of service through its own connected flags.
            "zone": None, "in_service": "Y",
            "v_min_pu": fnum(vlrow.get("low_voltage_limit")) / float(vlrow["nominal_v"]),
            "v_max_pu": fnum(vlrow.get("high_voltage_limit")) / float(vlrow["nominal_v"]),
        })
    return pd.DataFrame(rows), nominal


def solved_buses(net, case_id: str, nominal: dict[str, float]) -> pd.DataFrame:
    """The case's own solution (net_solved_bus), used to prove the conversion."""
    buses = net.get_bus_breaker_view_buses()
    rows = [{"case_id": case_id, "bus_id": str(bid), "vm_pu": fnum(b["v_mag"]) / nominal[b["voltage_level_id"]],
             "va_deg": fnum(b["v_angle"])} for bid, b in buses.iterrows() if not pd.isna(b.get("v_mag"))]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------

def limit_ratings(net, nominal_kv_of: dict[str, float]) -> dict[str, tuple[float, float]]:
    """element_id -> (continuous MVA, emergency MVA) from side-one current limits.

    nominal_kv_of maps element_id to the side-one nominal kV.
    """
    try:
        lim = net.get_operational_limits().reset_index()
    except Exception:  # an older or newer API shape: carry on without ratings
        return {}
    lim = lim[(lim["type"] == "CURRENT") & (lim["side"].astype(str).str.upper().isin(["ONE", "1"]))]
    out: dict[str, tuple[float, float]] = {}
    for eid, grp in lim.groupby("element_id"):
        kv = nominal_kv_of.get(eid)
        if not kv:
            continue
        perm = grp[grp["acceptable_duration"] < 0]["value"]
        temp = grp[grp["acceptable_duration"] >= 0].sort_values("acceptable_duration", ascending=False)["value"]
        cont = math.sqrt(3) * kv * float(perm.min()) / 1000.0 if len(perm) else math.nan
        emerg = math.sqrt(3) * kv * float(temp.iloc[0]) / 1000.0 if len(temp) else math.nan
        out[str(eid)] = (cont, emerg)
    return out


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------

def low_impedance(r_ohm: float, x_ohm: float, kv: float) -> bool:
    """True when |z| on a 100 MVA base is below LOW_Z_PU: treat it as a switch."""
    z_base = kv * kv / BASE_MVA
    return math.hypot(r_ohm, x_ohm) / z_base < LOW_Z_PU


def line_frames(net, case_id: str, nominal: dict, ratings: dict, r_temp_c: float):
    """net_line rows, and net_switch rows for near-zero-impedance lines."""
    lines = net.get_lines(all_attributes=True)
    bus1 = first_col(lines, "bus_breaker_bus1_id", "bus1_id")
    bus2 = first_col(lines, "bus_breaker_bus2_id", "bus2_id")
    rows, switches = [], []
    for lid, ln in lines.iterrows():
        kv = nominal[ln["voltage_level1_id"]]
        b1, b2 = bus1[lid], bus2[lid]
        on = bool(ln.get("connected1", True)) and bool(ln.get("connected2", True))
        if low_impedance(ln["r"], ln["x"], kv):
            switches.append({"case_id": case_id, "switch_id": f"Z-{lid}", "bus": b1, "element_type": "bus",
                             "element_id": b2, "closed": yn(on), "normally_open": "N"})
            continue
        cont, emerg = ratings.get(str(lid), (math.nan, math.nan))
        rows.append({
            "case_id": case_id, "line_id": str(lid), "name": ln.get("name") or str(lid),
            "from_bus": b1, "to_bus": b2, "circuit": 1, "length_km": 1.0, "conductor": None,
            "conductors_per_phase": None, "r_ohm_per_km": float(ln["r"]), "x_ohm_per_km": float(ln["x"]),
            "b_us_per_km": (fnum(ln.get("b1"), 0.0) + fnum(ln.get("b2"), 0.0)) * 1e6, "r_temp_c": r_temp_c,
            "rate_cont_mva": cont, "rate_emerg_mva": emerg, "rate_ncc_mva": None, "rate_ncc_basis": None,
            "commissioning_year": None, "status": "existing", "in_service": yn(on), "tower_group": None,
            "notes": "converted by pypowsybl: whole-line values on a notional 1 km; take length from GIS",
        })
    return pd.DataFrame(rows), switches


def tap_rho(net) -> dict[str, float]:
    """transformer id -> ratio of the ratio tap changer at its current position (1 if none)."""
    try:
        rtc = net.get_ratio_tap_changers()
    except Exception:
        return {}
    if "rho" in rtc.columns:
        return rtc["rho"].astype(float).to_dict()
    try:
        steps = net.get_ratio_tap_changer_steps()
    except Exception:
        return {}
    out = {}
    for tid, row in rtc.iterrows():
        key = (tid, int(row["tap"]))
        if key in steps.index:
            out[str(tid)] = float(steps.loc[key, "rho"])
    return out


def trafo_percent(r: float, x: float, g: float, b: float, u_kv: float, sn_mva: float) -> dict:
    """vk %, vkr %, pfe kW and i0 % from series r, x and shunt g, b at u_kv on sn_mva."""
    z_base = u_kv * u_kv / sn_mva
    return {"vk_percent": math.hypot(r, x) / z_base * 100.0, "vkr_percent": r / z_base * 100.0,
            "pfe_kw": abs(g) * u_kv * u_kv * 1000.0, "i0_percent": math.hypot(g, b) * z_base * 100.0}


def trafo_frame(net, case_id: str, ratings: dict) -> pd.DataFrame:
    """net_trafo rows for two-winding transformers (taps fixed at the case position)."""
    tr = net.get_2_windings_transformers(all_attributes=True)
    bus1 = first_col(tr, "bus_breaker_bus1_id", "bus1_id")
    bus2 = first_col(tr, "bus_breaker_bus2_id", "bus2_id")
    rho = tap_rho(net)
    rows = []
    for tid, t in tr.iterrows():
        u1, u2 = float(t["rated_u1"]), float(t["rated_u2"])
        u1_eff = u1 / rho.get(str(tid), 1.0)  # IIDM ratio = u2/u1 * rho
        cont, emerg = ratings.get(str(tid), (math.nan, math.nan))
        sn = fnum(t.get("rated_s"))
        sn = sn if sn > 0 else (cont if cont > 0 else BASE_MVA)
        pct = trafo_percent(float(t["r"]), float(t["x"]), fnum(t.get("g"), 0.0), fnum(t.get("b"), 0.0), u2, sn)
        hv_is_1 = u1 >= u2
        on = bool(t.get("connected1", True)) and bool(t.get("connected2", True))
        rows.append({
            "case_id": case_id, "trafo_id": str(tid), "name": t.get("name") or str(tid),
            "substation": None, "hv_bus": bus1[tid] if hv_is_1 else bus2[tid],
            "lv_bus": bus2[tid] if hv_is_1 else bus1[tid], "sn_mva": sn,
            "vn_hv_kv": u1_eff if hv_is_1 else u2, "vn_lv_kv": u2 if hv_is_1 else u1_eff,
            **pct, "load_loss_kw": None, "vector_group": None, "tap_side": None, "tap_neutral": None,
            "tap_min": None, "tap_max": None, "tap_step_percent": None, "tap_pos": None,
            "rate_cont_mva": cont if cont > 0 else sn, "rate_emerg_mva": emerg, "rate_ncc_mva": None,
            "rate_ncc_basis": None, "commissioning_year": None, "status": "existing", "in_service": yn(on),
            "notes": "converted by pypowsybl; tap fixed at case position"
                     + ("" if cont > 0 else "; no current limit, rating = rated MVA"),
        })
    return pd.DataFrame(rows)


def trafo3w_frame(net, case_id: str) -> pd.DataFrame:
    """net_trafo3w rows. IIDM gives each leg of the star at rated_u0; T01 wants the pairwise
    short-circuit voltages (HV-MV, MV-LV, LV-HV), each on the smaller winding rating."""
    tr = net.get_3_windings_transformers(all_attributes=True)
    rows = []
    for tid, t in tr.iterrows():
        u0 = float(t["rated_u0"])
        legs = {i: (float(t[f"r{i}"]), float(t[f"x{i}"]), fnum(t.get(f"rated_s{i}"), BASE_MVA)) for i in (1, 2, 3)}

        def pair(i: int, j: int) -> tuple[float, float]:
            s = min(legs[i][2], legs[j][2])
            z_base = u0 * u0 / s
            r, x = legs[i][0] + legs[j][0], legs[i][1] + legs[j][1]
            return math.hypot(r, x) / z_base * 100.0, r / z_base * 100.0

        vk12, vkr12 = pair(1, 2)
        vk23, vkr23 = pair(2, 3)
        vk31, vkr31 = pair(3, 1)
        g = sum(fnum(t.get(f"g{i}"), 0.0) for i in (1, 2, 3))
        b = sum(fnum(t.get(f"b{i}"), 0.0) for i in (1, 2, 3))
        bus = {i: first_col(tr.loc[[tid]], f"bus_breaker_bus{i}_id", f"bus{i}_id").iloc[0] for i in (1, 2, 3)}
        on = all(bool(t.get(f"connected{i}", True)) for i in (1, 2, 3))
        rows.append({
            "case_id": case_id, "trafo_id": str(tid), "name": t.get("name") or str(tid), "substation": None,
            "hv_bus": bus[1], "mv_bus": bus[2], "lv_bus": bus[3],
            "sn_hv_mva": legs[1][2], "sn_mv_mva": legs[2][2], "sn_lv_mva": legs[3][2],
            "vn_hv_kv": float(t["rated_u1"]), "vn_mv_kv": float(t["rated_u2"]), "vn_lv_kv": float(t["rated_u3"]),
            "vk_hv_percent": vk12, "vk_mv_percent": vk23, "vk_lv_percent": vk31,
            "vkr_hv_percent": vkr12, "vkr_mv_percent": vkr23, "vkr_lv_percent": vkr31,
            "pfe_kw": abs(g) * u0 * u0 * 1000.0, "i0_percent": math.hypot(g, b) * u0 * u0 / legs[1][2] * 100.0,
            "tap_side": None, "tap_neutral": None, "tap_min": None, "tap_max": None, "tap_step_percent": None,
            "tap_pos": None, "rate_cont_mva": legs[1][2], "commissioning_year": None, "status": "existing",
            "in_service": yn(on),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Injections
# ---------------------------------------------------------------------------

def slack_bus_ids(net) -> set[str]:
    """Bus-breaker bus ids marked as slack (the slackTerminal extension, set from the
    PSS/E type-3 bus). Empty when the extension is not there."""
    try:
        ext = net.get_extensions("slackTerminal")
    except Exception:
        return set()
    return {str(b) for b in first_col(ext, "bus_id") if b}


def gen_frame(net, case_id: str, nominal: dict) -> pd.DataFrame:
    """net_gen rows. Voltage-regulating units are PV, others PQ; the unit at the slack bus
    (or, failing that, the largest unit) is the slack."""
    g = net.get_generators(all_attributes=True)
    bus = first_col(g, "bus_breaker_bus_id", "bus_id")
    slack_buses = slack_bus_ids(net)
    rows = []
    for gid, r in g.iterrows():
        kv = nominal[r["voltage_level_id"]]
        control = "PV" if bool(r.get("voltage_regulator_on")) else "PQ"
        if str(bus[gid]) in slack_buses:
            control = "slack"
        rows.append({
            "case_id": case_id, "gen_id": str(gid), "name": r.get("name") or str(gid), "bus": bus[gid],
            "plant": r.get("name") or str(gid), "technology": TECHNOLOGY.get(str(r.get("energy_source")), "other"),
            "p_mw": fnum(r.get("target_p"), 0.0), "p_max_mw": fnum(r.get("max_p")),
            "p_min_mw": fnum(r.get("min_p")), "q_min_mvar": fnum(r.get("min_q")), "q_max_mvar": fnum(r.get("max_q")),
            "vm_pu": fnum(r.get("target_v"), kv) / kv, "control": control, "connection_kv": kv,
            "in_service": yn(r.get("connected", True)),
        })
    df = pd.DataFrame(rows)
    if len(df) and not (df["control"] == "slack").any():
        df.loc[df["p_max_mw"].fillna(df["p_mw"]).idxmax(), "control"] = "slack"
    return df


def load_frame(net, case_id: str) -> pd.DataFrame:
    """net_load rows from p0 and q0."""
    ld = net.get_loads(all_attributes=True)
    bus = first_col(ld, "bus_breaker_bus_id", "bus_id")
    return pd.DataFrame([{
        "case_id": case_id, "load_id": str(lid), "bus": bus[lid], "substation": None,
        "bsp_name": r.get("name") or str(lid), "share": None, "p_mw": fnum(r.get("p0"), 0.0),
        "q_mvar": fnum(r.get("q0"), 0.0), "in_service": yn(r.get("connected", True)),
    } for lid, r in ld.iterrows()])


def shunt_frame(net, case_id: str, nominal: dict) -> pd.DataFrame:
    """net_shunt rows. IIDM b > 0 is a capacitor; T01 q_mvar at 1.0 pu is +reactor,
    -capacitor, so q = -b * V^2."""
    sh = net.get_shunt_compensators(all_attributes=True)
    bus = first_col(sh, "bus_breaker_bus_id", "bus_id")
    return pd.DataFrame([{
        "case_id": case_id, "shunt_id": str(sid), "bus": bus[sid],
        "q_mvar": -fnum(r.get("b"), 0.0) * nominal[r["voltage_level_id"]] ** 2,
        "steps": int(fnum(r.get("max_section_count"), 1)), "in_service": yn(r.get("connected", True)),
    } for sid, r in sh.iterrows()])


def solved_branches(net, case_id: str) -> pd.DataFrame:
    """net_solved_branch rows for lines and two-winding transformers."""
    rows = []
    for df in (net.get_lines(), net.get_2_windings_transformers()):
        for eid, r in df.iterrows():
            if pd.isna(r.get("p1")):
                continue
            rows.append({"case_id": case_id, "branch_id": str(eid), "p_from_mw": float(r["p1"]),
                         "q_from_mvar": fnum(r.get("q1")), "p_to_mw": fnum(r.get("p2")),
                         "q_to_mvar": fnum(r.get("q2")), "loading_pct": None})
    return pd.DataFrame(rows)


def unsupported_counts(net) -> list[str]:
    """Element kinds this converter leaves out, with counts, for the import log."""
    notes = []
    for label, getter in (("static VAR compensators", "get_static_var_compensators"),
                          ("dangling lines", "get_dangling_lines"), ("HVDC lines", "get_hvdc_lines"),
                          ("phase tap changers", "get_phase_tap_changers")):
        try:
            n = len(getattr(net, getter)())
        except Exception:
            continue
        if n:
            notes.append(f"{n} {label} not converted")
    return notes


def to_t01(path: str | Path, case_id: str, *, case_type: str = "other", case_date: str | None = None,
           source_tool: str = "PSSE", r_temp_c: float = 20.0,
           parameters: dict | None = None) -> dict[str, pd.DataFrame]:
    """Read a native case file and return T01-shaped tables keyed by table name.

    path: .raw/.rawx (PSS/E v33/v35), CGMES .zip, or PowerFactory .dgs; pypowsybl picks the
        importer from the file.
    r_temp_c: conductor temperature the case's line R is quoted at (ask Planning; 20 C if unsure).
    The returned dict also holds 'warnings': a one-column DataFrame of what was left out.
    """
    pn = import_pypowsybl()
    net = pn.load(str(path), parameters or {})
    buses, nominal = bus_frame(net, case_id)
    lines = net.get_lines()
    trafos = net.get_2_windings_transformers()
    side1_kv = {**{str(i): nominal[v] for i, v in lines["voltage_level1_id"].items()},
                **{str(i): nominal[v] for i, v in trafos["voltage_level1_id"].items()}}
    ratings = limit_ratings(net, side1_kv)
    net_line, switches = line_frames(net, case_id, nominal, ratings, r_temp_c)
    case = pd.DataFrame([{
        "case_id": case_id, "case_type": case_type, "case_date": case_date, "case_hour": None,
        "description": f"converted from {Path(path).name} by pypowsybl", "source_tool": source_tool,
        "tool_version": None, "base_mva": BASE_MVA, "frequency_hz": 50.0, "perimeter": "national",
        "rating_note": "continuous = permanent current limit; emergency = longest temporary limit",
        "contact": None,
    }])
    return {
        "net_case": case, "net_bus": buses, "net_line": net_line,
        "net_trafo": trafo_frame(net, case_id, ratings), "net_trafo3w": trafo3w_frame(net, case_id),
        "net_gen": gen_frame(net, case_id, nominal), "net_load": load_frame(net, case_id),
        "net_shunt": shunt_frame(net, case_id, nominal), "net_switch": pd.DataFrame(switches),
        "net_boundary": pd.DataFrame(), "net_solved_bus": solved_buses(net, case_id, nominal),
        "net_solved_branch": solved_branches(net, case_id),
        "warnings": pd.DataFrame({"message": unsupported_counts(net)}),
    }
