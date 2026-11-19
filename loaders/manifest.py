"""Read and check data/<root>/<dataset>/manifest.toml (contracts section 8).

The manifest says what a delivery is, who sent it, how trustworthy it is (provenance) and
the sha256 of every file, so a file changed after receipt is refused. Synthetic data is
marked twice, in the manifest and in the files themselves, so it can never pass for real:
  - xlsx files carry the workbook keyword 'gridatlas-synthetic';
  - csv and vector files have names starting with 'SYNTHETIC_'.
"""
from __future__ import annotations

import hashlib
import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from engine.provenance import LEVELS

SYNTHETIC_KEYWORD = "gridatlas-synthetic"
SYNTHETIC_PREFIX = "SYNTHETIC_"
ROOTS = ("synthetic", "real", "open")


class ManifestError(ValueError):
    """The delivery cannot be loaded as described (missing file, changed file, bad provenance)."""


@dataclass(frozen=True)
class FileEntry:
    """One [[files]] entry."""

    path: str
    sha256: str = ""
    sheet: str = ""          # for csv and vector files: the spec sheet they fill
    layer: str = ""          # for open layers: the gis.layer_feature layer name
    name_field: str = ""     # for open layers: which attribute holds the feature name


@dataclass(frozen=True)
class Manifest:
    """A parsed manifest.toml plus where it was found."""

    folder: Path
    dataset: str
    template: str
    provenance: str
    received_from: str = ""
    received_on: date | None = None
    adapter: str = "template"
    files: tuple[FileEntry, ...] = field(default_factory=tuple)

    @property
    def root(self) -> str:
        """The data/ sub-folder the delivery sits in: synthetic, real or open."""
        return root_of(self.folder)

    @property
    def is_layers(self) -> bool:
        """True for open context layers (every file names a layer)."""
        return bool(self.files) and all(f.layer for f in self.files)

    def files_json(self) -> list[dict[str, Any]]:
        """The file list for meta.import_batch.files."""
        return [{k: v for k, v in (("path", f.path), ("sha256", f.sha256), ("sheet", f.sheet), ("layer", f.layer)) if v}
                for f in self.files]


def root_of(folder: Path) -> str:
    """The first of synthetic/real/open found in the folder's path (nearest first)."""
    for part in reversed(Path(folder).resolve().parts):
        if part in ROOTS:
            return part
    return ""


def parse_manifest(raw: dict[str, Any], folder: Path) -> Manifest:
    """Build a Manifest from the parsed TOML, checking the required fields."""
    missing = [k for k in ("dataset", "provenance", "files") if k not in raw]
    if missing:
        raise ManifestError(f"{folder}/manifest.toml is missing: {', '.join(missing)}")
    provenance = str(raw["provenance"]).strip().lower()
    if provenance not in LEVELS:
        raise ManifestError(f"provenance must be one of {', '.join(LEVELS)}, not {raw['provenance']!r}")
    received_on = raw.get("received_on")
    if isinstance(received_on, str):
        received_on = date.fromisoformat(received_on)
    files = tuple(
        FileEntry(path=str(f["path"]), sha256=str(f.get("sha256", "")).lower(), sheet=str(f.get("sheet", "")),
                  layer=str(f.get("layer", "")), name_field=str(f.get("name_field", "")))
        for f in raw["files"])
    return Manifest(folder=folder, dataset=str(raw["dataset"]), template=str(raw.get("template", "")),
                    provenance=provenance, received_from=str(raw.get("received_from", "")),
                    received_on=received_on, adapter=str(raw.get("adapter", "template")), files=files)


def read_manifest(folder: Path) -> Manifest:
    """Read folder/manifest.toml."""
    path = Path(folder) / "manifest.toml"
    if not path.exists():
        raise ManifestError(f"no manifest.toml in {folder}")
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"{path} is not valid TOML: {exc}") from None
    try:
        return parse_manifest(raw, Path(folder))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ManifestError):
            raise
        raise ManifestError(f"{path}: {type(exc).__name__}: {exc} (each [[files]] needs a path)") from None


def sha256_file(path: Path) -> str:
    """The sha256 of a file, read in 1 MB blocks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_files(manifest: Manifest) -> list[str]:
    """Check every listed file exists and matches its sha256. Returns problems (empty = fine)."""
    problems = []
    folder = manifest.folder.resolve()
    for entry in manifest.files:
        path = manifest.folder / entry.path
        if not path.resolve().is_relative_to(folder):
            # '../../somewhere' or an absolute path: a manifest only describes its own folder.
            problems.append(f"{entry.path}: outside the dataset folder; refused")
        elif not path.exists():
            problems.append(f"{entry.path}: listed in the manifest but not found")
        elif not entry.sha256:
            problems.append(f"{entry.path}: no sha256 in the manifest")
        elif sha256_file(path) != entry.sha256:
            problems.append(f"{entry.path}: sha256 does not match the manifest (file changed after receipt?)")
    return problems


def unlisted_files(manifest: Manifest) -> list[str]:
    """Files in the folder that the manifest does not list (they are not loaded)."""
    listed = {Path(f.path).as_posix() for f in manifest.files}
    out = []
    for path in sorted(manifest.folder.rglob("*")):
        rel = path.relative_to(manifest.folder).as_posix()
        if path.is_file() and rel != "manifest.toml" and rel not in listed and not path.name.startswith("."):
            out.append(rel)
    return out


def xlsx_is_synthetic(path: Path) -> bool:
    """True when the workbook's keywords include 'gridatlas-synthetic'."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    try:
        return SYNTHETIC_KEYWORD in (wb.properties.keywords or "")
    finally:
        wb.close()


def file_is_synthetic(path: Path) -> bool:
    """Whether a file carries the synthetic marker for its type."""
    if Path(path).suffix.lower() in (".xlsx", ".xlsm"):
        return xlsx_is_synthetic(path)
    return Path(path).name.startswith(SYNTHETIC_PREFIX)


def check_provenance(manifest: Manifest, env: dict[str, str] | None = None) -> list[str]:
    """Problems with the delivery's provenance (empty = fine).

    - synthetic data is never loaded from data/real;
    - on the server (ATLAS_ENV=server) synthetic loads need ALLOW_SYNTHETIC=1;
    - the files' synthetic markers must agree with the manifest, both ways.
    """
    env = dict(os.environ) if env is None else env
    problems = []
    synthetic = manifest.provenance == "synthetic"
    if synthetic and manifest.root == "real":
        problems.append("provenance is synthetic but the folder is under data/real")
    if synthetic and env.get("ATLAS_ENV") == "server" and env.get("ALLOW_SYNTHETIC") != "1":
        problems.append("synthetic data is refused on the server (set ALLOW_SYNTHETIC=1 to override)")
    folder = manifest.folder.resolve()
    for entry in manifest.files:
        path = manifest.folder / entry.path
        if not path.exists() or not path.resolve().is_relative_to(folder):
            continue   # verify_files reports these
        try:
            marked = file_is_synthetic(path)
        except Exception as exc:  # a corrupt or password-protected workbook
            problems.append(f"{entry.path}: cannot be opened ({type(exc).__name__}: {exc})")
            continue
        if synthetic and not marked:
            problems.append(f"{entry.path}: provenance is synthetic but the file has no synthetic marker")
        if marked and not synthetic:
            problems.append(f"{entry.path}: the file is marked synthetic but the manifest says {manifest.provenance}")
    return problems
