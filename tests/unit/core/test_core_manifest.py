"""Manifest reading and provenance rules (loaders/manifest.py)."""
import hashlib
from pathlib import Path

import pytest

from loaders.manifest import ManifestError, check_provenance, read_manifest, root_of, verify_files


def make(folder: Path, provenance="synthetic", name="SYNTHETIC_points.csv", sha=None):
    folder.mkdir(parents=True, exist_ok=True)
    data = b"point_id,value\nA,1\n"
    (folder / name).write_bytes(data)
    sha = sha or hashlib.sha256(data).hexdigest()
    (folder / "manifest.toml").write_text(
        f'dataset = "scada"\ntemplate = "T04"\nprovenance = "{provenance}"\nreceived_on = 2026-11-01\n'
        f'[[files]]\npath = "{name}"\nsheet = "hourly_data"\nsha256 = "{sha}"\n')
    return read_manifest(folder)


def test_read_and_verify(tmp_path):
    m = make(tmp_path / "synthetic" / "scada")
    assert m.dataset == "scada" and m.root == "synthetic" and m.files[0].sheet == "hourly_data"
    assert verify_files(m) == []
    assert check_provenance(m, env={}) == []


def test_sha_mismatch(tmp_path):
    m = make(tmp_path / "synthetic" / "scada", sha="0" * 64)
    assert any("sha256 does not match" in p for p in verify_files(m))


def test_synthetic_refused_under_real(tmp_path):
    m = make(tmp_path / "real" / "scada")
    assert any("data/real" in p for p in check_provenance(m, env={}))


def test_synthetic_refused_on_server_unless_allowed(tmp_path):
    m = make(tmp_path / "synthetic" / "scada")
    assert check_provenance(m, env={"ATLAS_ENV": "server"})
    assert check_provenance(m, env={"ATLAS_ENV": "server", "ALLOW_SYNTHETIC": "1"}) == []


def test_markers_must_agree(tmp_path):
    m = make(tmp_path / "synthetic" / "a", name="points.csv")       # synthetic without the prefix
    assert any("no synthetic marker" in p for p in check_provenance(m, env={}))
    m = make(tmp_path / "real" / "b", provenance="real")              # SYNTHETIC_ file claimed as real
    assert any("marked synthetic" in p for p in check_provenance(m, env={}))


def test_bad_provenance(tmp_path):
    with pytest.raises(ManifestError):
        make(tmp_path / "x", provenance="guess")


def test_root_of():
    assert root_of(Path("/data/synthetic/ncc_monthly")) == "synthetic"
    assert root_of(Path("/data/open/layers")) == "open"
