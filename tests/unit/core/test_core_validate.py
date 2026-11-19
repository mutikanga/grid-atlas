"""Row validation, without a database (loaders/generic.py validate_row)."""
import pandas as pd

from loaders.generic import batch_status, map_headers, validate_row
from loaders.names import NameResolver, alias_rows
from loaders.spec import load_specs

SPEC = load_specs()["ncc_monthly"]
SHEET = SPEC.sheet("substation_monthly")


def resolver():
    subs = pd.DataFrame({"ss_code": ["KAW", "KNO"], "name": ["Kawanda", "Kampala North"]})
    plants = pd.DataFrame({"plant_code": ["NMVT"], "name": ["Namanve thermal"]})
    aliases = pd.DataFrame({"alias": ["Kampala Nth"], "entity_type": ["substation"], "canonical_id": ["KNO"], "source": ["t"]})
    return NameResolver.from_frames(alias_rows(aliases, subs, plants), subs, plants)


def run(row: dict, sheet=SHEET):
    headers = list(row)
    positions, unknown = map_headers(headers, sheet)
    return validate_row(sheet, positions, list(row.values()), 5, resolver(), SPEC.id), unknown


def good_row(**over):
    row = {"month": "2026-03", "substation": "Kawanda S/S", "energy_mwh": "41,250", "peak_mw": 82.4}
    row.update(over)
    return row


def test_good_row_resolves_name():
    (record, issues, blank), _ = run(good_row())
    assert not blank and record is not None
    assert record["substation_code"] == "KAW" and record["energy_mwh"] == 41250.0
    assert [i for i in issues if i.severity == "error"] == []


def test_alias_resolves():
    (record, _, _), _ = run(good_row(substation="Kampala Nth"))
    assert record["substation_code"] == "KNO"


def test_unresolved_required_name_is_rejected_with_suggestion():
    (record, issues, _), _ = run(good_row(substation="Kawandaa"))
    assert record is None
    issue = next(i for i in issues if i.rule == "unresolved_name")
    assert issue.severity == "error" and issue.suggestion.startswith("KAW")
    assert issue.raw_row["substation"] == "Kawandaa"


def test_type_and_required_errors():
    (record, issues, _), _ = run(good_row(month="March", substation=""))
    assert record is None
    assert {i.rule for i in issues} >= {"type", "required"}


def test_unknown_columns_are_reported_not_loaded():
    (record, _, _), unknown = run(good_row(customer_name="Someone"))
    assert unknown == ["customer_name"]
    assert "customer_name" not in record


def test_blank_row_is_skipped():
    (record, issues, blank), _ = run({"month": None, "substation": "  "})
    assert blank and record is None and issues == []


def test_bounds():
    sheet = SPEC.sheet("system_summary")
    row = {"month": "2026-03", "sent_out_mwh": -5, "delivered_mwh": 1, "losses_mwh": 1, "peak_mw": 9000}
    (record, issues, _), _ = run(row, sheet)
    assert record is None                      # min = 0 on sent_out_mwh is an error
    assert any(i.rule == "min" and i.severity == "error" for i in issues)
    assert any(i.rule == "warn_max" and i.severity == "warning" for i in issues)
    row["sent_out_mwh"] = 5
    (record, issues, _), _ = run(row, sheet)
    assert record is not None and all(i.severity == "warning" for i in issues)


def test_qa_rows():
    sheet = SPEC.sheet("definitions")
    positions, _ = map_headers(["question_id", "question", "answer"], sheet)
    record, issues, blank = validate_row(sheet, positions, ["Q1", "How?", "From meters"], 2, resolver(), "T03")
    assert record == {"template": "T03", "sheet": "definitions", "question_id": "Q1", "question": "How?", "answer": "From meters"}
    _, _, blank = validate_row(sheet, positions, ["Q2", "Why?", None], 3, resolver(), "T03")
    assert blank


def test_batch_status():
    assert batch_status(10, 10, 0) == "ok"
    assert batch_status(0, 0, 0) == "ok"
    assert batch_status(10, 7, 3) == "partial"
    assert batch_status(10, 0, 10) == "failed"
