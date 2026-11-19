"""Engine configuration and project paths.

Each owner keeps its settings in its own file, config/engine/<owner>.toml. They are merged
into one dict keyed by file stem, so cfg["losses"]["r_temp_c"] comes from
config/engine/losses.toml. Keeping one file per owner means parallel work never edits the
same file.
"""
from __future__ import annotations

import hashlib
import json
import os
import tomllib
from datetime import date, datetime
from pathlib import Path
from typing import Any

# The project folder (/app inside the containers).
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
ENGINE_CONFIG_DIR = CONFIG_DIR / "engine"
SPEC_DIR = ROOT / "templates" / "spec"
MIGRATIONS_DIR = ROOT / "db" / "migrations"


def data_dir() -> Path:
    """The data folder: $ATLAS_DATA_DIR, else /data in the containers, else ./data.

    docker-compose mounts ./data at /data in the worker, while code lives at /app, so the
    data folder is not always ROOT/data.
    """
    env = os.environ.get("ATLAS_DATA_DIR")
    if env:
        return Path(env)
    if Path("/data").is_dir():
        return Path("/data")
    return ROOT / "data"


def load_config(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read every config/engine/*.toml into {file stem: settings}."""
    directory = directory or ENGINE_CONFIG_DIR
    cfg: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.toml")):
        with path.open("rb") as fh:
            cfg[path.stem] = tomllib.load(fh)
    return cfg


def _json_default(value: Any) -> str:
    """Let json.dumps handle the dates and times that TOML can hold."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def config_json(cfg: dict[str, Any]) -> str:
    """The config as canonical JSON (sorted keys), for meta.run.config and its hash."""
    return json.dumps(cfg, sort_keys=True, default=_json_default)


def config_sha256(cfg: dict[str, Any]) -> str:
    """A fingerprint of the config, stored with each run so results can be traced."""
    return hashlib.sha256(config_json(cfg).encode()).hexdigest()


def code_version() -> str:
    """VERSION (if present) plus a short hash of the mounted Python code.

    Code is mounted, not baked into the image, so the hash tells which code made a run.
    """
    version_file = ROOT / "VERSION"
    version = version_file.read_text().strip() if version_file.exists() else "dev"
    digest = hashlib.sha256()
    for folder in ("engine", "loaders", "api"):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return f"{version}+{digest.hexdigest()[:12]}"
