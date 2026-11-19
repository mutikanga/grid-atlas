"""Study calendar: the months, weekday and non-weekday counts, and East Africa Time.

Monthly losses are weighted load flows: a weekday profile times the number of weekdays,
plus a non-weekday profile times the number of weekend days and public holidays. This
module counts those days, using config/holidays_ug.csv.
"""
from __future__ import annotations

import calendar as _cal
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine.config import CONFIG_DIR

# East Africa Time: UTC+3 all year (Uganda has no daylight saving).
EAT = timezone(timedelta(hours=3), "EAT")

DEFAULT_START = "2025-09"
DEFAULT_END = "2026-09"
DEFAULT_FORECAST_YEARS = (2030,)


def parse_month(text: str) -> date:
    """'2026-03' -> date(2026, 3, 1)."""
    year, month = str(text).strip().split("-")[:2]
    return date(int(year), int(month), 1)


def next_month(month: date) -> date:
    """The first day of the following month."""
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)


def month_range(start: date, end: date) -> list[date]:
    """First days of every month from start to end, inclusive."""
    months, current = [], date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        current = next_month(current)
    return months


def study_months(cfg: dict[str, Any] | None = None) -> list[date]:
    """The study months from cfg['core']['study'] (default 2025-09 to 2026-09)."""
    study = ((cfg or {}).get("core") or {}).get("study") or {}
    return month_range(parse_month(study.get("start", DEFAULT_START)), parse_month(study.get("end", DEFAULT_END)))


def forecast_years(cfg: dict[str, Any] | None = None) -> list[int]:
    """Whole forecast years (default [2030])."""
    study = ((cfg or {}).get("core") or {}).get("study") or {}
    return [int(y) for y in study.get("forecast_years", DEFAULT_FORECAST_YEARS)]


def read_holidays(path: Path | None = None) -> dict[date, str]:
    """{day: name} from config/holidays_ug.csv (columns date, name)."""
    path = path or CONFIG_DIR / "holidays_ug.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {date.fromisoformat(r["date"].strip()): r["name"].strip() for r in csv.DictReader(fh) if r.get("date")}


def is_working_day(day: date, holidays: set[date] | dict[date, str]) -> bool:
    """Monday to Friday and not a public holiday."""
    return day.weekday() < 5 and day not in holidays


def day_type(day: date, holidays: set[date] | dict[date, str]) -> str:
    """'WD' for a working weekday, 'NWD' for a weekend day or public holiday."""
    return "WD" if is_working_day(day, holidays) else "NWD"


def count_days(start: date, end_exclusive: date, holidays: set[date] | dict[date, str]) -> tuple[int, int]:
    """(weekdays, non-weekdays) in [start, end_exclusive)."""
    n_wd = n_nwd = 0
    day = start
    while day < end_exclusive:
        if is_working_day(day, holidays):
            n_wd += 1
        else:
            n_nwd += 1
        day += timedelta(days=1)
    return n_wd, n_nwd


def month_row(month: date, holidays: set[date] | dict[date, str]) -> dict[str, Any]:
    """One ref.month row for a study month."""
    days = _cal.monthrange(month.year, month.month)[1]
    n_wd, n_nwd = count_days(month, next_month(month), holidays)
    return {"month": month, "label": month.strftime("%b %Y"), "days": days, "hours": 24 * days,
            "n_wd": n_wd, "n_nwd": n_nwd, "is_forecast": False}


def year_row(year: int, holidays: set[date] | dict[date, str]) -> dict[str, Any]:
    """One ref.month row standing for a whole forecast year (month = 1 January)."""
    start, end = date(year, 1, 1), date(year + 1, 1, 1)
    days = (end - start).days
    n_wd, n_nwd = count_days(start, end, holidays)
    return {"month": start, "label": str(year), "days": days, "hours": 24 * days,
            "n_wd": n_wd, "n_nwd": n_nwd, "is_forecast": True}


def month_table(cfg: dict[str, Any] | None = None, holidays: dict[date, str] | None = None) -> pd.DataFrame:
    """Rows for ref.month: the study months, then each forecast year."""
    holidays = read_holidays() if holidays is None else holidays
    rows = [month_row(m, holidays) for m in study_months(cfg)]
    rows += [year_row(y, holidays) for y in forecast_years(cfg)]
    return pd.DataFrame(rows, columns=["month", "label", "days", "hours", "n_wd", "n_nwd", "is_forecast"])


def to_eat(value: datetime) -> datetime:
    """A datetime in EAT. Naive values are taken to be EAT already (the data convention)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=EAT)
    return value.astimezone(EAT)
