"""Provenance: how trustworthy a result is, from the inputs it was made from.

Every import batch is tagged synthetic, approximate, open or real. A result is only as
good as its worst input, so a run takes the worst level among the batches it used
(synthetic is worst, real is best). The label is what every page, chart and export shows.
"""
from __future__ import annotations

from collections.abc import Iterable

# Best first. The worst-of rule picks the level with the highest index.
LEVELS: tuple[str, ...] = ("real", "open", "approximate", "synthetic")

LABELS: dict[str, str] = {
    "synthetic": "SYNTHETIC: NOT UETCL DATA",
    "approximate": "APPROXIMATE: HAND-BUILT OR STANDARD-SHAPE INPUTS",
    "open": "TRAINEE SHOWCASE: NOT OFFICIAL UETCL FIGURES",
    "real": "TRAINEE SHOWCASE: NOT OFFICIAL UETCL FIGURES",
}


def check_level(level: str) -> str:
    """Return level if it is one of LEVELS, else raise ValueError."""
    if level not in LEVELS:
        raise ValueError(f"unknown provenance {level!r}; expected one of {', '.join(LEVELS)}")
    return level


def worst_of(levels: Iterable[str]) -> str:
    """The worst level among the inputs.

    With no inputs at all we cannot vouch for anything, so the answer is 'synthetic'.
    """
    found = [check_level(level) for level in levels]
    if not found:
        return "synthetic"
    return max(found, key=LEVELS.index)


def label(level: str) -> str:
    """The banner text for a level."""
    return LABELS[check_level(level)]


def is_synthetic(level: str) -> bool:
    """True when the level means 'made-up data'."""
    return check_level(level) == "synthetic"


def register_level(sources: Iterable[str]) -> str:
    """Level of the config registers (substations, plants) from their 'source' column.

    The registers ship with synthetic defaults marked 'approximate' or 'synthetic'; once
    the team replaces them from GIS or T06 the level becomes real.
    """
    text = " ".join(s.lower() for s in sources if s)
    if "synthetic" in text or "approximate" in text:
        return "approximate"
    return "real"
