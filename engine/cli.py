"""Command line for the worker: python -m engine.cli <command>.

  worker                 wait for the database, migrate, bootstrap if asked, then idle
  migrate                apply db/migrations
  templates              rebuild the workbooks and the ts DDL, then migrate
  synth [--variant base|line_bound|dirty] [--seed 42]
                         generate data/synthetic (engine/synthetic, owner F5)
  load [--root data/synthetic] [--dataset X]
                         load dataset folders into ts.* (and the registers into ref.*)
  run [--stages a,b] [--pin]
                         run the analysis stages and record the run
  pin RUN_ID             show this run on every page
  scratch NAME           create database gridatlas_<name>, migrate, load data/synthetic,
                         print its DATABASE_URL (for testing in isolation)
  report                 a short text summary of the current run
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from engine import db, provenance
from engine.config import ROOT, code_version, config_json, config_sha256, data_dir, load_config
from engine.context import RunContext
from engine.migrate import MigrationError, migrate
from engine.stages import STAGES, blocked_by, load_stage, select_stages

log = logging.getLogger("atlas")
READY_FILE = Path("/tmp/atlas-worker-ready")


# ---------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------
def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")


def wait_for_db(url: str | None = None, timeout_s: float = 300.0) -> None:
    """Retry until the database accepts connections (the db container may still be starting)."""
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with db.connect(url) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:
            if time.monotonic() > deadline:
                raise RuntimeError(f"database not reachable after {timeout_s:.0f}s: {exc}") from exc
            log.info("waiting for the database: %s", str(exc).splitlines()[0] if str(exc) else exc)
            time.sleep(2)


def resolve_data_path(text: str) -> Path:
    """'data/synthetic' -> the real folder, whether data/ is ./data or mounted at /data."""
    path = Path(text)
    if path.is_absolute() or path.exists():
        return path
    if path.parts and path.parts[0] == "data":
        return data_dir().joinpath(*path.parts[1:])
    return data_dir() / path


# ---------------------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------------------
def input_batches(url: str | None = None) -> list[dict[str, Any]]:
    """The import batches whose rows are in the database now (ts.* and gis.layer_feature)."""
    tables = db.read_df(
        "SELECT table_schema, table_name FROM information_schema.columns "
        "WHERE column_name = 'batch_id' AND ((table_schema = 'ts') OR (table_schema = 'gis' AND table_name = 'layer_feature'))",
        url=url)
    if tables.empty:
        return []
    union = " UNION ".join(
        f'SELECT DISTINCT batch_id FROM "{r.table_schema}"."{r.table_name}"' for r in tables.itertuples())
    frame = db.read_df(
        f"SELECT b.batch_id, b.dataset, b.provenance, b.root, b.status FROM meta.import_batch b "
        f"WHERE b.batch_id IN ({union}) ORDER BY b.batch_id", url=url)
    return frame.to_dict("records")


def run_provenance(batches: list[dict[str, Any]], register_sources: list[str]) -> tuple[str, dict[str, Any]]:
    """Worst-of level over the input batches and the config registers, with the detail."""
    registers = provenance.register_level(register_sources)
    # No inputs at all means nothing real stands behind the run: worst_of([]) is synthetic.
    level = provenance.worst_of([b["provenance"] for b in batches] + [registers]) if batches else provenance.worst_of([])
    by_dataset: dict[str, str] = {}
    for b in batches:
        by_dataset[b["dataset"]] = provenance.worst_of([by_dataset.get(b["dataset"], "real"), b["provenance"]])
    detail = {
        "level": level,
        "label": provenance.label(level),
        "datasets": by_dataset,
        "registers": registers,
        "synthetic_inputs": sorted(d for d, lv in by_dataset.items() if lv == "synthetic"),
        "batches": [int(b["batch_id"]) for b in batches],
    }
    return level, detail


def final_status(stage_status: dict[str, str]) -> str:
    """ok if no stage failed; partial if some failed but another succeeded; else failed."""
    values = stage_status.values()
    if "failed" not in values:
        return "ok"
    return "partial" if "ok" in values else "failed"


def run_stage(ctx: RunContext, name: str, failed: set[str]) -> tuple[str, str]:
    """Run one stage and return (status, message)."""
    blockers = blocked_by(name, failed)
    if blockers:
        return "skipped", f"skipped: needs {', '.join(blockers)}, which failed"
    try:
        module = load_stage(name)
        module.run(ctx)
    except Exception as exc:
        ctx.log.exception("stage %s failed", name)
        return "failed", f"{type(exc).__name__}: {exc}"[:2000]
    if getattr(module, "NOT_IMPLEMENTED", False):
        return "skipped", "not implemented"
    return "ok", ""


def run_pipeline(stages: list[str], pin: bool = False, url: str | None = None) -> int:
    """Record a run in meta.run, run the stages in order, and return the run id."""
    from loaders.generic import refresh_registers   # imported here so the CLI starts fast

    cfg = load_config()
    with db.advisory_lock("atlas-job", url=url):
        refresh_registers(url)
        batches = input_batches(url)
        sources = db.read_df("SELECT source FROM ref.substation UNION ALL SELECT source FROM ref.plant", url=url)
        level, detail = run_provenance(batches, [s for s in sources["source"] if s])
        with db.get_engine(url).begin() as conn:
            from sqlalchemy import text
            run_id = conn.execute(text(
                "INSERT INTO meta.run (stages, code_version, config, config_sha256, provenance_level, provenance_detail) "
                "VALUES (:stages, :cv, CAST(:cfg AS jsonb), :sha, :level, CAST(:detail AS jsonb)) RETURNING run_id"),
                {"stages": stages, "cv": code_version(), "cfg": config_json(cfg), "sha": config_sha256(cfg),
                 "level": level, "detail": json.dumps(detail)}).scalar_one()
            for b in batches:
                conn.execute(text("INSERT INTO meta.run_input (run_id, batch_id) VALUES (:r, :b)"),
                             {"r": run_id, "b": int(b["batch_id"])})
        log.info("run %s started: stages %s; provenance %s", run_id, ",".join(stages), level)

        ctx = RunContext(run_id=run_id, cfg=cfg, log=logging.getLogger("atlas.run"), url=url)
        statuses: dict[str, str] = {}
        failed: set[str] = set()
        try:
            for name in stages:
                db.execute("INSERT INTO meta.run_stage (run_id, stage, started_at) VALUES (:r, :s, clock_timestamp())",
                           {"r": run_id, "s": name}, url=url)
                ctx.n_loadflows = ctx.n_failed = 0
                t0 = time.monotonic()
                status, message = run_stage(ctx, name, failed)
                statuses[name] = status
                if status == "failed":
                    failed.add(name)
                db.execute("UPDATE meta.run_stage SET finished_at = clock_timestamp(), status = :st, message = :m, "
                           "n_loadflows = :n, n_failed = :f WHERE run_id = :r AND stage = :s",
                           {"st": status, "m": message or None, "n": ctx.n_loadflows, "f": ctx.n_failed,
                            "r": run_id, "s": name}, url=url)
                log.info("stage %-14s %-7s %6.1fs %s", name, status, time.monotonic() - t0, message)
            status = final_status(statuses)
            message = f"failed stages: {', '.join(sorted(failed))}" if failed else None
        except BaseException as exc:
            status, message = "failed", f"run aborted: {type(exc).__name__}: {exc}"
            db.execute("UPDATE meta.run SET finished_at = clock_timestamp(), status = 'failed', message = :m "
                       "WHERE run_id = :r", {"m": message, "r": run_id}, url=url)
            raise
        db.execute("UPDATE meta.run SET finished_at = clock_timestamp(), status = :st, message = :m WHERE run_id = :r",
                   {"st": status, "m": message, "r": run_id}, url=url)
        if pin:
            pin_run(run_id, url)
        log.info("run %s finished: %s", run_id, status)
        return run_id


def pin_run(run_id: int, url: str | None = None) -> None:
    """Make run_id the current run on every page (meta.settings pinned_run_id)."""
    found = db.read_df("SELECT run_id FROM meta.run WHERE run_id = :r", {"r": int(run_id)}, url=url)
    if found.empty:
        raise SystemExit(f"run {run_id} does not exist")
    db.execute("INSERT INTO meta.settings (key, value) VALUES ('pinned_run_id', :v) "
               "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", {"v": str(int(run_id))}, url=url)
    log.info("pinned run %s", run_id)


# ---------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------
def cmd_migrate(args: argparse.Namespace) -> int:
    summary = migrate()
    print(f"applied: {', '.join(summary['applied']) or 'nothing'}")
    if summary["ts_rebuilt"]:
        print("ts input tables were rebuilt: reload inputs (./atlas load)")
    return 0


def cmd_templates(args: argparse.Namespace) -> int:
    for script in ("templates/build_templates.py", "templates/ddl.py"):
        result = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
        if result.returncode != 0:
            print(f"{script} failed", file=sys.stderr)
            return result.returncode
    return cmd_migrate(args)


def cmd_synth(args: argparse.Namespace) -> int:
    try:
        generate = importlib.import_module("engine.synthetic.generate")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("engine.synthetic"):
            print("the synthetic data generator (engine/synthetic/generate.py) is not built yet")
            return 1
        raise
    result = generate.main(["--variant", args.variant, "--seed", str(args.seed)])
    return int(result or 0)


def cmd_load(args: argparse.Namespace) -> int:
    from loaders.generic import load_root
    root = resolve_data_path(args.root)
    if not root.exists():
        print(f"{root} does not exist (run synth first?)", file=sys.stderr)
        return 1
    with db.advisory_lock("atlas-job"):
        results = load_root(root, args.dataset)
    if not results:
        print(f"no dataset folders with a manifest.toml under {root}")
    for r in results:
        print(f"batch {r.batch_id}: {r.dataset:<20} {r.status:<8} read {r.rows_read}, loaded {r.rows_loaded}, "
              f"rejected {r.rows_rejected}. {r.message}")
    return 1 if any(r.status == "failed" for r in results) else 0


def cmd_run(args: argparse.Namespace) -> int:
    default = load_config().get("core", {}).get("run", {}).get("stages", list(STAGES))
    try:
        stages = select_stages(args.stages, default)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    run_id = run_pipeline(stages, pin=args.pin)
    status = db.read_df("SELECT status FROM meta.run WHERE run_id = :r", {"r": run_id})["status"].iloc[0]
    print(f"run {run_id}: {status}")
    return 0 if status in ("ok", "partial") else 1


def cmd_pin(args: argparse.Namespace) -> int:
    pin_run(args.run_id)
    return 0


def scratch_url(base_url: str, database: str) -> str:
    """base_url pointing at another database on the same server."""
    return make_url(base_url).set(database=database).render_as_string(hide_password=False)


def cmd_scratch(args: argparse.Namespace) -> int:
    if not re.fullmatch(r"[a-z0-9_]{1,40}", args.name):
        print("NAME must be lower-case letters, digits or _", file=sys.stderr)
        return 1
    database = f"gridatlas_{args.name}"
    with db.connect(autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone()
        has_template = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'gridatlas_template'").fetchone()
        if exists:
            print(f"{database} already exists; migrating it")
        else:
            template = "TEMPLATE gridatlas_template" if has_template else ""
            conn.execute(f'CREATE DATABASE "{database}" {template}')
    url = scratch_url(db.database_url(), database)
    migrate(url)
    synthetic = data_dir() / "synthetic"
    if synthetic.exists():
        from loaders.generic import load_root
        for r in load_root(synthetic, url=url):
            print(f"batch {r.batch_id}: {r.dataset:<20} {r.status}")
    else:
        print(f"{synthetic} not found: database migrated but empty")
    print(f"DATABASE_URL={url}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    current = db.read_df("SELECT r.* FROM meta.run r JOIN meta.v_current_run c USING (run_id)")
    if current.empty:
        print("no current run (nothing has run successfully and nothing is pinned)")
        return 0
    r = current.iloc[0]
    print(f"Run {r.run_id}  status {r.status}  provenance {r.provenance_level}: {provenance.label(r.provenance_level or 'synthetic')}")
    print(f"  started {r.started_at:%Y-%m-%d %H:%M}  finished {r.finished_at:%Y-%m-%d %H:%M}  code {r.code_version}"
          if r.finished_at is not None else f"  started {r.started_at:%Y-%m-%d %H:%M} (still running)")
    stages = db.read_df("SELECT stage, status, n_loadflows, n_failed, message, "
                        "extract(epoch FROM finished_at - started_at) AS seconds FROM meta.run_stage "
                        "WHERE run_id = :r ORDER BY started_at", {"r": int(r.run_id)})
    for s in stages.itertuples():
        secs = f"{s.seconds:6.1f}s" if s.seconds == s.seconds and s.seconds is not None else "      "
        print(f"  {s.stage:<15} {s.status:<8} {secs}  load flows {s.n_loadflows} (failed {s.n_failed})  {s.message or ''}")
    inputs = db.read_df("SELECT b.dataset, b.provenance, b.status, b.rows_loaded, b.rows_rejected FROM meta.run_input i "
                        "JOIN meta.import_batch b USING (batch_id) WHERE i.run_id = :r ORDER BY b.dataset", {"r": int(r.run_id)})
    print(f"  inputs: {len(inputs)} batch(es)")
    for b in inputs.itertuples():
        print(f"    {b.dataset:<20} {b.provenance:<11} {b.status:<8} loaded {b.rows_loaded}, rejected {b.rows_rejected}")
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    READY_FILE.unlink(missing_ok=True)
    wait_for_db()
    migrate()
    if os.environ.get("BOOTSTRAP", "none") == "synthetic":
        try:
            n_runs = int(db.read_df("SELECT count(*) AS n FROM meta.run")["n"].iloc[0])
            if n_runs == 0:
                log.info("bootstrap: empty database, building the synthetic demo (synth, load, run --pin)")
                if cmd_synth(argparse.Namespace(variant="base", seed=42)) == 0:
                    cmd_load(argparse.Namespace(root="data/synthetic", dataset=None))
                    cmd_run(argparse.Namespace(stages=None, pin=True))
            else:
                log.info("bootstrap skipped: the database already has %s run(s)", n_runs)
        except Exception:
            # The stack should still come up so the problem can be inspected.
            log.exception("bootstrap failed")
    READY_FILE.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    log.info("worker ready; waiting for jobs (docker compose exec worker python -m engine.cli ...)")
    while not stop.wait(3600):
        pass
    log.info("worker stopping")
    READY_FILE.unlink(missing_ok=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine.cli", description="Grid Atlas worker commands")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("worker", help="wait for the database, migrate, optional bootstrap, idle").set_defaults(func=cmd_worker)
    sub.add_parser("migrate", help="apply db/migrations").set_defaults(func=cmd_migrate)
    sub.add_parser("templates", help="rebuild workbooks and ts DDL, then migrate").set_defaults(func=cmd_templates)
    p = sub.add_parser("synth", help="generate data/synthetic")
    p.add_argument("--variant", default="base", choices=["base", "line_bound", "dirty"])
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_synth)
    p = sub.add_parser("load", help="load dataset folders")
    p.add_argument("--root", default="data/synthetic")
    p.add_argument("--dataset", default=None)
    p.set_defaults(func=cmd_load)
    p = sub.add_parser("run", help="run the analysis stages")
    p.add_argument("--stages", default=None, help=f"comma-separated, from: {','.join(STAGES)}")
    p.add_argument("--pin", action="store_true", help="show this run on every page")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("pin", help="pin a run")
    p.add_argument("run_id", type=int)
    p.set_defaults(func=cmd_pin)
    p = sub.add_parser("scratch", help="create a private database for testing")
    p.add_argument("name")
    p.set_defaults(func=cmd_scratch)
    sub.add_parser("report", help="summary of the current run").set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    try:
        return int(args.func(args) or 0)
    except db.LockBusy as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except MigrationError as exc:
        print(f"migration refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
