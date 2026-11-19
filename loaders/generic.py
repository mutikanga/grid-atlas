"""Load one dataset folder (data/<root>/<dataset>/) into ts.*, driven by its template spec.

One load = one meta.import_batch. For each sheet delivered (xlsx sheet, csv files, vector
files, or a question sheet) every row is validated against the spec:
  - type, required, enum and min/max problems are errors: the row is not loaded;
  - warn_min/warn_max problems are warnings: the row is loaded;
  - columns not in the spec are ignored and logged once as info, so extra or personal
    fields never reach the database;
  - substation and plant names are mapped to codes in <col>_code (loaders/names.py).
Every problem goes to meta.import_issue with the row as delivered (known columns only).
Good rows replace existing rows with the same key, all in one transaction, so a corrected
delivery never leaves the database half old and half new.

This module also loads the config registers (config/*.csv) and the calendar into ref.*,
which happens on every load and run.
"""
from __future__ import annotations

import csv
import importlib
import json
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg import sql

from engine import calendar as atlas_calendar
from engine.config import CONFIG_DIR, code_version, load_config
from engine.db import connect, copy_rows
from loaders import units
from loaders.manifest import Manifest, ManifestError, check_provenance, read_manifest, unlisted_files, verify_files
from loaders.names import NameResolver, alias_rows
from loaders.spec import Column, Sheet, Spec, load_specs
from loaders.vector import VectorError, geometry_matches, read_vector, to_ewkt

log = logging.getLogger("atlas.load")

GEOM_KEY = "__geom__"
CHUNK_ROWS = 20_000
# At most this many issues per (sheet, column, rule, severity) are stored one by one. A
# month of SCADA in the wrong date format would otherwise write 400 000 identical issues;
# the rest are counted in one summary issue. Every bad row is still rejected.
MAX_ISSUES_PER_RULE = 1000
# Workbook sheets that are never data.
SKIP_SHEETS = {"readme"}


# ---------------------------------------------------------------------------------------
# Plain data holders
# ---------------------------------------------------------------------------------------
@dataclass
class Issue:
    """One line of meta.import_issue."""

    sheet: str | None
    row_num: int | None
    column_name: str | None
    severity: str            # error | warning | info
    rule: str
    message: str
    raw_value: str | None = None
    suggestion: str | None = None
    raw_row: dict[str, Any] | None = None

    def as_row(self, batch_id: int) -> tuple:
        raw_row = json.dumps(self.raw_row, default=str) if self.raw_row is not None else None
        return (batch_id, self.sheet, self.row_num, self.column_name, self.severity, self.rule,
                self.message, self.raw_value, self.suggestion, raw_row)


ISSUE_COLUMNS = ("batch_id", "sheet", "row_num", "column_name", "severity", "rule", "message",
                 "raw_value", "suggestion", "raw_row")


@dataclass
class RawTable:
    """Delivered rows of one sheet: header names and (row number, values) pairs.

    Adapters (loaders/adapters/<name>.py) return these too, so native layouts go through
    the same validation as the templates.
    """

    sheet: str
    headers: list[str]
    rows: Iterable[tuple[int, list[Any]]]
    source: str = ""          # file name, for messages


@dataclass
class SheetCounts:
    read: int = 0
    loaded: int = 0
    rejected: int = 0


@dataclass
class BatchResult:
    """What a load did, for the command line and the tests."""

    batch_id: int | None
    dataset: str
    status: str
    rows_read: int = 0
    rows_loaded: int = 0
    rows_rejected: int = 0
    message: str = ""
    issues: list[Issue] = field(default_factory=list)


# ---------------------------------------------------------------------------------------
# Validation (pure: no database)
# ---------------------------------------------------------------------------------------
# Values Excel shows when a formula fails. openpyxl (data_only) returns them as text.
EXCEL_ERRORS = {"#N/A", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#NULL!", "#SPILL!", "#CALC!", "#GETTING_DATA"}


def is_excel_error(value: Any) -> bool:
    """True for an Excel error value such as #N/A or #DIV/0!."""
    return isinstance(value, str) and value.strip().upper() in EXCEL_ERRORS


def header_key(name: Any) -> str:
    """Header text as a column name: trimmed, lower case, spaces as underscores."""
    return units.to_text(name).strip().lower().replace(" ", "_") if not units.is_blank(name) else ""


def map_headers(headers: list[Any], sheet: Sheet) -> tuple[dict[str, int], list[str]]:
    """{spec column: position} for the columns present, plus the unknown header names."""
    known = set(sheet.column_names) if sheet.format != "qa" else {"question_id", "question", "answer"}
    positions: dict[str, int] = {}
    unknown: list[str] = []
    for i, head in enumerate(headers):
        key = header_key(head)
        if not key:
            continue
        if key in known and key not in positions:
            positions[key] = i
        elif key not in known:
            unknown.append(units.to_text(head))
    return positions, unknown


def _check_bounds(col: Column, value: Any, sheet: str, row_num: int, raw: Any) -> list[Issue]:
    """min/max (error) and warn_min/warn_max (warning) for numeric columns."""
    if col.type not in ("int", "number") or value is None:
        return []
    issues = []
    for bound, op, severity in ((col.min, "min", "error"), (col.max, "max", "error"),
                                (col.warn_min, "warn_min", "warning"), (col.warn_max, "warn_max", "warning")):
        if bound is None:
            continue
        low = op.endswith("min")
        if (low and value < bound) or (not low and value > bound):
            word = "below the minimum" if low else "above the maximum"
            kind = "" if severity == "error" else "expected "
            issues.append(Issue(sheet, row_num, col.name, severity, op,
                                f"{col.name} = {value:g} is {word} {kind}of {bound:g}{' ' + col.unit if col.unit else ''}",
                                units.to_text(raw)))
    return issues


def _resolve(col: Column, value: str, resolver: NameResolver, sheet: str, row_num: int) -> tuple[str | None, list[Issue]]:
    """Map a name to its code. Returns (code or None, issues)."""
    kind = col.resolve_as
    assert kind is not None
    if col.name == "ss_code":
        # ss_code columns already hold codes; accept a known code or a known name, and let
        # a new well-formed code through with a warning (a hand-built network may add one).
        code = value.strip().upper()
        if code in resolver.known_codes("substation"):
            return code, []
        found = resolver.resolve(value, "substation")
        if found.code:
            return found.code, [Issue(sheet, row_num, col.name, "info", "name_to_code",
                                      f"'{value}' read as {found.code}", value)]
        if len(code) == 3 and code.isalpha():
            return code, [Issue(sheet, row_num, col.name, "warning", "unknown_code",
                                f"{code} is not in config/substations.csv", value, found.suggestion)]
        severity = "error" if col.required else "warning"
        return None, [Issue(sheet, row_num, col.name, severity, "unresolved_name",
                            f"'{value}' is not a substation code or known name", value, found.suggestion)]
    found = resolver.resolve(value, kind)
    if found.code:
        return found.code, []
    severity = "error" if col.required else "warning"
    return None, [Issue(sheet, row_num, col.name, severity, "unresolved_name",
                        f"{kind} name '{value}' is not in config/aliases.csv", value, found.suggestion)]


def validate_row(sheet: Sheet, positions: dict[str, int], values: list[Any], row_num: int,
                 resolver: NameResolver, template: str = "") -> tuple[dict[str, Any] | None, list[Issue], bool]:
    """Check one delivered row.

    Returns (record for the ts table or None if rejected, issues, blank). A row with only
    blank cells is skipped without comment (blank=True).
    """
    def cell(name: str) -> Any:
        i = positions.get(name)
        return values[i] if i is not None and i < len(values) else None

    if sheet.format == "qa":
        qid, answer = cell("question_id"), cell("answer")
        if units.is_blank(qid) or units.is_blank(answer):
            return None, [], True
        return {"template": template, "sheet": sheet.name, "question_id": units.to_text(qid),
                "question": None if units.is_blank(cell("question")) else units.to_text(cell("question")),
                "answer": units.to_text(answer)}, [], False

    raw_row = {c: units.to_text(cell(c)) for c in sheet.column_names if not units.is_blank(cell(c))}
    geom = values[-1] if sheet.format == "vector" and values else None
    if not raw_row and geom is None:
        return None, [], True

    record: dict[str, Any] = {}
    issues: list[Issue] = []
    for col in sheet.columns:
        raw = cell(col.name)
        if is_excel_error(raw):
            # A formula error (#N/A, #DIV/0!) is not a value: read it as blank, say so, and
            # reject the row only if the column is required.
            issues.append(Issue(sheet.name, row_num, col.name, "warning", "excel_error",
                                f"{col.name}: Excel error {raw.strip()} read as blank", raw.strip()))
            raw = None
        if units.is_blank(raw):
            if col.required:
                issues.append(Issue(sheet.name, row_num, col.name, "error", "required", f"{col.name} is required"))
            record[col.name] = None
            if col.code_column and col.code_column != col.name:
                record[col.code_column] = None
            continue
        try:
            value = units.coerce(raw, col.type, col.enum)
        except units.CoercionError as exc:
            rule = "enum" if col.type == "enum" else "type"
            issues.append(Issue(sheet.name, row_num, col.name, "error", rule, f"{col.name}: {exc}", units.to_text(raw)))
            record[col.name] = None
            continue
        issues += _check_bounds(col, value, sheet.name, row_num, raw)
        record[col.name] = value
        if col.code_column:
            code, found = _resolve(col, str(value), resolver, sheet.name, row_num)
            issues += found
            record[col.code_column] = code

    if sheet.format == "vector":
        record["geom"] = None
        if geom is None or getattr(geom, "is_empty", True):
            issues.append(Issue(sheet.name, row_num, None, "error", "geometry", "feature has no geometry"))
        else:
            if not geometry_matches(sheet.geometry, geom.geom_type):
                issues.append(Issue(sheet.name, row_num, None, "warning", "geometry_type",
                                    f"expected {sheet.geometry}, got {geom.geom_type}"))
            record["geom"] = to_ewkt(geom)

    for issue in issues:
        issue.raw_row = raw_row
    rejected = any(i.severity == "error" for i in issues)
    return (None if rejected else record), issues, False


# ---------------------------------------------------------------------------------------
# Reading delivered files
# ---------------------------------------------------------------------------------------
def _rows_from_iter(it: Iterator[tuple], start: int) -> Iterator[tuple[int, list[Any]]]:
    for n, values in enumerate(it, start=start):
        yield n, list(values)


def read_xlsx(path: Path, spec: Spec) -> tuple[list[RawTable], list[Issue], Any]:
    """The workbook's sheets that the spec knows (matched by name, ignoring case).

    Returns (tables, issues, workbook); the caller closes the workbook after reading.
    """
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    tables, issues = [], []
    by_name = {s.name.lower(): s for s in spec.sheets}
    for ws in wb.worksheets:
        name = ws.title.strip().lower()
        if name in SKIP_SHEETS:
            continue
        sheet = by_name.get(name)
        if sheet is None:
            issues.append(Issue(ws.title, None, None, "info", "unknown_sheet",
                                f"sheet '{ws.title}' in {path.name} is not in template {spec.id}; ignored"))
            continue
        if sheet.format in ("csv", "vector"):
            # The workbook only shows the layout; the data comes as separate files.
            continue
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if header is None:
            continue
        tables.append(RawTable(sheet.name, list(header), _rows_from_iter(it, 2), path.name))
    return tables, issues, wb


def csv_encoding(path: Path) -> str:
    """'utf-8-sig' when the whole file is valid UTF-8, else 'cp1252'.

    Excel and many Windows SCADA tools save CSV as Windows-1252. Reading that as UTF-8
    fails part-way through the file and would abort the whole load, so check first.
    """
    import codecs
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                decoder.decode(block)
            decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def read_csv(path: Path, sheet: str) -> tuple[RawTable, Any]:
    """A CSV file with a header row (comma or semicolon separated). Returns (table, file handle)."""
    # cp1252 leaves five byte values undefined; errors="replace" keeps those from failing.
    fh = path.open(newline="", encoding=csv_encoding(path), errors="replace")
    first = fh.readline()
    fh.seek(0)
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.reader(fh, delimiter=delimiter)
    header = next(reader, [])
    return RawTable(sheet, header, _rows_from_iter(reader, 2), path.name), fh


def read_vector_table(path: Path, sheet: Sheet) -> RawTable:
    """A GIS layer as rows of attributes, with the geometry as the last value."""
    gdf = read_vector(path)
    attrs = [c for c in gdf.columns if c != gdf.geometry.name]
    rows = ((i + 1, [*(None if pd.isna(v) else v for v in rec[:-1]), rec[-1]])
            for i, rec in enumerate(gdf[attrs + [gdf.geometry.name]].itertuples(index=False, name=None)))
    return RawTable(sheet.name, attrs + [GEOM_KEY], rows, path.name)


# ---------------------------------------------------------------------------------------
# Writing (inside the load transaction)
# ---------------------------------------------------------------------------------------
class SheetWriter:
    """Collects a sheet's good rows in a temporary table, then swaps them into ts.<table>."""

    def __init__(self, conn: psycopg.Connection, sheet: Sheet, index: int, batch_id: int):
        self.conn, self.sheet, self.batch_id = conn, sheet, batch_id
        self.temp = f"_load_{index}"
        self.columns = sheet.db_columns
        self.buffer: list[list[Any]] = []
        self.count = 0
        conn.execute(sql.SQL("CREATE TEMP TABLE {} (LIKE {}.{}) ON COMMIT DROP").format(
            sql.Identifier(self.temp), sql.Identifier("ts"), sql.Identifier(sheet.table)))

    def add(self, row_num: int, record: dict[str, Any]) -> None:
        record = {**record, "batch_id": self.batch_id, "row_num": row_num}
        self.buffer.append([record.get(c) for c in self.columns])
        if len(self.buffer) >= CHUNK_ROWS:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        stmt = sql.SQL("COPY {} ({}) FROM STDIN").format(
            sql.Identifier(self.temp), sql.SQL(", ").join(sql.Identifier(c) for c in self.columns))
        with self.conn.cursor() as cur, cur.copy(stmt) as copy:
            for row in self.buffer:
                copy.write_row(row)
        self.count += len(self.buffer)
        self.buffer = []

    def _key_part(self, table: sql.Composable, k: str) -> sql.Composable:
        """One key column of a row. A name column is compared by its resolved code when it
        has one, so 'Kawanda' and 'Kawanda S/S' are the same key."""
        col = self.sheet.column(k)
        if col is not None and col.code_column and col.code_column != k:
            return sql.SQL("COALESCE({t}.{c}, {t}.{k})").format(t=table, c=sql.Identifier(col.code_column), k=sql.Identifier(k))
        return sql.SQL("{}.{}").format(table, sql.Identifier(k))

    def _key_match(self, left: sql.Composable, right: sql.Composable) -> sql.Composable:
        """SQL that is true when two rows have the same key (blank key parts match blank)."""
        parts = []
        for k in self.sheet.db_key:
            col = self.sheet.column(k)
            # '=' lets PostgreSQL use a hash join on big tables; required parts are never NULL.
            op = "=" if (col is not None and col.required) or self.sheet.format == "qa" else "IS NOT DISTINCT FROM"
            parts.append(sql.SQL("{} " + op + " {}").format(self._key_part(left, k), self._key_part(right, k)))
        return sql.SQL(" AND ").join(parts)

    def drop_duplicates(self) -> list[Issue]:
        """Remove later rows that repeat an earlier row's key in the same delivery."""
        self.flush()
        if not self.sheet.db_key or self.count == 0:
            return []
        stmt = sql.SQL("DELETE FROM {t} a USING {t} b WHERE {m} AND a.ctid > b.ctid RETURNING a.row_num, {keys}").format(
            t=sql.Identifier(self.temp), m=self._key_match(sql.Identifier("a"), sql.Identifier("b")),
            keys=sql.SQL(", ").join(sql.SQL("a.{}").format(sql.Identifier(k)) for k in self.sheet.db_key))
        issues = []
        for row in self.conn.execute(stmt).fetchall():
            key = {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in zip(self.sheet.db_key, row[1:])}
            issues.append(Issue(self.sheet.name, row[0], None, "error", "duplicate_key",
                                f"another row in this delivery has the same key ({', '.join(self.sheet.db_key)})",
                                None, None, key))
        self.count -= len(issues)
        return issues

    def commit_rows(self) -> int:
        """Replace ts rows that share a key with the delivery, then insert the delivery."""
        target = sql.Identifier("ts", self.sheet.table)
        temp = sql.Identifier(self.temp)
        if self.count:
            self.conn.execute(sql.SQL("ANALYZE {}").format(temp))
            if self.sheet.db_key:
                self.conn.execute(sql.SQL("DELETE FROM {t} USING {s} WHERE {m}").format(
                    t=target, s=temp, m=self._key_match(target, temp)))
            self.conn.execute(sql.SQL("INSERT INTO {t} ({c}) SELECT {c} FROM {s}").format(
                t=target, s=temp, c=sql.SQL(", ").join(sql.Identifier(c) for c in self.columns)))
        self.conn.execute(sql.SQL("DROP TABLE {}").format(temp))
        return self.count


# ---------------------------------------------------------------------------------------
# Registers and calendar -> ref.*
# ---------------------------------------------------------------------------------------
def _read_csv_frame(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig").apply(lambda s: s.str.strip())


def _kv_list(text: str) -> list[int] | None:
    parts = [p for p in str(text).replace(",", "/").split("/") if p.strip()]
    return [int(float(p)) for p in parts] or None


def _num(text: str) -> float | None:
    return float(text) if str(text).strip() else None


def _upsert(conn: psycopg.Connection, table: str, key: str, columns: list[str], rows: list[list[Any]],
            prune: bool = True) -> None:
    """Insert or update rows by key; with prune, delete rows whose key is no longer listed."""
    schema, name = table.split(".")
    ident = sql.Identifier(schema, name)
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    updates = sql.SQL(", ").join(sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in columns if c != key)
    stmt = sql.SQL("INSERT INTO {t} ({cols}) VALUES ({ph}) ON CONFLICT ({k}) DO UPDATE SET {u}").format(
        t=ident, cols=cols, ph=sql.SQL(", ").join(sql.Placeholder() * len(columns)), k=sql.Identifier(key), u=updates)
    with conn.cursor() as cur:
        cur.executemany(stmt, rows)
        if not prune:
            return
        keys = [r[columns.index(key)] for r in rows]
        cur.execute(sql.SQL("DELETE FROM {t} WHERE NOT ({k} = ANY(%s))").format(t=ident, k=sql.Identifier(key)), (keys,))


def load_registers(conn: psycopg.Connection, config_dir: Path | None = None, cfg: dict | None = None) -> dict[str, int]:
    """Load config/substations.csv, plants.csv, aliases.csv, holidays_ug.csv and the study
    calendar into ref.*. Runs inside the caller's transaction. Returns row counts.

    Every canonical code and name is added to ref.alias automatically, so only other
    spellings need to be listed in config/aliases.csv.
    """
    config_dir = config_dir or CONFIG_DIR
    cfg = cfg if cfg is not None else load_config()
    subs = _read_csv_frame(config_dir / "substations.csv")
    plants = _read_csv_frame(config_dir / "plants.csv")
    aliases = _read_csv_frame(config_dir / "aliases.csv")
    holidays = atlas_calendar.read_holidays(config_dir / "holidays_ug.csv")

    bad_codes = [c for c in subs["ss_code"] if not (len(c) == 3 and c.isalpha() and c.isupper())]
    if bad_codes:
        raise ValueError(f"config/substations.csv: ss_code must be three upper-case letters: {bad_codes}")
    known = {"substation": set(subs["ss_code"]), "plant": set(plants["plant_code"])}
    for kind, code in zip(aliases["entity_type"], aliases["canonical_id"]):
        if code not in known.get(kind, set()):
            raise ValueError(f"config/aliases.csv: {kind} code {code} is not in the register")
    for code in plants["ss_code"]:
        if code and code not in known["substation"]:
            raise ValueError(f"config/plants.csv: substation {code} is not in config/substations.csv")

    sub_rows = []
    for r in subs.to_dict("records"):
        lat, lon = _num(r.get("lat", "")), _num(r.get("lon", ""))
        sub_rows.append([r["ss_code"], r["name"], _kv_list(r.get("kv_levels", "")), r.get("district") or None,
                         units.to_bool(r.get("in_central") or "N"), lat, lon,
                         f"SRID=4326;POINT({lon} {lat})" if lat is not None and lon is not None else None,
                         r.get("source") or None])
    plant_rows = [[r["plant_code"], r["name"], r.get("technology") or None, r.get("ss_code") or None,
                   _num(r.get("connection_kv", "")), r.get("source") or None] for r in plants.to_dict("records")]

    # Plants point at substations: add substations, then replace plants, then remove
    # substations no longer listed.
    sub_cols = ["ss_code", "name", "kv_levels", "district", "in_central", "lat", "lon", "geom", "source"]
    _upsert(conn, "ref.substation", "ss_code", sub_cols, sub_rows, prune=False)
    _upsert(conn, "ref.plant", "plant_code",
            ["plant_code", "name", "technology", "ss_code", "connection_kv", "source"], plant_rows)
    _upsert(conn, "ref.substation", "ss_code", sub_cols, sub_rows)

    alias_df = alias_rows(aliases, subs, plants)
    conn.execute("DELETE FROM ref.alias")
    copy_rows(conn, "ref.alias", list(alias_df.columns), alias_df.itertuples(index=False, name=None))

    conn.execute("DELETE FROM ref.holiday")
    copy_rows(conn, "ref.holiday", ["day", "name"], sorted(holidays.items()))

    months = atlas_calendar.month_table(cfg, holidays)
    conn.execute("DELETE FROM ref.month")
    copy_rows(conn, "ref.month", list(months.columns), months.itertuples(index=False, name=None))
    return {"substations": len(sub_rows), "plants": len(plant_rows), "aliases": len(alias_df),
            "holidays": len(holidays), "months": len(months)}


def resolver_from_db(conn: psycopg.Connection) -> NameResolver:
    """A NameResolver over ref.alias, ref.substation and ref.plant."""
    def frame(query: str, cols: list[str]) -> pd.DataFrame:
        return pd.DataFrame(conn.execute(query).fetchall(), columns=cols)
    return NameResolver.from_frames(
        frame("SELECT alias_norm, entity_type, canonical_id FROM ref.alias", ["alias_norm", "entity_type", "canonical_id"]),
        frame("SELECT ss_code, name FROM ref.substation", ["ss_code", "name"]),
        frame("SELECT plant_code, name FROM ref.plant", ["plant_code", "name"]))


# ---------------------------------------------------------------------------------------
# Loading one dataset folder
# ---------------------------------------------------------------------------------------
def _open_batch(conn: psycopg.Connection, m: Manifest, version: str) -> int:
    row = conn.execute(
        "INSERT INTO meta.import_batch (dataset, template, root, provenance, received_from, received_on, adapter, "
        "files, code_version) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING batch_id",
        (m.dataset, m.template or None, m.root or None, m.provenance, m.received_from or None, m.received_on,
         m.adapter, json.dumps(m.files_json()), version)).fetchone()
    return int(row[0])


def _close_batch(conn: psycopg.Connection, batch_id: int, result: BatchResult) -> None:
    conn.execute(
        "UPDATE meta.import_batch SET finished_at = now(), status = %s, rows_read = %s, rows_loaded = %s, "
        "rows_rejected = %s, message = %s WHERE batch_id = %s",
        (result.status, result.rows_read, result.rows_loaded, result.rows_rejected, result.message or None, batch_id))


def _write_issues(conn: psycopg.Connection, batch_id: int, issues: list[Issue]) -> None:
    copy_rows(conn, "meta.import_issue", ISSUE_COLUMNS, (i.as_row(batch_id) for i in issues))


def cap_issues(found: list[Issue], per_rule: dict[tuple, int], limit: int = MAX_ISSUES_PER_RULE) -> list[Issue]:
    """The issues to store one by one; counts every issue in per_rule (updated in place)."""
    kept = []
    for issue in found:
        key = (issue.sheet, issue.column_name, issue.rule, issue.severity)
        per_rule[key] = per_rule.get(key, 0) + 1
        if per_rule[key] <= limit:
            kept.append(issue)
    return kept


def overflow_issues(per_rule: dict[tuple, int], limit: int = MAX_ISSUES_PER_RULE) -> list[Issue]:
    """One summary issue for each (sheet, column, rule, severity) that went over the limit."""
    return [Issue(sheet, None, column, severity, rule,
                  f"{n - limit} more row(s) with this problem are not listed one by one (first {limit} are)")
            for (sheet, column, rule, severity), n in per_rule.items() if n > limit]


def batch_status(read: int, loaded: int, rejected: int, sheet_errors: int = 0) -> str:
    """ok when nothing was rejected; failed when rows came but none loaded; else partial."""
    if rejected == 0 and sheet_errors == 0:
        return "ok"
    if loaded == 0 and (read > 0 or sheet_errors > 0):
        return "failed"
    return "partial"


def _sources(m: Manifest, spec: Spec, issues: list[Issue], closers: list) -> Iterator[RawTable]:
    """Every delivered table in the folder, from the template layout or an adapter."""
    if m.adapter and m.adapter != "template":
        adapter = importlib.import_module(f"loaders.adapters.{m.adapter}")
        yield from adapter.read(m, spec)
        return
    for entry in m.files:
        path = m.folder / entry.path
        suffix = path.suffix.lower()
        if suffix in (".xlsx", ".xlsm"):
            tables, found, wb = read_xlsx(path, spec)
            closers.append(wb)
            issues.extend(found)
            yield from tables
            continue
        sheet = spec.sheet(entry.sheet) if entry.sheet else None
        if sheet is None:
            issues.append(Issue(entry.sheet or None, None, None, "error", "unknown_sheet",
                                f"{entry.path}: the manifest must name a sheet of {spec.id} for csv and GIS files"))
            continue
        if suffix in (".csv", ".txt"):
            table, fh = read_csv(path, sheet.name)
            closers.append(fh)
            yield table
        else:
            try:
                yield read_vector_table(path, sheet)
            except VectorError as exc:
                issues.append(Issue(sheet.name, None, None, "error", "vector", str(exc)))


def _load_tables(conn: psycopg.Connection, m: Manifest, spec: Spec, batch_id: int,
                 resolver: NameResolver, issues: list[Issue]) -> tuple[SheetCounts, int]:
    """Validate and stage every delivered table, then swap the rows into ts.*.

    Returns (counts, sheet-level errors).
    """
    counts = SheetCounts()
    sheet_errors = 0
    writers: dict[str, SheetWriter] = {}
    seen_sheets: set[str] = set()
    per_rule: dict[tuple, int] = {}
    closers: list = []
    try:
        for table in _sources(m, spec, issues, closers):
            sheet = spec.sheet(table.sheet)
            if sheet is None:
                issues.append(Issue(table.sheet, None, None, "error", "unknown_sheet", f"no sheet {table.sheet} in {spec.id}"))
                sheet_errors += 1
                continue
            seen_sheets.add(sheet.name)
            if sheet.format == "vector":
                positions, unknown = map_headers(table.headers[:-1], sheet)
            else:
                positions, unknown = map_headers(table.headers, sheet)
            for name in unknown:
                issues.append(Issue(sheet.name, None, name, "info", "unknown_column",
                                    f"column '{name}' in {table.source} is not in the template; ignored"))
            missing = [c.name for c in sheet.columns if c.required and c.name not in positions]
            if missing:
                # Without a required column no row can load; one sheet-level error says why.
                n = sum(1 for _, values in table.rows if any(not units.is_blank(v) for v in values))
                issues.append(Issue(sheet.name, None, ", ".join(missing), "error", "missing_column",
                                    f"{table.source}: required column(s) missing: {', '.join(missing)}; {n} row(s) not loaded"))
                counts.read += n
                counts.rejected += n
                sheet_errors += 1
                continue
            if sheet.name not in writers:
                writers[sheet.name] = SheetWriter(conn, sheet, len(writers), batch_id)
            writer = writers[sheet.name]
            for row_num, values in table.rows:
                record, found, blank = validate_row(sheet, positions, values, row_num, resolver, spec.id)
                if blank:
                    continue
                counts.read += 1
                issues.extend(cap_issues(found, per_rule))
                if record is None:
                    counts.rejected += 1
                else:
                    writer.add(row_num, record)
    finally:
        for c in closers:
            c.close()

    for writer in writers.values():
        dupes = writer.drop_duplicates()
        issues.extend(cap_issues(dupes, per_rule))
        counts.rejected += len(dupes)
        counts.loaded += writer.commit_rows()

    issues.extend(overflow_issues(per_rule))
    for sheet in spec.sheets:
        if sheet.name not in seen_sheets and sheet.required_sheet:
            issues.append(Issue(sheet.name, None, None, "info", "sheet_not_supplied",
                                f"sheet {sheet.name} was not in this delivery"))
    return counts, sheet_errors


def load_layers(conn: psycopg.Connection, m: Manifest, batch_id: int, issues: list[Issue]) -> SheetCounts:
    """Open context layers -> gis.layer_feature. Each layer replaces its earlier features."""
    counts = SheetCounts()
    for entry in m.files:
        try:
            gdf = read_vector(m.folder / entry.path)
        except VectorError as exc:
            issues.append(Issue(entry.layer, None, None, "error", "vector", str(exc)))
            continue
        attrs_cols = [c for c in gdf.columns if c != gdf.geometry.name]
        rows = []
        for i, rec in enumerate(gdf[attrs_cols + [gdf.geometry.name]].itertuples(index=False, name=None), start=1):
            counts.read += 1
            geom = to_ewkt(rec[-1])
            if geom is None:
                issues.append(Issue(entry.layer, i, None, "error", "geometry", "feature has no geometry"))
                counts.rejected += 1
                continue
            attrs = {c: (None if pd.isna(v) else units.to_text(v)) for c, v in zip(attrs_cols, rec[:-1])}
            name = attrs.get(entry.name_field) if entry.name_field else None
            rows.append((batch_id, entry.layer, name, json.dumps(attrs), geom))
        conn.execute("DELETE FROM gis.layer_feature WHERE layer = %s", (entry.layer,))
        counts.loaded += copy_rows(conn, "gis.layer_feature", ["batch_id", "layer", "name", "attrs", "geom"], rows)
    return counts


def load_folder(folder: Path, *, url: str | None = None, specs: dict[str, Spec] | None = None,
                env: dict[str, str] | None = None, version: str | None = None) -> BatchResult:
    """Load one dataset folder as one batch. Never raises for bad data: the batch says why."""
    folder = Path(folder)
    m = read_manifest(folder)
    specs = specs or load_specs()
    version = version or code_version()
    issues: list[Issue] = []

    with connect(url) as conn:
        batch_id = _open_batch(conn, m, version)
        conn.commit()    # the batch row survives even if the load below fails
        result = BatchResult(batch_id, m.dataset, "running")

        refusals = verify_files(m) + check_provenance(m, env)
        spec = specs.get(m.dataset)
        if spec is None and not m.is_layers:
            refusals.append(f"no template spec has dataset '{m.dataset}'")
        elif spec is not None and m.template and m.template != spec.id:
            refusals.append(f"manifest says template {m.template} but dataset {m.dataset} is {spec.id}")
        if refusals:
            issues = [Issue(None, None, None, "error", "refused", text) for text in refusals]
            result.status, result.message = "failed", "refused: " + "; ".join(refusals)
            _write_issues(conn, batch_id, issues)
            _close_batch(conn, batch_id, result)
            conn.commit()
            result.issues = issues
            return result

        for rel in unlisted_files(m):
            issues.append(Issue(None, None, None, "info", "unlisted_file", f"{rel} is not in the manifest; not loaded"))

        try:
            with conn.transaction():
                if m.is_layers:
                    counts, sheet_errors = load_layers(conn, m, batch_id, issues), 0
                else:
                    assert spec is not None
                    counts, sheet_errors = _load_tables(conn, m, spec, batch_id, resolver_from_db(conn), issues)
                result.rows_read, result.rows_loaded, result.rows_rejected = counts.read, counts.loaded, counts.rejected
                result.status = batch_status(counts.read, counts.loaded, counts.rejected, sheet_errors)
                n_err = sum(1 for i in issues if i.severity == "error")
                result.message = f"{counts.loaded} of {counts.read} rows loaded; {n_err} error(s)"
                _write_issues(conn, batch_id, issues)
                _close_batch(conn, batch_id, result)
            conn.commit()
        except Exception as exc:  # record any failure on the batch, then re-raise for the log
            conn.rollback()
            log.exception("load of %s failed", folder)
            failure = Issue(None, None, None, "error", "load_failed", f"{type(exc).__name__}: {exc}")
            result.status, result.message = "failed", failure.message
            result.rows_loaded = 0
            _write_issues(conn, batch_id, [failure])
            _close_batch(conn, batch_id, result)
            conn.commit()
            issues = [failure]
    result.issues = issues
    return result


def dataset_folders(root: Path, dataset: str | None = None) -> list[Path]:
    """Folders under root holding a manifest.toml (root itself, or root/<name>/)."""
    root = Path(root)
    if (root / "manifest.toml").exists():
        return [root]
    folders = sorted(p.parent for p in root.glob("*/manifest.toml"))
    if dataset:
        folders = [f for f in folders if f.name == dataset or _manifest_dataset(f) == dataset]
    return folders


def _manifest_dataset(folder: Path) -> str:
    try:
        return read_manifest(folder).dataset
    except ManifestError:
        return ""


def refresh_registers(url: str | None = None) -> dict[str, int]:
    """Load the config registers and calendar into ref.* in their own transaction."""
    with connect(url) as conn:
        counts = load_registers(conn)
        conn.commit()
    return counts


def load_root(root: Path, dataset: str | None = None, url: str | None = None) -> list[BatchResult]:
    """Refresh ref.*, then load every dataset folder under root (or only `dataset`)."""
    refresh_registers(url)
    specs = load_specs()
    version = code_version()
    results = []
    for folder in dataset_folders(root, dataset):
        try:
            results.append(load_folder(folder, url=url, specs=specs, version=version))
        except ManifestError as exc:
            log.error("%s: %s", folder, exc)
            results.append(BatchResult(None, folder.name, "failed", message=str(exc)))
    return results

