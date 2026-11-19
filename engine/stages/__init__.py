"""The analysis stages, their order, and what each depends on.

Each stage is engine/stages/<name>.py with `def run(ctx) -> None`. A stub that has not been
written yet sets NOT_IMPLEMENTED = True and is recorded as 'skipped'. A stage that raises
is marked 'failed'; later stages still run unless they depend on it.
"""
from __future__ import annotations

import importlib
from types import ModuleType

STAGES: tuple[str, ...] = (
    "network", "losses", "validation", "reconciliation", "remedies",
    "contingency", "forecast", "kawanda", "sites", "incidents",
)

# Stage -> stages whose results it reads. If one of these failed in this run, the stage
# is skipped rather than run on missing data.
DEPENDS: dict[str, tuple[str, ...]] = {
    "network": (),
    "losses": ("network",),
    "validation": ("network",),
    "reconciliation": ("losses",),
    "remedies": ("losses",),
    "contingency": ("network",),
    "forecast": ("network",),
    "kawanda": ("network",),
    "sites": ("network",),
    "incidents": (),
}


def select_stages(requested: str | list[str] | None, default: list[str] | None = None) -> list[str]:
    """The stages to run, in the canonical order. Unknown names raise ValueError."""
    if requested is None or requested == "" or requested == []:
        names = list(default or STAGES)
    elif isinstance(requested, str):
        names = [s.strip() for s in requested.split(",") if s.strip()]
    else:
        names = list(requested)
    unknown = [n for n in names if n not in STAGES]
    if unknown:
        raise ValueError(f"unknown stage(s): {', '.join(unknown)}; stages are {', '.join(STAGES)}")
    return [s for s in STAGES if s in names]


def blocked_by(stage: str, failed: set[str]) -> list[str]:
    """The failed stages this stage depends on (empty means it may run)."""
    return [d for d in DEPENDS.get(stage, ()) if d in failed]


def load_stage(name: str) -> ModuleType:
    """Import engine/stages/<name>.py."""
    if name not in STAGES:
        raise ValueError(f"unknown stage {name!r}")
    return importlib.import_module(f"engine.stages.{name}")
