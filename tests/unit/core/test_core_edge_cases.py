"""Edge cases real utility data hits, each one a bug found in review (no database)."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from engine.context import scenario_settings
from loaders.generic import csv_encoding, is_excel_error, map_headers, read_csv, validate_row
from loaders.manifest import ManifestError, check_provenance, read_manifest, verify_files
from loaders.names import NameResolver, alias_rows, normalise
from loaders.spec import load_specs
from loaders.units import CoercionError, coerce, to_datetime, to_int
from loaders.vector import to_ewkt

EAT = timezone(timedelta(hours=3))
SPEC = load_specs()["ncc_monthly"]


def resolver():
    subs = pd.DataFrame({"ss_code": ["KAW"], "name": ["Kawanda"]})
    plants = pd.DataFrame({"plant_code": ["NMVT"], "name": ["Namanve thermal"]})
    aliases = pd.DataFrame({"alias": [], "entity_type": [], "canonical_id": [], "source": []})
    return NameResolver.from_frames(alias_rows(aliases, subs, plants), subs, plants)


# ---- units -------------------------------------------------------------------------
def test_int_too_big_for_postgres_integer_is_a_row_error_not_a_failed_load():
    assert to_int("2147483647") == 2147483647
    with pytest.raises(CoercionError, match="too large"):
        to_int(3_000_000_000)


def test_day_first_datetime_as_scada_exports_write_it():
    assert to_datetime("12/03/2026 14:00") == datetime(2026, 3, 12, 14, 0, tzinfo=EAT)
    assert to_datetime("01/07/2026") == datetime(2026, 7, 1, tzinfo=EAT)
    with pytest.raises(CoercionError):
        to_datetime("31/02/2026 10:00")
    assert coerce("2026-03-12 20:00", "datetime") == datetime(2026, 3, 12, 20, 0, tzinfo=EAT)


# ---- names ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["Kawanda S.S.", "Kawanda S.S", "Kawanda S-S", "Kawanda Sub-Station 132kV",
                                 "KAWANDA SUB STATION", "Kawanda S/S"])
def test_common_substation_suffixes_are_dropped(raw):
    assert normalise(raw) == "KAWANDA"


def test_blank_alias_source_gets_a_default():
    subs = pd.DataFrame({"ss_code": ["KAW"], "name": ["Kawanda"]})
    plants = pd.DataFrame({"plant_code": [], "name": []})
    aliases = pd.DataFrame({"alias": ["Kawanda West"], "entity_type": ["substation"], "canonical_id": ["KAW"], "source": [""]})
    rows = alias_rows(aliases, subs, plants)
    assert rows.loc[rows.alias_norm == "KAWANDA WEST", "source"].item() == "config/aliases.csv"


# ---- Excel error values ------------------------------------------------------------
def test_excel_error_in_optional_column_is_blank_with_warning():
    assert is_excel_error(" #N/A ") and is_excel_error("#DIV/0!") and not is_excel_error("N/A text")
    sheet = SPEC.sheet("substation_monthly")
    row = {"month": "2026-03", "substation": "Kawanda", "energy_mwh": 100.0, "peak_mw": 10, "metering_kv": "#N/A"}
    positions, _ = map_headers(list(row), sheet)
    record, issues, _ = validate_row(sheet, positions, list(row.values()), 2, resolver(), "T03")
    assert record is not None and record["metering_kv"] is None
    assert [(i.rule, i.severity) for i in issues] == [("excel_error", "warning")]


def test_excel_error_in_required_column_rejects_the_row():
    sheet = SPEC.sheet("substation_monthly")
    row = {"month": "2026-03", "substation": "Kawanda", "energy_mwh": "#DIV/0!", "peak_mw": 10}
    positions, _ = map_headers(list(row), sheet)
    record, issues, _ = validate_row(sheet, positions, list(row.values()), 2, resolver(), "T03")
    assert record is None
    assert {i.rule for i in issues} == {"excel_error", "required"}


# ---- CSV encoding ----------------------------------------------------------------------
def test_windows_1252_csv_is_read_not_crashed(tmp_path: Path):
    path = tmp_path / "SYNTHETIC_points.csv"
    path.write_bytes("point_id,description\nP1,Temperature \xb0C at Kawanda\n".encode("cp1252"))
    assert csv_encoding(path) == "cp1252"
    table, fh = read_csv(path, "points")
    try:
        rows = list(table.rows)
    finally:
        fh.close()
    assert rows == [(2, ["P1", "Temperature °C at Kawanda"])]
    utf8 = tmp_path / "u.csv"
    utf8.write_text("a\n°\n", encoding="utf-8")
    assert csv_encoding(utf8) == "utf-8-sig"


# ---- GIS -----------------------------------------------------------------------------
def test_z_coordinates_are_dropped_for_the_2d_geometry_columns():
    assert to_ewkt(Point(32.5, 0.4, 1180.0)) == "SRID=4326;POINT (32.5 0.4)"
    assert to_ewkt(LineString([(32.5, 0.4, 0), (32.6, 0.3, 0)])) == "SRID=4326;LINESTRING (32.5 0.4, 32.6 0.3)"


# ---- manifest --------------------------------------------------------------------------
def _manifest(folder: Path, path: str, sha: str = "0" * 64) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.toml").write_text(
        f'dataset = "ncc_monthly"\ntemplate = "T03"\nprovenance = "real"\n[[files]]\npath = "{path}"\nsha256 = "{sha}"\n')


def test_manifest_path_outside_the_folder_is_refused(tmp_path: Path):
    (tmp_path / "secret.xlsx").write_bytes(b"not a workbook")
    folder = tmp_path / "real" / "ncc_monthly"
    _manifest(folder, "../../secret.xlsx")
    m = read_manifest(folder)
    assert any("outside the dataset folder" in p for p in verify_files(m))
    assert check_provenance(m, env={}) == []        # never opened


def test_corrupt_or_protected_workbook_is_a_refusal_not_a_crash(tmp_path: Path):
    folder = tmp_path / "real" / "ncc_monthly"
    folder.mkdir(parents=True)
    (folder / "T03.xlsx").write_bytes(b"this is not a zip file")
    _manifest(folder, "T03.xlsx")
    problems = check_provenance(read_manifest(folder), env={})
    assert len(problems) == 1 and "cannot be opened" in problems[0]


def test_malformed_manifest_is_a_manifest_error(tmp_path: Path):
    (tmp_path / "manifest.toml").write_text('dataset = "ncc_monthly"\nprovenance = \n')
    with pytest.raises(ManifestError, match="not valid TOML"):
        read_manifest(tmp_path)
    (tmp_path / "manifest.toml").write_text('dataset = "x"\nprovenance = "real"\n[[files]]\nsha256 = "ab"\n')
    with pytest.raises(ManifestError, match="path"):
        read_manifest(tmp_path)


# ---- network scenarios for ctx.net ---------------------------------------------------
NETWORK_CFG = {"scenarios": {"base": {"statuses": ["existing", "committed"]},
                             "2030": {"as_of": "2030-12-31", "statuses": ["existing", "committed", "planned"]}}}


def test_configured_2030_scenario_includes_planned_projects():
    statuses, as_of = scenario_settings(NETWORK_CFG, "2030")
    assert statuses == ("existing", "committed", "planned") and as_of == date(2030, 12, 31)
    # an explicit as_of wins over the configured one
    assert scenario_settings(NETWORK_CFG, "2030", date(2028, 1, 1))[1] == date(2028, 1, 1)


def test_fallback_and_unknown_scenarios():
    assert scenario_settings({}, "base") == (("existing", "committed"), None)
    assert scenario_settings({}, "planned")[0] == ("existing", "committed", "planned")
    with pytest.raises(ValueError, match="unknown network scenario"):
        scenario_settings(NETWORK_CFG, "2031")


def test_decimal_comma_is_an_error_not_a_factor_of_ten():
    assert coerce("1,234.5", "number") == 1234.5 and coerce("-12,345,678", "number") == -12345678
    for bad in ("61,5", "1,23", "12,3456"):
        with pytest.raises(CoercionError, match="decimal point"):
            coerce(bad, "number")


def test_a_flood_of_identical_issues_is_capped_with_a_summary():
    from loaders.generic import Issue, cap_issues, overflow_issues
    per_rule: dict = {}
    kept = []
    for row in range(2, 2 + 25):
        kept += cap_issues([Issue("hourly_data", row, "timestamp", "error", "type", "bad date")], per_rule, limit=10)
    kept += cap_issues([Issue("hourly_data", 99, "value", "error", "type", "bad number")], per_rule, limit=10)
    assert len(kept) == 11
    summary = overflow_issues(per_rule, limit=10)
    assert len(summary) == 1 and summary[0].column_name == "timestamp" and "15 more" in summary[0].message
