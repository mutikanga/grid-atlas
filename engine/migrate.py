"""Apply db/migrations/NNN_name.sql in order, tracking each file's sha256.

Number ranges (docs/dev/contracts.md section 7):
  001-099  core tables: applied once. A changed file is an error; write a new migration.
  100-199  generated ts.* input tables: rebuildable. When one changes, schema ts is dropped
           with CASCADE and all 1NN files are re-applied; the inputs must then be reloaded.
  200-899  results tables: applied once, like 001-099.
  900-999  api views: re-applied on every migrate, after everything else.

The planning logic (plan_migrations) is pure so it can be unit-tested without a database.
Runs as atlas_rw, which owns every schema. Safe to run again: nothing changes the second time.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from engine.config import MIGRATIONS_DIR
from engine.db import connect, lock_key

log = logging.getLogger("atlas.migrate")

_NAME_RE = re.compile(r"^(\d{3})_[A-Za-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    """A migration cannot be applied safely (for example an applied file was edited)."""


@dataclass(frozen=True)
class MigrationFile:
    """One migration file: its name, number, content hash and path."""

    name: str
    number: int
    sha256: str
    path: Path | None = None

    @property
    def kind(self) -> str:
        """'once', 'rebuild' (100-199) or 'view' (900-999)."""
        return kind_of(self.number)


@dataclass(frozen=True)
class Step:
    """What to do with one file: apply, skip, or reset_ts before re-applying 1NN files."""

    action: str          # apply | skip | reset_ts
    name: str = ""
    reason: str = ""


def kind_of(number: int) -> str:
    """The range a migration number falls in."""
    if 100 <= number <= 199:
        return "rebuild"
    if 900 <= number <= 999:
        return "view"
    if 1 <= number <= 899:
        return "once"
    raise MigrationError(f"migration number {number:03d} is outside 001-999")


def sha256_text(text: str) -> str:
    """The sha256 of a file's text (line endings normalised so Windows edits do not count)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode()).hexdigest()


def discover(directory: Path | None = None) -> list[MigrationFile]:
    """The migration files in name order. Files not named NNN_name.sql are ignored.

    $ATLAS_MIGRATIONS_DIR overrides the folder (for testing a migration before it lands).
    """
    directory = directory or Path(os.environ.get("ATLAS_MIGRATIONS_DIR") or MIGRATIONS_DIR)
    files = []
    for path in sorted(directory.glob("*.sql")):
        match = _NAME_RE.match(path.name)
        if not match:
            log.warning("ignoring %s: migration files are named NNN_name.sql", path.name)
            continue
        files.append(MigrationFile(path.name, int(match.group(1)), sha256_text(path.read_text(encoding="utf-8")), path))
    return files


def plan_migrations(files: list[MigrationFile], applied: dict[str, str]) -> list[Step]:
    """Decide what to do with each file, given {filename: sha256} already applied.

    Order: every non-view file in name order (with a reset_ts step before the 1NN files if
    any of them changed), then every view file in name order.
    """
    ordered = sorted(files, key=lambda f: f.name)
    for f in ordered:
        if f.kind == "once" and f.name in applied and applied[f.name] != f.sha256:
            raise MigrationError(
                f"{f.name} was changed after it was applied. Files 001-099 and 200-899 are applied "
                "once: put the change in a new migration (or ./atlas reset in dev).")

    rebuild = [f for f in ordered if f.kind == "rebuild"]
    ts_changed = any(f.name in applied and applied[f.name] != f.sha256 for f in rebuild)

    steps: list[Step] = []
    for f in ordered:
        if f.kind == "view":
            continue
        if f.kind == "rebuild" and ts_changed:
            if not any(s.action == "reset_ts" for s in steps):
                steps.append(Step("reset_ts", reason="a 1NN input-table migration changed"))
            steps.append(Step("apply", f.name, "rebuild ts"))
        elif f.name in applied:
            steps.append(Step("skip", f.name, "already applied"))
        else:
            steps.append(Step("apply", f.name, "new"))
    for f in ordered:
        if f.kind == "view":
            steps.append(Step("apply", f.name, "views are re-applied every time"))
    return steps


BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS meta;
CREATE TABLE IF NOT EXISTS meta.schema_migration (
    filename   text PRIMARY KEY,
    sha256     text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""

# Re-run after all views so views created by later 9NN files are readable by atlas_ro too.
# Skipped quietly when the role does not exist (for example a bare test database).
GRANT_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_ro')
       AND EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'api') THEN
        GRANT USAGE ON SCHEMA api TO atlas_ro;
        GRANT SELECT ON ALL TABLES IN SCHEMA api TO atlas_ro;
    END IF;
END
$$;
"""


def _applied(conn: psycopg.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT filename, sha256 FROM meta.schema_migration").fetchall()
    return {name: sha for name, sha in rows}


def _apply_file(conn: psycopg.Connection, f: MigrationFile) -> None:
    """Run one file and record it, in one transaction."""
    assert f.path is not None
    sql_text = f.path.read_text(encoding="utf-8")
    with conn.transaction():
        conn.execute(sql_text)
        conn.execute(
            "INSERT INTO meta.schema_migration (filename, sha256) VALUES (%s, %s) "
            "ON CONFLICT (filename) DO UPDATE SET sha256 = EXCLUDED.sha256, applied_at = now()",
            (f.name, f.sha256))


def _reset_ts(conn: psycopg.Connection) -> None:
    """Drop schema ts (and views that depend on it) and forget the 1NN migrations."""
    with conn.transaction():
        conn.execute("DROP SCHEMA IF EXISTS ts CASCADE")
        conn.execute("DELETE FROM meta.schema_migration WHERE filename ~ '^1[0-9]{2}_'")


def migrate(url: str | None = None, directory: Path | None = None) -> dict[str, list[str]]:
    """Bring the database up to date. Returns {'applied': [...], 'skipped': [...], 'ts_rebuilt': [...]}."""
    files = {f.name: f for f in discover(directory)}
    summary: dict[str, list[str]] = {"applied": [], "skipped": [], "ts_rebuilt": []}
    with connect(url, autocommit=True) as conn:
        # One migrator at a time (the worker and a manual ./atlas migrate could overlap).
        conn.execute("SELECT pg_advisory_lock(%s)", (lock_key("atlas-migrate"),))
        try:
            conn.execute(BOOTSTRAP_SQL)
            steps = plan_migrations(list(files.values()), _applied(conn))
            for step in steps:
                if step.action == "reset_ts":
                    log.warning("input tables changed: dropping schema ts and re-creating it")
                    _reset_ts(conn)
                    summary["ts_rebuilt"].append("ts")
                elif step.action == "skip":
                    summary["skipped"].append(step.name)
                else:
                    log.info("applying %s (%s)", step.name, step.reason)
                    try:
                        _apply_file(conn, files[step.name])
                    except psycopg.Error as exc:
                        raise MigrationError(f"{step.name} failed: {exc}") from exc
                    summary["applied"].append(step.name)
            conn.execute(GRANT_SQL)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (lock_key("atlas-migrate"),))
    if summary["ts_rebuilt"]:
        log.warning("The ts input tables were rebuilt and are now empty: reload inputs (./atlas load).")
    return summary
