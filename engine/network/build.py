"""Build a pandapower network from T01-shaped tables.

The T01 workbook (templates/spec/T01_network_model.toml) is the one canonical shape for
every network source: Planning's own workbook, a PSS/E or CGMES case converted by
loaders/network_pypowsybl.py, or the hand-built fallback from loaders/network_handbuilt.py.
This module turns those tables into a pandapower net for one case, so every later stage
(losses, N-1, 2030, Kawanda, headroom) runs on the same model.

Every element's pandapower `name` is its T01 id (for example `L-KAW-MUT-132-1`), and
identity columns (ss_code, in_central, rate_mva, ...) are added to the element tables so
results can be reported by substation and region without another lookup.
"""

from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pandapower as pp

# Temperature coefficient of resistance for aluminium, per degree C.
ALPHA_AL_PER_C = 0.00403
DEFAULT_R_TEMP_C = 20.0
DEFAULT_FREQUENCY_HZ = 50.0
RATING_SETS = ("cont", "emerg", "ncc", "min")
TABLES = ("net_case", "net_bus", "net_line", "net_trafo", "net_trafo3w", "net_gen",
          "net_load", "net_shunt", "net_switch", "net_boundary")
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


# ---------------------------------------------------------------------------
# Small value helpers. Inputs come from Excel, CSV or Postgres, so blanks can be
# None, NaN, NA or empty strings, and yes/no can be "Y"/"N" or booleans.
# ---------------------------------------------------------------------------

def is_blank(value) -> bool:
    """True for None, NaN, pandas NA and empty or whitespace-only strings."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def num(value, default: float = math.nan) -> float:
    """Return value as a float, or the default when it is blank or not a number."""
    if is_blank(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def yes(value, default: bool = True) -> bool:
    """Read a yes/no cell: Y, YES, TRUE, 1 or True mean yes. Blank gives the default."""
    if is_blank(value):
        return default
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1", "T"}


def text(value, default: str | None = None) -> str | None:
    """Return value as a stripped string, or the default when blank."""
    if is_blank(value):
        return default
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def norm_name(value) -> str:
    """Normalise a substation name for matching: lower case, letters and digits only,
    and common suffixes such as 'S/S' or 'substation' removed."""
    s = str(value or "").lower()
    s = re.sub(r"\b(s/s|ss|substation|sub-station|sub station)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def resistance_at(r_ref: float, t_ref_c: float, t_c: float) -> float:
    """Correct a resistance quoted at t_ref_c to the conductor temperature t_c.

    R_T = R_ref * (1 + 0.00403 * (T - T_ref)). A 20 C vs 50 C error alone is about 12 %,
    which is larger than the whole 10 % loss gate, so this matters.
    """
    return r_ref * (1.0 + ALPHA_AL_PER_C * (t_c - t_ref_c))


def shift_from_vector_group(vector_group) -> float:
    """Phase shift in degrees from the clock number at the end of a vector group
    (YNd5 -> 150, Dyn11 -> 330, YNyn0 -> 0). Blank gives 0."""
    match = re.search(r"(\d+)\s*$", str(vector_group or ""))
    return (int(match.group(1)) % 12) * 30.0 if match else 0.0


def pick_rating(row, rating_set: str) -> tuple[float, str]:
    """Choose the rating (MVA) for a line or transformer row and say which set it came from.

    cont: continuous. emerg: emergency, or continuous when blank. ncc: the NCC operating
    limit, or continuous when blank. min: the lowest of the ratings given.
    """
    if rating_set not in RATING_SETS:
        raise ValueError(f"rating_set must be one of {RATING_SETS}, not {rating_set!r}")
    rates = {"cont": num(row.get("rate_cont_mva")), "emerg": num(row.get("rate_emerg_mva")),
             "ncc": num(row.get("rate_ncc_mva"))}
    given = {k: v for k, v in rates.items() if not math.isnan(v) and v > 0}
    if rating_set == "min":
        if not given:
            return math.nan, "missing"
        key = min(given, key=given.get)
        return given[key], key
    if rating_set in given:
        return given[rating_set], rating_set
    if "cont" in given:
        return given["cont"], "cont"
    return math.nan, "missing"


# ---------------------------------------------------------------------------
# Typical transformer values, used only when a T01 row leaves a value blank.
# ---------------------------------------------------------------------------

def read_transformer_defaults(path: Path | None = None) -> pd.DataFrame:
    """Read config/transformer_defaults.csv: typical vk, vkr, pfe and i0 by MVA band."""
    return pd.read_csv(path or CONFIG_DIR / "transformer_defaults.csv")


def typical_trafo(sn_mva: float, defaults: pd.DataFrame | None = None) -> dict[str, float]:
    """Typical vk_percent, vkr_percent, pfe_kw and i0_percent for a transformer of sn_mva."""
    table = defaults if defaults is not None else read_transformer_defaults()
    band = table[(table.mva_min <= sn_mva) & (sn_mva < table.mva_max)]
    row = (band if len(band) else table.iloc[[-1]]).iloc[0]
    return {"vk_percent": float(row.vk_percent), "vkr_percent": float(row.vkr_percent),
            "pfe_kw": float(row.pfe_percent) / 100.0 * sn_mva * 1000.0,
            "i0_percent": float(row.i0_percent)}


# ---------------------------------------------------------------------------
# Table preparation
# ---------------------------------------------------------------------------

def get_table(net_tables: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    """Fetch one table by name, accepting 'net_bus' or 'ts.net_bus'. Missing gives empty."""
    for key in (name, f"ts.{name}"):
        if key in net_tables and net_tables[key] is not None:
            return net_tables[key].copy()
    return pd.DataFrame()


def case_rows(df: pd.DataFrame, case_id: str) -> pd.DataFrame:
    """Rows for one case. Rows with no case_id column (extra elements) are kept."""
    if df.empty or "case_id" not in df.columns:
        return df.reset_index(drop=True)
    keep = df["case_id"].isna() | (df["case_id"].astype(str) == str(case_id))
    return df[keep].reset_index(drop=True)


def merged_tables(net_tables: dict[str, pd.DataFrame], case_id: str,
                  extra: dict[str, pd.DataFrame] | None) -> dict[str, pd.DataFrame]:
    """All T01 tables for one case, with any extra elements (e.g. 2030 projects) appended."""
    out = {}
    for name in TABLES:
        parts = [case_rows(get_table(net_tables, name), case_id)]
        if extra:
            parts.append(case_rows(get_table(extra, name), case_id))
        parts = [p for p in parts if not p.empty]
        out[name] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return out


# The id column of each T01 table that has one. results.element and results.bus key on it,
# so two rows with the same id would break the write.
ID_COLUMNS = {"net_bus": "bus_id", "net_line": "line_id", "net_trafo": "trafo_id",
              "net_trafo3w": "trafo_id", "net_gen": "gen_id", "net_load": "load_id",
              "net_shunt": "shunt_id", "net_switch": "switch_id"}


def drop_duplicate_ids(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Keep one row per element id, the last one, and say which ids were repeated.

    Extra elements are appended after the case's own rows, so an extra row with an id the
    case already has (an uprating or reconductoring project) replaces the old row.
    """
    warnings = []
    for name, id_col in ID_COLUMNS.items():
        df = tables.get(name)
        if df is None or df.empty or id_col not in df.columns:
            continue
        ids = df[id_col].map(text)
        dup = ids.duplicated(keep="last")
        if dup.any():
            repeated = sorted({str(i) for i in ids[dup]})
            warnings.append(f"{name}: id(s) {', '.join(repeated[:10])} given more than once; "
                            "the last row is used")
            tables[name] = df[~dup].reset_index(drop=True)
    return warnings


def status_filter(df: pd.DataFrame, as_of: date | None, statuses) -> pd.DataFrame:
    """Keep rows whose status is wanted and that were commissioned by the as-of date.

    A blank status counts as existing. A blank commissioning_year never filters a row out.
    """
    if df.empty:
        return df
    keep = pd.Series(True, index=df.index)
    if "status" in df.columns:
        status = df["status"].map(lambda s: text(s, "existing").lower())
        keep &= status.isin([s.lower() for s in statuses])
    if as_of is not None and "commissioning_year" in df.columns:
        year = df["commissioning_year"].map(num)
        keep &= year.isna() | (year <= as_of.year)
    return df[keep].reset_index(drop=True)


def substation_lookup(substations: pd.DataFrame | None) -> tuple[dict[str, str], dict[str, bool]]:
    """Two maps from the substations register: normalised name or code -> ss_code, and
    ss_code -> in_central."""
    by_name: dict[str, str] = {}
    central: dict[str, bool] = {}
    if substations is None or substations.empty:
        return by_name, central
    for row in substations.to_dict("records"):
        code = text(row.get("ss_code"))
        if not code:
            continue
        central[code] = yes(row.get("in_central"), default=False)
        by_name[norm_name(code)] = code
        if text(row.get("name")):
            by_name.setdefault(norm_name(row["name"]), code)
    return by_name, central


def resolve_ss(row: dict, by_name: dict[str, str], name_col: str = "substation") -> str | None:
    """Substation code for a row: substation_code (filled by the loader), else ss_code,
    else the name matched against the register after normalising."""
    for col in (f"{name_col}_code", "ss_code"):
        code = text(row.get(col))
        if code:
            return code
    raw = text(row.get(name_col))
    if not raw:
        return None
    return by_name.get(norm_name(raw))


def attach(df: pd.DataFrame, ident: list[dict]) -> None:
    """Add identity columns to a pandapower element table, aligned on its index.

    ident holds one dict per element, with the element's index under "idx".
    """
    if not ident:
        return
    frame = pd.DataFrame(ident).set_index("idx")
    for c in frame.columns:
        df[c] = frame[c].reindex(df.index).astype(object)


def ss_central(net, ss: str | None, bus: int, central: dict[str, bool]) -> bool:
    """in_central for an element at substation ss: the register's flag, else its bus's."""
    if ss in central:
        return central[ss]
    return bool(net.bus.at[bus, "in_central"])


# ---------------------------------------------------------------------------
# Element builders. Each adds one T01 table to the net and returns warnings.
# ---------------------------------------------------------------------------

def add_buses(net, buses: pd.DataFrame, by_name, central) -> list[str]:
    """One pandapower bus per T01 bus row."""
    warnings, ident = [], []
    for row in buses.to_dict("records"):
        bus_id = text(row["bus_id"])
        ss = resolve_ss(row, by_name)
        if ss is None:
            warnings.append(f"bus {bus_id}: substation {row.get('substation')!r} not in the register")
        idx = pp.create_bus(net, vn_kv=num(row["vn_kv"]), name=bus_id, zone=text(row.get("zone")),
                            in_service=yes(row.get("in_service")),
                            min_vm_pu=num(row.get("v_min_pu")), max_vm_pu=num(row.get("v_max_pu")))
        # The register decides in_central. A substation it does not list (a hand-built one,
        # say) may carry its own in_central on the bus row.
        in_central = central[ss] if ss in central else yes(row.get("in_central"), default=False)
        ident.append({"idx": idx, "bus_id": bus_id, "ss_code": ss, "in_central": in_central,
                      "display_name": text(row.get("name"), bus_id)})
    attach(net.bus, ident)
    return warnings


def add_lines(net, lines: pd.DataFrame, bus_ix: dict[str, int], r_temp_c: float,
              rating_set: str, freq_hz: float, line_in_central: str) -> list[str]:
    """Lines with R corrected to r_temp_c and max_i_ka set from the chosen rating."""
    warnings, ident = [], []
    for row in lines.to_dict("records"):
        line_id = text(row["line_id"])
        fb, tb = text(row.get("from_bus")), text(row.get("to_bus"))
        if fb not in bus_ix or tb not in bus_ix:
            warnings.append(f"line {line_id}: bus {fb if fb not in bus_ix else tb} not found; skipped")
            continue
        f, t = bus_ix[fb], bus_ix[tb]
        vn_kv = float(net.bus.at[f, "vn_kv"])
        rate, basis = pick_rating(row, rating_set)
        max_i_ka = rate / (math.sqrt(3) * vn_kv) if not math.isnan(rate) else math.nan
        r = resistance_at(num(row.get("r_ohm_per_km")), num(row.get("r_temp_c"), DEFAULT_R_TEMP_C),
                          r_temp_c)
        b_us = num(row.get("b_us_per_km"), 0.0)
        c_nf = b_us * 1e3 / (2 * math.pi * freq_hz)  # B = 2*pi*f*C, uS -> nF
        idx = pp.create_line_from_parameters(
            net, from_bus=f, to_bus=t, length_km=num(row.get("length_km")), r_ohm_per_km=r,
            x_ohm_per_km=num(row.get("x_ohm_per_km")), c_nf_per_km=c_nf,
            max_i_ka=max_i_ka if not math.isnan(max_i_ka) else 0.0, name=line_id,
            in_service=yes(row.get("in_service")))
        ss_from, ss_to = net.bus.at[f, "ss_code"], net.bus.at[t, "ss_code"]
        c_from, c_to = bool(net.bus.at[f, "in_central"]), bool(net.bus.at[t, "in_central"])
        ident.append({
            "idx": idx, "line_id": line_id, "ss_from": ss_from, "ss_to": ss_to,
            "in_central": (c_from and c_to) if line_in_central == "both" else (c_from or c_to),
            "rate_mva": rate, "rate_basis": basis,
            "commissioning_year": num(row.get("commissioning_year")),
            "tower_group": text(row.get("tower_group")), "status": text(row.get("status"), "existing"),
            "is_equivalent": "equivalent" in str(row.get("notes") or "").lower(),
            "display_name": text(row.get("name"), line_id),
            "r_ref_ohm_per_km": num(row.get("r_ohm_per_km")),
            "r_ref_temp_c": num(row.get("r_temp_c"), DEFAULT_R_TEMP_C),
            "param_source": text(row.get("param_source"))})
    attach(net.line, ident)
    return warnings


def trafo_vkr(row, sn_mva: float, typical: dict) -> float:
    """vkr_percent from the row, else from load_loss_kw (vkr = P_cu / S_n), else typical."""
    vkr = num(row.get("vkr_percent"))
    if not math.isnan(vkr):
        return vkr
    load_loss_kw = num(row.get("load_loss_kw"))
    if not math.isnan(load_loss_kw) and sn_mva > 0:
        return load_loss_kw / (sn_mva * 1000.0) * 100.0
    return typical["vkr_percent"]


def tap_args(row) -> dict:
    """pandapower tap arguments; no tap changer when tap_step_percent is blank."""
    step = num(row.get("tap_step_percent"))
    if math.isnan(step):
        return {}
    neutral = num(row.get("tap_neutral"), 0.0)
    return {"tap_side": text(row.get("tap_side"), "hv").lower(), "tap_neutral": neutral,
            "tap_min": num(row.get("tap_min"), neutral), "tap_max": num(row.get("tap_max"), neutral),
            "tap_step_percent": step, "tap_pos": num(row.get("tap_pos"), neutral),
            "tap_changer_type": "Ratio"}


def add_trafos(net, trafos: pd.DataFrame, bus_ix, rating_set, defaults, by_name, central) -> list[str]:
    """Two-winding transformers. Blank vkr, pfe or i0 take typical values for the size."""
    warnings, ident = [], []
    for row in trafos.to_dict("records"):
        trafo_id = text(row["trafo_id"])
        hv, lv = text(row.get("hv_bus")), text(row.get("lv_bus"))
        if hv not in bus_ix or lv not in bus_ix:
            warnings.append(f"trafo {trafo_id}: bus {hv if hv not in bus_ix else lv} not found; skipped")
            continue
        sn = num(row.get("sn_mva"))
        typ = typical_trafo(sn, defaults)
        blanks = [c for c in ("vkr_percent", "pfe_kw", "i0_percent") if is_blank(row.get(c))
                  and not (c == "vkr_percent" and not is_blank(row.get("load_loss_kw")))]
        if blanks:
            warnings.append(f"trafo {trafo_id}: typical values used for {', '.join(blanks)}")
        idx = pp.create_transformer_from_parameters(
            net, hv_bus=bus_ix[hv], lv_bus=bus_ix[lv], sn_mva=sn, vn_hv_kv=num(row.get("vn_hv_kv")),
            vn_lv_kv=num(row.get("vn_lv_kv")), vkr_percent=trafo_vkr(row, sn, typ),
            vk_percent=num(row.get("vk_percent"), typ["vk_percent"]),
            pfe_kw=num(row.get("pfe_kw"), typ["pfe_kw"]),
            i0_percent=num(row.get("i0_percent"), typ["i0_percent"]),
            shift_degree=shift_from_vector_group(row.get("vector_group")),
            vector_group=text(row.get("vector_group")), name=trafo_id,
            in_service=yes(row.get("in_service")), **tap_args(row))
        ss = resolve_ss(row, by_name) or net.bus.at[bus_ix[hv], "ss_code"]
        rate, basis = pick_rating(row, rating_set)
        ident.append({
            "idx": idx, "trafo_id": trafo_id, "ss_code": ss,
            "in_central": ss_central(net, ss, bus_ix[hv], central), "rate_mva": rate,
            "rate_basis": basis, "commissioning_year": num(row.get("commissioning_year")),
            "status": text(row.get("status"), "existing"),
            "is_equivalent": "equivalent" in str(row.get("notes") or "").lower(),
            "display_name": text(row.get("name"), trafo_id),
            "param_source": text(row.get("param_source"))})
    attach(net.trafo, ident)
    return warnings


def add_trafos3w(net, trafos: pd.DataFrame, bus_ix, defaults, by_name, central) -> list[str]:
    """Three-winding transformers. T01 gives only a continuous rating (HV winding)."""
    warnings, ident = [], []
    for row in trafos.to_dict("records"):
        trafo_id = text(row["trafo_id"])
        ends = [text(row.get(c)) for c in ("hv_bus", "mv_bus", "lv_bus")]
        missing = [b for b in ends if b not in bus_ix]
        if missing:
            warnings.append(f"trafo3w {trafo_id}: bus {missing[0]} not found; skipped")
            continue
        typ = typical_trafo(num(row.get("sn_hv_mva")), defaults)
        vkr = {w: num(row.get(f"vkr_{w}_percent"), typ["vkr_percent"]) for w in ("hv", "mv", "lv")}
        # A blank vk would make the whole load flow fail, so use the typical value and say so.
        vk = {w: num(row.get(f"vk_{w}_percent"), typ["vk_percent"]) for w in ("hv", "mv", "lv")}
        blanks = [f"vk_{w}_percent" for w in ("hv", "mv", "lv") if is_blank(row.get(f"vk_{w}_percent"))]
        if blanks:
            warnings.append(f"trafo3w {trafo_id}: typical values used for {', '.join(blanks)}")
        idx = pp.create_transformer3w_from_parameters(
            net, hv_bus=bus_ix[ends[0]], mv_bus=bus_ix[ends[1]], lv_bus=bus_ix[ends[2]],
            vn_hv_kv=num(row.get("vn_hv_kv")), vn_mv_kv=num(row.get("vn_mv_kv")),
            vn_lv_kv=num(row.get("vn_lv_kv")), sn_hv_mva=num(row.get("sn_hv_mva")),
            sn_mv_mva=num(row.get("sn_mv_mva")), sn_lv_mva=num(row.get("sn_lv_mva")),
            vk_hv_percent=vk["hv"], vk_mv_percent=vk["mv"], vk_lv_percent=vk["lv"], vkr_hv_percent=vkr["hv"],
            vkr_mv_percent=vkr["mv"], vkr_lv_percent=vkr["lv"],
            pfe_kw=num(row.get("pfe_kw"), typ["pfe_kw"]),
            i0_percent=num(row.get("i0_percent"), typ["i0_percent"]), name=trafo_id,
            in_service=yes(row.get("in_service")), **tap_args(row))
        ss = resolve_ss(row, by_name) or net.bus.at[bus_ix[ends[0]], "ss_code"]
        rate = num(row.get("rate_cont_mva"))
        ident.append({
            "idx": idx, "trafo_id": trafo_id, "ss_code": ss,
            "in_central": ss_central(net, ss, bus_ix[ends[0]], central), "rate_mva": rate,
            "rate_basis": "cont" if not math.isnan(rate) else "missing",
            "commissioning_year": num(row.get("commissioning_year")),
            "status": text(row.get("status"), "existing"), "is_equivalent": False,
            "display_name": text(row.get("name"), trafo_id)})
    attach(net.trafo3w, ident)
    return warnings


GEN_IDENTITY = ["gen_id", "plant_code", "technology", "ss_code", "in_central", "is_equivalent",
                "display_name"]


def gen_identity(net, idx: int, gen_id: str, plant_code, technology, bus: int,
                 is_equivalent: bool, display_name: str) -> dict:
    """Identity columns shared by ext_grid, gen and sgen rows."""
    values = [gen_id, plant_code, technology, net.bus.at[bus, "ss_code"],
              bool(net.bus.at[bus, "in_central"]), is_equivalent, display_name]
    return {"idx": idx, **dict(zip(GEN_IDENTITY, values))}


def attach_gens(net, ident: dict[str, list[dict]]) -> None:
    """Attach gen identity rows collected per pandapower table (ext_grid, gen, sgen),
    keeping rows already attached by an earlier step."""
    for table, rows in ident.items():
        if not rows:
            continue
        old = net[table][GEN_IDENTITY].dropna(how="all") if set(GEN_IDENTITY) <= set(net[table]) else None
        merged = [] if old is None else [{"idx": i, **r} for i, r in old.to_dict("index").items()]
        attach(net[table], merged + rows)


def pq_gen_q(row) -> float:
    """Reactive output of a PQ generator. T01 has no q column, so a fixed MVAr is given by
    q_min_mvar = q_max_mvar; otherwise 0. A non-spec q_mvar column, if present, wins."""
    q = num(row.get("q_mvar"))
    if not math.isnan(q):
        return q
    q_min, q_max = num(row.get("q_min_mvar")), num(row.get("q_max_mvar"))
    return q_min if not math.isnan(q_min) and q_min == q_max else 0.0


def add_gens(net, gens: pd.DataFrame, bus_ix) -> list[str]:
    """Generators by control mode: slack -> ext_grid, PV -> gen, PQ -> sgen."""
    warnings, ident = [], {"ext_grid": [], "gen": [], "sgen": []}
    for row in gens.to_dict("records"):
        gen_id = text(row["gen_id"])
        bus = text(row.get("bus"))
        if bus not in bus_ix:
            warnings.append(f"gen {gen_id}: bus {bus} not found; skipped")
            continue
        b = bus_ix[bus]
        control = text(row.get("control"), "PV").upper()
        on = yes(row.get("in_service"))
        limits = {"max_q_mvar": num(row.get("q_max_mvar")), "min_q_mvar": num(row.get("q_min_mvar")),
                  "max_p_mw": num(row.get("p_max_mw")), "min_p_mw": num(row.get("p_min_mw"))}
        if control == "SLACK":
            table = "ext_grid"
            idx = pp.create_ext_grid(net, b, vm_pu=num(row.get("vm_pu"), 1.0), name=gen_id,
                                     in_service=on, **limits)
        elif control == "PV":
            table = "gen"
            idx = pp.create_gen(net, b, p_mw=num(row.get("p_mw"), 0.0),
                                vm_pu=num(row.get("vm_pu"), 1.0), name=gen_id, in_service=on, **limits)
        else:
            table = "sgen"
            idx = pp.create_sgen(net, b, p_mw=num(row.get("p_mw"), 0.0), q_mvar=pq_gen_q(row),
                                 name=gen_id, in_service=on, **limits)
        plant_code = text(row.get("plant_code")) or text(row.get("plant"))
        ident[table].append(gen_identity(net, idx, gen_id, plant_code, text(row.get("technology")),
                                         b, False, text(row.get("name"), gen_id)))
    attach_gens(net, ident)
    return warnings


def add_boundary(net, boundary: pd.DataFrame, bus_ix) -> list[str]:
    """Boundary points of a partial network: slack -> ext_grid, pv -> gen, fixed_p -> sgen.

    Their ids are B-<bus_id>, and they are flagged is_equivalent so reports can leave them out.
    """
    warnings, ident = [], {"ext_grid": [], "gen": [], "sgen": []}
    for row in boundary.to_dict("records"):
        bus = text(row.get("bus"))
        if bus not in bus_ix:
            warnings.append(f"boundary at bus {bus}: bus not found; skipped")
            continue
        b, kind, gen_id = bus_ix[bus], text(row.get("kind"), "slack").lower(), f"B-{bus}"
        vm = num(row.get("vm_pu"), 1.0)
        p = num(row.get("p_mw"), 0.0)
        if kind == "slack":
            table, idx = "ext_grid", pp.create_ext_grid(net, b, vm_pu=vm, name=gen_id)
        elif kind == "pv":
            table, idx = "gen", pp.create_gen(net, b, p_mw=p, vm_pu=vm, name=gen_id)
        else:
            table, idx = "sgen", pp.create_sgen(net, b, p_mw=p, q_mvar=0.0, name=gen_id)
        ident[table].append(gen_identity(net, idx, gen_id, None, "boundary", b, True,
                                         text(row.get("note"), gen_id)))
    attach_gens(net, ident)
    return warnings


def add_loads(net, loads: pd.DataFrame, bus_ix, by_name, central) -> list[str]:
    """Loads (bulk supply points) with their substation code and share."""
    warnings, ident = [], []
    for row in loads.to_dict("records"):
        load_id = text(row["load_id"])
        bus = text(row.get("bus"))
        if bus not in bus_ix:
            warnings.append(f"load {load_id}: bus {bus} not found; skipped")
            continue
        b = bus_ix[bus]
        idx = pp.create_load(net, b, p_mw=num(row.get("p_mw"), 0.0), q_mvar=num(row.get("q_mvar"), 0.0),
                             name=load_id, in_service=yes(row.get("in_service")))
        ss = resolve_ss(row, by_name) or net.bus.at[b, "ss_code"]
        ident.append({"idx": idx, "load_id": load_id, "ss_code": ss, "share": num(row.get("share")),
                      "in_central": ss_central(net, ss, b, central),
                      "display_name": text(row.get("bsp_name"), load_id)})
    attach(net.load, ident)
    if len(net.load):
        net.load["share"] = net.load["share"].astype(float)
        fill_equal_shares(net)
    return warnings


def fill_equal_shares(net) -> None:
    """A blank share splits the substation's demand equally among its blank-share loads."""
    blank = net.load["share"].isna()
    for ss, grp in net.load[blank].groupby("ss_code", dropna=False):
        given = net.load.loc[~blank & (net.load.ss_code == ss), "share"].sum()
        net.load.loc[grp.index, "share"] = max(0.0, 1.0 - given) / len(grp)


def add_shunts(net, shunts: pd.DataFrame, bus_ix) -> list[str]:
    """Shunts: q_mvar at 1.0 pu, positive for a reactor, negative for a capacitor."""
    warnings, ident = [], []
    for row in shunts.to_dict("records"):
        shunt_id, bus = text(row["shunt_id"]), text(row.get("bus"))
        if bus not in bus_ix:
            warnings.append(f"shunt {shunt_id}: bus {bus} not found; skipped")
            continue
        b = bus_ix[bus]
        idx = pp.create_shunt(net, b, q_mvar=num(row.get("q_mvar"), 0.0),
                              vn_kv=float(net.bus.at[b, "vn_kv"]), name=shunt_id,
                              in_service=yes(row.get("in_service")))
        ident.append({"idx": idx, "shunt_id": shunt_id, "ss_code": net.bus.at[b, "ss_code"],
                      "in_central": bool(net.bus.at[b, "in_central"]),
                      "steps": num(row.get("steps"), 1.0)})
    attach(net.shunt, ident)
    return warnings


def element_buses(net, et: str, idx: int) -> set[int]:
    """The buses a line ('l'), transformer ('t') or three-winding transformer ('t3') joins."""
    table, cols = {"l": ("line", ("from_bus", "to_bus")), "t": ("trafo", ("hv_bus", "lv_bus")),
                   "t3": ("trafo3w", ("hv_bus", "mv_bus", "lv_bus"))}[et]
    return {int(net[table].at[idx, c]) for c in cols}


def add_switches(net, switches: pd.DataFrame, bus_ix) -> list[str]:
    """Switches on lines, transformers (2- or 3-winding) or between two buses."""
    warnings, ident = [], []
    line_ix = dict(zip(net.line.name, net.line.index))
    trafo_ix = dict(zip(net.trafo.name, net.trafo.index))
    trafo3w_ix = dict(zip(net.trafo3w.name, net.trafo3w.index))
    for row in switches.to_dict("records"):
        sw_id, bus, et = text(row["switch_id"]), text(row.get("bus")), text(row.get("element_type"), "")
        el = text(row.get("element_id"))
        target = None
        if bus not in bus_ix:
            pass
        elif et == "line" and el in line_ix:
            target = ("l", line_ix[el])
        elif et == "trafo" and el in trafo_ix:
            target = ("t", trafo_ix[el])
        elif et == "trafo" and el in trafo3w_ix:
            target = ("t3", trafo3w_ix[el])
        elif et == "bus" and el in bus_ix:
            target = ("b", bus_ix[el])
        if target is None:
            warnings.append(f"switch {sw_id}: bus {bus} or {et} {el} not found; skipped")
            continue
        if target[0] != "b" and bus_ix[bus] not in element_buses(net, *target):
            # pandapower refuses a branch switch at a bus the branch does not touch.
            warnings.append(f"switch {sw_id}: bus {bus} is not an end of {et} {el}; skipped")
            continue
        idx = pp.create_switch(net, bus_ix[bus], element=target[1], et=target[0],
                               closed=yes(row.get("closed")), name=sw_id)
        ident.append({"idx": idx, "switch_id": sw_id})
    attach(net.switch, ident)
    return warnings


def ensure_slack(net) -> list[str]:
    """If nothing is a slack, make the largest PV generator the slack so a load flow can run."""
    has_slack = bool(net.ext_grid.in_service.any()) or bool((net.gen.slack & net.gen.in_service).any())
    if has_slack:
        return []
    running = net.gen[net.gen.in_service]
    if running.empty:
        return ["no slack: no in-service ext_grid, slack generator, slack boundary or PV unit"]
    # Only an in-service unit can hold the reference; an out-of-service slack solves nothing.
    big = running["max_p_mw"].fillna(running["p_mw"]).idxmax()
    net.gen.at[big, "slack"] = True
    return [f"no slack in the case; generator {net.gen.at[big, 'name']} made the slack"]


def case_frequency(case: pd.DataFrame) -> float:
    """System frequency from net_case, 50 Hz when blank."""
    if case.empty or "frequency_hz" not in case.columns:
        return DEFAULT_FREQUENCY_HZ
    return num(case["frequency_hz"].iloc[0], DEFAULT_FREQUENCY_HZ)


def build_net(net_tables: dict[str, pd.DataFrame], case_id: str, substations: pd.DataFrame, *,
              as_of: date | None = None, statuses=("existing", "committed"), r_temp_c: float = 50.0,
              rating_set: str = "cont", extra: dict[str, pd.DataFrame] | None = None,
              line_in_central: str = "any",
              trafo_defaults: pd.DataFrame | None = None) -> pp.pandapowerNet:
    """Build the pandapower net for one case from T01-shaped tables.

    net_tables: DataFrames keyed by table name (net_bus, net_line, ...; a 'ts.' prefix is fine).
    substations: the register (ss_code, name, in_central) used for codes and the Central flag.
    as_of / statuses: keep only lines and transformers with a wanted status that were
        commissioned by the as-of year (2030 uses statuses existing, committed, planned).
    r_temp_c: conductor temperature line R is corrected to.
    rating_set: cont | emerg | ncc | min; line max_i_ka follows it, so loading_percent is
        against that rating. For transformers use element_results(), which applies rate_mva.
    extra: more T01-shaped elements to add (planned projects), filtered the same way.

    Problems that do not stop the build (a missing bus, typical values used) are kept in
    net["atlas_warnings"]; check_net() reports them with the other checks.
    """
    tables = merged_tables(net_tables, case_id, extra)
    duplicate_warnings = drop_duplicate_ids(tables)
    if tables["net_bus"].empty:
        raise ValueError(f"case {case_id!r} has no buses")
    defaults = trafo_defaults if trafo_defaults is not None else read_transformer_defaults()
    case = tables["net_case"]
    base_mva = num(case["base_mva"].iloc[0], 100.0) if "base_mva" in case.columns and len(case) else 100.0
    freq = case_frequency(case)
    net = pp.create_empty_network(name=str(case_id), f_hz=freq, sn_mva=base_mva)
    by_name, central = substation_lookup(substations)

    warnings = duplicate_warnings + add_buses(net, tables["net_bus"], by_name, central)
    bus_ix = dict(zip(net.bus.bus_id, net.bus.index))
    warnings += add_lines(net, status_filter(tables["net_line"], as_of, statuses), bus_ix, r_temp_c,
                          rating_set, freq, line_in_central)
    warnings += add_trafos(net, status_filter(tables["net_trafo"], as_of, statuses), bus_ix,
                           rating_set, defaults, by_name, central)
    warnings += add_trafos3w(net, status_filter(tables["net_trafo3w"], as_of, statuses), bus_ix,
                             defaults, by_name, central)
    warnings += add_gens(net, tables["net_gen"], bus_ix)
    warnings += add_boundary(net, tables["net_boundary"], bus_ix)
    warnings += add_loads(net, tables["net_load"], bus_ix, by_name, central)
    warnings += add_shunts(net, tables["net_shunt"], bus_ix)
    warnings += add_switches(net, tables["net_switch"], bus_ix)
    warnings += ensure_slack(net)
    net["atlas_warnings"] = warnings
    net["atlas_case"] = {"case_id": str(case_id), "as_of": str(as_of) if as_of else None,
                         "statuses": list(statuses), "r_temp_c": r_temp_c, "rating_set": rating_set}
    return net


# ---------------------------------------------------------------------------
# Registers for results.element and results.bus
# ---------------------------------------------------------------------------

ELEMENT_COLUMNS = ["element_type", "element_id", "name", "ss_from", "ss_to", "kv", "length_km",
                   "in_central", "is_equivalent", "rate_mva", "rate_basis", "commissioning_year",
                   "tower_group", "status"]


def col(df: pd.DataFrame, name: str, default=None) -> pd.Series:
    """A column of df, or a column of the default value when it is missing."""
    return df[name] if name in df.columns else pd.Series(default, index=df.index, dtype=object)


def register_rows(df: pd.DataFrame, element_type: str, **cols) -> pd.DataFrame:
    """Rows of the element register for one pandapower table."""
    if df.empty:
        return pd.DataFrame(columns=ELEMENT_COLUMNS)
    out = pd.DataFrame({"element_type": element_type, "element_id": df["name"].astype(str)},
                       index=df.index)
    for c in ELEMENT_COLUMNS[2:]:
        out[c] = cols[c] if c in cols else None
    return out


def as_flag(value) -> bool:
    """A stored True/False that may be blank: blank means False."""
    return False if is_blank(value) else bool(value)


def element_register(net) -> pd.DataFrame:
    """One row per line, transformer, generator (incl. boundary infeeds), load and shunt,
    with the columns of results.element (minus run_id)."""
    vn = net.bus.vn_kv
    ss = net.bus.get("ss_code", pd.Series(None, index=net.bus.index))
    parts = []
    ln = net.line
    if len(ln):
        parts.append(register_rows(
            ln, "line", name=col(ln, "display_name"), ss_from=col(ln, "ss_from"), ss_to=col(ln, "ss_to"),
            kv=ln.from_bus.map(vn), length_km=ln.length_km, in_central=col(ln, "in_central", False),
            is_equivalent=col(ln, "is_equivalent", False), rate_mva=col(ln, "rate_mva"),
            rate_basis=col(ln, "rate_basis"), commissioning_year=col(ln, "commissioning_year"),
            tower_group=col(ln, "tower_group"), status=col(ln, "status")))
    for table, et, hv in (("trafo", "trafo", "hv_bus"), ("trafo3w", "trafo3w", "hv_bus")):
        tr = net[table]
        if len(tr):
            parts.append(register_rows(
                tr, et, name=col(tr, "display_name"), ss_from=col(tr, "ss_code"), ss_to=col(tr, "ss_code"),
                kv=tr.vn_hv_kv, in_central=col(tr, "in_central", False),
                is_equivalent=col(tr, "is_equivalent", False), rate_mva=col(tr, "rate_mva"),
                rate_basis=col(tr, "rate_basis"), commissioning_year=col(tr, "commissioning_year"),
                status=col(tr, "status")))
    for table in ("ext_grid", "gen", "sgen"):
        g = net[table]
        if len(g):
            parts.append(register_rows(
                g, "gen", name=col(g, "display_name"), ss_from=g.bus.map(ss), ss_to=g.bus.map(ss),
                kv=g.bus.map(vn), in_central=col(g, "in_central", False),
                is_equivalent=col(g, "is_equivalent", False), status="existing"))
    for table, et in (("load", "load"), ("shunt", "shunt")):
        d = net[table]
        if len(d):
            parts.append(register_rows(
                d, et, name=col(d, "display_name") if "display_name" in d else d["name"],
                ss_from=d.bus.map(ss), ss_to=d.bus.map(ss), kv=d.bus.map(vn),
                in_central=col(d, "in_central", False), is_equivalent=False, status="existing"))
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame(columns=ELEMENT_COLUMNS)
    # Drop all-blank columns before concat (pandas warns otherwise), then restore the order.
    parts = [p.dropna(axis=1, how="all") for p in parts]
    out = pd.concat(parts, ignore_index=True).reindex(columns=ELEMENT_COLUMNS)
    for c in ("in_central", "is_equivalent"):
        out[c] = out[c].map(as_flag)
    out["commissioning_year"] = pd.to_numeric(out["commissioning_year"], errors="coerce").astype("Int64")
    for c in ("kv", "length_km", "rate_mva"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def bus_register(net) -> pd.DataFrame:
    """One row per bus with the columns of results.bus (minus run_id)."""
    b = net.bus
    return pd.DataFrame({
        "bus_id": b["name"].astype(str).values,
        "ss_code": col(b, "ss_code").values,
        "vn_kv": b.vn_kv.astype(float).values,
        "in_central": col(b, "in_central", False).map(as_flag).values,
    })
