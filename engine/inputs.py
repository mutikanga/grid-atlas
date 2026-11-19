"""The inputs bundle every engine stage reads (F3b).

``load_inputs(ctx)`` reads the network tables, the reference registers and the NCC,
SCADA and operations inputs once per run and returns an ``Inputs`` object.
``RunContext.inputs`` caches it, so stages share one copy.

Normalisation done here, so the rest of the engine can rely on it:
- every ``month`` column is a 'YYYY-MM' string;
- every date-time column is a naive pandas Timestamp in East Africa Time (EAT);
- SCADA hourly data is read one month at a time, only when asked (``inputs.scada(month)``),
  because a year of it for every point is large.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pandas as pd

from engine.profiles import cases_cfg

log = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3))
HANDBUILT_CASE_ID = "HANDBUILT"

# T01 network tables (ts.net_*), keyed in net_tables without the schema.
T01_TABLES = (
    "net_case", "net_bus", "net_line", "net_trafo", "net_trafo3w", "net_gen", "net_load",
    "net_shunt", "net_switch", "net_boundary", "net_solved_bus", "net_solved_branch", "net_change",
)
# T12 hand-built schedules (ts.hb_*), converted to T01 shape when no model was delivered.
T12_TABLES = ("hb_substation", "hb_line", "hb_trafo", "hb_gen", "hb_boundary")
# Names the F3a converter in loaders/network_handbuilt.py may use (first match wins).
HANDBUILT_CONVERTERS = ("to_net_tables", "handbuilt_to_net_tables", "convert", "build_net_tables")

SCADA_COLUMNS = ["timestamp", "point_id", "value", "unit", "quality"]
DATETIME_COLUMNS = ("timestamp", "peak_at", "min_at", "start_at", "end_at")


def _empty() -> pd.DataFrame:
    return pd.DataFrame()


@dataclass
class Inputs:
    """Everything the engine needs from ts.* and ref.*, read once per run.

    Unit tests build one by hand; every field has an empty default.
    ``scada_frames`` holds SCADA months already in memory (tests put data there);
    ``scada_loader`` reads a month from the database the first time it is asked for.
    ``cache`` is scratch space for engine/profiles.py (shapes per month), so the
    same month is not worked out twice in one run.
    """

    case_id: str = ""
    net_tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    substations: pd.DataFrame = field(default_factory=_empty)
    plants: pd.DataFrame = field(default_factory=_empty)
    months: pd.DataFrame = field(default_factory=_empty)
    holidays: pd.DataFrame = field(default_factory=_empty)
    substation_monthly: pd.DataFrame = field(default_factory=_empty)
    generation_monthly: pd.DataFrame = field(default_factory=_empty)
    sample_days: pd.DataFrame = field(default_factory=_empty)
    scada_points: pd.DataFrame = field(default_factory=_empty)
    events: pd.DataFrame = field(default_factory=_empty)
    system_monthly: pd.DataFrame = field(default_factory=_empty)
    is_handbuilt: bool = False
    scada_loader: Callable[[str], pd.DataFrame] | None = field(default=None, repr=False)
    scada_frames: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)
    cache: dict[Any, Any] = field(default_factory=dict, repr=False)

    def scada(self, month: str) -> pd.DataFrame:
        """SCADA hourly rows for one 'YYYY-MM' month (columns timestamp, point_id, value, unit, quality).

        Empty when the month has no SCADA.
        """
        if month not in self.scada_frames:
            df = self.scada_loader(month) if self.scada_loader else None
            if df is None or df.empty:
                df = pd.DataFrame(columns=SCADA_COLUMNS)
            self.scada_frames[month] = df
        return self.scada_frames[month]

    def case_table(self, name: str) -> pd.DataFrame:
        """One T01 table (for example 'net_load') limited to the base case."""
        df = self.net_tables.get(name, pd.DataFrame())
        if df.empty or "case_id" not in df.columns:
            return df
        return df[df["case_id"] == self.case_id]


# --------------------------------------------------------------------------- normalising


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Months to 'YYYY-MM' strings and date-times to naive EAT Timestamps."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    df = df.copy()
    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"].astype(str).str[:7], format="%Y-%m").dt.strftime("%Y-%m")
    for col in DATETIME_COLUMNS:
        if col in df.columns:
            df[col] = to_eat_naive(df[col])
    return df


def to_eat_naive(values: pd.Series) -> pd.Series:
    """Timestamps as naive EAT. Time-zone-aware values are converted; naive ones are taken as EAT."""
    try:
        s = pd.to_datetime(values)
    except (ValueError, TypeError):
        # Python datetimes with different UTC offsets in one column: go through UTC.
        s = pd.to_datetime(values, utc=True)
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_convert("Africa/Kampala").dt.tz_localize(None)
    return s


# --------------------------------------------------------------------------- choosing the case


def choose_base_case(net_case: pd.DataFrame | None, configured: str | None = None) -> str:
    """The base case_id: the configured one, else the first 'as_operated_peak', else the first case.

    A configured case that is not in ``net_case`` (a typo, or a hand-built network
    replacing the model) is ignored with a warning, because an unknown case_id would
    leave the run with no loads and no generators.
    """
    if net_case is None or net_case.empty:
        return configured or ""
    if configured:
        if "case_id" not in net_case.columns or configured in set(net_case["case_id"].astype(str)):
            return configured
        log.warning("cases.base_case %r is not in ts.net_case; choosing the base case automatically", configured)
    peak = net_case[net_case["case_type"] == "as_operated_peak"] if "case_type" in net_case.columns else net_case.iloc[0:0]
    return str((peak if not peak.empty else net_case)["case_id"].iloc[0])


def handbuilt_net_tables(hb_tables: dict[str, pd.DataFrame], plants: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Convert T12 hand-built schedules into T01-shaped tables with case_id 'HANDBUILT'.

    The conversion itself belongs to F3a (loaders/network_handbuilt.py); this only finds
    and calls it. The plants register is passed on when the converter accepts it, so the
    generators get the same plant codes as NCC's generation figures (without it the
    converter falls back to the first three letters of the plant name, which would not
    match, and the plants would get no monthly profile).
    """
    module = importlib.import_module("loaders.network_handbuilt")
    for name in HANDBUILT_CONVERTERS:
        fn = getattr(module, name, None)
        if callable(fn):
            if plants is not None and "plants" in inspect.signature(fn).parameters:
                return fn(hb_tables, plants=plants)
            return fn(hb_tables)
    raise AttributeError(f"loaders.network_handbuilt has none of {HANDBUILT_CONVERTERS}")


# --------------------------------------------------------------------------- loading


def _scada_month_loader(ctx: Any) -> Callable[[str], pd.DataFrame]:
    """A function that reads one month of ts.scada_hourly, bounded in EAT."""

    def load(month: str) -> pd.DataFrame:
        year, mon = (int(x) for x in month.split("-"))
        start = datetime(year, mon, 1, tzinfo=EAT)
        end = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=EAT)
        df = ctx.read(
            'select "timestamp", point_id, value, unit, quality from ts.scada_hourly '
            'where "timestamp" >= :start and "timestamp" < :end',
            {"start": start, "end": end},
        )
        return normalise(df)

    return load


def load_inputs(ctx: Any) -> Inputs:
    """Read the run's inputs from the database into an ``Inputs`` bundle.

    The network comes from the T01 tables. When ts.net_case is empty and the T12
    hand-built tables have rows, they are converted to T01 shape (case_id 'HANDBUILT').
    """
    c = cases_cfg(ctx.cfg)
    plants = ctx.table("ref.plant")
    net_tables = {name: ctx.table(f"ts.{name}") for name in T01_TABLES}
    is_handbuilt = False
    if net_tables["net_case"].empty:
        hb = {name: ctx.table(f"ts.{name}") for name in T12_TABLES}
        if any(not df.empty for df in hb.values()):
            ctx.log.info("No T01 network case loaded; using the hand-built T12 network (approximate)")
            net_tables = {**net_tables, **handbuilt_net_tables(hb, plants)}
            is_handbuilt = True
    case_id = choose_base_case(net_tables.get("net_case"), c["base_case"] or (HANDBUILT_CASE_ID if is_handbuilt else ""))
    if not case_id:
        ctx.log.warning("No network case found in ts.net_case or ts.hb_*")

    return Inputs(
        case_id=case_id,
        net_tables=net_tables,
        substations=ctx.table("ref.substation"),
        plants=plants,
        months=normalise(ctx.table("ref.month")),
        holidays=ctx.table("ref.holiday"),
        substation_monthly=normalise(ctx.table("ts.ncc_substation_monthly")),
        generation_monthly=normalise(ctx.table("ts.ncc_generation_monthly")),
        sample_days=normalise(ctx.table("ts.ncc_sample_day")),
        scada_points=ctx.table("ts.scada_point"),
        events=normalise(ctx.table("ts.ops_event")),
        system_monthly=normalise(ctx.table("ts.ncc_system_monthly")),
        is_handbuilt=is_handbuilt,
        scada_loader=_scada_month_loader(ctx),
    )
