"""truth.json records the planted outcomes, and the files agree with it."""
from __future__ import annotations

import openpyxl
import pytest

MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12"] + [f"2026-{m:02d}" for m in range(1, 10)]
CENTRAL_PLANTS = ("NMVT", "KBSS", "NKGS", "KAPS")


def sheet_rows(path, name) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True)
    rows = list(wb[name].iter_rows(values_only=True))
    return [dict(zip(rows[0], r)) for r in rows[1:] if any(v is not None for v in r)]


def test_truth_has_the_planted_outcomes(truth):
    assert truth["study_months"] == MONTHS
    rec = truth["reconciliation"]
    assert rec["expected_gate"] == {"n_months": 13, "n_pass": 11, "n_explained": 2, "n_unexplained": 0,
                                    "gate_passed": True}
    assert set(rec["planted"]) == {"2026-02", "2025-12"}
    assert set(rec["months"]) == set(MONTHS)
    for key in ("n1", "radial", "kawanda", "scada", "operations", "dirty"):
        assert key in truth
    assert truth["scada"]["missing_months"] == ["2026-01", "2026-06"]
    assert truth["scada"]["full_months"] == ["2026-07", "2026-08", "2026-09"]


def test_reconciliation_design(truth):
    """Normal months: reported loss within 2 % of truth and the expected engine gap well inside 10 %.
    Planted months: clearly outside 10 %."""
    months = truth["reconciliation"]["months"]
    n_pass = 0
    for m, r in months.items():
        if r["planted"]:
            assert abs(r["expected_gap_pct"]) > 12, m
            continue
        assert abs(r["reported_vs_truth_pct"]) <= 2.0 + 1e-6, m
        assert abs(r["expected_gap_pct"]) <= 6.5, m
        assert abs(r["engine_emulated_vs_truth_pct"]) <= 8, m
        n_pass += 1
    assert n_pass == 11
    assert months["2026-02"]["planted"] == "meter_error"
    assert months["2025-12"]["planted"] == "estimated_boundary"
    assert 13 < months["2026-02"]["reported_vs_truth_pct"] < 17


def test_n1_planted_overloads(truth):
    n1 = truth["n1"]
    # The month of the study-period Central peak, and most others, show the KAW-MUT overload.
    peak_month = truth["ncc"]["central_peak_at"][:7]
    assert peak_month in n1["months_kaw_mut_overload"]
    assert len(n1["months_kaw_mut_overload"]) >= 6
    for m in n1["months_kaw_mut_overload"]:
        assert n1["by_month"][m]["trips"]["L-KAW-MUT-132-1"]["post_pct"] > 100
    assert "2026-09" in n1["months_kaw_mut_overload"]
    if truth["network_variant"] == "base":
        assert "2026-09" in n1["months_kaw_trafo_overload"]
        assert truth["kawanda"]["expected_binding_hypothesis"] == "H1_transformers"
    elif truth["network_variant"] == "line_bound":
        assert truth["kawanda"]["expected_binding_hypothesis"] == "H2_lines"


def test_kap_is_radial(truth):
    for m, mw in truth["radial"]["islanded_mw_by_month"].items():
        assert mw == pytest.approx(truth["n1"]["by_month"][m]["kap_load_mw"], rel=1e-3), m
        assert mw > 10


def test_boundary_balance_from_the_files(syn_root, truth, clean_files):
    """L_met from T03 (boundary meters + Central plants - BSP deliveries) equals the reported loss in truth.json."""
    path = syn_root / "ncc_monthly" / "SYNTHETIC_T03_ncc_monthly.xlsx"
    meters = sheet_rows(path, "boundary_meters")
    gens = sheet_rows(path, "generation_monthly")
    subs = sheet_rows(path, "substation_monthly")
    central_plants = {truth["names"]["ncc_plant_names"][c] for c in CENTRAL_PLANTS}
    for m in MONTHS:
        imp = sum(r["energy_mwh"] for r in meters if r["month"] == m and r["direction"] == "import")
        exp = sum(r["energy_mwh"] for r in meters if r["month"] == m and r["direction"] == "export")
        plants = sum(r["sent_out_mwh"] for r in gens if r["month"] == m and r["plant"] in central_plants)
        deliv = sum(r["energy_mwh"] for r in subs if r["month"] == m)
        loss = imp - exp + plants - deliv
        want = truth["reconciliation"]["months"][m]["reported_loss_mwh"]
        assert loss == pytest.approx(want, rel=2e-3, abs=2.0), m


def test_t11_explains_the_planted_months(syn_root):
    rows = sheet_rows(syn_root / "recon_explanations" / "SYNTHETIC_T11_recon_explanations.xlsx", "explanations")
    by_month = {r["month"]: r for r in rows}
    assert set(by_month) == {"2025-12", "2026-02"}
    assert by_month["2026-02"]["cause_code"] == "meter_error"
    for r in rows:
        assert r["basis"] == "central_boundary" and r["reviewed_by"], "EXPLAINED needs a reviewer"


def test_operations_plants(syn_root, truth):
    path = syn_root / "ncc_operations" / "SYNTHETIC_T05_ncc_operations.xlsx"
    cons = sheet_rows(path, "constraints")
    assert cons[0]["constraint_id"] == "KAW-1"
    curt = sheet_rows(path, "curtailments")
    refs = {r["customer_ref"] for r in curt if r["reason"] == "kawanda_constraint"}
    assert refs == {"DC-1", "DC-2"}
    assert any(r["reason"] == "generation_shortfall" for r in curt)
    deferred = sheet_rows(path, "deferred_connections")
    assert len(deferred) == 2 and all(r["requested_mw"] == 20 for r in deferred)
    events = sheet_rows(path, "events")
    outage = [e for e in events if e["event_type"] == "planned_outage"]
    assert outage and outage[0]["element_ref"] == "L-KAW-KNO-132-1"
    assert outage[0]["start_at"].startswith("2026-04")
    assert sum(1 for e in events if e["constraint_related"] == "Y") >= 3
    months = {e["start_at"][:7] for e in events if e["start_at"]}
    assert len(months) >= 6, "events spread over the 13 months"


def test_projects_include_kawanda_relief(syn_root):
    rows = sheet_rows(syn_root / "projects_and_loads" / "SYNTHETIC_T08_projects_and_loads.xlsx", "projects")
    relief = [r for r in rows if r["relief_for"] == "KAW"]
    assert len(relief) == 1 and relief[0]["model_ref"] == "T-KAW-3" and relief[0]["cod"] == "2027-06"
    assert any(r["model_ref"] == "L-KAW-KNO-132-2" and r["cod"].startswith("2028") for r in rows)


def test_growth_and_sites(syn_root):
    g = sheet_rows(syn_root / "growth" / "SYNTHETIC_T10_growth.xlsx", "growth_rates")
    assert {(r["scenario"], r["rate_pct_per_yr"]) for r in g} == {("low", 5.0), ("base", 7.0), ("high", 9.0)}
    s = sheet_rows(syn_root / "sites" / "SYNTHETIC_T09_sites.xlsx", "sites")
    assert len(s) == 10
