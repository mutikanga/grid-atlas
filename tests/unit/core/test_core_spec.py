"""Reading the template specs (loaders/spec.py)."""
from loaders.spec import load_specs


def test_all_specs_load():
    specs = load_specs()
    assert len(specs) == 13
    assert {s.id for s in specs.values()} == {f"T{i:02d}" for i in range(1, 14)}
    for dataset, spec in specs.items():
        assert dataset == spec.slug
        tables = [sh.table for sh in spec.sheets]
        assert all(t == "qa_answer" or t.split("_")[0] in {"net", "gis", "ncc", "scada", "ops", "com", "uedcl", "plan", "site", "team", "hb"} for t in tables)


def test_ncc_monthly_sheet_details():
    spec = load_specs()["ncc_monthly"]
    sheet = spec.sheet("substation_monthly")
    assert sheet.table == "ncc_substation_monthly"
    assert sheet.key == ("month", "substation", "metering_point")
    sub = sheet.column("substation")
    assert sub.required and sub.resolve_as == "substation" and sub.code_column == "substation_code"
    assert "substation_code" in sheet.db_columns
    assert sheet.db_columns[:2] == ["batch_id", "row_num"]
    qa = spec.sheet("definitions")
    assert qa.format == "qa" and qa.db_key == ["template", "sheet", "question_id"] and len(qa.questions) >= 10


def test_db_columns_match_generated_ddl():
    """Every spec sheet's columns equal the columns templates/ddl.py generates."""
    import importlib.util
    from engine.config import ROOT
    module_spec = importlib.util.spec_from_file_location("ddl", ROOT / "templates" / "ddl.py")
    ddl = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(ddl)
    sql = ddl.render(ddl.load_specs())
    for spec in load_specs().values():
        for sheet in spec.sheets:
            if sheet.format == "qa":
                continue
            block = sql.split(f"CREATE TABLE IF NOT EXISTS ts.{sheet.table} (")[1].split(");")[0]
            cols = [line.strip().split()[0] for line in block.strip().splitlines()]
            assert cols == sheet.db_columns, sheet.table


def test_ss_code_resolves_in_place():
    sheet = load_specs()["handbuilt_network"].sheet("substations")
    col = sheet.column("ss_code")
    assert col.resolve_as == "substation" and col.code_column == "ss_code"
    assert sheet.db_columns.count("ss_code") == 1
