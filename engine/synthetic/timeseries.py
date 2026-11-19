"""Hourly 'truth' load and generation for the 13 study months (Sep 2025 to Sep 2026).

The fake reality is built from:
- a 24-hour shape per load class and day type (weekday, or weekend/holiday);
- 7 % a year growth, a mild seasonal swing and a Christmas dip;
- day-to-day and hour-to-hour noise.

Generation: solar follows a clear-sky curve with daily cloud; Namanve thermal runs as
a peaker; Nalubaale and Karuma follow a daily schedule; Bujagali (the slack) takes
whatever is left. Times are EAT, timestamped at the start of the hour.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

from engine.synthetic.network import MBR_LOAD_ID, Network

START = datetime(2025, 9, 1, 0, 0)
END = datetime(2026, 9, 30, 23, 0)
MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 9), (2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 10)]]
GROWTH_PER_YEAR = 0.07
GROWTH_REF = datetime(2026, 9, 15)

# Uganda public holidays in the study period (matches config/holidays_ug.csv).
HOLIDAYS = {
    date(2025, 10, 9), date(2025, 12, 25), date(2025, 12, 26), date(2026, 1, 1), date(2026, 1, 26),
    date(2026, 2, 16), date(2026, 3, 8), date(2026, 3, 20), date(2026, 4, 3), date(2026, 4, 6),
    date(2026, 5, 1), date(2026, 5, 27), date(2026, 6, 3), date(2026, 6, 9),
}

# The planned 5-day outage of Kawanda - Kampala North circuit 1 (also reported in T05 events).
OUTAGE_LINE = "L-KAW-KNO-132-1"
OUTAGE_START = datetime(2026, 4, 13, 6, 0)
OUTAGE_END = datetime(2026, 4, 18, 6, 0)

# 24-hour shapes (fraction of the class peak) for weekdays (WD) and weekends/holidays (NWD).
# Close to config/profiles/standard_profiles.csv but not identical, so the engine's
# standard-shape fallback is a fair, imperfect stand-in.
SHAPES: dict[str, dict[str, list[float]]] = {
    "urban_commercial": {
        "WD": [0.52, 0.48, 0.46, 0.46, 0.47, 0.51, 0.60, 0.72, 0.85, 0.93, 0.97, 0.99, 0.98, 0.96, 0.97, 0.96,
               0.93, 0.90, 0.90, 0.96, 1.00, 0.86, 0.71, 0.59],
        "NWD": [0.48, 0.45, 0.43, 0.43, 0.44, 0.46, 0.51, 0.57, 0.64, 0.70, 0.74, 0.76, 0.76, 0.75, 0.74, 0.73,
                0.72, 0.73, 0.79, 0.86, 0.84, 0.75, 0.64, 0.54],
    },
    "urban_residential": {
        "WD": [0.46, 0.42, 0.40, 0.39, 0.41, 0.48, 0.63, 0.69, 0.63, 0.59, 0.58, 0.59, 0.61, 0.60, 0.59, 0.59,
               0.62, 0.71, 0.87, 0.98, 1.00, 0.93, 0.76, 0.58],
        "NWD": [0.48, 0.44, 0.42, 0.41, 0.42, 0.46, 0.57, 0.66, 0.68, 0.67, 0.66, 0.66, 0.67, 0.66, 0.64, 0.64,
                0.67, 0.75, 0.89, 0.97, 0.98, 0.91, 0.76, 0.59],
    },
    "industrial": {
        "WD": [0.80, 0.78, 0.77, 0.77, 0.78, 0.81, 0.87, 0.93, 0.98, 1.00, 1.00, 0.99, 0.96, 0.97, 0.99, 0.98,
               0.96, 0.93, 0.90, 0.90, 0.89, 0.86, 0.83, 0.81],
        "NWD": [0.73, 0.71, 0.70, 0.70, 0.71, 0.73, 0.76, 0.79, 0.82, 0.84, 0.85, 0.85, 0.84, 0.83, 0.83, 0.83,
                0.82, 0.81, 0.81, 0.82, 0.81, 0.79, 0.77, 0.75],
    },
    "mixed": {
        "WD": [0.57, 0.54, 0.52, 0.51, 0.53, 0.58, 0.67, 0.75, 0.80, 0.83, 0.85, 0.86, 0.86, 0.85, 0.85, 0.84,
               0.84, 0.86, 0.92, 0.99, 1.00, 0.92, 0.79, 0.65],
        "NWD": [0.55, 0.52, 0.50, 0.49, 0.50, 0.54, 0.60, 0.67, 0.72, 0.75, 0.77, 0.78, 0.78, 0.77, 0.76, 0.76,
                0.76, 0.78, 0.86, 0.95, 0.96, 0.89, 0.76, 0.63],
    },
}
# Kawanda carries two data-centre customers (DC-1, DC-2) that draw flat: this share of its peak.
KAW_FLAT_SHARE = 0.32
DC_SPLIT = {"DC-1": 0.6, "DC-2": 0.4}


def rng_for(seed: int, purpose: str) -> np.random.Generator:
    """A random generator for one purpose, so changing one part does not reshuffle the rest."""
    return np.random.default_rng([seed, zlib.crc32(purpose.encode())])


@dataclass
class Calendar:
    """The hourly index of the study period and its day attributes."""

    hours: pd.DatetimeIndex
    hour_of_day: np.ndarray
    day_index: np.ndarray       # 0..n_days-1 for each hour
    days: pd.DatetimeIndex      # one entry per day
    is_wd: np.ndarray           # per hour: weekday and not a holiday
    month: np.ndarray           # per hour: 'YYYY-MM'


def make_calendar() -> Calendar:
    """Build the hourly calendar from START to END (EAT, start-of-hour stamps)."""
    hours = pd.date_range(START, END, freq="h")
    days = pd.date_range(START.date(), END.date(), freq="D")
    day_index = ((hours.normalize() - days[0]).days).to_numpy()
    is_wd_day = np.array([d.weekday() < 5 and d.date() not in HOLIDAYS for d in days])
    return Calendar(
        hours=hours,
        hour_of_day=hours.hour.to_numpy(),
        day_index=day_index,
        days=days,
        is_wd=is_wd_day[day_index],
        month=hours.strftime("%Y-%m").to_numpy(),
    )


def shape_matrix(cal: Calendar, load_class: str) -> np.ndarray:
    """The class shape value for every hour of the calendar."""
    wd = np.array(SHAPES[load_class]["WD"])[cal.hour_of_day]
    nwd = np.array(SHAPES[load_class]["NWD"])[cal.hour_of_day]
    return np.where(cal.is_wd, wd, nwd)


def growth_factor(cal: Calendar) -> np.ndarray:
    """7 % a year compound growth, equal to 1 in mid-September 2026."""
    years = (cal.hours - pd.Timestamp(GROWTH_REF)).total_seconds().to_numpy() / (365.25 * 86400)
    return (1 + GROWTH_PER_YEAR) ** years


def seasonal_factor(cal: Calendar) -> np.ndarray:
    """A mild seasonal swing (highest in the hot dry spell around March) and a Christmas dip."""
    doy = cal.hours.dayofyear.to_numpy()
    f = 1 + 0.025 * np.cos(2 * np.pi * (doy - 75) / 365.25)
    md = cal.hours.month.to_numpy() * 100 + cal.hours.day.to_numpy()
    xmas = (md >= 1220) | (md <= 105)
    return np.where(xmas, f * 0.93, f)


@dataclass
class TruthSeries:
    """Hourly truth injections. Arrays are hours x elements, in the order of the id lists."""

    cal: Calendar
    load_ids: list[str]
    load_p: np.ndarray
    load_q: np.ndarray
    gen_ids: list[str]        # every generator except the slack
    gen_p: np.ndarray
    dc_p: dict[str, np.ndarray]  # data-centre draw inside the Kawanda load (for T05 / T06)


def load_series(nw: Network, cal: Calendar, seed: int) -> tuple[list[str], np.ndarray, np.ndarray, dict]:
    """Hourly P and Q for every load, including the MBR export tie."""
    rng = rng_for(seed, "loads")
    n_h, n_d = len(cal.hours), len(cal.days)
    common_day = 1 + 0.02 * rng.standard_normal(n_d)
    base = growth_factor(cal) * seasonal_factor(cal) * common_day[cal.day_index]
    ids, ps, qs = [], [], []
    dc = {}
    for r in nw.loads.itertuples():
        own_day = 1 + 0.015 * rng.standard_normal(n_d)
        hourly = 1 + 0.012 * rng.standard_normal(n_h)
        if r.load_id == MBR_LOAD_ID:
            # Export to the west: 28 MW at night rising to about 45 MW in the evening.
            shape = 0.62 + 0.38 * (shape_matrix(cal, "mixed") - 0.5) / 0.5
            p = r.peak_mw * shape * own_day[cal.day_index] * hourly * growth_factor(cal) ** 0.5
        elif r.ss_code == "KAW":
            flat = KAW_FLAT_SHARE * r.peak_mw * growth_factor(cal) * (1 + 0.01 * rng.standard_normal(n_h))
            rest = (1 - KAW_FLAT_SHARE) * r.peak_mw * shape_matrix(cal, r.load_class) * base
            p = flat + rest * own_day[cal.day_index] * hourly
            dc = {k: flat * v for k, v in DC_SPLIT.items()}
        else:
            p = r.peak_mw * shape_matrix(cal, r.load_class) * base * own_day[cal.day_index] * hourly
        tan_phi = np.tan(np.arccos(r.pf))
        q = p * tan_phi * (1 + 0.03 * rng.standard_normal(n_h))
        ids.append(r.load_id)
        ps.append(p)
        qs.append(q)
    return ids, np.column_stack(ps), np.column_stack(qs), dc


def clear_sky(hour_of_day: np.ndarray) -> np.ndarray:
    """Clear-sky solar output (0..1) for the hour starting at hour_of_day (sun 06:30 to 18:30)."""
    mid = hour_of_day + 0.5
    return np.where((mid > 6.5) & (mid < 18.5), np.sin(np.pi * (mid - 6.5) / 12.0), 0.0)


def gen_series(nw: Network, cal: Calendar, seed: int) -> tuple[list[str], np.ndarray]:
    """Hourly MW for every generator except the slack (Bujagali takes the balance)."""
    rng = rng_for(seed, "gens")
    n_h, n_d = len(cal.hours), len(cal.days)
    h = cal.hour_of_day
    month_num = cal.hours.month.to_numpy()
    evening = np.array(SHAPES["urban_residential"]["WD"])[h]
    ids, cols = [], []
    for r in nw.gens.itertuples():
        if r.control == "slack":
            continue
        if r.technology == "solar":
            rainy = np.isin(month_num, [3, 4, 5, 10, 11])
            cloud_day = rng.uniform(0.45, 1.0, n_d)[cal.day_index]
            cloud_day = np.where(rainy, cloud_day * 0.85, cloud_day)
            p = r.p_max_mw * 0.96 * clear_sky(h) * cloud_day * np.clip(1 + 0.08 * rng.standard_normal(n_h), 0.5, 1.1)
        elif r.technology == "thermal":
            # A peaker: off at night, part load by day, near full in the evening; less on NWD.
            sched = np.select([h < 6, h < 17, h < 23], [0.0, 12.0, 42.0], 20.0)
            sched = np.where(cal.is_wd, sched, sched * 0.6)
            p = sched * np.clip(1 + 0.05 * rng.standard_normal(n_h), 0.8, 1.15)
            # Ten days of maintenance in May 2026.
            maint = (cal.hours >= pd.Timestamp("2026-05-11")) & (cal.hours < pd.Timestamp("2026-05-21"))
            p = np.where(maint, 0.0, p)
        elif r.gen_id == "G-NALH-1":
            dry = np.isin(month_num, [1, 2, 3])
            p = (140.0 + 40.0 * (evening - 0.4) / 0.6) * np.where(dry, 0.92, 1.0)
            p = p * (1 + 0.02 * rng.standard_normal(n_d))[cal.day_index]
        else:  # Karuma
            p = (175.0 + 95.0 * (evening - 0.4) / 0.6) * (1 + 0.03 * rng.standard_normal(n_d))[cal.day_index]
            p = p * growth_factor(cal) ** 0.6
        ids.append(r.gen_id)
        cols.append(np.clip(p, 0.0, r.p_max_mw))
    return ids, np.column_stack(cols)


def make_series(nw: Network, seed: int) -> TruthSeries:
    """All hourly truth injections for the study period."""
    cal = make_calendar()
    load_ids, load_p, load_q, dc = load_series(nw, cal, seed)
    gen_ids, gen_p = gen_series(nw, cal, seed)
    return TruthSeries(cal, load_ids, load_p, load_q, gen_ids, gen_p, dc)
