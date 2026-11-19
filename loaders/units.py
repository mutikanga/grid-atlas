"""Turn delivered cell values into typed values (contracts section 3.2).

Excel and CSV give us strings, floats, datetimes and Excel serial numbers. Each function
here takes one raw value and returns the clean Python value, or raises CoercionError with
a short message that ends up in meta.import_issue. Blank cells become None.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any

from engine.calendar import EAT

# Excel stores dates as days since 1899-12-30 (the 1900 leap-year bug is baked in).
EXCEL_EPOCH = datetime(1899, 12, 30)

_MONTH_RE = re.compile(r"^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?$")
_DMY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
# 12/03/2026 14:00, day first: how many Ugandan SCADA and Excel exports write date-times.
_DMY_TIME_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")
_THOUSANDS_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d*)?$")
_TRUE = {"Y", "YES", "TRUE", "T", "1"}
_FALSE = {"N", "NO", "FALSE", "F", "0"}


class CoercionError(ValueError):
    """A value cannot be read as the column's type."""


def is_blank(value: Any) -> bool:
    """None, NaN, or text that is empty after stripping."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def to_text(value: Any) -> str:
    """Text with surrounding spaces removed. 132.0 from Excel becomes '132'."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def to_number(value: Any) -> float:
    """A float. Text may use thousands separators ('1,234.5' or '1 234.5')."""
    if isinstance(value, bool):
        raise CoercionError("expected a number, got a yes/no value")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(" ", "").replace(" ", "")
        if "," in text:
            # Only true thousands groups ('1,234,567.8') are accepted. A decimal comma
            # ('61,5' from a semicolon CSV) would otherwise silently become 615.
            if not _THOUSANDS_RE.match(text):
                raise CoercionError(f"expected a number with a decimal point, got {str(value).strip()!r}")
            text = text.replace(",", "")
        try:
            number = float(text)
        except ValueError:
            raise CoercionError(f"expected a number, got {str(value).strip()!r}") from None
    if math.isnan(number) or math.isinf(number):
        raise CoercionError("expected a finite number")
    return number


# int columns are PostgreSQL 'integer' (32-bit). A bigger value would make COPY fail and
# roll back the whole load, so it is rejected here as one bad row instead.
INT_MAX = 2**31 - 1


def to_int(value: Any) -> int:
    """A whole number. 3.0 is fine; 3.5 is an error."""
    number = to_number(value)
    if not number.is_integer():
        raise CoercionError(f"expected a whole number, got {number:g}")
    if abs(number) > INT_MAX:
        raise CoercionError(f"{number:g} is too large for a whole-number column")
    return int(number)


def excel_serial_to_datetime(serial: float) -> datetime:
    """An Excel serial date number (e.g. 46082.5) as a datetime."""
    if not 1 <= serial < 2958466:   # 1900-01-01 .. 9999-12-31
        raise CoercionError(f"{serial:g} is not a valid Excel date")
    return EXCEL_EPOCH + timedelta(days=serial)


def _date_from(value: Any) -> date:
    """Shared date reading for date and month columns."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return excel_serial_to_datetime(float(value)).date()
    text = str(value).strip()
    match = _MONTH_RE.match(text)
    if match and match.group(3):
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)), text)
    match = _DMY_RE.match(text)   # 12/03/2026: day first, as written in Uganda
    if match:
        return _safe_date(int(match.group(3)), int(match.group(2)), int(match.group(1)), text)
    match = _DATETIME_RE.match(text)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)), text)
    raise CoercionError(f"expected a date as YYYY-MM-DD, got {text!r}")


def _safe_date(year: int, month: int, day: int, text: str) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise CoercionError(f"{text!r} is not a real date") from None


def to_month(value: Any) -> date:
    """The first day of the month. Accepts 'YYYY-MM', a date or an Excel date."""
    if isinstance(value, str):
        match = _MONTH_RE.match(value.strip())
        if match and not match.group(3):
            return _safe_date(int(match.group(1)), int(match.group(2)), 1, value)
    try:
        day = _date_from(value)
    except CoercionError:
        raise CoercionError(f"expected a month as YYYY-MM, got {to_text(value)!r}") from None
    return date(day.year, day.month, 1)


def to_date(value: Any) -> date:
    """A calendar date. Accepts 'YYYY-MM-DD', 'DD/MM/YYYY', a date or an Excel date."""
    return _date_from(value)


def to_datetime(value: Any) -> datetime:
    """A timezone-aware datetime. Values without a zone are East Africa Time (UTC+3)."""
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time())
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result = excel_serial_to_datetime(float(value))
        result = result.replace(microsecond=0) + timedelta(seconds=round(result.microsecond / 1e6))
    else:
        text = str(value).strip()
        match = _DATETIME_RE.match(text)
        dmy = None if match else _DMY_TIME_RE.match(text)
        if dmy:
            d, mo, y, h, mi, s = dmy.groups()
            zone = None
        elif not match:
            raise CoercionError(f"expected a date-time as YYYY-MM-DD HH:MM, got {text!r}")
        else:
            y, mo, d, h, mi, s, zone = match.groups()
        try:
            result = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
        except ValueError:
            raise CoercionError(f"{text!r} is not a real date-time") from None
        if zone:
            result = datetime.fromisoformat(f"{result.isoformat()}{'+00:00' if zone == 'Z' else _colon(zone)}")
    if result.tzinfo is None:
        return result.replace(tzinfo=EAT)
    return result.astimezone(EAT)


def _colon(zone: str) -> str:
    """'+0300' -> '+03:00'."""
    return zone if ":" in zone else f"{zone[:3]}:{zone[3:]}"


def to_bool(value: Any) -> bool:
    """Y/N, yes/no, true/false, 1/0 as a boolean."""
    if isinstance(value, bool):
        return value
    text = to_text(value).upper()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise CoercionError(f"expected Y or N, got {to_text(value)!r}")


def to_enum(value: Any, allowed: tuple[str, ...] | list[str]) -> str:
    """One of the allowed values. Case and surrounding spaces are forgiven."""
    text = to_text(value)
    if text in allowed:
        return text
    for option in allowed:
        if option.lower() == text.lower():
            return option
    raise CoercionError(f"{text!r} is not one of: {', '.join(allowed)}")


def coerce(value: Any, type_: str, enum: tuple[str, ...] | list[str] = ()) -> Any:
    """Convert value to the spec type. Blank gives None; a bad value raises CoercionError."""
    if is_blank(value):
        return None
    if type_ == "text":
        return to_text(value)
    if type_ == "int":
        return to_int(value)
    if type_ == "number":
        return to_number(value)
    if type_ == "month":
        return to_month(value)
    if type_ == "date":
        return to_date(value)
    if type_ == "datetime":
        return to_datetime(value)
    if type_ == "yn":
        return to_bool(value)
    if type_ == "enum":
        return to_enum(value, enum)
    raise ValueError(f"unknown spec type {type_!r}")
