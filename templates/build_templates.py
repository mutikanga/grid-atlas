"""Generate the data-request workbooks (templates/T??_<slug>.xlsx) from templates/spec/*.toml.

Each workbook has:
  README      what the data is for, how to send it, and a column guide for every sheet
  <sheets>    row 1 = column names (exactly what the loader reads), data from row 2;
              each header cell carries a note with the unit, description and example;
              enum and Y/N columns get drop-down lists.

Run inside the Python image (needs openpyxl):
    ./atlas templates
or  docker run --rm -v "$PWD":/app -w /app gridatlas-py:dev python templates/build_templates.py
"""
from __future__ import annotations

import sys
import tomllib
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
SPEC_DIR = HERE / "spec"
OUT_DIR = HERE

HEADER_FILL_REQUIRED = PatternFill("solid", fgColor="1F4E79")
HEADER_FILL_OPTIONAL = PatternFill("solid", fgColor="5B7FA6")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
H2_FONT = Font(bold=True, size=12)
BOLD = Font(bold=True)
GREY = Font(italic=True, color="666666")
WRAP = Alignment(wrap_text=True, vertical="top")
VALIDATION_ROWS = 5000

TYPE_HINT = {
    "text": "text",
    "int": "whole number",
    "number": "number",
    "month": "month as YYYY-MM",
    "date": "date as YYYY-MM-DD",
    "datetime": "date-time as YYYY-MM-DD HH:MM (EAT)",
    "yn": "Y or N",
    "enum": "one of the listed values",
}


def _example_text(col: dict) -> str:
    ex = col.get("example", "")
    return "" if ex == "" else str(ex)


def _write_readme(wb: Workbook, spec: dict, spec_file: str) -> None:
    ws = wb.active
    ws.title = "README"
    ws.column_dimensions["A"].width = 26
    for letter in "BCDEF":
        ws.column_dimensions[letter].width = 34
    row = 1
    ws.cell(row, 1, f"{spec['id']}  {spec['title']}").font = TITLE_FONT
    row += 1
    for label, value in (
        ("For", spec["holder"]),
        ("Data period", spec["period"]),
        ("Request number(s)", ", ".join(str(r) for r in spec["requests"]) or "internal"),
        ("Priority", spec["criticality"]),
    ):
        ws.cell(row, 1, label).font = BOLD
        ws.cell(row, 2, value)
        row += 1
    row += 1
    for line in spec["intro"].strip().splitlines():
        cell = ws.cell(row, 1, line)
        if line.isupper() and line.strip():
            cell.font = H2_FONT
        row += 1
    row += 1

    ws.cell(row, 1, "SHEETS IN THIS WORKBOOK").font = H2_FONT
    row += 1
    for i, head in enumerate(("Sheet", "One row is", "Needed?", "How to send", "Notes"), start=1):
        ws.cell(row, i, head).font = BOLD
    row += 1
    for sheet in spec["sheets"]:
        fmt = sheet.get("format", "xlsx")
        how = {
            "xlsx": "fill in this sheet",
            "csv": f"CSV files named {sheet.get('file_pattern', '')}",
            "vector": f"GIS file ({sheet.get('geometry', '')}): GeoPackage, Shapefile with .prj, GeoJSON or KML",
            "qa": "answer in this sheet",
        }[fmt]
        values = (sheet["name"], sheet.get("grain", ""),
                  "yes" if sheet.get("required_sheet", True) else "if available", how, sheet.get("notes", ""))
        for i, v in enumerate(values, start=1):
            ws.cell(row, i, v).alignment = WRAP
        row += 1
    row += 1

    ws.cell(row, 1, "COLUMN GUIDE").font = H2_FONT
    row += 1
    ws.cell(row, 1, "Column names in row 1 of each sheet must not be changed. Extra columns are ignored.").font = GREY
    row += 2
    for sheet in spec["sheets"]:
        if sheet.get("format") == "qa":
            continue
        ws.cell(row, 1, f"Sheet: {sheet['name']}  ({sheet['title']})").font = BOLD
        row += 1
        for i, head in enumerate(("Column", "Description", "Unit / type", "Required", "Example", "Allowed values"), start=1):
            ws.cell(row, i, head).font = BOLD
        row += 1
        for col in sheet["columns"]:
            unit = col.get("unit") or TYPE_HINT[col["type"]]
            values = (col["name"], col["desc"], unit, "yes" if col.get("required") else "",
                      _example_text(col), ", ".join(col.get("enum", [])) if col["type"] == "enum" else "")
            for i, v in enumerate(values, start=1):
                ws.cell(row, i, v).alignment = WRAP
            row += 1
        row += 1
    ws.cell(row, 1, f"Generated from templates/spec/{spec_file} on {date.today():%d %b %Y}. "
                    "Examples use dummy names; they are not estimates of real values.").font = GREY


def _write_sheet(wb: Workbook, sheet: dict) -> None:
    ws = wb.create_sheet(sheet["name"])
    if sheet.get("format") == "qa":
        heads = ("question_id", "question", "answer")
        for i, h in enumerate(heads, start=1):
            c = ws.cell(1, i, h)
            c.font, c.fill = HEADER_FONT, HEADER_FILL_REQUIRED
        ws.column_dimensions["A"].width = 12
        ws.column_dimensions["B"].width = 70
        ws.column_dimensions["C"].width = 70
        for r, q in enumerate(sheet["questions"], start=2):
            ws.cell(r, 1, q["id"])
            ws.cell(r, 2, q["text"]).alignment = WRAP
            ws.cell(r, 3).alignment = WRAP
        ws.freeze_panes = "A2"
        return

    for i, col in enumerate(sheet["columns"], start=1):
        cell = ws.cell(1, i, col["name"])
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL_REQUIRED if col.get("required") else HEADER_FILL_OPTIONAL
        unit = col.get("unit") or TYPE_HINT[col["type"]]
        text = f"{col['desc']}\nUnit/type: {unit}\nRequired: {'yes' if col.get('required') else 'no'}"
        if _example_text(col):
            text += f"\nExample: {_example_text(col)}"
        if col["type"] == "enum":
            text += f"\nAllowed: {', '.join(col['enum'])}"
        cell.comment = Comment(text, "Grid Atlas", width=320, height=140)
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(40, len(col["name"]) + 4))
        allowed = col.get("enum") if col["type"] == "enum" else (["Y", "N"] if col["type"] == "yn" else None)
        if allowed:
            formula = '"' + ",".join(allowed) + '"'
            if len(formula) <= 255:              # Excel's limit for an inline list
                dv = DataValidation(type="list", formula1=formula, allow_blank=True)
                letter = get_column_letter(i)
                dv.add(f"{letter}2:{letter}{VALIDATION_ROWS}")
                ws.add_data_validation(dv)
    ws.freeze_panes = "A2"


def build(spec_path: Path) -> Path:
    spec = tomllib.loads(spec_path.read_text(encoding="utf-8"))
    wb = Workbook()
    _write_readme(wb, spec, spec_path.name)
    for sheet in spec["sheets"]:
        _write_sheet(wb, sheet)
    wb.properties.title = f"{spec['id']} {spec['title']}"
    wb.properties.subject = "Grid Atlas data request template"
    wb.properties.creator = "Grid Atlas team"
    wb.properties.keywords = f"gridatlas-template {spec['id']}"
    out = OUT_DIR / f"{spec['id']}_{spec['slug']}.xlsx"
    wb.save(out)
    return out


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted(SPEC_DIR.glob("T*.toml"))
    for p in paths:
        out = build(p)
        print(f"wrote {out.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
