"""Generate the synthetic Grid Atlas inputs: every template, in its exact format, under data/synthetic/.

Usage (inside the gridatlas-py image):
    python -m engine.cli synth --variant base|line_bound|dirty --seed 42
or directly:
    python -c "from engine.synthetic.generate import main; main(['--variant','base','--seed','42'])"

What it does, in order:
1. builds the synthetic network and simulates every hour of Sep 2025 - Sep 2026 with the
   truth model (R at 60 C);
2. cuts every template's sheets from that simulation (T01-T13);
3. plants the outcomes the engine must reproduce (see truth.json);
4. for --variant dirty, injects data-quality faults for the loader tests;
5. writes the files and a manifest.toml per dataset, and data/synthetic/truth.json.

The output is deterministic for a given seed and variant, and is written only under
data/synthetic/.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from engine.synthetic import dirty as dirty_mod
from engine.synthetic import out_ncc, out_network, out_other, planted
from engine.synthetic.network import VARIANTS
from engine.synthetic.timeseries import MONTHS
from engine.synthetic.world import (ENGINE_SAFE_PCT, ESTIMATED_METER, ESTIMATED_READING_ERROR, METER_ERROR_METER,
                                    METER_ERROR_SHARE, NCC_PLANT_NAMES, NCC_SS_NAMES, PLANTED_ESTIMATED_MONTH,
                                    PLANTED_METER_ERROR_MONTH, build_world)
from engine.synthetic.writers import (Manifest, ManifestFile, column_names, load_specs, write_geojson, write_manifest,
                                      write_workbook)

log = logging.getLogger("engine.synthetic")
ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "data" / "synthetic"
OPEN_DATASET = "open_layers"
QA_DEFAULT = "SYNTHETIC test answer."


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="synth", description="Write the synthetic inputs under data/synthetic/.")
    p.add_argument("--variant", choices=VARIANTS, default="base")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(OUT_ROOT), help="output folder; must be data/synthetic or inside it")
    return p.parse_args(argv)


def safe_out(path: str) -> Path:
    """Refuse any output folder outside data/synthetic (the generator writes nowhere else)."""
    out = Path(path).resolve()
    if out != OUT_ROOT and OUT_ROOT not in out.parents:
        raise SystemExit(f"refusing to write outside {OUT_ROOT}: {out}")
    return out


def _qa(spec: dict, answers: dict[str, str] | None = None) -> dict[str, dict]:
    """Answers for every qa sheet of a spec (a default answer where none is given)."""
    out = {}
    for sh in spec["sheets"]:
        if sh.get("format") == "qa":
            out[sh["name"]] = {q["id"]: (answers or {}).get(q["id"], QA_DEFAULT) for q in sh["questions"]}
    return out


def build_all(variant: str, seed: int) -> dict:
    """Simulate and assemble every dataset's sheets (no files written yet)."""
    t0 = time.time()
    net_variant = "base" if variant == "dirty" else variant
    w = build_world(net_variant, seed)
    log.info("truth simulation done in %.1f s", time.time() - t0)
    ops, f5 = out_ncc.t05_tables(w)
    t03, f3 = out_ncc.t03_tables(w, ops)
    t01, f1 = out_network.t01_tables(w)
    t12 = out_network.t12_tables(w.nw)
    gis_pts, gis_cct, crosswalk = out_network.t02_features(w.nw, seed)
    t06 = out_other.t06_tables(w, t03)
    t07 = out_other.t07_tables(w, t03, t06)
    t08 = out_other.t08_tables(w)
    t09, site_feats = out_other.t09_tables(w)
    t10 = out_other.t10_tables()
    t11 = out_other.t11_tables(w)
    n1_rows = planted.t13_contingency_rows(w)
    t13 = out_other.t13_tables(w, n1_rows, out_network.asset_age_rows(w.nw))
    points = out_ncc.scada_points(w)
    values = out_ncc.point_values(w, points)
    scada = {m: df for m in MONTHS if (df := out_ncc.scada_month(w, m, points, values)) is not None}
    t04 = {"points": points, "breaker_changes": out_ncc.breaker_rows(ops["events"])}
    log.info("sheets assembled in %.1f s", time.time() - t0)
    n1 = planted.n1_by_month(w)
    sweep = planted.kawanda_sweep(w)
    log.info("planted checks done in %.1f s", time.time() - t0)
    return {
        "world": w, "variant": variant, "seed": seed,
        "sheets": {"network_model": t01, "ncc_monthly": t03, "ncc_operations": ops, "commercial": t06,
                   "uedcl_feeders": t07, "projects_and_loads": t08, "sites": t09, "growth": t10,
                   "recon_explanations": t11, "handbuilt_network": t12, "planning_studies": t13,
                   "gis": {"crosswalk": crosswalk}, "scada": t04},
        "vectors": {"gis": {"substations": gis_pts, "circuits": gis_cct}, "sites": {"site_boundaries": site_feats}},
        "scada_months": scada,
        "facts": {"t01": f1, "t03": f3, "t05": f5, "n1": n1, "kawanda": sweep},
    }


ANSWERS = {
    "ncc_monthly": out_ncc.T03_ANSWERS,
    "scada": out_ncc.T04_ANSWERS,
    "ncc_operations": out_ncc.T05_ANSWERS,
}


def write_all(bundle: dict, out: Path) -> dict[str, list[str]]:
    """Write every dataset folder with its manifest. Returns dataset -> file names."""
    specs = load_specs()
    written: dict[str, list[str]] = {}
    for slug, spec in specs.items():
        folder = out / slug
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        files: list[ManifestFile] = []
        xlsx = f"SYNTHETIC_{spec['id']}_{slug}.xlsx"
        write_workbook(folder / xlsx, spec, bundle["sheets"].get(slug, {}), _qa(spec, ANSWERS.get(slug)))
        files.append(ManifestFile(xlsx))
        for sh in spec["sheets"]:
            fmt = sh.get("format", "xlsx")
            if fmt == "vector":
                feats = bundle["vectors"].get(slug, {}).get(sh["name"])
                if feats is None:
                    continue
                name = f"SYNTHETIC_{spec['id']}_{sh['name']}.geojson"
                types = {c["name"]: c["type"] for c in sh["columns"]}
                write_geojson(folder / name, feats, sh["name"], column_names(sh), types)
                files.append(ManifestFile(name, sheet=sh["name"]))
            elif fmt == "csv" and slug == "scada":
                for month, df in sorted(bundle["scada_months"].items()):
                    name = f"SYNTHETIC_scada_{month}.csv"
                    df[column_names(sh)].to_csv(folder / name, index=False, lineterminator="\n")
                    files.append(ManifestFile(name, sheet=sh["name"]))
        write_manifest(folder, Manifest(dataset=spec["dataset"], template=spec["id"], files=files,
                                        notes="SYNTHETIC data generated by engine/synthetic; not UETCL data"))
        written[slug] = [f.path for f in files]
    # Open context layers (synthetic stand-ins for data/open/layers).
    folder = out / OPEN_DATASET
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    files = []
    for layer, feats in out_other.open_layers().items():
        name = f"SYNTHETIC_{layer}.geojson"
        write_geojson(folder / name, feats, layer)
        files.append(ManifestFile(name, layer=layer, name_field="name"))
    write_manifest(folder, Manifest(dataset=OPEN_DATASET, template="OPEN", adapter="vector", files=files,
                                    notes="SYNTHETIC open context layers (crude shapes); not real boundaries"))
    written[OPEN_DATASET] = [f.path for f in files]
    return written


def truth_document(bundle: dict, injections: list[dict]) -> dict:
    """The expected outcomes for the golden tests (data/synthetic/truth.json)."""
    w = bundle["world"]
    recon = w.recon.drop(columns=["reported_deliveries", "reported_plants"]).copy()
    for c in recon.columns:
        if recon[c].dtype.kind == "f":
            recon[c] = recon[c].round(3)
    rmonths = recon.set_index("month").to_dict(orient="index")
    n_pass = sum(1 for m, r in rmonths.items() if not r["planted"] and abs(r["expected_gap_pct"]) <= 10)
    peak_months = [m for m, r in bundle["facts"]["n1"].items()
                   if r["trips"]["L-KAW-MUT-132-1"]["post_pct"] > 100]
    trafo_months = [m for m, r in bundle["facts"]["n1"].items() if r["trips"]["T-KAW-1"]["post_pct"] > 100]
    return {
        "_comment": "SYNTHETIC: expected outcomes of the planted features, for the golden tests. Not UETCL data.",
        "generator": "engine/synthetic", "seed": bundle["seed"], "variant": bundle["variant"],
        "network_variant": w.variant, "study_months": MONTHS,
        "network": {"n_buses": len(w.nw.buses), "n_lines_existing": int((w.nw.lines.status == "existing").sum()),
                    "n_trafos_existing": int((w.nw.trafos.status == "existing").sum()),
                    "truth_r_temp_c": 60.0, "engine_default_r_temp_c": 50.0,
                    "central_perimeter": "elements with both ends in Central; boundary meters at the Central end of each tie",
                    "boundary_meters": [{"meter_id": m.meter_id, "line_id": m.line_id, "central_end": m.ss, "far_end": m.far}
                                        for m in w.meters],
                    **bundle["facts"]["t01"]},
        "names": {"ncc_substation_variants": NCC_SS_NAMES, "ncc_plant_names": NCC_PLANT_NAMES,
                  "commercial_plant_names": out_other.COMMERCIAL_PLANT_NAMES},
        "reconciliation": {
            "basis": "central_boundary (metered_boundary)",
            "definition": "L_met = sum(boundary imports) - sum(boundary exports) + sum(Central plant sent-out) - sum(BSP deliveries)",
            "tolerance_pct": 10.0,
            "expected_gate": {"n_months": 13, "n_pass": 11, "n_explained": 2, "n_unexplained": 0, "gate_passed": True},
            "planted": {
                PLANTED_METER_ERROR_MONTH: {"kind": "meter_error", "meter_id": METER_ERROR_METER,
                                            "loss_error_share": METER_ERROR_SHARE, "t11_cause_code": "meter_error"},
                PLANTED_ESTIMATED_MONTH: {"kind": "estimated_boundary_reading", "meter_id": ESTIMATED_METER,
                                          "direction": "export", "reading_error": ESTIMATED_READING_ERROR,
                                          "t11_cause_code": "data_gap"},
            },
            "n_pass_by_emulation": n_pass,
            "engine_emulation_note": ("expected_gap_pct uses a miniature of the engine method (R at 50 C, sample days "
                                      f"or full SCADA months, energy-scaled). Normal months are kept within +-{ENGINE_SAFE_PCT} %."),
            "months": rmonths,
        },
        "n1": {"expectation": "At each month's peak hour, tripping L-KAW-MUT-132-1 overloads L-KAW-MUT-132-2 above 100 % "
                              "in the months listed; in the base variant tripping T-KAW-1 overloads T-KAW-2.",
               "months_kaw_mut_overload": peak_months, "months_kaw_trafo_overload": trafo_months,
               "by_month": bundle["facts"]["n1"]},
        "radial": {"trip": "L-KAP-KAW-132-1", "islands": "KAP-132-1, KAP-33-1", "islanded_load": "D-KAP-1",
                   "islanded_mw_by_month": {m: r["radial_islanded_mw"] for m, r in bundle["facts"]["n1"].items()}},
        "kawanda": bundle["facts"]["kawanda"],
        "scada": {"full_months": list(out_ncc.SCADA_FULL_MONTHS), "missing_months": list(out_ncc.SCADA_MISSING_MONTHS),
                  "sample_day_months": [m for m in MONTHS if m not in out_ncc.SCADA_FULL_MONTHS + out_ncc.SCADA_MISSING_MONTHS],
                  "noise": "about 1 % on P/Q (plus 0.05 MW absolute), 0.2 % on kV; about 0.1 % of rows quality 'bad' with value 0",
                  "sign_convention": out_ncc.SIGN},
        "operations": {**bundle["facts"]["t05"], "planned_outage": {"element_ref": "L-KAW-KNO-132-1",
                       "start_at": "2026-04-13 06:00", "end_at": "2026-04-18 06:00", "in_truth_simulation": True}},
        "ncc": bundle["facts"]["t03"],
        "dirty": {"active": bundle["variant"] == "dirty", "injections": injections},
    }


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point. Returns 0 on success."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    args = parse_args(argv)
    out = safe_out(args.out)
    t0 = time.time()
    log.info("synthetic generation: variant=%s seed=%s out=%s", args.variant, args.seed, out)
    bundle = build_all(args.variant, args.seed)
    injections: list[dict] = []
    if args.variant == "dirty":
        injections = dirty_mod.inject(bundle["sheets"], bundle["scada_months"])
    out.mkdir(parents=True, exist_ok=True)
    written = write_all(bundle, out)
    truth = truth_document(bundle, injections)
    (out / "truth.json").write_text(json.dumps(truth, indent=2, default=str) + "\n", encoding="utf-8")
    log.info("wrote %d datasets and truth.json in %.1f s", len(written), time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
