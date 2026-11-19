"""Provenance worst-of rule (engine/provenance.py)."""
import pytest

from engine.provenance import LABELS, is_synthetic, label, register_level, worst_of


def test_worst_of():
    assert worst_of(["real", "real"]) == "real"
    assert worst_of(["real", "open"]) == "open"
    assert worst_of(["open", "approximate", "real"]) == "approximate"
    assert worst_of(["real", "synthetic", "approximate"]) == "synthetic"
    assert worst_of([]) == "synthetic"


def test_unknown_level():
    with pytest.raises(ValueError):
        worst_of(["real", "guess"])


def test_labels():
    assert label("synthetic") == "SYNTHETIC: NOT UETCL DATA"
    assert label("approximate") == "APPROXIMATE: HAND-BUILT OR STANDARD-SHAPE INPUTS"
    assert label("real") == "TRAINEE SHOWCASE: NOT OFFICIAL UETCL FIGURES"
    assert set(LABELS) == {"synthetic", "approximate", "open", "real"}
    assert is_synthetic("synthetic") and not is_synthetic("real")


def test_register_level():
    assert register_level(["approximate, synthetic default, replace from GIS"]) == "approximate"
    assert register_level(["Planning GIS 2026-11", "UETCL asset register"]) == "real"


def test_run_provenance_includes_registers():
    from engine.cli import run_provenance
    level, detail = run_provenance([{"batch_id": 1, "dataset": "ncc_monthly", "provenance": "real"}], ["approximate default"])
    assert level == "approximate" and detail["registers"] == "approximate"
    level, detail = run_provenance([{"batch_id": 1, "dataset": "ncc_monthly", "provenance": "synthetic"},
                                    {"batch_id": 2, "dataset": "gis", "provenance": "real"}], ["GIS"])
    assert level == "synthetic" and detail["synthetic_inputs"] == ["ncc_monthly"]
    assert run_provenance([], ["GIS"])[0] == "synthetic"
