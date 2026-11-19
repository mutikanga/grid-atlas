"""Database tests for the core layer: migrations, registers, the loader and the run framework.

Run against a private database (see conftest.py), for example with the stack up:
    docker compose run --rm -e TEST_ADMIN_URL=postgresql://atlas_rw:...@db/postgres \
        -e ATLAS_RO_PASSWORD=... worker pytest -q tests/integration/test_core.py
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
from openpyxl import Workbook

from engine.config import ROOT
from engine.migrate import migrate
from loaders.generic import load_folder, load_root, refresh_registers
from loaders.spec import load_specs

EAT = timezone(timedelta(hours=3))


# ---------------------------------------------------------------------------------------
# Building small deliveries
# ---------------------------------------------------------------------------------------
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(folder: Path, dataset: str, template: str, provenance: str, files: list[tuple[str, str]]) -> None:
    """files: (path, sheet or '')."""
    lines = [f'dataset = "{dataset}"', f'template = "{template}"', f'provenance = "{provenance}"',
             'received_from = "tests/integration"', "received_on = 2026-11-01", 'adapter = "template"']
    for path, sheet in files:
        lines += ["[[files]]", f'path = "{path}"', f'sha256 = "{sha(folder / path)}"']
        if sheet:
            lines.append(f'sheet = "{sheet}"')
    (folder / "manifest.toml").write_text("\n".join(lines) + "\n")


def workbook(path: Path, sheets: dict[str, list[list]], synthetic: bool = True) -> None:
    wb = Workbook()
    wb.active.title = "README"
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    if synthetic:
        wb.properties.keywords = "gridatlas-synthetic T03"
    wb.save(path)


SUB_HEAD = ["month", "substation", "metering_point", "energy_mwh", "peak_mw", "customer_name"]


def make_ncc_monthly(root: Path, energy_kaw: float = 41250.0) -> Path:
    """A tiny T03 delivery with good rows, bad rows, aliases and a duplicate key."""
    folder = root / "synthetic" / "ncc_monthly"
    folder.mkdir(parents=True, exist_ok=True)
    name = "SYNTHETIC_T03_ncc_monthly.xlsx"
    workbook(folder / name, {
        "definitions": [["question_id", "question", "answer"], ["Q1", "How?", "From the 132 kV meters"], ["Q2", "Q2?", None]],
        "system_summary": [
            ["month", "sent_out_mwh", "delivered_mwh", "losses_mwh", "peak_mw", "peak_at", "estimated"],
            ["2026-03", 100000, 96500, 3500, 200, "2026-03-12 20:00", "N"],          # good
            ["2026-04", "1,234", 1200, 34, 9000, datetime(2026, 4, 9, 20), "Y"],    # good, warn_max on peak
            ["2026-05", -5, 1, 1, 10, None, "N"],                                   # min error
            ["May 2026", 1, 1, 1, 10, None, "maybe"],                               # month and yn errors
        ],
        "substation_monthly": [
            SUB_HEAD,
            ["2026-03", "Kawanda S/S", "T1+T2 LV", energy_kaw, 82.4, "Someone"],   # name normalised
            ["2026-03", "Kampala Nth", None, 30000, 60, None],                     # alias
            ["2026-03", "Kawandaa", None, 100, 1, None],                           # unresolved: suggestion
            ["2026-03", "Kawanda", "T1+T2 LV", 1, 1, None],                        # duplicate key of row 2
            [None, None, None, None, None, None],                                  # blank: ignored
        ],
        "not_a_sheet": [["x"], [1]],
    })
    write_manifest(folder, "ncc_monthly", "T03", "synthetic", [(name, "")])
    return folder


def make_scada(root: Path) -> Path:
    folder = root / "synthetic" / "scada"
    folder.mkdir(parents=True, exist_ok=True)
    name = "SYNTHETIC_scada_2026-03.csv"
    (folder / name).write_text(
        "timestamp,point_id,value,unit,quality\n"
        "2026-03-12 20:00,KAW.L1.P,92.4,MW,good\n"
        "2026-03-12 21:00,KAW.L1.P,90.1,MW,good\n"
        "not a time,KAW.L1.P,1,MW,good\n")
    write_manifest(folder, "scada", "T04", "synthetic", [(name, "hourly_data")])
    return folder


def make_gis(root: Path) -> Path:
    """A circuit layer in UTM 36N, to prove reprojection to WGS 84."""
    import geopandas as gpd
    from shapely.geometry import LineString
    folder = root / "synthetic" / "gis"
    folder.mkdir(parents=True, exist_ok=True)
    name = "SYNTHETIC_circuits.geojson"
    line = gpd.GeoSeries([LineString([(32.535, 0.417), (32.547, 0.288)])], crs="EPSG:4326").to_crs("EPSG:32636")
    gdf = gpd.GeoDataFrame({"circuit_id": ["C1"], "model_branch_id": ["L-KAW-MUT-132-1"], "from_substation": ["Kawanda"],
                            "to_substation": ["Mutundwe"], "kv": [132], "status": ["existing"]}, geometry=line)
    gdf.to_file(folder / name, driver="GeoJSON")
    write_manifest(folder, "gis", "T02", "synthetic", [(name, "circuits")])
    return folder


def issues(conn: psycopg.Connection, batch_id: int) -> list[tuple]:
    return conn.execute("SELECT sheet, row_num, column_name, severity, rule, suggestion, raw_row FROM meta.import_issue "
                        "WHERE batch_id = %s ORDER BY issue_id", (batch_id,)).fetchall()


class StubStage:
    """Stands in for a stage module, so these tests do not depend on other owners' stages."""

    def __init__(self, fail: bool = False):
        self.fail = fail

    def run(self, ctx) -> None:
        if self.fail:
            raise RuntimeError("planted failure")
        ctx.log.info("stub stage ran")


def stub_stages(monkeypatch, failing: set[str] = frozenset()) -> None:
    import engine.cli
    monkeypatch.setattr(engine.cli, "load_stage", lambda name: StubStage(name in failing))


# ---------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------
def test_migrate_is_idempotent(migrated_db):
    again = migrate(migrated_db)
    assert again["applied"] == ["900_api_core.sql"] or all(n.startswith("9") for n in again["applied"])
    assert "001_meta.sql" in again["skipped"]
    with psycopg.connect(migrated_db) as conn:
        names = [r[0] for r in conn.execute("SELECT filename FROM meta.schema_migration ORDER BY filename")]
    assert names[:5] == ["001_meta.sql", "002_ref.sql", "003_gis.sql", "004_results_core.sql", "100_ts_generated.sql"]


def test_registers(migrated_db):
    counts = refresh_registers(migrated_db)
    assert counts["substations"] == 15 and counts["months"] == 14
    with psycopg.connect(migrated_db) as conn:
        assert conn.execute("SELECT count(*) FROM ref.substation WHERE in_central").fetchone()[0] == 11
        assert conn.execute("SELECT canonical_id FROM ref.alias WHERE alias_norm = 'KAWANDA' AND entity_type = 'substation'").fetchone()[0] == "KAW"
        assert conn.execute("SELECT canonical_id FROM ref.alias WHERE alias_norm = 'KAW'").fetchone()[0] == "KAW"
        assert conn.execute("SELECT ST_SRID(geom) FROM ref.substation WHERE ss_code = 'KAW'").fetchone()[0] == 4326
    refresh_registers(migrated_db)   # a second refresh changes nothing and does not fail


def test_template_workbooks_load_empty(migrated_db, tmp_path):
    """The blank request workbooks themselves load cleanly: no rows, no errors."""
    refresh_registers(migrated_db)
    specs = load_specs()
    for spec in specs.values():
        folder = tmp_path / "templates" / spec.dataset
        folder.mkdir(parents=True)
        name = f"{spec.id}_{spec.slug}.xlsx"
        shutil.copy(ROOT / "templates" / name, folder / name)
        write_manifest(folder, spec.dataset, spec.id, "approximate", [(name, "")])
        result = load_folder(folder, url=migrated_db, specs=specs, env={})
        errors = [i for i in result.issues if i.severity == "error"]
        assert result.status == "ok", (spec.id, result.message, errors)
        assert result.rows_loaded == 0 and not errors


def test_load_quarantine_aliases_and_replace(migrated_db, tmp_path):
    refresh_registers(migrated_db)
    folder = make_ncc_monthly(tmp_path)
    result = load_folder(folder, url=migrated_db, env={})
    assert result.status == "partial", result.message
    # system_summary 2 good + 2 bad; substation 2 good + unresolved + duplicate; Q1 answered
    assert (result.rows_read, result.rows_loaded, result.rows_rejected) == (9, 5, 4)

    with psycopg.connect(migrated_db) as conn:
        found = issues(conn, result.batch_id)
        rules = {(s, r) for s, _, _, sev, r, _, _ in found if sev == "error"}
        assert {("system_summary", "min"), ("system_summary", "type"), ("substation_monthly", "unresolved_name"),
                ("substation_monthly", "duplicate_key")} <= rules
        unresolved = next(i for i in found if i[4] == "unresolved_name")
        assert unresolved[1] == 4 and unresolved[5].startswith("KAW") and unresolved[6]["substation"] == "Kawandaa"
        assert "customer_name" not in unresolved[6]          # unknown columns never stored
        assert any(i[4] == "unknown_column" and i[2] == "customer_name" and i[3] == "info" for i in found)
        assert any(i[4] == "warn_max" and i[3] == "warning" for i in found)
        assert any(i[4] == "unknown_sheet" and i[0] == "not_a_sheet" for i in found)

        rows = conn.execute("SELECT substation, substation_code, metering_point, energy_mwh, row_num FROM ts.ncc_substation_monthly "
                            "ORDER BY substation_code").fetchall()
        assert [(r[1], r[3]) for r in rows] == [("KAW", 41250.0), ("KNO", 30000.0)]
        assert rows[0][4] == 2                                # spreadsheet row number kept
        peak_at = conn.execute("SELECT peak_at FROM ts.ncc_system_monthly WHERE month = '2026-03-01'").fetchone()[0]
        assert peak_at == datetime(2026, 3, 12, 20, tzinfo=EAT)
        assert conn.execute("SELECT answer FROM ts.qa_answer WHERE question_id = 'Q1'").fetchone()[0].startswith("From")
        assert conn.execute("SELECT count(*) FROM ts.qa_answer").fetchone()[0] == 1

    # A corrected delivery replaces rows with the same key; it does not add to them.
    shutil.rmtree(folder)
    folder = make_ncc_monthly(tmp_path, energy_kaw=41300.0)
    second = load_folder(folder, url=migrated_db, env={})
    with psycopg.connect(migrated_db) as conn:
        rows = conn.execute("SELECT substation_code, energy_mwh, batch_id FROM ts.ncc_substation_monthly ORDER BY 1").fetchall()
        assert rows == [("KAW", 41300.0, second.batch_id), ("KNO", 30000.0, second.batch_id)]
        assert conn.execute("SELECT count(*) FROM ts.ncc_system_monthly").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM ts.qa_answer").fetchone()[0] == 1


def test_csv_and_vector(migrated_db, tmp_path):
    refresh_registers(migrated_db)
    scada = load_folder(make_scada(tmp_path), url=migrated_db, env={})
    assert (scada.status, scada.rows_loaded, scada.rows_rejected) == ("partial", 2, 1)
    gis = load_folder(make_gis(tmp_path), url=migrated_db, env={})
    assert gis.status == "ok", gis.message
    with psycopg.connect(migrated_db) as conn:
        ts0 = conn.execute("SELECT min(timestamp) FROM ts.scada_hourly").fetchone()[0]
        assert ts0 == datetime(2026, 3, 12, 20, tzinfo=EAT)
        row = conn.execute("SELECT from_substation_code, to_substation_code, ST_SRID(geom), ST_X(ST_StartPoint(geom)) "
                           "FROM ts.gis_circuit").fetchone()
        assert row[:3] == ("KAW", "MUT", 4326) and abs(row[3] - 32.535) < 1e-6


def test_refusals(migrated_db, tmp_path):
    refresh_registers(migrated_db)
    folder = make_scada(tmp_path)
    (folder / "SYNTHETIC_scada_2026-03.csv").write_text("changed after receipt\n")
    result = load_folder(folder, url=migrated_db, env={})
    assert result.status == "failed" and "sha256" in result.message
    server = load_folder(make_gis(tmp_path / "other"), url=migrated_db, env={"ATLAS_ENV": "server"})
    assert server.status == "failed" and "server" in server.message


def test_load_root_and_run(migrated_db, tmp_path, monkeypatch):
    from engine.cli import run_pipeline
    stub_stages(monkeypatch)
    from engine.stages import STAGES
    make_ncc_monthly(tmp_path)
    make_scada(tmp_path)
    results = load_root(tmp_path / "synthetic", url=migrated_db)
    assert {r.dataset for r in results} == {"ncc_monthly", "scada"}

    run_id = run_pipeline(list(STAGES), pin=True, url=migrated_db)
    with psycopg.connect(migrated_db) as conn:
        status, level, detail = conn.execute(
            "SELECT status, provenance_level, provenance_detail FROM meta.run WHERE run_id = %s", (run_id,)).fetchone()
        assert status == "ok" and level == "synthetic" and "ncc_monthly" in detail["synthetic_inputs"]
        stages = conn.execute("SELECT stage, status, message, finished_at >= started_at FROM meta.run_stage "
                              "WHERE run_id = %s", (run_id,)).fetchall()
        assert len(stages) == len(STAGES) and all(s[3] for s in stages)
        assert conn.execute("SELECT count(*) FROM meta.run_input WHERE run_id = %s", (run_id,)).fetchone()[0] >= 2
        assert conn.execute("SELECT run_id FROM meta.v_current_run").fetchone()[0] == run_id
        conn.execute("INSERT INTO results.element (run_id, element_type, element_id, ss_from, ss_to, kv, commissioning_year) "
                     "VALUES (%s, 'line', 'L-KAW-MUT-132-1', 'KAW', 'MUT', 132, 2003), "
                     "(%s, 'line', 'L-KAW-KNO-132-1', 'KAW', 'KNO', 132, NULL), "
                     "(%s, 'trafo', 'T-KAW-1', 'KAW', 'KAW', 132, NULL)", (run_id, run_id, run_id))
        conn.commit()
        geo = {r[0]: r[1:] for r in conn.execute(
            "SELECT element_id, geom_source, geojson->>'type', run_id FROM api.v_elements").fetchall()}
        assert geo == {"L-KAW-MUT-132-1": ("gis", "LineString", run_id), "L-KAW-KNO-132-1": ("straight", "LineString", run_id),
                       "T-KAW-1": ("point", "Point", run_id)}   # no zero-length line for a transformer


def test_failed_stage_does_not_stop_the_run(migrated_db, monkeypatch):
    from engine.cli import run_pipeline
    stub_stages(monkeypatch, failing={"losses"})
    run_id = run_pipeline(["network", "losses", "reconciliation", "incidents"], url=migrated_db)
    with psycopg.connect(migrated_db) as conn:
        got = dict(conn.execute("SELECT stage, status FROM meta.run_stage WHERE run_id = %s", (run_id,)).fetchall())
        assert got == {"network": "ok", "losses": "failed", "reconciliation": "skipped", "incidents": "ok"}
        assert conn.execute("SELECT status FROM meta.run WHERE run_id = %s", (run_id,)).fetchone()[0] == "partial"
        # a partial run is not current unless pinned; the pinned run stays current
        assert conn.execute("SELECT run_id FROM meta.v_current_run").fetchone()[0] != run_id


def test_api_role_reads_views_only(migrated_db, ro_url_for):
    ro = ro_url_for(migrated_db)
    with psycopg.connect(ro) as conn:
        for view in ("v_provenance", "v_runs", "v_months", "v_import_batches", "v_import_issues", "v_substations", "v_elements"):
            conn.execute(f"SELECT * FROM api.{view} LIMIT 1").fetchall()
        months = [r[0] for r in conn.execute("SELECT month FROM api.v_months ORDER BY month")]
        assert months[0] == "2025-09" and months[-1] == "2030" and len(months) == 14
        assert conn.execute("SELECT count(*) FROM api.v_substations").fetchone()[0] == 15
    for statement in ("SELECT * FROM meta.run", "SELECT * FROM ts.ncc_system_monthly",
                      "INSERT INTO meta.settings VALUES ('x', 'y')", "CREATE TABLE api.x (a int)",
                      "CREATE TABLE public.x (a int)", "DELETE FROM api.v_runs"):
        with psycopg.connect(ro) as conn:
            with pytest.raises(psycopg.Error):
                conn.execute(statement)


def test_3d_gis_and_windows_csv_load(migrated_db, tmp_path):
    """Review fixes: Z coordinates (KML, PointZ shapefiles) and Windows-1252 CSV used to fail the whole load."""
    import geopandas as gpd
    from shapely.geometry import LineString
    refresh_registers(migrated_db)
    folder = tmp_path / "synthetic" / "gis"
    folder.mkdir(parents=True)
    name = "SYNTHETIC_circuits_3d.geojson"
    gdf = gpd.GeoDataFrame({"circuit_id": ["C9"], "model_branch_id": ["L-KAW-LUG-132-1"], "from_substation": ["Kawanda S.S."],
                            "to_substation": ["Lugogo"], "kv": [132], "status": ["existing"]},
                           geometry=[LineString([(32.535, 0.417, 1180.0), (32.601, 0.329, 1190.0)])], crs="EPSG:4326")
    gdf.to_file(folder / name, driver="GeoJSON")
    write_manifest(folder, "gis", "T02", "synthetic", [(name, "circuits")])
    gis = load_folder(folder, url=migrated_db, env={})
    assert gis.status == "ok" and gis.rows_loaded == 1, gis.message

    scada = tmp_path / "synthetic" / "scada"
    scada.mkdir(parents=True)
    csv_name = "SYNTHETIC_scada_2026-04.csv"
    (scada / csv_name).write_bytes("timestamp;point_id;value;unit;quality\n"
                                   "12/04/2026 20:00;KAW.T1.\xb0C;61.5;MW;good\n"
                                   "12/04/2026 21:00;KAW.T1.\xb0C;61,5;MW;good\n".encode("cp1252"))
    write_manifest(scada, "scada", "T04", "synthetic", [(csv_name, "hourly_data")])
    result = load_folder(scada, url=migrated_db, env={})
    # the decimal-comma row is rejected, never read as 615
    assert (result.rows_read, result.rows_loaded, result.status) == (2, 1, "partial"), result.message
    with psycopg.connect(migrated_db) as conn:
        dims = conn.execute("SELECT ST_NDims(geom), from_substation_code FROM ts.gis_circuit WHERE circuit_id = 'C9'").fetchone()
        assert dims == (2, "KAW")
        point, value = conn.execute("SELECT point_id, value FROM ts.scada_hourly WHERE batch_id = %s",
                                    (result.batch_id,)).fetchone()
        assert (point, value) == ("KAW.T1.°C", 61.5)


def test_bad_folder_does_not_stop_the_other_loads(migrated_db, tmp_path):
    """A corrupt workbook or a broken manifest fails its own batch; load_root carries on."""
    root = tmp_path / "real"
    broken = root / "ncc_monthly"
    broken.mkdir(parents=True)
    (broken / "T03.xlsx").write_bytes(b"password-protected or corrupt")
    write_manifest(broken, "ncc_monthly", "T03", "real", [("T03.xlsx", "")])
    bad_toml = root / "commercial"
    bad_toml.mkdir()
    (bad_toml / "manifest.toml").write_text("dataset = \n")
    good = root / "growth"
    good.mkdir()
    shutil.copy(ROOT / "templates" / "T10_growth.xlsx", good / "T10_growth.xlsx")
    write_manifest(good, "growth", "T10", "real", [("T10_growth.xlsx", "")])
    results = {r.dataset: r for r in load_root(root, url=migrated_db)}
    assert results["ncc_monthly"].status == "failed" and "cannot be opened" in results["ncc_monthly"].message
    assert results["commercial"].status == "failed" and results["commercial"].batch_id is None
    assert results["growth"].status == "ok"


def test_context_reads_and_writes_results(migrated_db):
    """ctx.write stamps run_id and copes with the quoted table name results."case"."""
    import pandas as pd
    from engine.context import RunContext
    with psycopg.connect(migrated_db) as conn:
        run_id = conn.execute("INSERT INTO meta.run (status) VALUES ('running') RETURNING run_id").fetchone()[0]
        conn.commit()
    ctx = RunContext(run_id=run_id, cfg={}, url=migrated_db)
    frame = pd.DataFrame([{"case_key": "2026-03|WD|20", "kind": "hour", "month": date(2026, 3, 1), "day_type": "WD",
                           "hour": 20, "weight_h": 22.0, "total_load_mw": float("nan"), "converged": True}])
    assert ctx.write("case", frame) == 1
    got = ctx.table("results.case")
    assert len(got) == 1 and got["run_id"].iloc[0] == run_id and got["total_load_mw"].isna().all()
    with pytest.raises(ValueError):
        ctx.write("meta.run", frame)
