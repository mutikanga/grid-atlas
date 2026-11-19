"""The 'dirty' variant: deliberate data-quality faults so the loader's quarantine is exercised.

Each injection is recorded (dataset, sheet, row, column, kind) in truth.json so the
loader tests can check that every fault is caught. Row numbers are given two ways:
``excel_row`` (header on row 1, so the first data row is 2) and ``data_index`` (0-based).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Injection = dict


def _record(dataset: str, sheet: str, idx: int, column: str, kind: str, value, expect: str) -> Injection:
    return {"dataset": dataset, "sheet": sheet, "data_index": int(idx), "excel_row": int(idx) + 2,
            "column": column, "kind": kind, "value": None if value is None else str(value), "expected_severity": expect}


def _row(df: pd.DataFrame, **match) -> int:
    """Index of the first row matching all column=value pairs."""
    m = np.ones(len(df), dtype=bool)
    for k, v in match.items():
        m &= (df[k].astype(str) == str(v)).to_numpy()
    hits = np.where(m)[0]
    if not len(hits):
        raise KeyError(f"no row with {match}")
    return int(hits[0])


def inject(sheets: dict[str, dict[str, pd.DataFrame]], scada: dict[str, pd.DataFrame]) -> list[Injection]:
    """Mutate the sheets (dataset -> sheet -> DataFrame) and SCADA months in place; return what was done."""
    log: list[Injection] = []

    sub = sheets["ncc_monthly"]["substation_monthly"]
    i = _row(sub, month="2026-03", metering_point="KAW 33 kV feeders (BSP)")
    sub.at[i, "substation"] = "Kawnda"
    log.append(_record("ncc_monthly", "substation_monthly", i, "substation", "misspelled_name", "Kawnda", "error"))
    i = _row(sub, month="2026-04", metering_point="MUT 33 kV feeders (BSP)")
    sub.at[i, "substation"] = "Mutundw"
    log.append(_record("ncc_monthly", "substation_monthly", i, "substation", "misspelled_name", "Mutundw", "error"))
    i = _row(sub, month="2026-05", metering_point="LUG 33 kV feeders (BSP)")
    sub.at[i, "energy_mwh"] = float(sub.at[i, "energy_mwh"]) * 1000.0
    log.append(_record("ncc_monthly", "substation_monthly", i, "energy_mwh", "kwh_entered_as_mwh", sub.at[i, "energy_mwh"], "warning"))
    i = _row(sub, month="2026-07", metering_point="KNO 33 kV feeders (BSP)")
    sub.at[i, "energy_mwh"] = None
    log.append(_record("ncc_monthly", "substation_monthly", i, "energy_mwh", "missing_required", None, "error"))
    i = _row(sub, month="2026-06", metering_point="QWY 33 kV feeders (BSP)")
    dup = sub.iloc[[i]].copy()
    sheets["ncc_monthly"]["substation_monthly"] = sub = pd.concat([sub, dup], ignore_index=True)
    log.append(_record("ncc_monthly", "substation_monthly", len(sub) - 1, "month,substation,metering_point",
                       "duplicate_key", "2026-06 QWY", "error"))

    bm = sheets["ncc_monthly"]["boundary_meters"]
    i = _row(bm, month="2026-08", meter_id="LUG-M01", direction="import")
    bm.at[i, "direction"] = "imp"
    log.append(_record("ncc_monthly", "boundary_meters", i, "direction", "bad_enum", "imp", "error"))

    gen = sheets["ncc_monthly"]["generation_monthly"]
    i = _row(gen, month="2025-10", plant="Kabulasoke Solar Plant")
    gen.at[i, "plant"] = "Kabulasok Solar"
    log.append(_record("ncc_monthly", "generation_monthly", i, "plant", "misspelled_name", "Kabulasok Solar", "error"))

    ev = sheets["ncc_operations"]["events"]
    i = 1
    ev.at[i, "event_type"] = "forced trip"
    log.append(_record("ncc_operations", "events", i, "event_type", "bad_enum", "forced trip", "error"))
    i = 2
    ev.at[i, "start_at"] = None
    log.append(_record("ncc_operations", "events", i, "start_at", "missing_required", None, "error"))

    sales = sheets["commercial"]["bsp_sales"] = sheets["commercial"]["bsp_sales"].astype({"energy_kwh": float})
    i = _row(sales, month="2026-02", meter_id="MUT-B01")
    sales.at[i, "energy_kwh"] = round(float(sales.at[i, "energy_kwh"]) / 1000.0, 3)
    log.append(_record("commercial", "bsp_sales", i, "energy_kwh", "mwh_entered_as_kwh", sales.at[i, "energy_kwh"], "warning"))
    i = _row(sales, month="2026-03", meter_id="NKG-B01")
    sales.at[i, "bulk_supply_point"] = None
    log.append(_record("commercial", "bsp_sales", i, "bulk_supply_point", "missing_required", None, "error"))

    month = "2026-08"
    df = scada[month]
    dup_rows = df.iloc[[100, 101, 102]].copy()
    scada[month] = df = pd.concat([df, dup_rows], ignore_index=True)
    for k in range(3):
        log.append(_record("scada", "hourly_data", len(df) - 3 + k, "timestamp,point_id", "duplicate_key",
                           f"{dup_rows.iloc[k]['timestamp']} {dup_rows.iloc[k]['point_id']}", "error"))
    df.at[200, "timestamp"] = "2026-08-31 25:00"
    log.append(_record("scada", "hourly_data", 200, "timestamp", "bad_datetime", "2026-08-31 25:00", "error"))
    df.at[300, "value"] = None
    log.append(_record("scada", "hourly_data", 300, "value", "missing_required", None, "error"))
    for inj in log:
        if inj["dataset"] == "scada":
            inj["file"] = f"SYNTHETIC_scada_{month}.csv"
    return log
