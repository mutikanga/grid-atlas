"""The table registry: the allow-list of everything the API can show or export.

Each router describes its tables once, with `register(TableSpec(...))` at import time.
The screen (`/api/...` JSON) and the downloads (`/export/<name>.csv|.xlsx`) both read
through this registry, so they always show the same columns, units and decimals.

Only names written here by a developer ever reach SQL. A request can choose a table
by name and give filter values, but the view, the column names and the ORDER BY come
from the spec, and filter values are always bound parameters (see `api/render.py`).

Example (in a router module):

    register(TableSpec(
        name="loss_monthly",
        title="Modelled losses by month",
        view="api.v_loss_monthly",
        columns=[
            Col("month", "Month"),
            Col("loss_mwh", "Losses", "MWh", 0),
            Col("loss_pct", "Losses", "%", 2),
        ],
        filters={"month": "month"},
        order_by="month",
    ))
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A plain lower-case SQL identifier. Anything else is refused at registration time.
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
# Views must live in the api schema: atlas_ro can read nothing else anyway.
_VIEW = re.compile(r"^api\.[a-z_][a-z0-9_]*$")
# One ORDER BY term: a column name with an optional direction.
_ORDER_TERM = re.compile(r"^[a-z_][a-z0-9_]*(\s+(asc|desc))?(\s+nulls\s+(first|last))?$")


@dataclass(frozen=True)
class Col:
    """One column of a table: its view column (`key`), a header label, unit and decimals.

    `decimals=None` means "do not round" (text, dates, ids). Units are display text,
    for example "MW", "MWh", "%", "UGX".
    """

    key: str
    label: str
    unit: str = ""
    decimals: int | None = None


@dataclass(frozen=True)
class TableSpec:
    """A registered table: which view it reads, which columns it shows, which filters it accepts.

    `filters` maps a query-string parameter to a view column, for example
    `{"month": "month", "element": "element_id"}`. Unknown parameters are ignored.
    `order_by` is a comma-separated list of view columns, each optionally `asc`/`desc`.
    """

    name: str
    title: str
    view: str
    columns: tuple[Col, ...] | list[Col]
    filters: dict[str, str] = field(default_factory=dict)
    order_by: str = ""

    def __post_init__(self) -> None:
        # Freeze the column list so a spec cannot change after registration.
        object.__setattr__(self, "columns", tuple(self.columns))
        object.__setattr__(self, "filters", dict(self.filters))
        validate(self)

    @property
    def column_keys(self) -> list[str]:
        """The view columns to select, in display order."""
        return [c.key for c in self.columns]


_REGISTRY: dict[str, TableSpec] = {}


def validate(spec: TableSpec) -> None:
    """Refuse any spec whose names could not be safely written into SQL."""
    if not _IDENT.match(spec.name):
        raise ValueError(f"table name {spec.name!r} must be snake_case")
    if not _VIEW.match(spec.view):
        raise ValueError(f"table {spec.name}: view {spec.view!r} must be api.<view_name>")
    if not spec.columns:
        raise ValueError(f"table {spec.name}: no columns")
    keys = [c.key for c in spec.columns]
    if len(set(keys)) != len(keys):
        raise ValueError(f"table {spec.name}: duplicate column keys")
    for col in spec.columns:
        if not _IDENT.match(col.key):
            raise ValueError(f"table {spec.name}: column {col.key!r} is not a plain identifier")
        if col.key == "provenance":
            raise ValueError(f"table {spec.name}: 'provenance' is added by the API, do not list it")
        if col.decimals is not None and not (0 <= col.decimals <= 10):
            raise ValueError(f"table {spec.name}: column {col.key} decimals out of range")
    for param, column in spec.filters.items():
        if not _IDENT.match(param) or not _IDENT.match(column):
            raise ValueError(f"table {spec.name}: filter {param!r} -> {column!r} is not safe")
    for term in filter(None, (t.strip().lower() for t in spec.order_by.split(","))):
        if not _ORDER_TERM.match(term):
            raise ValueError(f"table {spec.name}: order_by term {term!r} is not allowed")


def register(spec: TableSpec) -> TableSpec:
    """Add a table to the registry (or replace one with the same name) and return it."""
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> TableSpec:
    """Return the registered table called `name`. Raises KeyError if there is none."""
    return _REGISTRY[name]


def all() -> list[TableSpec]:  # noqa: A001 - the contract names this function `all`
    """Every registered table, sorted by name."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]
