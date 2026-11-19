"""Database access for the API.

The API connects as `atlas_ro`, which can only SELECT from the `api.*` views and runs
every transaction read-only with a 5 s statement timeout (set on the role, contracts
section 7). This module adds nothing clever on top: one small connection pool and one
`query` function that returns a pandas DataFrame.

Tests replace `query` with a fake (monkeypatch `api.db.query`), so every other module
must call it as `db.query(...)` rather than importing the function directly.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_engine: Engine | None = None


def database_url() -> str:
    """Return the SQLAlchemy URL from DATABASE_URL, forcing the psycopg 3 driver.

    docker-compose gives a plain `postgresql://` URL; SQLAlchemy would then look for
    psycopg2, which the image does not have.
    """
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    for plain in ("postgresql://", "postgres://"):
        if url.startswith(plain):
            return "postgresql+psycopg://" + url[len(plain):]
    return url


def get_engine() -> Engine:
    """Create the engine on first use. The pool is small because the API has 512 MB."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            database_url(),
            pool_size=3,
            max_overflow=2,
            pool_pre_ping=True,  # survive a database restart without a 500
            pool_recycle=1800,
        )
    return _engine


def query(sql: str, params: Mapping[str, Any] | None = None) -> pd.DataFrame:
    """Run one SELECT and return the rows as a DataFrame.

    `sql` must use named bind parameters (`:name`) for every value that came from a
    request. Never format request values into the SQL string.
    """
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), dict(params or {}))
        rows = result.fetchall()
        return pd.DataFrame(rows, columns=list(result.keys()))
