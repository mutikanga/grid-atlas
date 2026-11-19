"""Load-flow snapshots: which loads and generation to solve for, and how much each counts (F3b).

A month's losses are a weighted sum of load flows. ``month_snapshots`` makes one
snapshot per day type and hour (48 a month): the 24-hour shapes from engine/profiles.py,
scaled so each substation's energy equals NCC's monthly figure, with weight
``weight_h`` = the number of days of that type (each snapshot stands for that hour on
every such day). The weights add up to 24 x the days in the month.

When SCADA covers many days of a type we still make 24 snapshots for it, from the
average shape. That keeps the run small; the cost is that day-to-day spread is averaged
out, which understates losses slightly (losses grow with the square of the load).

Other snapshots:
- ``peak_snapshot`` / ``min_snapshot``: the coincident peak or minimum hour, used for
  N-1 and overvoltage checks. Not energy-scaled: they use measured or reported MW.
- ``hour_snapshot``: one exact SCADA hour, to compare the model with measurements.

Case keys are readable: '2026-03|WD|20', '2026-03|peak', '2026-03|min',
'2026-03|2026-03-12 20:00'.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from engine.profiles import (
    DAY_TYPES,
    HOURS,
    SOURCE_RANK,
    cases_cfg,
    code_column,
    day_type,
    day_type_counts,
    gen_profiles,
    holiday_set,
    in_service_mask,
    ncc_substation_month,
    q_ratio_from_pf,
    rows_for_month,
    scada_gen_hourly,
    scada_substation_hourly,
    substation_profiles,
)

if TYPE_CHECKING:
    from engine.inputs import Inputs

log = logging.getLogger(__name__)

LOAD_COLUMNS = ["load_id", "p_mw", "q_mvar"]
GEN_COLUMNS = ["gen_id", "p_mw"]


@dataclass
class Snapshot:
    """One load flow to run: the loads and generator outputs to set, and its weight.

    ``kind`` is 'snapshot' (part of a monthly energy sum), 'peak', 'min' or 'hour'.
    ``weight_h`` is the number of hours it stands for (None for peak, min and hour cases).
    ``loads`` has columns load_id, p_mw, q_mvar; ``gens`` has gen_id, p_mw. Elements not
    listed keep the values in the network model; the slack generator balances.
    """

    case_key: str
    kind: str
    month: str
    day_type: str | None
    hour: int | None
    weight_h: float | None
    loads: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=LOAD_COLUMNS))
    gens: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=GEN_COLUMNS))
    profile_source: str = ""
    note: str = ""

    @property
    def total_load_mw(self) -> float:
        """Sum of the loads this snapshot sets."""
        return float(self.loads["p_mw"].sum()) if not self.loads.empty else 0.0

    @property
    def total_gen_mw(self) -> float:
        """Sum of the generator outputs this snapshot sets (the slack is not included)."""
        return float(self.gens["p_mw"].sum()) if not self.gens.empty else 0.0


# --------------------------------------------------------------------------- loads in the model


def normalise_shares(shares: pd.Series) -> pd.Series:
    """Shares of one substation's demand, adding up to 1.

    Blank shares split what the given shares leave over, equally. When nothing is
    given, every load gets an equal share. Shares that add up to more or less than 1
    are rescaled.
    """
    s = shares.astype(float)
    blank = s.isna()
    if blank.all():
        return pd.Series(1.0 / len(s), index=s.index)
    if blank.any():
        s[blank] = max(0.0, 1.0 - s[~blank].sum()) / blank.sum()
    total = s.sum()
    return s / total if total > 0 else pd.Series(1.0 / len(s), index=s.index)


def case_loads(inputs: Inputs) -> pd.DataFrame:
    """The base case's in-service loads with their substation and share (load_id, ss_code, share)."""
    loads = inputs.case_table("net_load")
    cols = ["load_id", "ss_code", "share"]
    if loads is None or loads.empty:
        return pd.DataFrame(columns=cols)
    loads = loads[in_service_mask(loads)].copy()
    # The resolved substation_code first (it may exist without the raw name column).
    ss = code_column(loads, "substation").replace("", np.nan)
    buses = inputs.case_table("net_bus")
    if not buses.empty and "bus_id" in buses.columns:
        bus_ss = buses.assign(ss=code_column(buses, "substation")).set_index("bus_id")["ss"]
        ss = ss.fillna(loads["bus"].map(bus_ss))
    # Last resort: canonical bus ids start with the substation code ('KAW-132-1').
    ss = ss.fillna(loads["bus"].astype(str).str.split("-").str[0])
    loads["ss_code"] = ss
    if "share" not in loads.columns:
        loads["share"] = np.nan
    loads["share"] = loads.groupby("ss_code")["share"].transform(normalise_shares)
    return loads[cols].reset_index(drop=True)


def split_to_loads(ss_values: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """Spread substation P and Q (ss_code, p_mw, q_mvar) over the loads by share."""
    if ss_values.empty or shares.empty:
        return pd.DataFrame(columns=LOAD_COLUMNS)
    df = shares.merge(ss_values, on="ss_code")
    df["p_mw"] = df["p_mw"] * df["share"]
    df["q_mvar"] = df["q_mvar"] * df["share"]
    return df[LOAD_COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------- energy scaling


def energy_scale_factors(profiles: pd.DataFrame, energy_mwh: pd.Series, counts: dict[str, int]) -> pd.Series:
    """k per substation so that sum over day types of n_days x sum over hours of k x P(h) = NCC energy.

    k is 1 where NCC energy is missing or the shape has no energy.
    """
    if profiles.empty:
        return pd.Series(dtype=float)
    weights = profiles["day_type"].map(counts).astype(float)
    modelled = (profiles["p_mw"] * weights).groupby(profiles["ss_code"]).sum()
    target = energy_mwh.reindex(modelled.index)
    k = target / modelled
    return k.where(target.notna() & (modelled > 0), 1.0).astype(float)


def scale_profiles(profiles: pd.DataFrame, k: pd.Series) -> pd.DataFrame:
    """Multiply each substation's P and Q by its factor k."""
    factor = profiles["ss_code"].map(k).fillna(1.0)
    return profiles.assign(p_mw=profiles["p_mw"] * factor, q_mvar=profiles["q_mvar"] * factor)


def worst_source(sources: pd.Series) -> str:
    """The least direct source among the substations: scada < borrowed < standard."""
    present = [s for s in sources.dropna().unique() if s in SOURCE_RANK]
    return max(present, key=SOURCE_RANK.__getitem__) if present else "model"


def source_note(profiles: pd.DataFrame) -> str:
    """For example 'scada 9, standard 2' (substations per source)."""
    if profiles.empty:
        return "no profiles"
    per_ss = profiles.groupby("ss_code")["profile_source"].first().value_counts()
    return ", ".join(f"{src} {n}" for src, n in per_ss.items())


@dataclass
class MonthParts:
    """What every snapshot of a month is built from (worked out once per call)."""

    counts: dict[str, int]
    scaled: pd.DataFrame          # energy-scaled profiles: ss_code, day_type, hour, p_mw, q_mvar, ...
    k: pd.Series                  # scale factor per substation
    shares: pd.DataFrame          # load_id, ss_code, share
    gens: pd.DataFrame            # gen_id, day_type, hour, p_mw, profile_source
    note: str


def month_parts(inputs: Inputs, month: str, cfg: dict | None) -> MonthParts:
    """Profiles scaled to NCC energy, load shares and generator profiles for one month."""
    c = cases_cfg(cfg)
    counts = day_type_counts(month, inputs.holidays)
    profiles = substation_profiles(inputs, month, cfg)
    ncc = ncc_substation_month(inputs, month)
    k = energy_scale_factors(profiles, ncc["energy_mwh"], counts)
    notes = [source_note(profiles)]
    off = k[(k < c["scale_warn_low"]) | (k > c["scale_warn_high"])]
    for ss, val in off.items():
        log.warning("%s %s: shape scaled by %.2f to match NCC energy (outside %.2f-%.2f)",
                    month, ss, val, c["scale_warn_low"], c["scale_warn_high"])
    if not off.empty:
        notes.append("scale outside band: " + ", ".join(f"{ss} {v:.2f}" for ss, v in off.items()))
    unscaled = sorted(set(profiles["ss_code"]) - set(ncc["energy_mwh"].dropna().index)) if not profiles.empty else []
    if unscaled:
        notes.append("no NCC energy, unscaled: " + ", ".join(unscaled))
    shares = case_loads(inputs)
    no_loads = sorted(set(profiles["ss_code"]) - set(shares["ss_code"])) if not profiles.empty else []
    if no_loads:
        log.warning("%s: substations with a profile but no load in case %s: %s", month, inputs.case_id, no_loads)
        notes.append("no load in model: " + ", ".join(no_loads))
    return MonthParts(counts, scale_profiles(profiles, k), k, shares, gen_profiles(inputs, month, cfg), "; ".join(notes))


def _profile_at(parts: MonthParts, dt: str, hour: int) -> pd.DataFrame:
    """Scaled substation P and Q at one day type and hour (ss_code, p_mw, q_mvar)."""
    sel = parts.scaled[(parts.scaled["day_type"] == dt) & (parts.scaled["hour"] == hour)]
    return sel[["ss_code", "p_mw", "q_mvar"]].reset_index(drop=True)


def _gens_at(parts: MonthParts, dt: str, hour: int) -> pd.DataFrame:
    sel = parts.gens[(parts.gens["day_type"] == dt) & (parts.gens["hour"] == hour)]
    return sel[GEN_COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------- monthly snapshots


def month_snapshots(inputs: Inputs, month: str, cfg: dict | None = None) -> list[Snapshot]:
    """48 weighted snapshots for a month (24 hours x WD and NWD).

    Each substation's energy over the weighted snapshots equals NCC's monthly energy.
    """
    parts = month_parts(inputs, month, cfg)
    source = worst_source(parts.scaled["profile_source"]) if not parts.scaled.empty else "model"
    snaps = []
    for dt in DAY_TYPES:
        n = parts.counts[dt]
        if n == 0:
            continue
        for h in HOURS:
            snaps.append(Snapshot(
                case_key=f"{month}|{dt}|{h}", kind="snapshot", month=month, day_type=dt, hour=h,
                weight_h=float(n), loads=split_to_loads(_profile_at(parts, dt, h), parts.shares),
                gens=_gens_at(parts, dt, h), profile_source=source, note=parts.note,
            ))
    return snaps


# --------------------------------------------------------------------------- peak, minimum, exact hour


def _ss_ratio(values: pd.DataFrame, default: float) -> pd.Series:
    """Q/P per substation from a frame of ss_code, p_mw, q_mvar (default where P is zero)."""
    v = values.set_index("ss_code")
    ratio = v["q_mvar"] / v["p_mw"].where(v["p_mw"] > 0)
    return ratio.fillna(default)


def _scada_hour_snapshot(inputs: Inputs, month: str, when: pd.Timestamp, parts: MonthParts, cfg: dict | None,
                         case_key: str, kind: str, label: str) -> Snapshot | None:
    """A snapshot from SCADA at one hour; substations not measured then take their profile value."""
    c = cases_cfg(cfg)
    hourly = scada_substation_hourly(inputs, month, cfg)
    at = hourly[hourly["timestamp"] == when]
    if at.empty:
        return None
    dt, h = day_type(when.date(), holiday_set(inputs.holidays)), int(when.hour)
    base = _profile_at(parts, dt, h).set_index("ss_code")
    measured = at.set_index("ss_code")[["p_mw", "q_mvar"]].astype(float)
    measured["q_mvar"] = measured["q_mvar"].fillna(measured["p_mw"] * q_ratio_from_pf(c["pf_default"]))
    ss_values = measured.combine_first(base).reset_index()
    gens = _gens_at(parts, dt, h).set_index("gen_id")
    gen_scada = scada_gen_hourly(inputs, month, cfg)
    gen_at = gen_scada[gen_scada["timestamp"] == when].set_index("gen_id")[["p_mw"]]
    gens = gen_at.combine_first(gens).reset_index()
    note = f"{label} {when:%Y-%m-%d %H:%M}: {len(measured)} substations measured, {len(base.index.difference(measured.index))} from profiles"
    return Snapshot(case_key=case_key, kind=kind, month=month, day_type=dt, hour=h, weight_h=None,
                    loads=split_to_loads(ss_values, parts.shares), gens=gens[GEN_COLUMNS],
                    profile_source="scada", note=note)


def scada_extreme_time(hourly: pd.DataFrame, which: str) -> pd.Timestamp | None:
    """The hour with the highest (``peak``) or lowest (``min``) total of substation loads.

    Only hours where every SCADA substation reported are compared, so a gap in the data
    cannot look like a minimum. If no hour is complete, gaps count as zero.
    """
    if hourly.empty:
        return None
    wide = hourly.pivot_table(index="timestamp", columns="ss_code", values="p_mw", aggfunc="sum")
    full = wide.dropna()
    if full.empty:
        full = wide.fillna(0.0)
    total = full.sum(axis=1)
    return pd.Timestamp(total.idxmax() if which == "peak" else total.idxmin())


def coincidence_factor(inputs: Inputs, month: str, ncc: pd.DataFrame, cfg: dict | None) -> float:
    """System peak / sum of substation peaks, capped at 1.

    Falls back to sum of coincident_mw / sum of peak_mw over substations that report both,
    then to the configured default. A factor above 1 means the system figure and the
    substation list cover different perimeters, so it is capped and a warning is logged.
    """
    c = cases_cfg(cfg)
    peaks = ncc["peak_mw"].dropna()
    system = rows_for_month(inputs.system_monthly, month)
    if not system.empty and "peak_mw" in system.columns and pd.notna(system["peak_mw"].iloc[0]) and peaks.sum() > 0:
        cf = float(system["peak_mw"].iloc[0]) / float(peaks.sum())
    else:
        both = ncc[["coincident_mw", "peak_mw"]].dropna()
        cf = float(both["coincident_mw"].sum() / both["peak_mw"].sum()) if both["peak_mw"].sum() > 0 else float(c["coincidence"]["default_factor"])
    if cf > 1.0:
        log.warning("%s: coincidence factor %.3f above 1 (perimeters differ?); capped at 1", month, cf)
        cf = 1.0
    return cf


def _ncc_extreme_hour(inputs: Inputs, month: str, parts: MonthParts, which: str) -> tuple[str, int]:
    """Day type and hour of the peak or minimum when there is no SCADA.

    NCC's system peak_at (or min_at) gives the hour when known; otherwise it is the
    hour where the scaled profiles add up to the most or the least.
    """
    system = rows_for_month(inputs.system_monthly, month)
    at_col = "peak_at" if which == "peak" else "min_at"
    if not system.empty and at_col in system.columns and pd.notna(system[at_col].iloc[0]):
        at = pd.Timestamp(system[at_col].iloc[0])
        return day_type(at.date(), holiday_set(inputs.holidays)), int(at.hour)
    totals = parts.scaled.groupby(["day_type", "hour"])["p_mw"].sum()
    totals = totals[[parts.counts.get(dt, 0) > 0 for dt, _ in totals.index]]
    if totals.empty:
        return "WD", 19
    dt, h = totals.idxmax() if which == "peak" else totals.idxmin()
    return str(dt), int(h)


def _extreme_snapshot(inputs: Inputs, month: str, cfg: dict | None, which: str) -> Snapshot:
    """Shared code for peak_snapshot and min_snapshot."""
    c = cases_cfg(cfg)
    parts = month_parts(inputs, month, cfg)
    key = f"{month}|{which}"
    when = scada_extreme_time(scada_substation_hourly(inputs, month, cfg), which)
    if when is not None:
        snap = _scada_hour_snapshot(inputs, month, when, parts, cfg, key, which, f"SCADA {which}")
        if snap is not None:
            return snap

    dt, h = _ncc_extreme_hour(inputs, month, parts, which)
    base = _profile_at(parts, dt, h)
    ncc = ncc_substation_month(inputs, month)
    if which == "peak":
        cf = coincidence_factor(inputs, month, ncc, cfg)
        p = ncc["coincident_mw"].fillna(ncc["peak_mw"] * cf)
        label = f"NCC coincident peak (factor {cf:.3f} where coincident_mw is blank)"
    else:
        p = ncc["min_mw"].copy()
        label = "NCC minimum"
        system = rows_for_month(inputs.system_monthly, month)
        if not system.empty and "min_mw" in system.columns and pd.notna(system["min_mw"].iloc[0]) and p.sum() > 0:
            # Substation minima do not happen at the same hour, so their sum is below the
            # system minimum and is scaled up to it. If the system minimum is above the sum
            # of the substations' peaks, the system figure covers a wider area (national
            # against Central), and scaling would inflate every load: keep the minima.
            sys_min = float(system["min_mw"].iloc[0])
            ceiling = float(np.nan_to_num(ncc.loc[p.dropna().index, "peak_mw"].sum()))
            if ceiling > 0 and sys_min > ceiling:
                log.warning("%s: system min_mw %.1f is above the sum of substation peaks %.1f "
                            "(perimeters differ?); substation minima not scaled", month, sys_min, ceiling)
                label = "NCC minimum (not scaled: system perimeter differs)"
            else:
                p = p * sys_min / float(p.sum())
    p = p.dropna()
    ratio = _ss_ratio(base, q_ratio_from_pf(c["pf_default"])).reindex(p.index).fillna(q_ratio_from_pf(c["pf_default"]))
    reported = pd.DataFrame({"p_mw": p, "q_mvar": p * ratio})
    if reported.empty:
        label = f"profile {which} hour"
    ss_values = reported.combine_first(base.set_index("ss_code")).rename_axis("ss_code").reset_index()
    source = worst_source(parts.scaled["profile_source"]) if not parts.scaled.empty else "model"
    note = f"{label}, {dt} hour {h}; {len(reported)} substations from NCC; {parts.note}"
    return Snapshot(case_key=key, kind=which, month=month, day_type=dt, hour=h, weight_h=None,
                    loads=split_to_loads(ss_values, parts.shares), gens=_gens_at(parts, dt, h),
                    profile_source=source, note=note)


def peak_snapshot(inputs: Inputs, month: str, cfg: dict | None = None) -> Snapshot:
    """The month's coincident peak hour.

    Order of preference: the SCADA hour with the highest system total (unscaled);
    else NCC's coincident_mw per substation, or peak_mw x the coincidence factor.
    """
    return _extreme_snapshot(inputs, month, cfg, "peak")


def min_snapshot(inputs: Inputs, month: str, cfg: dict | None = None) -> Snapshot:
    """The month's minimum-load hour (for overvoltage checks), chosen like the peak."""
    return _extreme_snapshot(inputs, month, cfg, "min")


def hour_snapshot(inputs: Inputs, when: datetime, cfg: dict | None = None) -> Snapshot | None:
    """The exact SCADA hour ``when`` (EAT), for comparing the model with measurements.

    None when SCADA has no substation data for that hour.
    """
    ts = pd.Timestamp(when)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Africa/Kampala").tz_localize(None)
    ts = ts.floor("h")
    month = f"{ts:%Y-%m}"
    if scada_substation_hourly(inputs, month, cfg).empty:
        return None
    parts = month_parts(inputs, month, cfg)
    return _scada_hour_snapshot(inputs, month, ts, parts, cfg, f"{month}|{ts:%Y-%m-%d %H:%M}", "hour", "SCADA hour")


# --------------------------------------------------------------------------- applying to a net


def _set_by_id(table: pd.DataFrame, id_col: str, values: pd.DataFrame, columns: list[str]) -> int:
    """Write ``columns`` of ``values`` into ``table`` rows matched on ``id_col``; return rows set."""
    if values.empty or table.empty or id_col not in table.columns:
        return 0
    index = pd.Series(table.index, index=table[id_col])
    index = index[~index.index.duplicated()]
    hit = values[values[id_col].isin(index.index)]
    rows = index.loc[hit[id_col]].to_numpy()
    for col in columns:
        vals = hit[col].to_numpy(dtype=float)
        ok = ~np.isnan(vals)  # never write NaN into the net: the load flow would fail
        table.loc[rows[ok], col] = vals[ok]
    return len(rows)


def apply_snapshot(net: Any, snap: Snapshot) -> int:
    """Set load P and Q (by load_id) and generator P (by gen_id, in net.gen and net.sgen).

    Elements not in the snapshot keep their values. Returns how many elements were set.
    """
    n = 0
    if "load_id" in snap.loads.columns:
        n += _set_by_id(net.load, "load_id", snap.loads, ["p_mw", "q_mvar"])
    if "gen_id" in snap.gens.columns:
        n += _set_by_id(net.gen, "gen_id", snap.gens, ["p_mw"])
        n += _set_by_id(net.sgen, "gen_id", snap.gens, ["p_mw"])
    return n


def scale_loads(net: Any, factor: float, ss_codes: list[str] | set[str] | None = None) -> None:
    """Multiply load P and Q by ``factor``, for all loads or only those at ``ss_codes``."""
    mask = pd.Series(True, index=net.load.index)
    if ss_codes is not None:
        mask = net.load["ss_code"].isin(list(ss_codes))
    net.load.loc[mask, "p_mw"] = net.load.loc[mask, "p_mw"] * factor
    net.load.loc[mask, "q_mvar"] = net.load.loc[mask, "q_mvar"] * factor
