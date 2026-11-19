"""Small hand-built inputs for the profile and snapshot tests (no database).

Dummy codes only (EXA, EXB, SOL, SLK), so nobody mistakes them for real figures.
March 2026 has 31 days: 22 weekdays, 9 weekend days. With the dummy holiday on
Monday 9 March it has 21 WD and 10 NWD.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.inputs import Inputs  # noqa: E402

MONTH = "2026-03"
HOLIDAY = "2026-03-09"


def net_tables() -> dict[str, pd.DataFrame]:
    """One case with three loads at two substations, a solar plant and a slack unit."""
    case = pd.DataFrame({"case_id": ["OTHER", "C1"], "case_type": ["light_load", "as_operated_peak"]})
    loads = pd.DataFrame({
        "case_id": ["C1", "C1", "C1", "OTHER"],
        "load_id": ["D-EXA-1", "D-EXA-2", "D-EXB-1", "D-EXA-1"],
        "bus": ["EXA-33-1", "EXA-33-2", "EXB-33-1", "EXA-33-1"],
        "substation_code": ["EXA", "EXA", "EXB", "EXA"],
        "share": [0.6, np.nan, np.nan, 1.0],
        "p_mw": [10.0, 10.0, 10.0, 10.0],
        "q_mvar": [1.0, 1.0, 1.0, 1.0],
        "in_service": [True, True, True, True],
    })
    gens = pd.DataFrame({
        "case_id": ["C1", "C1"],
        "gen_id": ["G-SOL-1", "G-SLK-1"],
        "plant_code": ["SOL", "SLK"],
        "technology": ["solar", "hydro"],
        "p_max_mw": [20.0, 200.0],
        "control": ["PQ", "slack"],
        "in_service": [True, True],
    })
    return {"net_case": case, "net_load": loads, "net_gen": gens}


def base_inputs(**overrides) -> Inputs:
    """Inputs for March 2026 with NCC figures and no SCADA."""
    fields = dict(
        case_id="C1",
        net_tables=net_tables(),
        months=pd.DataFrame({"month": ["2026-02", MONTH, "2026-04"], "is_forecast": [False, False, False]}),
        holidays=pd.DataFrame({"day": [pd.Timestamp(HOLIDAY).date()], "name": ["Example holiday"]}),
        substation_monthly=pd.DataFrame({
            "month": [MONTH, MONTH],
            "substation": ["Example A", "Example B"],
            "substation_code": ["EXA", "EXB"],
            "energy_mwh": [30000.0, 15000.0],
            "peak_mw": [60.0, 30.0],
            "peak_mvar": [np.nan, 9.0],
            "coincident_mw": [np.nan, 25.0],
            "min_mw": [np.nan, np.nan],
        }),
        generation_monthly=pd.DataFrame({
            "month": [MONTH], "plant": ["Example solar"], "plant_code": ["SOL"],
            "technology": ["solar"], "sent_out_mwh": [3000.0],
        }),
    )
    fields.update(overrides)
    return Inputs(**fields)


def scada_points() -> pd.DataFrame:
    """EXA has a bsp bay (P and Q) and a transformer bay; the bsp bay must be chosen."""
    return pd.DataFrame({
        "point_id": ["EXA.F1.P", "EXA.F1.Q", "EXA.T1.P"],
        "substation": ["Example A"] * 3,
        "substation_code": ["EXA"] * 3,
        "element_type": ["bsp", "bsp", "transformer"],
        "winding": ["na", "na", "hv"],
        "voltage_kv": [33.0, 33.0, 132.0],
        "quantity": ["P", "Q", "P"],
        "unit": ["MW", "MVAr", "MW"],
        "sign_convention": ["+ = from the busbar into the feeder"] * 3,
    })


def scada_hour_value(day: str, hour: int) -> float:
    """Known synthetic load: 20 MW + hour, plus 10 MW on the weekday sample."""
    return 20.0 + hour + (10.0 if day == "2026-03-10" else 0.0)


def scada_frame() -> pd.DataFrame:
    """Two days of hourly SCADA for EXA: Tuesday 10 March (WD) and Sunday 15 March (NWD)."""
    rows = []
    for day in ("2026-03-10", "2026-03-15"):
        for h in range(24):
            ts = pd.Timestamp(f"{day} {h:02d}:00")
            p = scada_hour_value(day, h)
            rows += [(ts, "EXA.F1.P", p, "MW", "good"), (ts, "EXA.F1.Q", p * 0.3, "MVAr", "good"),
                     (ts, "EXA.T1.P", 999.0, "MW", "good")]
    rows.append((pd.Timestamp("2026-03-10 05:00"), "EXA.F1.P", -500.0, "MW", "bad"))
    return pd.DataFrame(rows, columns=["timestamp", "point_id", "value", "unit", "quality"])


@pytest.fixture
def inputs() -> Inputs:
    return base_inputs()


@pytest.fixture
def scada_inputs() -> Inputs:
    return base_inputs(scada_points=scada_points(), scada_frames={MONTH: scada_frame()})
