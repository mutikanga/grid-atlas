"""Database helpers: one SQLAlchemy engine, DataFrame reads, fast COPY writes, locks.

The connection string comes from $DATABASE_URL, for example
    postgresql+psycopg://atlas_rw:secret@db/gridatlas
SQLAlchemy is used for reads (pandas understands it); psycopg is used directly for COPY,
which is many times faster than INSERT for the thousands of rows a run writes.
"""
from __future__ import annotations

import json
import math
import os
import re
import zlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
import psycopg
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# schema.table, both plain lower-case identifiers. Anything else is refused, so a table
# name can never smuggle SQL into a query.
_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


class LockBusy(RuntimeError):
    """Another job holds the advisory lock (for example a load or run in progress)."""


def database_url() -> str:
    """The SQLAlchemy URL from $DATABASE_URL."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (for example postgresql+psycopg://atlas_rw:...@db/gridatlas)")
    return url


def libpq_url(url: str | None = None) -> str:
    """The same URL in the form psycopg expects (no '+psycopg' driver suffix)."""
    url = url or database_url()
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


@lru_cache(maxsize=8)
def get_engine(url: str | None = None) -> Engine:
    """A cached SQLAlchemy engine for the URL (default $DATABASE_URL)."""
    url = url or database_url()
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return create_engine(url, pool_pre_ping=True, future=True)


def connect(url: str | None = None, autocommit: bool = False) -> psycopg.Connection:
    """A plain psycopg connection, for COPY, migrations and multi-step transactions."""
    return psycopg.connect(libpq_url(url), autocommit=autocommit)


def check_table_name(name: str) -> str:
    """Return name if it is a safe 'schema.table', else raise ValueError."""
    if not _TABLE_RE.match(name):
        raise ValueError(f"not a valid schema.table name: {name!r}")
    return name


def read_df(query: str, params: dict[str, Any] | None = None, url: str | None = None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. Use :name placeholders for parameters."""
    with get_engine(url).connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def execute(query: str, params: dict[str, Any] | None = None, url: str | None = None) -> int:
    """Run one statement in its own transaction and return the affected row count."""
    with get_engine(url).begin() as conn:
        result = conn.execute(text(query), params or {})
        return result.rowcount


def to_db_value(value: Any) -> Any:
    """Turn a pandas/numpy cell into a plain Python value psycopg can send.

    NaN, NaT and pd.NA become None (SQL NULL); numpy scalars become Python numbers;
    dicts and lists become JSON text (for jsonb columns).
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if isinstance(value, np.ndarray):
        return [to_db_value(v) for v in value.tolist()]
    if value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (str, int, float, bool, date, datetime, Decimal)):
        return value
    return value


def copy_rows(conn: psycopg.Connection, table: str, columns: Sequence[str], rows: Iterator[Sequence[Any]] | Sequence[Sequence[Any]]) -> int:
    """COPY rows (sequences in column order) into schema.table on an open connection."""
    check_table_name(table)
    schema, name = table.split(".")
    stmt = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(schema), sql.Identifier(name),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    n = 0
    with conn.cursor() as cur:
        with cur.copy(stmt) as copy:
            for row in rows:
                copy.write_row([to_db_value(v) for v in row])
                n += 1
    return n


def copy_df(table: str, df: pd.DataFrame, conn: psycopg.Connection | None = None, url: str | None = None) -> int:
    """Bulk-load a DataFrame into schema.table with COPY. Returns the row count.

    Column names must match the table's. With conn, the caller owns the transaction;
    without it, a connection is opened and committed here.
    """
    if df.empty:
        return 0
    columns = [str(c) for c in df.columns]
    rows = df.astype(object).itertuples(index=False, name=None)
    if conn is not None:
        return copy_rows(conn, table, columns, rows)
    with connect(url) as own:
        n = copy_rows(own, table, columns, rows)
        own.commit()
    return n


def lock_key(name: str) -> int:
    """A stable 32-bit key for pg_advisory_lock from a readable name."""
    return zlib.crc32(name.encode())


@contextmanager
def advisory_lock(name: str = "atlas-job", wait: bool = False, url: str | None = None) -> Iterator[None]:
    """Hold a session advisory lock while the block runs.

    Loads and runs take the same lock, so two of them never overlap. With wait=False a
    busy lock raises LockBusy at once instead of queueing behind a long run.
    """
    conn = connect(url, autocommit=True)
    key = lock_key(name)
    try:
        if wait:
            conn.execute("SELECT pg_advisory_lock(%s)", (key,))
        else:
            got = conn.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0]
            if not got:
                raise LockBusy(f"another job holds the '{name}' lock; try again when it finishes")
        try:
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
    finally:
        conn.close()
