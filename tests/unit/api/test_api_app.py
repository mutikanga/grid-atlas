"""Tests for the app, the registry, provenance and the meta, network and export routers."""

from __future__ import annotations

import pytest

from api import provenance, tables
from api.tables import Col, TableSpec

# Values from conftest.SYNTHETIC_PROV: run 7 started 06:00 UTC, which is 09:00 EAT.
STARTED_EAT = "2026-11-01 09:00"
PROV_COLUMNS = ["run_id", "level", "label", "synthetic", "detail", "code_version", "started_at", "finished_at"]


# ---------------------------------------------------------------- registry


def test_registry_refuses_unsafe_names():
    good = dict(name="t_ok", title="T", view="api.v_ok", columns=[Col("a", "A")])
    TableSpec(**good)
    with pytest.raises(ValueError):
        TableSpec(**{**good, "view": "meta.run"})  # outside the api schema
    with pytest.raises(ValueError):
        TableSpec(**{**good, "view": "api.v_ok; drop table x"})
    with pytest.raises(ValueError):
        TableSpec(**{**good, "columns": [Col("a b", "A")]})
    with pytest.raises(ValueError):
        TableSpec(**{**good, "filters": {"m": "month) or (1=1"}})
    with pytest.raises(ValueError):
        TableSpec(**{**good, "order_by": "a; select 1"})
    with pytest.raises(ValueError):
        TableSpec(**{**good, "columns": [Col("provenance", "P")]})


def test_register_get_all():
    spec = tables.register(TableSpec(name="t_reg", title="T", view="api.v_reg", columns=[Col("a", "A")],
                                     order_by="a desc nulls last"))
    assert tables.get("t_reg") is spec
    assert "t_reg" in [t.name for t in tables.all()]
    with pytest.raises(KeyError):
        tables.get("t_missing")


# ---------------------------------------------------------------- provenance


@pytest.mark.parametrize(
    "level, synthetic, kind, prefix",
    [
        ("synthetic", True, "synthetic", "SYNTHETIC_"),
        ("SYNTHETIC", False, "synthetic", "SYNTHETIC_"),
        ("partly synthetic", False, "synthetic", "SYNTHETIC_"),
        ("approximate", False, "approximate", "APPROXIMATE_"),
        ("open", False, "open", ""),
        ("real", False, "real", ""),
        ("REAL - VERIFIED", False, "real", ""),
        ("real", True, "synthetic", "SYNTHETIC_"),  # a synthetic flag always wins
        ("something new", False, "synthetic", "SYNTHETIC_"),  # unknown is the safe side
        (None, None, "none", "SYNTHETIC_"),
    ],
)
def test_provenance_classification(level, synthetic, kind, prefix):
    prov = provenance.enrich({"level": level, "synthetic": synthetic, "run_id": 1})
    assert prov["kind"] == kind
    assert provenance.file_prefix(prov) == prefix
    assert prov["is_real"] == (prefix == "" and kind in ("open", "real"))
    assert bool(prov["watermark"]) == (not prov["is_real"])


def test_provenance_is_cached(fake_db):
    provenance.current()
    provenance.current()
    assert sum("api.v_provenance" in sql for sql, _ in fake_db.calls) == 1


def test_no_run_means_not_real(fake_db):
    import pandas as pd

    fake_db.frames["api.v_provenance"] = pd.DataFrame(columns=PROV_COLUMNS)
    prov = provenance.current()
    assert prov["kind"] == "none" and prov["is_real"] is False


# ---------------------------------------------------------------- app


def all_route_methods(app) -> dict[str, set[str]]:
    """Every path with its HTTP methods: the OpenAPI paths plus the routes kept out of the schema.

    FastAPI 0.162 keeps included routers as private wrapper objects in `app.routes`, so the
    public views are the OpenAPI document and each router's own `routes`.
    """
    from api.routers import discover

    found: dict[str, set[str]] = {}
    for path, ops in app.openapi()["paths"].items():
        found.setdefault(path, set()).update(m.upper() for m in ops)
    for _name, router in discover():
        for route in router.routes:
            found.setdefault(route.path, set()).update(getattr(route, "methods", set()) or set())
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            found.setdefault(route.path, set()).update(route.methods or set())
    return found


def test_only_get_routes(client):
    from api.main import app

    routes = all_route_methods(app)
    assert routes, "no routes found"
    for path, methods in routes.items():
        assert methods <= {"GET", "HEAD"}, f"{path} allows {methods}"
    assert client.post("/api/health").status_code == 405
    assert client.delete("/export/runs.csv").status_code == 405


def test_core_routes_exist():
    from api.main import app

    paths = set(all_route_methods(app))
    for path in ["/api/health", "/api/meta/provenance", "/api/meta/runs", "/api/meta/months",
                 "/api/meta/imports", "/api/meta/imports/issues", "/api/network/geo",
                 "/export/{name}.csv", "/export/{name}.xlsx", "/api/docs", "/api/openapi.json"]:
        assert path in paths, path


def test_docs_are_self_hosted(client):
    html = client.get("/api/docs").text
    assert "/vendor/swagger-ui/swagger-ui-bundle.js" in html
    assert "/vendor/swagger-ui/swagger-ui.css" in html
    assert "cdn.jsdelivr" not in html and "unpkg" not in html
    assert client.get("/api/openapi.json").json()["info"]["title"] == "UETCL Grid Atlas API"


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] == "ok"


def test_health_reports_database_failure(client, monkeypatch):
    from api import db

    def down(sql, params=None):
        raise ConnectionError("database is down")

    monkeypatch.setattr(db, "query", down)
    resp = client.get("/api/health")
    assert resp.status_code == 503 and "down" in resp.json()["database"]


def test_meta_provenance(client):
    body = client.get("/api/meta/provenance").json()
    assert body["run_id"] == 7 and body["kind"] == "synthetic" and body["is_real"] is False
    assert body["started_at"] == STARTED_EAT
    assert body["watermark"] == "SYNTHETIC: NOT UETCL DATA"


def test_months_end_with_2030(client):
    rows = client.get("/api/meta/months").json()["rows"]
    assert [r["month"] for r in rows] == ["2025-09", "2025-10", "2030"]
    assert rows[-1]["is_forecast"] is True


def test_months_keep_the_views_own_2030_row(client, fake_db):
    import pandas as pd

    fake_db.frames["api.v_months"] = pd.DataFrame([
        {"month": "2025-09", "label": "Sep 2025", "is_forecast": False},
        {"month": "2030", "label": "2030", "is_forecast": True},
    ])
    rows = client.get("/api/meta/months").json()["rows"]
    assert rows == [{"month": "2025-09", "label": "Sep 2025", "is_forecast": False},
                    {"month": "2030", "label": "2030", "is_forecast": True}]


def test_months_fallback_when_view_empty(client, fake_db):
    fake_db.frames["api.v_months"] = fake_db.frames["api.v_months"].iloc[0:0]
    rows = client.get("/api/meta/months").json()["rows"]
    assert len(rows) == 14 and rows[0]["month"] == "2025-09" and rows[12]["month"] == "2026-09"


def test_runs_and_imports_tables(client, fake_db):
    runs = client.get("/api/meta/runs").json()
    assert runs["rows"][0]["started_at"] == STARTED_EAT
    assert runs["rows"][0]["stages"] == ["network", "losses"]
    issues = client.get("/api/meta/imports/issues", params={"batch_id": "3", "severity": "error"}).json()
    assert issues["rows"][0]["column_name"] == "sent_out_mwh"
    assert issues["export"]["csv"] == "/export/import_issues.csv?batch_id=3&severity=error"
    sql, params = [c for c in fake_db.calls if "api.v_import_issues" in c[0]][-1]
    assert params == {"f0": "3", "f1": "error"} and ":f0" in sql


# ---------------------------------------------------------------- network


def test_network_geo(client):
    geo = client.get("/api/network/geo").json()
    assert geo["type"] == "FeatureCollection"
    assert geo["provenance"]["kind"] == "synthetic"
    by_id = {f["id"]: f for f in geo["features"]}
    kaw = by_id["KAW"]
    assert kaw["geometry"] == {"type": "Point", "coordinates": [32.5, 0.42]}
    assert kaw["properties"]["kind"] == "substation" and kaw["properties"]["kv_levels"] == "132/33"
    assert by_id["MUT"]["geometry"] is None  # no coordinates: no geometry, but still listed
    line = by_id["L-KAW-MUT-132-1"]
    assert line["geometry"]["type"] == "LineString"
    props = line["properties"]
    assert props["kind"] == "element" and props["age_years"] == 28 and props["length_km"] == 12.35
    assert set(props) >= {"element_type", "element_id", "name", "ss_from", "ss_to", "kv", "length_km",
                          "in_central", "rate_mva", "commissioning_year", "age_years", "status"}
    assert "geojson" not in props
    assert by_id["T-KAW-1"]["geometry"] is None


def test_export_list_and_unknown(client):
    names = [t["name"] for t in client.get("/export/").json()["tables"]]
    assert {"runs", "import_batches", "import_issues", "months"} <= set(names)
    assert client.get("/export/not_a_table.csv").status_code == 404
