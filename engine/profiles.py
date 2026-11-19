"""Hourly load and generation shapes for one month (F3b).

A load flow gives MW at one instant, but losses are wanted in MWh for a month.
So each month is represented by 24-hour shapes for two day types:

- WD: a weekday that is not a public holiday;
- NWD: a Saturday, Sunday or public holiday.

For every substation and day type we build P(h) and Q(h) for h = 0..23, from the
best source available, and record which one was used (``profile_source``):

1. ``scada``: the month's own SCADA, averaged over every supplied day of that type;
2. ``borrowed``: the same substation's SCADA shape from the nearest month that has it;
3. ``standard``: a generic shape for the substation's load class
   (``config/profiles/standard_profiles.csv``), fitted to NCC's monthly energy and peak.

engine/cases.py then scales the shapes so the month's energy matches NCC's figure
and turns them into weighted load-flow snapshots.

The functions are pure: they take DataFrames (or an Inputs bundle) and return DataFrames.
"""
from __future__ import annotations

import calendar
import logging
import math
from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # imported only for type hints, to avoid a circular import
    from engine.inputs import Inputs

log = logging.getLogger(__name__)

DAY_TYPES = ("WD", "NWD")
HOURS = list(range(24))
ROOT = Path(__file__).resolve().parents[1]

# The order says which source is "worst": a snapshot mixing sources reports the worst one.
SOURCE_RANK = {"scada": 0, "borrowed": 1, "standard": 2}

# Defaults for config/engine/cases.toml, so a missing key never breaks a run.
DEFAULTS: dict[str, Any] = {
    "base_case": "",
    "pf_default": 0.95,
    "scale_warn_low": 0.75,
    "scale_warn_high": 1.25,
    "standard_profiles": "config/profiles/standard_profiles.csv",
    "default_class": "mixed",
    "borrow_max_months": 12,
    "scada_drop_quality": ["bad", "missing"],
    "coincidence": {"default_factor": 1.0},
    "class_by_substation": {},
}

PROFILE_COLUMNS = ["ss_code", "day_type", "hour", "p_mw", "q_mvar", "profile_source", "n_days", "note"]
GEN_PROFILE_COLUMNS = ["gen_id", "day_type", "hour", "p_mw", "profile_source"]


# --------------------------------------------------------------------------- config


def cases_cfg(cfg: dict | None) -> dict[str, Any]:
    """Return the ``cases`` settings with defaults filled in.

    Accepts either the full merged engine config (``cfg["cases"]``) or the cases
    section itself, so unit tests can pass a small dict.
    """
    cfg = cfg or {}
    section = cfg.get("cases", cfg) if isinstance(cfg, dict) else {}
    out = dict(DEFAULTS)
    out.update(section or {})
    out["coincidence"] = {**DEFAULTS["coincidence"], **(section or {}).get("coincidence", {})}
    return out


def q_ratio_from_pf(pf: float) -> float:
    """Q/P for a lagging power factor, for example 0.95 -> 0.329."""
    pf = min(max(float(pf), 0.01), 1.0)
    return math.tan(math.acos(pf))


# --------------------------------------------------------------------------- calendar


def month_days(month: str) -> list[date]:
    """All calendar days of a 'YYYY-MM' month."""
    year, mon = (int(x) for x in month.split("-"))
    n = calendar.monthrange(year, mon)[1]
    return [date(year, mon, d) for d in range(1, n + 1)]


def holiday_set(holidays: pd.DataFrame | set | None) -> set[date]:
    """Turn ref.holiday (column ``day``, or ``date``) into a set of dates."""
    if holidays is None:
        return set()
    if isinstance(holidays, set):
        return holidays
    if holidays.empty:
        return set()
    col = "day" if "day" in holidays.columns else "date"
    return set(pd.to_datetime(holidays[col]).dt.date)


def day_type(d: date, holidays: set[date]) -> str:
    """WD for a working weekday, NWD for a weekend day or a public holiday."""
    return "NWD" if d.weekday() >= 5 or d in holidays else "WD"


def day_type_counts(month: str, holidays: pd.DataFrame | set | None) -> dict[str, int]:
    """Number of WD and NWD days in the month. They always add up to the days in the month."""
    hols = holiday_set(holidays)
    counts = Counter(day_type(d, hols) for d in month_days(month))
    return {dt: counts.get(dt, 0) for dt in DAY_TYPES}


def month_offset(a: str, b: str) -> int:
    """Signed number of months from a to b ('2026-01' to '2026-03' is 2)."""
    ya, ma = (int(x) for x in a.split("-"))
    yb, mb = (int(x) for x in b.split("-"))
    return (yb - ya) * 12 + (mb - ma)


# --------------------------------------------------------------------------- small helpers


def code_column(df: pd.DataFrame, col: str) -> pd.Series:
    """The resolved ``<col>_code`` column, falling back to the raw name where it is blank."""
    if f"{col}_code" in df.columns:
        codes = df[f"{col}_code"]
        return codes.where(codes.notna() & (codes.astype(str) != ""), df.get(col))
    return df[col] if col in df.columns else pd.Series([None] * len(df), index=df.index)


def in_service_mask(df: pd.DataFrame) -> pd.Series:
    """True for rows that are in service. Blank counts as in service.

    The database gives booleans, but the hand-built converter writes the template's
    'Y' / 'N' text, and ``bool('N')`` is True, so text is read explicitly.
    """
    if "in_service" not in df.columns:
        return pd.Series(True, index=df.index)

    def yes(v: Any) -> bool:
        if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
            return True
        if isinstance(v, str):
            return v.strip().upper() not in ("N", "NO", "FALSE", "0")
        return bool(v)

    return df["in_service"].map(yes).astype(bool)


def rows_for_month(df: pd.DataFrame | None, month: str) -> pd.DataFrame:
    """Rows of a monthly table for one 'YYYY-MM' month (``month`` already normalised)."""
    if df is None or df.empty or "month" not in df.columns:
        return pd.DataFrame()
    return df[df["month"].astype(str).str[:7] == month]


def ncc_substation_month(inputs: Inputs, month: str) -> pd.DataFrame:
    """NCC substation figures for the month, one row per substation code.

    A substation reported on several metering points is summed (energy, peaks, minima).
    Summing several meters' peaks overstates the substation peak slightly; it is rare.
    """
    rows = rows_for_month(inputs.substation_monthly, month)
    cols = ["energy_mwh", "peak_mw", "peak_mvar", "coincident_mw", "min_mw"]
    if rows.empty:
        return pd.DataFrame(columns=cols, index=pd.Index([], name="ss_code"))
    rows = rows.assign(ss_code=code_column(rows, "substation"))
    for col in cols:
        if col not in rows.columns:
            rows[col] = np.nan
    return rows.groupby("ss_code")[cols].sum(min_count=1)


def _fill_hours(values: pd.Series) -> pd.Series:
    """Reindex to hours 0..23 and fill gaps by straight-line interpolation around the clock."""
    s = values.reindex(HOURS).astype(float)
    if s.isna().all() or not s.isna().any():
        return s
    tripled = pd.concat([s, s, s], ignore_index=True).interpolate(limit_direction="both")
    return pd.Series(tripled.iloc[24:48].to_numpy(), index=HOURS)


# --------------------------------------------------------------------------- SCADA


def point_sign(convention: str | None) -> float:
    """+1 when a positive value means 'from the busbar into the bay' (our assumption), else -1.

    Only explicit wording that says the opposite flips the sign.
    """
    text = " ".join(str(convention or "").lower().replace("bus bar", "busbar").split()) + " "
    reversed_markers = ("into the busbar", "to the busbar", "towards the busbar", "into busbar", "to busbar",
                        "into the bus ", "bay to bus")
    forward_markers = ("from the busbar", "from busbar", "out of the busbar", "out of busbar", "bus to bay")

    def first(markers: tuple[str, ...]) -> int:
        hits = [text.find(m) for m in markers if m in text]
        return min(hits) if hits else len(text) + 1

    # Text such as "+ = from the busbar; - = to the busbar" names both directions:
    # whichever direction is named first is the positive one.
    return -1.0 if first(reversed_markers) < first(forward_markers) else 1.0


def clean_scada(scada: pd.DataFrame, drop_quality: list[str] | tuple[str, ...] = ("bad", "missing")) -> pd.DataFrame:
    """Drop bad rows and average sub-hourly values into hours (timestamp = start of hour)."""
    if scada is None or scada.empty:
        return pd.DataFrame(columns=["timestamp", "point_id", "value"])
    df = scada
    if "quality" in df.columns:
        df = df[~df["quality"].isin(list(drop_quality))]
    df = df.dropna(subset=["value"])
    df = df.assign(timestamp=pd.to_datetime(df["timestamp"]).dt.floor("h"))
    return df.groupby(["timestamp", "point_id"], as_index=False)["value"].mean()


def select_load_points(points: pd.DataFrame) -> pd.DataFrame:
    """Choose the SCADA P and Q points that measure each substation's load.

    Rule, per substation:
    - bulk supply point bays (element_type ``bsp``) when there are any, because they
      measure exactly what the substation delivers;
    - otherwise the transformer bays measured on the HV side (winding hv, na or blank)
      at the lowest voltage present, so a 220/132/33 kV site counts its 132/33 kV
      transformers once and not the 220/132 kV ones as well.
    With our sign convention (+ = from the busbar into the bay) a positive value is load.
    Returns columns point_id, ss_code, quantity, sign.
    """
    cols = ["point_id", "ss_code", "quantity", "sign"]
    if points is None or points.empty:
        return pd.DataFrame(columns=cols)
    pts = points[points["quantity"].isin(["P", "Q"])].copy()
    pts["ss_code"] = code_column(pts, "substation")
    chosen = []
    for _, grp in pts.groupby("ss_code"):
        bsp = grp[grp["element_type"] == "bsp"]
        if not bsp.empty:
            chosen.append(bsp)
            continue
        trafo = grp[grp["element_type"] == "transformer"]
        if "winding" in trafo.columns:
            trafo = trafo[~trafo["winding"].isin(["lv", "mv"])]
        if "voltage_kv" in trafo.columns and trafo["voltage_kv"].notna().any():
            trafo = trafo[trafo["voltage_kv"] == trafo["voltage_kv"].min()]
        if not trafo.empty:
            chosen.append(trafo)
    if not chosen:
        return pd.DataFrame(columns=cols)
    out = pd.concat(chosen)
    conv = out["sign_convention"] if "sign_convention" in out.columns else pd.Series(None, index=out.index)
    out["sign"] = [point_sign(c) for c in conv]
    return out[cols].reset_index(drop=True)


def substation_hourly(clean: pd.DataFrame, load_points: pd.DataFrame) -> pd.DataFrame:
    """Hourly load per substation: the signed sum of its chosen points.

    An hour is kept only when every P point of that substation reported, so a missing
    bay does not make the load look low. If no hour is complete, all hours are kept.
    Returns columns ss_code, timestamp, p_mw, q_mvar (q_mvar NaN when no Q points).
    """
    cols = ["ss_code", "timestamp", "p_mw", "q_mvar"]
    if clean.empty or load_points.empty:
        return pd.DataFrame(columns=cols)
    df = clean.merge(load_points, on="point_id")
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["value"] = df["value"] * df["sign"]
    p = df[df["quantity"] == "P"]
    n_points = load_points[load_points["quantity"] == "P"].groupby("ss_code")["point_id"].nunique()
    agg = p.groupby(["ss_code", "timestamp"]).agg(p_mw=("value", "sum"), n=("point_id", "nunique")).reset_index()
    agg["complete"] = agg["n"] == agg["ss_code"].map(n_points)
    has_complete = agg.groupby("ss_code")["complete"].transform("any")
    agg = agg[agg["complete"] | ~has_complete]
    q = df[df["quantity"] == "Q"].groupby(["ss_code", "timestamp"])["value"].sum().rename("q_mvar").reset_index()
    out = agg.merge(q, on=["ss_code", "timestamp"], how="left")
    return out[cols].reset_index(drop=True)


def shapes_from_hourly(
    hourly: pd.DataFrame,
    holidays: set[date],
    sample_days: dict[str, date | None] | None = None,
    key: str = "ss_code",
) -> pd.DataFrame:
    """Average 24-hour shapes per element and day type from hourly values.

    Every supplied day of a type counts equally. When the data has no day of one type
    (for example only NCC's two sample days and the off-peak day fell on a weekday),
    NCC's designated sample day stands in (peak day for WD, off-peak day for NWD),
    otherwise the other type's shape is copied; the note says so.
    Returns columns <key>, day_type, hour, p_mw, q_mvar, n_days, note.
    """
    cols = [key, "day_type", "hour", "p_mw", "q_mvar", "n_days", "note"]
    if hourly.empty:
        return pd.DataFrame(columns=cols)
    sample_days = sample_days or {}
    df = hourly.copy()
    ts = pd.to_datetime(df["timestamp"])
    df["day"] = ts.dt.date
    df["hour"] = ts.dt.hour
    df["day_type"] = [day_type(d, holidays) for d in df["day"]]
    if "q_mvar" not in df.columns:
        df["q_mvar"] = np.nan
    rows = []
    for elem, grp in df.groupby(key):
        by_type: dict[str, pd.DataFrame] = {}
        notes: list[str] = []
        for dt in DAY_TYPES:
            part = grp[grp["day_type"] == dt]
            if part.empty and sample_days.get(dt) is not None:
                part = grp[grp["day"] == sample_days[dt]]
                if not part.empty:
                    notes.append(f"{dt} from NCC sample day {sample_days[dt]}")
            by_type[dt] = part
        for dt in DAY_TYPES:
            part = by_type[dt]
            other = by_type["NWD" if dt == "WD" else "WD"]
            if part.empty:
                part = other
                notes.append(f"{dt} copied from the other day type")
            mean = part.groupby("hour")[["p_mw", "q_mvar"]].mean()
            p = _fill_hours(mean["p_mw"])
            q = _fill_hours(mean["q_mvar"])
            for h in HOURS:
                rows.append((elem, dt, h, p[h], q[h], int(part["day"].nunique()), "; ".join(notes)))
    return pd.DataFrame(rows, columns=cols)


def sample_days_for(inputs: Inputs, month: str) -> dict[str, date | None]:
    """NCC's designated days for the month: peak day stands for WD, off-peak day for NWD."""
    rows = rows_for_month(inputs.sample_days, month)
    if rows.empty:
        return {}
    row = rows.iloc[0]

    def as_date(v: Any) -> date | None:
        return None if v is None or pd.isna(v) else pd.Timestamp(v).date()

    return {"WD": as_date(row.get("peak_day")), "NWD": as_date(row.get("offpeak_day"))}


def scada_substation_hourly(inputs: Inputs, month: str, cfg: dict | None = None) -> pd.DataFrame:
    """Hourly load per substation from the month's SCADA (cached on the Inputs bundle)."""
    key = ("ss_hourly", month)
    if key not in inputs.cache:
        c = cases_cfg(cfg)
        clean = clean_scada(inputs.scada(month), c["scada_drop_quality"])
        inputs.cache[key] = substation_hourly(clean, select_load_points(inputs.scada_points))
    return inputs.cache[key]


def scada_shapes(inputs: Inputs, month: str, cfg: dict | None = None) -> pd.DataFrame:
    """Per-substation SCADA shapes for one month, Q filled from pf_default where missing."""
    key = ("ss_shapes", month)
    if key not in inputs.cache:
        c = cases_cfg(cfg)
        hourly = scada_substation_hourly(inputs, month, cfg)
        shapes = shapes_from_hourly(hourly, holiday_set(inputs.holidays), sample_days_for(inputs, month))
        if not shapes.empty:
            shapes["q_mvar"] = shapes["q_mvar"].fillna(shapes["p_mw"] * q_ratio_from_pf(c["pf_default"]))
        inputs.cache[key] = shapes
    return inputs.cache[key]


# --------------------------------------------------------------------------- standard shapes


def load_standard_profiles(path: str | Path | None = None) -> pd.DataFrame:
    """Read the standard shapes in long form: class, day_type, hour, sigma.

    Each class is normalised so its highest hour over both day types is exactly 1,
    which is what makes the energy-and-peak fit hit the peak.
    """
    path = Path(path or DEFAULTS["standard_profiles"])
    if not path.is_absolute():
        path = ROOT / path
    wide = pd.read_csv(path)
    hour_cols = [f"h{h:02d}" for h in HOURS]
    long = wide.melt(id_vars=["class", "day_type"], value_vars=hour_cols, var_name="h", value_name="sigma")
    long["hour"] = long["h"].str[1:].astype(int)
    long["sigma"] = long["sigma"] / long.groupby("class")["sigma"].transform("max")
    return long[["class", "day_type", "hour", "sigma"]].sort_values(["class", "day_type", "hour"]).reset_index(drop=True)


def fit_standard_shape(energy_mwh: float, peak_mw: float | None, s_sum: float, n_days: int) -> tuple[float, float, str]:
    """Fit P(h) = a + b * sigma(h) to a month's energy E and peak Pmax.

    With sigma's maximum equal to 1 and S = sum over days and hours of sigma:
        b = (E - 24*D*Pmax) / (S - 24*D),   a = Pmax - b
    gives exactly E MWh and exactly Pmax MW at the peak hour.
    Special cases (the returned label says which one applied):
    - ``a_clipped``: a would be negative (a very peaky month), so a = 0 and b = E/S;
      energy stays exact, the peak comes out above Pmax;
    - ``flat``: the shape is flat, or E is above 24*D*Pmax (load factor over 1, a data
      error), so a flat E/(24*D) is used;
    - ``energy_only``: no usable peak, so b = E/S.
    """
    hours = 24.0 * n_days
    if peak_mw is None or not np.isfinite(peak_mw) or peak_mw <= 0:
        return 0.0, energy_mwh / s_sum, "energy_only"
    if abs(s_sum - hours) < 1e-9:
        return energy_mwh / hours, 0.0, "flat"
    b = (energy_mwh - hours * peak_mw) / (s_sum - hours)
    a = peak_mw - b
    if b < 0:
        return energy_mwh / hours, 0.0, "flat"
    if a < 0:
        return 0.0, energy_mwh / s_sum, "a_clipped"
    return a, b, "fit"


def standard_shape_rows(
    ss_code: str,
    sigma: pd.DataFrame,
    counts: dict[str, int],
    energy_mwh: float,
    peak_mw: float | None,
    q_ratio: float,
) -> pd.DataFrame:
    """Profile rows for one substation from its class shape ``sigma`` (day_type, hour, sigma)."""
    s_sum = float(sum(counts[dt] * sigma.loc[sigma["day_type"] == dt, "sigma"].sum() for dt in DAY_TYPES))
    a, b, branch = fit_standard_shape(energy_mwh, peak_mw, s_sum, sum(counts.values()))
    out = sigma[["day_type", "hour"]].copy()
    out["p_mw"] = a + b * sigma["sigma"].to_numpy()
    out["q_mvar"] = out["p_mw"] * q_ratio
    out["ss_code"] = ss_code
    out["profile_source"] = "standard"
    out["n_days"] = 0
    out["note"] = f"standard shape, fit {branch} (a={a:.3f}, b={b:.3f})"
    return out[PROFILE_COLUMNS]


# --------------------------------------------------------------------------- substation profiles


def candidate_months(inputs: Inputs, month: str, max_offset: int) -> list[str]:
    """Other months to borrow from, nearest first (earlier month first on a tie)."""
    months: set[str] = set()
    if inputs.months is not None and not inputs.months.empty:
        m = inputs.months
        if "is_forecast" in m.columns:
            m = m[~m["is_forecast"].fillna(False).astype(bool)]
        months |= set(m["month"].astype(str).str[:7])
    if inputs.substation_monthly is not None and not inputs.substation_monthly.empty:
        months |= set(inputs.substation_monthly["month"].astype(str).str[:7])
    months.discard(month)
    near = [m for m in months if abs(month_offset(month, m)) <= max_offset]
    return sorted(near, key=lambda m: (abs(month_offset(month, m)), m))


def borrowed_shape(inputs: Inputs, month: str, ss_code: str, cfg: dict | None = None) -> tuple[pd.DataFrame, str] | None:
    """The substation's SCADA shape from the nearest other month, and that month; None if none."""
    c = cases_cfg(cfg)
    for other in candidate_months(inputs, month, int(c["borrow_max_months"])):
        shapes = scada_shapes(inputs, other, cfg)
        if shapes.empty:
            continue
        rows = shapes[shapes["ss_code"] == ss_code]
        if not rows.empty:
            return rows.copy(), other
    return None


def substation_profiles(inputs: Inputs, month: str, cfg: dict | None = None) -> pd.DataFrame:
    """24-hour P and Q shapes per substation and day type for one month, unscaled.

    Columns: ss_code, day_type, hour, p_mw, q_mvar, profile_source, n_days, note.
    SCADA and borrowed shapes are in measured MW; standard shapes are already fitted
    to NCC energy and peak. A substation with no SCADA anywhere and no NCC energy gets
    no profile (its loads keep the network model's values) and a warning is logged.
    The result is cached on ``inputs`` per month.
    """
    key = ("ss_profiles", month)
    if key in inputs.cache:
        return inputs.cache[key]
    c = cases_cfg(cfg)
    counts = day_type_counts(month, inputs.holidays)
    ncc = ncc_substation_month(inputs, month)
    own = scada_shapes(inputs, month, cfg)
    own_codes = set(own["ss_code"]) if not own.empty else set()
    standard: pd.DataFrame | None = None
    q_default = q_ratio_from_pf(c["pf_default"])

    frames = []
    if own_codes:
        frames.append(own.assign(profile_source="scada")[PROFILE_COLUMNS])
    for ss in sorted(set(ncc.index) - own_codes):
        found = borrowed_shape(inputs, month, ss, cfg)
        if found is not None:
            rows, other = found
            rows["profile_source"] = "borrowed"
            rows["note"] = f"shape borrowed from {other}"
            frames.append(rows[PROFILE_COLUMNS])
            continue
        energy = ncc.at[ss, "energy_mwh"]
        if pd.isna(energy):
            log.warning("%s %s: no SCADA in any month and no NCC energy; loads keep model values", month, ss)
            continue
        if standard is None:
            standard = load_standard_profiles(c["standard_profiles"])
        cls = c["class_by_substation"].get(ss, c["default_class"])
        sigma = standard[standard["class"] == cls]
        if sigma.empty:
            sigma = standard[standard["class"] == c["default_class"]]
        peak, peak_q = ncc.at[ss, "peak_mw"], ncc.at[ss, "peak_mvar"]
        q_ratio = peak_q / peak if pd.notna(peak_q) and pd.notna(peak) and peak > 0 else q_default
        frames.append(standard_shape_rows(ss, sigma.reset_index(drop=True), counts, float(energy), peak, q_ratio))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=PROFILE_COLUMNS)
    inputs.cache[key] = out
    return out


# --------------------------------------------------------------------------- generation


def case_gens(inputs: Inputs) -> pd.DataFrame:
    """Generators of the base case that are in service and not the slack.

    The slack balances each load flow, so it never gets a fixed P.
    Columns: gen_id, plant_code, technology, p_max_mw.
    """
    gens = inputs.net_tables.get("net_gen", pd.DataFrame())
    cols = ["gen_id", "plant_code", "technology", "p_max_mw"]
    if gens is None or gens.empty:
        return pd.DataFrame(columns=cols)
    gens = gens[gens["case_id"] == inputs.case_id] if "case_id" in gens.columns else gens
    gens = gens[in_service_mask(gens)]
    if "control" in gens.columns:
        gens = gens[gens["control"].fillna("") != "slack"]
    gens = gens.assign(plant_code=code_column(gens, "plant"))
    for col in cols:
        if col not in gens.columns:
            gens[col] = np.nan
    return gens[cols].reset_index(drop=True)


def solar_shape() -> np.ndarray:
    """A clear-sky-like daily shape: zero at night, a half sine from 06:00 to 18:00 (EAT).

    Kampala is on the equator, so sunrise and sunset move little through the year.
    """
    h = np.arange(24) + 0.5
    return np.where((h > 6) & (h < 18), np.sin(np.pi * (h - 6) / 12), 0.0)


def scada_gen_hourly(inputs: Inputs, month: str, cfg: dict | None = None) -> pd.DataFrame:
    """Hourly MW per generator from SCADA generator P points (columns gen_id, timestamp, p_mw).

    A point is matched to a generator through ``element_ref`` (a T01 gen_id), or to a
    plant (``element_ref`` = plant code) and split over its units by rating.
    Our convention (+ = from the busbar into the bay) makes output negative, so the
    sign is flipped; if a point is still mostly negative its own convention differs
    and it is flipped back.
    """
    key = ("gen_hourly", month)
    if key in inputs.cache:
        return inputs.cache[key]
    cols = ["gen_id", "timestamp", "p_mw"]
    out = pd.DataFrame(columns=cols)
    pts = inputs.scada_points
    gens = case_gens(inputs)
    if pts is not None and not pts.empty and not gens.empty and "element_ref" in pts.columns:
        pts = pts[(pts["element_type"] == "generator") & (pts["quantity"] == "P")]
        clean = clean_scada(inputs.scada(month), cases_cfg(cfg)["scada_drop_quality"])
        frames = []
        for _, pt in pts.iterrows():
            ref = pt["element_ref"]
            if ref in set(gens["gen_id"]):
                units = gens[gens["gen_id"] == ref]
            else:
                units = gens[gens["plant_code"] == ref]
            vals = clean[clean["point_id"] == pt["point_id"]]
            if units.empty or vals.empty:
                continue
            p = -vals["value"] * point_sign(pt.get("sign_convention"))
            if p.sum() < 0:
                p = -p
            weights = units["p_max_mw"].fillna(1.0).to_numpy()
            weights = weights / weights.sum()
            for gen_id, w in zip(units["gen_id"], weights):
                frames.append(pd.DataFrame({"gen_id": gen_id, "timestamp": vals["timestamp"].to_numpy(), "p_mw": p.to_numpy() * w}))
        if frames:
            out = pd.concat(frames).groupby(["gen_id", "timestamp"], as_index=False)["p_mw"].sum()
    inputs.cache[key] = out
    return out


def gen_profiles(inputs: Inputs, month: str, cfg: dict | None = None) -> pd.DataFrame:
    """24-hour P shape per generator and day type for one month.

    - Generators with SCADA: the measured average shape (``scada``), not rescaled.
    - Other generators of a plant with NCC sent-out energy: solar follows the clear-sky
      shape, everything else is flat at the monthly average (``standard``). The plant's
      energy is split over its units by rated MW.
    - Generators with neither keep the network model's P (not listed here).
    Columns: gen_id, day_type, hour, p_mw, profile_source.
    """
    key = ("gen_profiles", month)
    if key in inputs.cache:
        return inputs.cache[key]
    hols = holiday_set(inputs.holidays)
    counts = day_type_counts(month, hols)
    n_days = sum(counts.values())
    gens = case_gens(inputs)
    frames = []

    measured = shapes_from_hourly(scada_gen_hourly(inputs, month, cfg), hols, key="gen_id")
    if not measured.empty:
        frames.append(measured.assign(profile_source="scada")[GEN_PROFILE_COLUMNS])
    done = set(measured["gen_id"]) if not measured.empty else set()
    # Monthly MWh already covered by measured units, so a plant with some units on SCADA
    # gives only the rest of its NCC energy to the other units.
    measured_mwh = (
        (measured["p_mw"].fillna(0.0) * measured["day_type"].map(counts)).groupby(measured["gen_id"]).sum()
        if not measured.empty else pd.Series(dtype=float)
    )

    gm = rows_for_month(inputs.generation_monthly, month)
    if not gm.empty and not gens.empty:
        gm = gm.assign(plant_code=code_column(gm, "plant"))
        energy = gm.groupby("plant_code")["sent_out_mwh"].sum(min_count=1)
        tech = gm.groupby("plant_code")["technology"].first() if "technology" in gm.columns else pd.Series(dtype=object)
        for plant, e in energy.items():
            units = gens[(gens["plant_code"] == plant) & ~gens["gen_id"].isin(done)]
            if units.empty or pd.isna(e):
                continue
            plant_gen_ids = gens.loc[gens["plant_code"] == plant, "gen_id"]
            e = max(0.0, float(e) - float(measured_mwh.reindex(plant_gen_ids).fillna(0.0).sum()))
            technology = tech.get(plant)
            if technology is None or pd.isna(technology):
                technology = units["technology"].dropna().iloc[0] if units["technology"].notna().any() else "other"
            shape = solar_shape() if technology == "solar" else np.ones(24)
            day_mw = float(e) / n_days * shape / shape.sum()  # MW per hour of a typical day
            weights = units["p_max_mw"].fillna(1.0).to_numpy()
            weights = weights / weights.sum()
            for gen_id, w in zip(units["gen_id"], weights):
                for dt in DAY_TYPES:
                    frames.append(pd.DataFrame({"gen_id": gen_id, "day_type": dt, "hour": HOURS,
                                                "p_mw": day_mw * w, "profile_source": "standard"}))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=GEN_PROFILE_COLUMNS)
    inputs.cache[key] = out
    return out
