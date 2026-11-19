"""Cell coercion (loaders/units.py)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from loaders.units import CoercionError, coerce, is_blank

EAT = timezone(timedelta(hours=3))


@pytest.mark.parametrize("raw, expected", [
    ("2026-03", date(2026, 3, 1)),
    ("2026-3", date(2026, 3, 1)),
    ("2026-03-17", date(2026, 3, 1)),
    (datetime(2026, 3, 17, 8, 0), date(2026, 3, 1)),
    (date(2025, 9, 30), date(2025, 9, 1)),
    (46082.0, date(2026, 3, 1)),          # Excel serial for 2026-03-01
])
def test_month(raw, expected):
    assert coerce(raw, "month") == expected


def test_month_rejects_text():
    with pytest.raises(CoercionError):
        coerce("March", "month")
    with pytest.raises(CoercionError):
        coerce("2026-13", "month")


def test_date():
    assert coerce("2026-03-12", "date") == date(2026, 3, 12)
    assert coerce("12/03/2026", "date") == date(2026, 3, 12)   # day first
    assert coerce(datetime(2026, 3, 12, 20), "date") == date(2026, 3, 12)
    with pytest.raises(CoercionError):
        coerce("2026-02-30", "date")


def test_datetime_is_eat():
    v = coerce("2026-03-12 20:00", "datetime")
    assert v == datetime(2026, 3, 12, 20, 0, tzinfo=EAT)
    assert v.utcoffset() == timedelta(hours=3)
    assert coerce(datetime(2026, 3, 12, 20), "datetime") == datetime(2026, 3, 12, 20, tzinfo=EAT)
    # an explicit UTC time is converted to EAT
    assert coerce("2026-03-12T17:00:00Z", "datetime") == datetime(2026, 3, 12, 20, 0, tzinfo=EAT)
    assert coerce("2026-03-12T20:00:00+03:00", "datetime").hour == 20
    # Excel serial with a fraction of a day
    assert coerce(46082.5, "datetime") == datetime(2026, 3, 1, 12, 0, tzinfo=EAT)
    with pytest.raises(CoercionError):
        coerce("yesterday", "datetime")


@pytest.mark.parametrize("raw, expected", [("Y", True), ("n", False), ("yes", True), ("No", False),
                                           ("TRUE", True), ("false", False), (1, True), (0.0, False)])
def test_yn(raw, expected):
    assert coerce(raw, "yn") is expected


def test_yn_rejects_other():
    with pytest.raises(CoercionError):
        coerce("maybe", "yn")


def test_numbers():
    assert coerce("1,234.5", "number") == 1234.5
    assert coerce("12 345", "number") == 12345.0
    assert coerce(7, "number") == 7.0
    assert coerce("3", "int") == 3
    assert coerce(3.0, "int") == 3
    assert coerce("1,200", "int") == 1200
    with pytest.raises(CoercionError):
        coerce("3.5", "int")
    with pytest.raises(CoercionError):
        coerce("abc", "number")
    with pytest.raises(CoercionError):
        coerce(True, "number")


def test_text_and_enum():
    assert coerce(132.0, "text") == "132"
    assert coerce("  Kawanda ", "text") == "Kawanda"
    assert coerce(400, "enum", ["400", "220"]) == "400"
    assert coerce("Metered", "enum", ["metered", "estimated"]) == "metered"
    with pytest.raises(CoercionError):
        coerce("guessed", "enum", ["metered", "estimated"])


def test_blank():
    for v in (None, "", "   ", float("nan")):
        assert is_blank(v)
        assert coerce(v, "number") is None
    assert not is_blank(0)
