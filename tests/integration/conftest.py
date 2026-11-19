"""Fixtures for database tests: a private database per test session.

Each session gets its own database, copied from gridatlas_template (PostGIS installed),
migrated, and dropped at the end. The shared 'gridatlas' database is never touched.

Environment (any one way to reach the server is enough):
  TEST_ADMIN_URL   a role that may CREATE DATABASE (atlas_rw has CREATEDB), connected to
                   any existing database, e.g. postgresql://atlas_rw:rw@db/postgres
  DATABASE_URL     used instead when TEST_ADMIN_URL is not set (the database is swapped)
  TEST_RO_URL      the API role, e.g. postgresql://atlas_ro:ro@db/postgres; else built
                   from the admin URL with user atlas_ro and $ATLAS_RO_PASSWORD
Tests are skipped when no database is reachable.

Usage in a test module:
    def test_something(migrated_db):           # URL of a migrated private database
        ...
    def test_api(migrated_db, ro_url_for): ro = ro_url_for(migrated_db)
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator

import psycopg
import pytest
from sqlalchemy.engine import make_url

from engine import db
from engine.migrate import migrate


def _admin_url() -> str | None:
    url = os.environ.get("TEST_ADMIN_URL") or os.environ.get("DATABASE_URL")
    if not url:
        return None
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def _with_database(url: str, database: str) -> str:
    return make_url(url).set(database=database).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def admin_url() -> str:
    """URL of a role allowed to create databases; skips the tests if none is reachable."""
    url = _admin_url()
    if url is None:
        pytest.skip("no TEST_ADMIN_URL or DATABASE_URL: database tests skipped")
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(f"database not reachable: {exc}")
    return url


def create_private_db(admin: str, prefix: str = "gridatlas_test") -> str:
    """Create an empty private database from gridatlas_template and return its URL."""
    # drop_private_db only drops gridatlas_test* databases, so every prefix must start so.
    assert prefix.startswith("gridatlas_test"), "prefix must start with gridatlas_test"
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        has_template = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'gridatlas_template'").fetchone()
        conn.execute(f'CREATE DATABASE "{name}"' + (" TEMPLATE gridatlas_template" if has_template else ""))
    return _with_database(admin, name)


def drop_private_db(admin: str, url: str) -> None:
    """Drop a database made by create_private_db (closing any open sessions first)."""
    name = make_url(url).database
    assert name and name.startswith("gridatlas_test"), "refusing to drop a database this suite did not create"
    db.get_engine.cache_clear()     # pooled SQLAlchemy connections would block the drop
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
def private_db(admin_url: str) -> Iterator[str]:
    """An empty private database for the whole session; dropped afterwards."""
    url = create_private_db(admin_url)
    try:
        yield url
    finally:
        drop_private_db(admin_url, url)


@pytest.fixture(scope="session")
def migrated_db(private_db: str) -> Iterator[str]:
    """The private database with all migrations applied. DATABASE_URL points at it meanwhile."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = private_db
    db.get_engine.cache_clear()
    try:
        migrate(private_db)
        yield private_db
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        db.get_engine.cache_clear()


@pytest.fixture(scope="session")
def ro_url_for() -> Callable[[str], str]:
    """Turns a private database URL into the API role's URL for the same database."""
    def build(url: str) -> str:
        explicit = os.environ.get("TEST_RO_URL")
        if explicit:
            return _with_database(explicit, make_url(url).database)
        password = os.environ.get("ATLAS_RO_PASSWORD")
        if not password:
            pytest.skip("set TEST_RO_URL or ATLAS_RO_PASSWORD to test the read-only role")
        return make_url(url).set(username="atlas_ro", password=password).render_as_string(hide_password=False)
    return build
