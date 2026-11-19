"""Read templates/spec/*.toml into typed objects.

The specs are the single source of truth for the workbooks, the ts.* tables and the
loader's validation (docs/dev/contracts.md section 3). Which columns hold substation or
plant names is decided by templates/ddl.py, which also creates their <col>_code columns.
"""
from __future__ import annotations

import importlib.util
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from engine.config import ROOT, SPEC_DIR

TYPES = ("text", "int", "number", "month", "date", "datetime", "yn", "enum")
FORMATS = ("xlsx", "csv", "vector", "qa")


@lru_cache(maxsize=1)
def _ddl_module():
    """templates/ddl.py, loaded by path (templates/ is not a package)."""
    path = ROOT / "templates" / "ddl.py"
    module_spec = importlib.util.spec_from_file_location("atlas_templates_ddl", path)
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    return module


def resolvable(column: str) -> str | None:
    """'substation', 'plant' or None: what kind of name a column holds (from templates/ddl.py)."""
    return _ddl_module().resolvable(column)


@dataclass(frozen=True)
class Column:
    """One column of a sheet."""

    name: str
    type: str
    desc: str = ""
    example: Any = ""
    unit: str = ""
    required: bool = False
    enum: tuple[str, ...] = ()
    min: float | None = None
    max: float | None = None
    warn_min: float | None = None
    warn_max: float | None = None

    @property
    def resolve_as(self) -> str | None:
        """'substation' or 'plant' when the column holds a name to map to a code."""
        return resolvable(self.name)

    @property
    def code_column(self) -> str | None:
        """Where the resolved code goes: <name>_code, or the column itself for ss_code."""
        if not self.resolve_as:
            return None
        return self.name if self.name == "ss_code" else f"{self.name}_code"


@dataclass(frozen=True)
class Question:
    id: str
    text: str


@dataclass(frozen=True)
class Sheet:
    """One sheet of a template, which loads into one ts table."""

    name: str
    table: str
    title: str = ""
    format: str = "xlsx"
    grain: str = ""
    key: tuple[str, ...] = ()
    required_sheet: bool = True
    notes: str = ""
    columns: tuple[Column, ...] = ()
    questions: tuple[Question, ...] = ()
    file_pattern: str = ""
    geometry: str = ""

    def column(self, name: str) -> Column | None:
        for col in self.columns:
            if col.name == name:
                return col
        return None

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def db_columns(self) -> list[str]:
        """The ts table's columns in order, as templates/ddl.py creates them."""
        if self.format == "qa":
            return ["batch_id", "row_num", "template", "sheet", "question_id", "question", "answer"]
        cols = ["batch_id", "row_num"]
        for col in self.columns:
            cols.append(col.name)
            if col.code_column and col.code_column != col.name:
                cols.append(col.code_column)
        if self.format == "vector":
            cols.append("geom")
        return cols

    @property
    def db_key(self) -> list[str]:
        """The natural key used to replace rows on reload."""
        if self.format == "qa":
            return ["template", "sheet", "question_id"]
        return list(self.key)


@dataclass(frozen=True)
class Spec:
    """One template (T01 to T13)."""

    id: str
    slug: str
    title: str
    dataset: str
    criticality: str
    sheets: tuple[Sheet, ...] = field(default_factory=tuple)
    path: Path | None = None

    def sheet(self, name: str) -> Sheet | None:
        for s in self.sheets:
            if s.name == name:
                return s
        return None


def _column(raw: dict[str, Any]) -> Column:
    if raw["type"] not in TYPES:
        raise ValueError(f"column {raw['name']}: unknown type {raw['type']!r}")
    return Column(
        name=raw["name"], type=raw["type"], desc=raw.get("desc", ""), example=raw.get("example", ""),
        unit=raw.get("unit", ""), required=bool(raw.get("required", False)),
        enum=tuple(str(v) for v in raw.get("enum", ())),
        min=raw.get("min"), max=raw.get("max"), warn_min=raw.get("warn_min"), warn_max=raw.get("warn_max"),
    )


def _sheet(raw: dict[str, Any]) -> Sheet:
    fmt = raw.get("format", "xlsx")
    if fmt not in FORMATS:
        raise ValueError(f"sheet {raw['name']}: unknown format {fmt!r}")
    return Sheet(
        name=raw["name"], table=raw["table"], title=raw.get("title", ""), format=fmt,
        grain=raw.get("grain", ""), key=tuple(raw.get("key", ())),
        required_sheet=bool(raw.get("required_sheet", True)), notes=raw.get("notes", ""),
        columns=tuple(_column(c) for c in raw.get("columns", ())),
        questions=tuple(Question(q["id"], q["text"]) for q in raw.get("questions", ())),
        file_pattern=raw.get("file_pattern", ""), geometry=raw.get("geometry", ""),
    )


def parse_spec(raw: dict[str, Any], path: Path | None = None) -> Spec:
    """Build a Spec from the parsed TOML dict."""
    return Spec(
        id=raw["id"], slug=raw["slug"], title=raw.get("title", ""),
        dataset=raw.get("dataset", raw["slug"]), criticality=raw.get("criticality", "medium"),
        sheets=tuple(_sheet(s) for s in raw.get("sheets", ())), path=path,
    )


def load_spec(path: Path) -> Spec:
    """Read one spec file."""
    with path.open("rb") as fh:
        return parse_spec(tomllib.load(fh), path)


def load_specs(directory: Path | None = None) -> dict[str, Spec]:
    """All specs keyed by dataset code (which equals the slug)."""
    directory = directory or SPEC_DIR
    specs = [load_spec(p) for p in sorted(directory.glob("T*.toml"))]
    return {s.dataset: s for s in specs}
