"""Stage list, selection and dependencies (engine/stages)."""
import pytest

from engine.cli import final_status
from engine.stages import STAGES, blocked_by, load_stage, select_stages


def test_order_and_selection():
    assert STAGES[0] == "network" and STAGES[-1] == "incidents" and len(STAGES) == 10
    assert select_stages("losses,network") == ["network", "losses"]
    assert select_stages(None) == list(STAGES)
    with pytest.raises(ValueError):
        select_stages("network,nonsense")


def test_every_stage_module_has_run():
    for name in STAGES:
        assert callable(load_stage(name).run)


def test_dependencies():
    assert blocked_by("reconciliation", {"losses"}) == ["losses"]
    assert blocked_by("incidents", {"network"}) == []


def test_final_status():
    assert final_status({"network": "ok", "losses": "skipped"}) == "ok"
    assert final_status({"network": "ok", "losses": "failed"}) == "partial"
    assert final_status({"network": "failed", "losses": "skipped"}) == "failed"
