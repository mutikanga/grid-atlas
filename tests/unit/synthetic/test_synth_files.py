"""Every generated synthetic file matches its template spec, and every manifest verifies."""
from __future__ import annotations

import csv
import hashlib
import json
import tomllib
from pathlib import Path

import openpyxl
import pytest

from synth_spec_check import check_rows

DATASETS = ["network_model", "gis", "ncc_monthly", "scada", "ncc_operations", "commercial", "uedcl_feeders",
            "projects_and_loads", "sites", "growth", "recon_explanations", "handbuilt_network", "planning_studies"]
GEOMETRY = {"Point": {"Point"}, "LineString": {"LineString"}, "Polygon": {"Polygon"},
            "MultiPolygon": {"MultiPolygon", "Polygon"}}


def manifest(folder: Path) -> dict:
    with (folder / "manifest.toml").open("rb") as fh:
        return tomllib.load(fh)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_spec_has_a_dataset_folder(syn_root, specs):
    assert sorted(specs) == sorted(DATASETS)
    for slug in specs:
        assert (syn_root / slug / "manifest.toml").exists(), slug


@pytest.mark.parametrize("slug", DATASETS + ["open_layers"])
def test_manifest_verifies(syn_root, slug):
    folder = syn_root / slug
    m = manifest(folder)
    assert m["provenance"] == "synthetic"
    assert m["received_from"] == "engine/synthetic"
    assert str(m["received_on"]) == "2026-11-01"
    assert m["dataset"] == slug
    listed = {f["path"] for f in m["files"]}
    on_disk = {p.name for p in folder.iterdir() if p.name != "manifest.toml"}
    assert listed == on_disk, "every file is listed, and nothing else is in the folder"
    for f in m["files"]:
        assert f["path"].startswith("SYNTHETIC_")
        assert sha(folder / f["path"]) == f["sha256"], f["path"]
        if slug == "open_layers":
            assert f["layer"] and f["name_field"] == "name"


@pytest.mark.parametrize("slug", DATASETS)
def test_workbook_matches_spec(syn_root, specs, clean_files, slug):
    spec = specs[slug]
    folder = syn_root / slug
    m = manifest(folder)
    assert m["template"] == spec["id"]
    xlsx = folder / f"SYNTHETIC_{spec['id']}_{slug}.xlsx"
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    assert "gridatlas-synthetic" in (wb.properties.keywords or "")
    problems = []
    for sh in spec["sheets"]:
        fmt = sh.get("format", "xlsx")
        if fmt in ("csv", "vector"):
            assert sh["name"] not in wb.sheetnames
            continue
        assert sh["name"] in wb.sheetnames, f"{slug}: missing sheet {sh['name']}"
        rows = list(wb[sh["name"]].iter_rows(values_only=True))
        header = [c for c in rows[0] if c is not None]
        data = [r[: len(header)] for r in rows[1:] if any(v is not None for v in r)]
        if fmt == "qa":
            assert header == ["question_id", "question", "answer"]
            assert [r[0] for r in data] == [q["id"] for q in sh["questions"]]
            assert all(r[2] for r in data), "every question has an answer"
            continue
        if sh.get("required_sheet", True):
            assert data, f"{slug}.{sh['name']} is a required sheet but has no rows"
        problems += check_rows(sh, header, data)
    assert not problems, "\n".join(problems[:20])


def test_scada_csv_files_match_spec(syn_root, specs, clean_files, truth):
    sheet = next(s for s in specs["scada"]["sheets"] if s["name"] == "hourly_data")
    folder = syn_root / "scada"
    files = sorted(p.name for p in folder.glob("SYNTHETIC_scada_*.csv"))
    months = [f[len("SYNTHETIC_scada_"):-4] for f in files]
    for missing in truth["scada"]["missing_months"]:
        assert missing not in months
    assert set(truth["scada"]["full_months"]) <= set(months)
    for name in files:
        with (folder / name).open(newline="") as fh:
            rows = list(csv.reader(fh))
        header, data = rows[0], rows[1:]
        typed = [(r[0], r[1], float(r[2]), r[3], r[4]) for r in data]
        problems = check_rows(sheet, header, typed)
        assert not problems, f"{name}: " + "\n".join(problems[:10])
        days = {r[0][:10] for r in data}
        month = name[len("SYNTHETIC_scada_"):-4]
        if month in truth["scada"]["full_months"]:
            assert len(days) >= 30
        else:
            assert days == set(truth["ncc"]["sample_days"][month]), f"{month}: only the two sample days"


def test_scada_points_cover_the_required_bays(syn_root):
    wb = openpyxl.load_workbook(syn_root / "scada" / "SYNTHETIC_T04_scada.xlsx", read_only=True)
    rows = list(wb["points"].iter_rows(values_only=True))
    head = rows[0]
    pts = [dict(zip(head, r)) for r in rows[1:]]
    kinds = {(p["element_type"], p["winding"], p["quantity"]) for p in pts}
    assert ("line", "na", "P") in kinds and ("line", "na", "Q") in kinds
    assert ("transformer", "lv", "P") in kinds and ("transformer", "lv", "Q") in kinds
    assert ("busbar", "na", "V") in kinds
    refs = {p["element_ref"] for p in pts}
    assert {"L-KAW-MUT-132-1", "L-KAW-MUT-132-2", "T-KAW-1", "T-KAW-2"} <= refs


@pytest.mark.parametrize("slug,sheet_name", [("gis", "substations"), ("gis", "circuits"), ("sites", "site_boundaries")])
def test_vector_layers_match_spec(syn_root, specs, clean_files, slug, sheet_name):
    sheet = next(s for s in specs[slug]["sheets"] if s["name"] == sheet_name)
    path = syn_root / slug / f"SYNTHETIC_{specs[slug]['id']}_{sheet_name}.geojson"
    fc = json.loads(path.read_text(encoding="utf-8"))
    assert fc["features"], "layer has features"
    cols = [c["name"] for c in sheet["columns"]]
    rows = []
    for f in fc["features"]:
        assert f["geometry"]["type"] in GEOMETRY[sheet["geometry"]]
        assert list(f["properties"]) == cols
        rows.append(tuple(f["properties"][c] for c in cols))
        lon, lat = _first_point(f["geometry"]["coordinates"])
        assert 29.4 <= lon <= 35.1 and -1.6 <= lat <= 4.4, "inside Uganda, lon/lat order"
    problems = check_rows(sheet, cols, rows)
    assert not problems, "\n".join(problems[:10])


def _first_point(coords):
    while isinstance(coords[0], list):
        coords = coords[0]
    return coords[0], coords[1]


def test_canonical_ids_in_network_model(syn_root):
    wb = openpyxl.load_workbook(syn_root / "network_model" / "SYNTHETIC_T01_network_model.xlsx", read_only=True)
    lines = [r[1] for r in list(wb["lines"].iter_rows(values_only=True))[1:]]
    trafos = [r[1] for r in list(wb["transformers"].iter_rows(values_only=True))[1:]]
    buses = [r[1] for r in list(wb["buses"].iter_rows(values_only=True))[1:]]
    assert "L-KAW-MUT-132-1" in lines and "L-KAW-MUT-132-2" in lines and "L-KAP-KAW-132-1" in lines
    assert {"T-KAW-1", "T-KAW-2", "T-KAW-3"} <= set(trafos)
    assert "KAW-132-1" in buses and "KAR-400-1" in buses
    for lid in lines:
        _, a, b, kv, ckt = lid.split("-")
        assert a < b, f"{lid}: ends in alphabetical order"
    cases = [r[0] for r in list(wb["cases"].iter_rows(values_only=True))[1:]]
    assert cases == ["SYNTH-PEAK", "SYNTH-2030"]
