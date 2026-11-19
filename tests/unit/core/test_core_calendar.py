"""Study calendar and day-type weights (engine/calendar.py)."""
from datetime import date

from engine.calendar import count_days, day_type, month_table, read_holidays, study_months


def test_default_study_months():
    months = study_months({})
    assert len(months) == 13
    assert months[0] == date(2025, 9, 1) and months[-1] == date(2026, 9, 1)


def test_months_from_config():
    cfg = {"core": {"study": {"start": "2026-01", "end": "2026-03", "forecast_years": [2030, 2031]}}}
    table = month_table(cfg, holidays={})
    assert list(table.month) == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2030, 1, 1), date(2031, 1, 1)]
    assert list(table.is_forecast) == [False, False, False, True, True]


def test_weights_add_up():
    holidays = read_holidays()
    table = month_table({}, holidays)
    assert (table.n_wd + table.n_nwd == table.days).all()
    assert (table.hours == 24 * table.days).all()
    year = table[table.is_forecast].iloc[0]
    assert year.label == "2030" and year.days == 365


def test_march_2026_counts():
    # March 2026: 22 weekdays; Women's Day (8th) is a Sunday; Eid al-Fitr (20th, approximate) is a Friday.
    holidays = read_holidays()
    assert count_days(date(2026, 3, 1), date(2026, 4, 1), {}) == (22, 9)
    assert count_days(date(2026, 3, 1), date(2026, 4, 1), holidays) == (21, 10)


def test_day_type():
    holidays = read_holidays()
    assert day_type(date(2026, 3, 12), holidays) == "WD"     # Thursday
    assert day_type(date(2026, 3, 14), holidays) == "NWD"    # Saturday
    assert day_type(date(2026, 10, 9), holidays) == "NWD"    # Independence Day, a Friday


def test_holidays_cover_the_period():
    holidays = read_holidays()
    assert min(holidays) <= date(2025, 10, 9) and max(holidays) >= date(2030, 12, 25)
    assert any("approximate" in name for name in holidays.values())
