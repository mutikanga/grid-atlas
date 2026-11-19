"""Check template spec files (templates/spec/*.toml) against docs/dev/contracts.md section 3.

Standard library only, so it runs in a bare python:3.12 container:

    docker run --rm -v "$PWD":/w -w /w python:3.12-slim-bookworm \
        python templates/validate_spec.py               # every spec, plus cross-file checks
    ... python templates/validate_spec.py templates/spec/T03_ncc_monthly.toml

Exit status 0 means every file passed; 1 means at least one error was printed.
"""
from __future__ import annotations

import re
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent / "spec"

TOP_REQUIRED = ["id", "slug", "title", "holder", "requests", "dataset", "criticality", "period", "intro", "sheets"]
CRITICALITY = {"critical", "high", "medium", "low"}
FORMATS = {"xlsx", "csv", "vector", "qa"}
GEOMETRIES = {"Point", "LineString", "Polygon", "MultiPolygon"}
TYPES = {"text", "int", "number", "month", "date", "datetime", "yn", "enum"}
COLUMN_KEYS = {"name", "type", "unit", "required", "desc", "example", "enum",
               "min", "max", "warn_min", "warn_max"}
TABLE_PREFIXES = ("net_", "gis_", "ncc_", "scada_", "ops_", "com_", "uedcl_", "plan_", "site_", "team_", "hb_")
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED_COLUMNS = {"batch_id", "row_num"}


def _example_ok(col: dict) -> str | None:
    """Return an error message if the example does not fit the column type."""
    ex, t = col.get("example"), col.get("type")
    if ex is None:
        return "missing example"
    if ex == "" and not col.get("required"):
        return None                       # blank example allowed for optional columns
    try:
        if t == "int" and not (isinstance(ex, int) and not isinstance(ex, bool)):
            return f"example {ex!r} is not an int"
        if t == "number" and not (isinstance(ex, (int, float)) and not isinstance(ex, bool)):
            return f"example {ex!r} is not a number"
        if t == "month":
            datetime.strptime(str(ex), "%Y-%m")
        if t == "date":
            if not isinstance(ex, date):
                datetime.strptime(str(ex), "%Y-%m-%d")
        if t == "datetime":
            datetime.strptime(str(ex), "%Y-%m-%d %H:%M")
        if t == "yn" and ex not in ("Y", "N"):
            return f"example {ex!r} must be Y or N"
        if t == "enum" and ex not in col.get("enum", []):
            return f"example {ex!r} not in enum {col.get('enum')}"
    except ValueError:
        return f"example {ex!r} does not match type {t}"
    return None


def check_file(path: Path) -> tuple[list[str], dict]:
    errors: list[str] = []
    try:
        spec = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return [f"{path.name}: cannot parse TOML: {exc}"], {}

    def err(msg: str) -> None:
        errors.append(f"{path.name}: {msg}")

    for key in TOP_REQUIRED:
        if key not in spec:
            err(f"missing top-level key '{key}'")
    tid = spec.get("id", "")
    if not re.fullmatch(r"T\d{2}", str(tid)):
        err(f"id {tid!r} must look like T01")
    if spec.get("slug") and not SNAKE.match(spec["slug"]):
        err(f"slug {spec['slug']!r} must be snake_case")
    expected_name = f"{tid}_{spec.get('slug')}.toml"
    if path.name != expected_name:
        err(f"file should be named {expected_name}")
    if spec.get("criticality") not in CRITICALITY:
        err(f"criticality must be one of {sorted(CRITICALITY)}")
    if not isinstance(spec.get("requests", []), list):
        err("requests must be a list of request numbers (may be empty for internal templates)")

    sheet_names: set[str] = set()
    for i, sheet in enumerate(spec.get("sheets", [])):
        where = f"sheet[{i}] {sheet.get('name', '?')}"
        for key in ("name", "table", "title", "grain"):
            if key not in sheet:
                err(f"{where}: missing '{key}'")
        name = sheet.get("name", "")
        if not SNAKE.match(name) or len(name) > 31:
            err(f"{where}: name must be snake_case and at most 31 characters")
        if name in sheet_names:
            err(f"{where}: duplicate sheet name")
        sheet_names.add(name)
        fmt = sheet.get("format", "xlsx")
        if fmt not in FORMATS:
            err(f"{where}: format must be one of {sorted(FORMATS)}")
        table = sheet.get("table", "")
        if fmt != "qa":
            if not SNAKE.match(table) or not table.startswith(TABLE_PREFIXES):
                err(f"{where}: table {table!r} must be snake_case with a source prefix {TABLE_PREFIXES}")
        if fmt == "vector" and sheet.get("geometry") not in GEOMETRIES:
            err(f"{where}: vector sheets need geometry in {sorted(GEOMETRIES)}")
        if fmt == "csv" and not sheet.get("file_pattern"):
            err(f"{where}: csv sheets need file_pattern")
        if fmt == "qa":
            qs = sheet.get("questions", [])
            if not qs:
                err(f"{where}: qa sheets need questions")
            for q in qs:
                if not {"id", "text"} <= set(q):
                    err(f"{where}: each question needs id and text")
            continue

        cols = sheet.get("columns", [])
        if not cols:
            err(f"{where}: no columns")
        seen: set[str] = set()
        for col in cols:
            cname = col.get("name", "?")
            cw = f"{where}.{cname}"
            unknown = set(col) - COLUMN_KEYS
            if unknown:
                err(f"{cw}: unknown keys {sorted(unknown)}")
            for key in ("name", "type", "desc", "example"):
                if key not in col:
                    err(f"{cw}: missing '{key}'")
            if not SNAKE.match(cname):
                err(f"{cw}: column name must be snake_case")
            if cname in RESERVED_COLUMNS:
                err(f"{cw}: {cname} is reserved")
            if cname in seen:
                err(f"{cw}: duplicate column")
            seen.add(cname)
            if col.get("type") not in TYPES:
                err(f"{cw}: type must be one of {sorted(TYPES)}")
            if col.get("type") == "enum" and not col.get("enum"):
                err(f"{cw}: enum columns need an enum list")
            msg = _example_ok(col)
            if msg:
                err(f"{cw}: {msg}")
        for k in sheet.get("key", []):
            if k not in seen:
                err(f"{where}: key column {k!r} is not a column")
    return errors, spec


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted(SPEC_DIR.glob("T*.toml"))
    all_errors: list[str] = []
    tables: dict[str, str] = {}
    ids: dict[str, str] = {}
    for path in paths:
        errors, spec = check_file(path)
        all_errors += errors
        if spec:
            if spec.get("id") in ids:
                all_errors.append(f"{path.name}: id {spec['id']} also used by {ids[spec['id']]}")
            ids[spec.get("id")] = path.name
            for sheet in spec.get("sheets", []):
                t = sheet.get("table")
                if sheet.get("format") == "qa" or not t:
                    continue
                if t in tables:
                    all_errors.append(f"{path.name}: table {t} also defined in {tables[t]}")
                tables[t] = path.name
        n_cols = sum(len(s.get("columns", [])) for s in spec.get("sheets", [])) if spec else 0
        print(f"{'FAIL' if errors else 'ok  '} {path.name}: {len(spec.get('sheets', [])) if spec else 0} sheets, {n_cols} columns")
    for e in all_errors:
        print("  " + e)
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
