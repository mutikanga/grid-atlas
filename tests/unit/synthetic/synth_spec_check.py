"""A small, independent checker of rows against a template spec (used by the synthetic tests).

It deliberately does not import the loaders: the synthetic files must satisfy the spec
on their own, whatever the loader does.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

PATTERNS = {
    "month": re.compile(r"^\d{4}-\d{2}$"),
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "datetime": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"),
}
PARSE = {"month": "%Y-%m", "date": "%Y-%m-%d", "datetime": "%Y-%m-%d %H:%M"}


def blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and v.strip() == "")


def check_value(col: dict, v) -> str | None:
    """None if v is acceptable for the column, else a short reason."""
    if blank(v):
        return "missing required" if col.get("required") else None
    t = col["type"]
    if t in PATTERNS:
        s = str(v)
        if not PATTERNS[t].match(s):
            return f"bad {t} {s!r}"
        try:
            datetime.strptime(s, PARSE[t])
        except ValueError:
            return f"unparseable {t} {s!r}"
        return None
    if t == "yn":
        return None if v in ("Y", "N") else f"bad yn {v!r}"
    if t == "enum":
        return None if str(v) in col["enum"] else f"{v!r} not in {col['enum']}"
    if t in ("int", "number"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return f"not a number {v!r}"
        if t == "int" and not float(v).is_integer():
            return f"not an integer {v!r}"
        if "min" in col and v < col["min"]:
            return f"{v} below min {col['min']}"
        if "max" in col and v > col["max"]:
            return f"{v} above max {col['max']}"
    return None


def check_rows(sheet: dict, header: list[str], rows: list[tuple]) -> list[str]:
    """All problems found in a sheet's rows (empty list when clean)."""
    problems = []
    expected = [c["name"] for c in sheet["columns"]]
    if header != expected:
        return [f"{sheet['name']}: header {header} != spec {expected}"]
    cols = sheet["columns"]
    keys = sheet.get("key", [])
    seen = set()
    for n, row in enumerate(rows, start=2):
        for col, v in zip(cols, row):
            why = check_value(col, v)
            if why:
                problems.append(f"{sheet['name']} row {n} {col['name']}: {why}")
        if keys:
            k = tuple(row[header.index(c)] for c in keys)
            if k in seen:
                problems.append(f"{sheet['name']} row {n}: duplicate key {k}")
            seen.add(k)
    return problems
