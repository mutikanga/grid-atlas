"""Turn the T12 hand-built schedules into T01-shaped network tables.

If Planning's model is late, the team fills T12 (templates/spec/T12_handbuilt_network.toml)
from line and transformer schedules. This module turns it into the same tables as T01,
with case_id 'HANDBUILT', so the one builder (engine/network/build.py) serves both paths.

Parameters the schedules do not give come from typical values:
- lines: config/conductors.csv (R at 20 C, X, B per km and ampacity per conductor and kV),
  with bundling when conductors_per_phase is more than the row's own bundle;
- line length, when blank: straight-line distance times the routing factor in
  config/engine/network.toml [handbuilt];
- transformers: config/transformer_defaults.csv by MVA band.
Every such row is marked param_source 'typical', and everything built on it is APPROXIMATE.

Ids follow docs/dev/contracts.md section 2: buses KAW-132-1, lines L-KAW-MUT-132-1,
transformers T-KAW-1, generators G-<PLANT>-<n>, loads D-KAW-1.
"""

from __future__ import annotations

import math
import re
import tomllib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
CASE_ID = "HANDBUILT"
# 2*pi*f * 2*pi*eps0 in uS/km at 50 Hz, for 1 / ln(D/r): the susceptance of a line per km.
B_CONST_US_PER_KM_50HZ = 2 * math.pi * 50 * 2 * math.pi * 8.854e-12 * 1e9
# 2*pi*f * 2e-4 ohm/km at 50 Hz, for ln(D/GMR): the reactance of a line per km.
X_CONST_OHM_PER_KM_50HZ = 2 * math.pi * 50 * 2e-4

DEFAULT_HB_CFG = {"routing_factor": 1.2, "bundle_spacing_m": 0.40, "frequency_hz": 50.0,
                  "base_mva": 100.0, "case_date": "2026-09-30", "default_vm_pu": 1.0}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def blank(value) -> bool:
    """True for None, NaN and empty strings."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def num(value, default: float = math.nan) -> float:
    """value as a float, or the default when blank."""
    return default if blank(value) else float(value)


def kv_label(kv: float) -> str:
    """kV as used in ids: 132.0 -> '132', 0.4 -> '0.4'."""
    kv = float(kv)
    return str(int(kv)) if kv.is_integer() else f"{kv:g}"


def bus_id(ss: str, kv: float) -> str:
    """Bus id per the contract: one bus per substation per voltage, e.g. KAW-132-1."""
    return f"{ss}-{kv_label(kv)}-1"


def line_id(a: str, b: str, kv: float, circuit: int) -> str:
    """Line id with the two substations in alphabetical order: L-KAW-MUT-132-1."""
    a, b = sorted([a, b])
    return f"L-{a}-{b}-{kv_label(kv)}-{int(circuit)}"


def code(row: dict, col: str) -> str:
    """Substation code from a row: the loader's resolved <col>_code, else the cell itself."""
    value = row.get(f"{col}_code")
    if blank(value):
        value = row.get(col)
    return str(value).strip().upper()


def norm(value) -> str:
    """Lower case, letters and digits only, for name matching."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS 84 points."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_kv_levels(text) -> list[float]:
    """'220/132/33' -> [220.0, 132.0, 33.0]."""
    return [float(x) for x in re.split(r"[/,; ]+", str(text or "").strip()) if x]


def table(tables: dict[str, pd.DataFrame], name: str) -> pd.DataFrame:
    """One T12 table by name, with or without the 'ts.' prefix; missing gives empty."""
    for key in (name, f"ts.{name}"):
        if key in tables and tables[key] is not None:
            return tables[key]
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Typical parameters
# ---------------------------------------------------------------------------

def read_config(path: Path | None = None) -> dict:
    """[handbuilt] settings from config/engine/network.toml, with defaults."""
    path = path or CONFIG_DIR / "engine" / "network.toml"
    cfg = dict(DEFAULT_HB_CFG)
    if path.exists():
        with open(path, "rb") as f:
            cfg.update(tomllib.load(f).get("handbuilt", {}))
    return cfg


def read_conductors(path: Path | None = None) -> pd.DataFrame:
    """config/conductors.csv: typical per-km values per conductor and voltage."""
    return pd.read_csv(path or CONFIG_DIR / "conductors.csv")


def read_trafo_defaults(path: Path | None = None) -> pd.DataFrame:
    """config/transformer_defaults.csv: typical impedances by MVA band."""
    return pd.read_csv(path or CONFIG_DIR / "transformer_defaults.csv")


def conductor_row(conductors: pd.DataFrame, name: str, kv: float) -> dict:
    """The conductors.csv row for a conductor at a voltage. Falls back to the nearest
    voltage listed for that conductor. Raises KeyError for an unknown conductor."""
    rows = conductors[conductors["conductor"].map(norm) == norm(name)]
    if rows.empty:
        known = ", ".join(sorted(conductors["conductor"].unique()))
        raise KeyError(f"conductor {name!r} is not in config/conductors.csv (known: {known})")
    nearest = (rows["kv"] - kv).abs().idxmin()
    return rows.loc[nearest].to_dict()


def bundled(cond: dict, n: int, spacing_m: float) -> dict:
    """Per-km values for n identical sub-conductors per phase, from single-conductor values.

    R and ampacity scale with n. X and B change through the bundle's equivalent radius:
    GMR_eq = (GMR * s^(n-1))^(1/n), and the same for the outer radius.
    """
    if n <= 1:
        return cond
    gmr = cond["gmr_mm"] / 1000.0
    r = cond["diameter_mm"] / 2000.0
    gmr_eq = (gmr * spacing_m ** (n - 1)) ** (1.0 / n)
    r_eq = (r * spacing_m ** (n - 1)) ** (1.0 / n)
    x = cond["x_ohm_per_km"] - X_CONST_OHM_PER_KM_50HZ * math.log(gmr_eq / gmr)
    ln_d_r = B_CONST_US_PER_KM_50HZ / cond["b_us_per_km"] - math.log(r_eq / r)
    return {**cond, "bundle": n, "r20_ohm_per_km": cond["r20_ohm_per_km"] / n, "x_ohm_per_km": x,
            "b_us_per_km": B_CONST_US_PER_KM_50HZ / ln_d_r, "ampacity_a": cond["ampacity_a"] * n}


def line_params(conductors: pd.DataFrame, name: str, kv: float, per_phase, spacing_m: float) -> dict:
    """R (20 C), X, B per km and ampacity for one line from its conductor and bundle."""
    cond = conductor_row(conductors, name, kv)
    own = int(cond.get("bundle", 1) or 1)
    n = own if blank(per_phase) else int(per_phase)
    if n != own and own == 1:
        cond = bundled(cond, n, spacing_m)
    return cond


def typical_trafo(sn_mva: float, defaults: pd.DataFrame) -> dict:
    """Typical vk, vkr, pfe (kW) and i0 for a transformer of sn_mva."""
    band = defaults[(defaults.mva_min <= sn_mva) & (sn_mva < defaults.mva_max)]
    row = (band if len(band) else defaults.iloc[[-1]]).iloc[0]
    return {"vk_percent": float(row.vk_percent), "vkr_percent": float(row.vkr_percent),
            "pfe_kw": float(row.pfe_percent) / 100.0 * sn_mva * 1000.0,
            "i0_percent": float(row.i0_percent)}


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

def build_buses(subs: pd.DataFrame, extra_levels: dict[str, set[float]]) -> pd.DataFrame:
    """One bus per substation per voltage level. extra_levels adds levels used by lines,
    transformers or generators that kv_levels left out."""
    rows = []
    for s in subs.to_dict("records"):
        ss = code(s, "ss_code")
        levels = set(parse_kv_levels(s.get("kv_levels"))) | extra_levels.get(ss, set())
        for kv in sorted(levels, reverse=True):
            rows.append({"case_id": CASE_ID, "bus_id": bus_id(ss, kv),
                         "name": f"{s.get('name') or ss} {kv_label(kv)} kV", "substation": s.get("name") or ss,
                         "substation_code": ss, "vn_kv": kv, "zone": None, "in_service": "Y",
                         # Not a T01 column: build_net uses it when ref.substation lacks ss.
                         "in_central": s.get("in_central"),
                         "v_min_pu": None, "v_max_pu": None})
    return pd.DataFrame(rows)


def levels_used(hb: dict[str, pd.DataFrame]) -> dict[str, set[float]]:
    """Voltage levels each substation needs, from lines, transformers, gens and boundary."""
    used: dict[str, set[float]] = {}
    for r in table(hb, "hb_line").to_dict("records"):
        for col in ("from_ss", "to_ss"):
            used.setdefault(code(r, col), set()).add(float(r["kv"]))
    for r in table(hb, "hb_trafo").to_dict("records"):
        used.setdefault(code(r, "substation"), set()).update({float(r["hv_kv"]), float(r["lv_kv"])})
    for r in table(hb, "hb_gen").to_dict("records"):
        used.setdefault(code(r, "substation"), set()).add(float(r["connection_kv"]))
    for r in table(hb, "hb_boundary").to_dict("records"):
        used.setdefault(code(r, "substation"), set()).add(float(r["kv"]))
    return used


def build_lines(lines: pd.DataFrame, subs: pd.DataFrame, conductors: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Line circuits with typical per-km values; blank length = haversine x routing factor."""
    where = {code(s, "ss_code"): (num(s.get("lat")), num(s.get("lon"))) for s in subs.to_dict("records")}
    rows = []
    for r in lines.to_dict("records"):
        a, b = sorted([code(r, "from_ss"), code(r, "to_ss")])
        kv = float(r["kv"])
        p = line_params(conductors, str(r["conductor"]), kv, r.get("conductors_per_phase"),
                        float(cfg["bundle_spacing_m"]))
        length = num(r.get("length_km"))
        length_note = "schedule length"
        if math.isnan(length):
            ends = [where.get(ss, (math.nan, math.nan)) for ss in (a, b)]
            if any(math.isnan(v) for end in ends for v in end):
                raise ValueError(f"hb_line {a}-{b} {kv_label(kv)} kV: length_km is blank and "
                                 "hb_substation has no lat/lon for both ends; give the length "
                                 "or add the substation")
            length = haversine_km(*ends[0], *ends[1]) * float(cfg["routing_factor"])
            length_note = f"straight line x {cfg['routing_factor']}"
        rows.append({
            "case_id": CASE_ID, "line_id": line_id(a, b, kv, r["circuit"]),
            "name": f"{a}-{b} {kv_label(kv)} kV circuit {int(r['circuit'])}",
            "from_bus": bus_id(a, kv), "to_bus": bus_id(b, kv), "circuit": int(r["circuit"]),
            "length_km": round(length, 3), "conductor": r["conductor"], "conductors_per_phase": int(p.get("bundle", 1)),
            "r_ohm_per_km": p["r20_ohm_per_km"], "x_ohm_per_km": p["x_ohm_per_km"],
            "b_us_per_km": p["b_us_per_km"], "r_temp_c": 20.0,
            "rate_cont_mva": round(math.sqrt(3) * kv * p["ampacity_a"] / 1000.0, 1),
            "rate_emerg_mva": None, "rate_ncc_mva": None, "rate_ncc_basis": None,
            "commissioning_year": r.get("commissioning_year"), "status": r.get("status") or "existing",
            "in_service": "Y", "tower_group": r.get("tower_group"), "param_source": "typical",
            "notes": f"typical: {r['conductor']} from config/conductors.csv; {length_note}",
        })
    return pd.DataFrame(rows)


def trafo_numbers(trafos: pd.DataFrame) -> list[int]:
    """The n in T-<SS>-<n>: the schedule's unit number when units are unique within the
    substation, otherwise a running number (highest voltage first, then unit)."""
    if trafos.empty:
        return []
    ss = trafos.apply(lambda r: code(r, "substation"), axis=1)
    unique = not pd.DataFrame({"ss": ss, "unit": trafos["unit"]}).duplicated().any()
    if unique:
        return [int(u) for u in trafos["unit"]]
    order = trafos.assign(_ss=ss).sort_values(["_ss", "hv_kv", "lv_kv", "unit"],
                                              ascending=[True, False, False, True])
    numbers = order.groupby("_ss").cumcount() + 1
    return [int(n) for n in numbers.reindex(trafos.index)]


def build_trafos(trafos: pd.DataFrame, defaults: pd.DataFrame) -> pd.DataFrame:
    """Two-winding transformers with typical vk (if blank), vkr, pfe and i0 for their size."""
    rows = []
    for (ix, r), n in zip(trafos.iterrows(), trafo_numbers(trafos)):
        ss, sn = code(r, "substation"), float(r["mva"])
        typ = typical_trafo(sn, defaults)
        rows.append({
            "case_id": CASE_ID, "trafo_id": f"T-{ss}-{n}",
            "name": f"{ss} T{n} {kv_label(r['hv_kv'])}/{kv_label(r['lv_kv'])} kV",
            "substation": ss, "substation_code": ss, "hv_bus": bus_id(ss, r["hv_kv"]),
            "lv_bus": bus_id(ss, r["lv_kv"]), "sn_mva": sn, "vn_hv_kv": float(r["hv_kv"]),
            "vn_lv_kv": float(r["lv_kv"]), "vk_percent": num(r.get("vk_percent"), typ["vk_percent"]),
            "vkr_percent": typ["vkr_percent"], "load_loss_kw": None, "pfe_kw": round(typ["pfe_kw"], 2),
            "i0_percent": typ["i0_percent"], "vector_group": None, "tap_side": None,
            "tap_neutral": None, "tap_min": None, "tap_max": None, "tap_step_percent": None,
            "tap_pos": None, "rate_cont_mva": sn, "rate_emerg_mva": None, "rate_ncc_mva": None,
            "rate_ncc_basis": None, "commissioning_year": r.get("commissioning_year"),
            "status": r.get("status") or "existing", "in_service": "Y", "param_source": "typical",
            "notes": "typical: impedances from config/transformer_defaults.csv"
                     + ("" if blank(r.get("vk_percent")) else " (vk from schedule)"),
        })
    return pd.DataFrame(rows)


def registered_code(plant: str, plants: pd.DataFrame | None) -> str | None:
    """The plant's code in the plants register, matched by name or code, or None."""
    if plants is None or plants.empty:
        return None
    match = plants[plants["name"].map(norm) == norm(plant)]
    if len(match):
        return str(match["plant_code"].iloc[0])
    match = plants[plants["plant_code"].astype(str).str.upper() == str(plant).upper()]
    if len(match):
        return str(match["plant_code"].iloc[0])
    return None


def plant_code(plant: str, plants: pd.DataFrame | None) -> str:
    """Plant code from the plants register by name, else made from the name."""
    found = registered_code(plant, plants)
    if found:
        return found
    words = [re.sub(r"[^A-Za-z]", "", w).upper() for w in str(plant).split()]
    words = [w for w in words if w]
    if not words:
        return "GEN"
    # First word's first three letters plus the initials of the rest: "Example Hydro" -> EXAH.
    return words[0][:3] + "".join(w[0] for w in words[1:])


def build_gens(gens: pd.DataFrame, plants: pd.DataFrame | None, cfg: dict) -> pd.DataFrame:
    """Generators. Solar and wind run PQ; the rest PV at default_vm_pu. p_mw is a 0 MW
    placeholder: the snapshot (engine/cases.py) sets the dispatch."""
    rows = []
    of_plant: dict[str, str] = {}   # normalised plant name -> its code, fixed at first sight
    for r in gens.to_dict("records"):
        ss = code(r, "substation")
        plant = norm(r["plant"])
        if plant not in of_plant:
            if not blank(r.get("plant_code")):
                pc = str(r["plant_code"]).upper()
            elif registered_code(r["plant"], plants):
                pc = registered_code(r["plant"], plants)  # two names of one plant share it
            else:
                # A made-up code: two different plants must not share it (EXAH, EXAH2).
                pc = base = plant_code(r["plant"], None)
                taken, k = set(of_plant.values()), 1
                while pc in taken:
                    k += 1
                    pc = f"{base}{k}"
            of_plant[plant] = pc
        pc = of_plant[plant]  # every unit of a plant gets the same code
        if str(r.get("status") or "existing") not in ("existing", "committed"):
            continue  # T01 generators have no status column; planned units are left out
        rows.append({
            "case_id": CASE_ID, "gen_id": f"G-{pc}-{int(r['unit'])}", "name": f"{r['plant']} unit {int(r['unit'])}",
            "bus": bus_id(ss, r["connection_kv"]), "plant": r["plant"], "plant_code": pc,
            "technology": r["technology"], "p_mw": 0.0, "p_max_mw": float(r["p_max_mw"]),
            "p_min_mw": r.get("p_min_mw"), "q_min_mvar": r.get("q_min_mvar"), "q_max_mvar": r.get("q_max_mvar"),
            "vm_pu": float(cfg["default_vm_pu"]),
            "control": "PQ" if r["technology"] in ("solar", "wind") else "PV",
            "connection_kv": float(r["connection_kv"]), "in_service": "Y",
        })
    return pd.DataFrame(rows)


def connected_bus_ids(lines: pd.DataFrame, trafos: pd.DataFrame) -> set[str]:
    """Bus ids that at least one line or transformer touches."""
    ids: set[str] = set()
    for df, cols in ((lines, ("from_bus", "to_bus")), (trafos, ("hv_bus", "lv_bus"))):
        for c in cols:
            if c in df.columns:
                ids.update(df[c].astype(str))
    return ids


def build_loads(buses: pd.DataFrame, connected: set[str] | None = None) -> pd.DataFrame:
    """One load per substation at its lowest-voltage connected bus: share 1, 0 MW placeholder.

    A level listed in kv_levels with no transformer (for example 33 kV at a substation whose
    132/33 kV units are missing from the schedule) is skipped, so the load is not islanded.
    """
    if buses.empty:
        return pd.DataFrame()
    df = buses.assign(_connected=buses["bus_id"].isin(connected) if connected else True)
    df = df.sort_values(["substation_code", "_connected", "vn_kv"], ascending=[True, False, True])
    lowest = df.groupby("substation_code", sort=True).head(1)
    return pd.DataFrame([{
        "case_id": CASE_ID, "load_id": f"D-{b['substation_code']}-1", "bus": b["bus_id"],
        "substation": b["substation"], "substation_code": b["substation_code"], "bsp_name": b["substation"],
        "share": 1.0, "p_mw": 0.0, "q_mvar": 0.0, "in_service": "Y",
    } for b in lowest.to_dict("records")])


def build_boundary(boundary: pd.DataFrame) -> pd.DataFrame:
    """Boundary points at SS-kV-1 buses."""
    return pd.DataFrame([{
        "case_id": CASE_ID, "bus": bus_id(code(r, "substation"), r["kv"]), "kind": r["kind"],
        "vm_pu": r.get("vm_pu"), "p_mw": r.get("p_mw"), "note": r.get("note"),
    } for r in boundary.to_dict("records")])


def build_case(cfg: dict) -> pd.DataFrame:
    """The single HANDBUILT case row."""
    return pd.DataFrame([{
        "case_id": CASE_ID, "case_type": "as_operated_peak", "case_date": cfg["case_date"],
        "case_hour": None, "description": "Hand-built approximate model from T12 schedules (typical parameters)",
        "source_tool": "handbuilt", "tool_version": None, "base_mva": float(cfg["base_mva"]),
        "frequency_hz": float(cfg["frequency_hz"]), "perimeter": "central",
        "rating_note": "line ratings from typical conductor ampacity; transformer ratings = nameplate MVA",
        "contact": None,
    }])


def to_net_tables(hb_tables: dict[str, pd.DataFrame], *, plants: pd.DataFrame | None = None,
                  cfg: dict | None = None, conductors: pd.DataFrame | None = None,
                  trafo_defaults: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Convert T12 tables (hb_substation, hb_line, hb_trafo, hb_gen, hb_boundary) into
    T01-shaped tables (net_case, net_bus, ...) with case_id 'HANDBUILT'.

    plants: optional plants register (plant_code, name) for generator ids.
    cfg, conductors, trafo_defaults: override the config files (tests use this).
    """
    cfg = {**DEFAULT_HB_CFG, **(cfg if cfg is not None else read_config())}
    conductors = conductors if conductors is not None else read_conductors()
    defaults = trafo_defaults if trafo_defaults is not None else read_trafo_defaults()
    subs = table(hb_tables, "hb_substation")
    if subs.empty:
        raise ValueError("hb_substation is empty: the hand-built model needs its substations")
    buses = build_buses(subs, levels_used(hb_tables))
    trafos = table(hb_tables, "hb_trafo")
    net_line = build_lines(table(hb_tables, "hb_line"), subs, conductors, cfg)
    net_trafo = build_trafos(trafos.reset_index(drop=True), defaults) if not trafos.empty else pd.DataFrame()
    return {
        "net_case": build_case(cfg),
        "net_bus": buses,
        "net_line": net_line,
        "net_trafo": net_trafo,
        "net_trafo3w": pd.DataFrame(),
        "net_gen": build_gens(table(hb_tables, "hb_gen"), plants, cfg),
        "net_load": build_loads(buses, connected_bus_ids(net_line, net_trafo)),
        "net_shunt": pd.DataFrame(),
        "net_switch": pd.DataFrame(),
        "net_boundary": build_boundary(table(hb_tables, "hb_boundary")),
    }


def substations_register(hb_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """A substations register (ss_code, name, in_central, lat, lon) from hb_substation,
    for tests or when ref.substation lacks a hand-built substation."""
    subs = table(hb_tables, "hb_substation")
    return pd.DataFrame({"ss_code": [code(r, "ss_code") for r in subs.to_dict("records")],
                         "name": subs["name"].values, "in_central": subs["in_central"].values,
                         "lat": subs["lat"].values, "lon": subs["lon"].values})
