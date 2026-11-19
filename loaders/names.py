"""Map the names people write ('Kawanda S/S 132kV', 'Kampala Nth') to canonical codes.

NCC, Planning, GIS and SCADA all spell substations differently. A name is normalised
(upper case, no punctuation, no filler words or voltages), then looked up in ref.alias,
which holds config/aliases.csv plus every canonical code and name. If nothing matches, the
closest known name is offered as a suggestion, but never applied: a person adds the alias
to config/aliases.csv after checking it.
"""
from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import pandas as pd

# Filler words dropped from names, after punctuation is removed.
DROP_TOKENS = {"SUBSTATION", "SUBSTN", "SUB", "SS", "PS", "KV"}
# Voltage numbers dropped when they stand alone ('Kawanda 132').
VOLTAGES = {"11", "22", "33", "66", "132", "220", "400"}
SUGGEST_CUTOFF = 0.8

_SS_RE = re.compile(r"(?<![A-Z0-9])S\s*[/.\-]\s*S\.?(?![A-Z0-9])")       # S/S, S.S., S-S
_KV_RE = re.compile(r"\b\d{2,3}(?:\.\d+)?(?:\s*/\s*\d{2,3}(?:\.\d+)?)*\s*KV\b")  # 132kV, 220/132 kV
_RATIO_RE = re.compile(r"\b\d{2,3}(?:\s*/\s*\d{2,3})+\b")                     # 33/11, 220/132/33
_POWER_STATION_RE = re.compile(r"\bPOWER\s+STATION\b")
_SUB_STATION_RE = re.compile(r"\bSUB\s+STATION\b")                         # Sub-station, Sub Station
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")


def normalise(name: object) -> str:
    """'Kawanda S/S 132kV' -> 'KAWANDA'; 'Kampala-North' -> 'KAMPALA NORTH'.

    Upper-cases, removes S/S, voltages (132, 33/11, 220 kV), punctuation and the words
    SUBSTATION, SS, POWER STATION, PS and KV, then collapses spaces.
    """
    if name is None:
        return ""
    text = str(name).upper()
    text = _SS_RE.sub(" ", text)
    text = _KV_RE.sub(" ", text)
    text = _RATIO_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _POWER_STATION_RE.sub(" ", text)
    text = _SUB_STATION_RE.sub(" ", text)
    tokens = [t for t in text.split() if t not in DROP_TOKENS and t not in VOLTAGES]
    return " ".join(tokens)


@dataclass
class Resolution:
    """The outcome of looking up one name."""

    code: str | None
    suggestion: str | None = None


@dataclass
class NameResolver:
    """Looks names up in {entity_type: {normalised name: canonical code}}."""

    lookup: dict[str, dict[str, str]] = field(default_factory=dict)
    labels: dict[str, dict[str, str]] = field(default_factory=dict)   # code -> display name

    @classmethod
    def from_frames(cls, aliases: pd.DataFrame, substations: pd.DataFrame | None = None,
                    plants: pd.DataFrame | None = None) -> "NameResolver":
        """Build from ref.alias(alias_norm, entity_type, canonical_id) and the registers."""
        resolver = cls({"substation": {}, "plant": {}}, {"substation": {}, "plant": {}})
        for kind, frame, code_col in (("substation", substations, "ss_code"), ("plant", plants, "plant_code")):
            if frame is None:
                continue
            for code, name in zip(frame[code_col], frame["name"]):
                resolver.add(kind, code, code)
                resolver.add(kind, name, code)
                resolver.labels[kind][code] = name
        for alias_norm, kind, code in zip(aliases["alias_norm"], aliases["entity_type"], aliases["canonical_id"]):
            resolver.lookup.setdefault(kind, {})[alias_norm] = code
        return resolver

    def add(self, entity_type: str, name: str, code: str) -> None:
        """Teach the resolver one name."""
        key = normalise(name)
        if key:
            self.lookup.setdefault(entity_type, {})[key] = code

    def resolve(self, raw: object, entity_type: str) -> Resolution:
        """The canonical code for raw, or None with the closest known name as a suggestion."""
        table = self.lookup.get(entity_type, {})
        key = normalise(raw)
        if key in table:
            return Resolution(table[key])
        close = difflib.get_close_matches(key, list(table), n=1, cutoff=SUGGEST_CUTOFF)
        if not close:
            return Resolution(None)
        code = table[close[0]]
        label = self.labels.get(entity_type, {}).get(code, close[0].title())
        return Resolution(None, f"{code} ({label})? add '{raw}' to config/aliases.csv if right")

    def known_codes(self, entity_type: str) -> set[str]:
        return set(self.lookup.get(entity_type, {}).values())


def alias_rows(aliases: pd.DataFrame, substations: pd.DataFrame, plants: pd.DataFrame) -> pd.DataFrame:
    """Rows for ref.alias: config/aliases.csv plus each canonical code and name.

    Raises ValueError when one normalised name points at two different codes, because a
    silent choice would put data on the wrong substation.
    """
    rows: list[tuple[str, str, str, str]] = []
    for code, name in zip(substations["ss_code"], substations["name"]):
        rows += [(normalise(code), "substation", code, "canonical code"), (normalise(name), "substation", code, "canonical name")]
    for code, name in zip(plants["plant_code"], plants["name"]):
        rows += [(normalise(code), "plant", code, "canonical code"), (normalise(name), "plant", code, "canonical name")]
    for alias, kind, code, source in zip(aliases["alias"], aliases["entity_type"], aliases["canonical_id"], aliases["source"]):
        rows.append((normalise(alias), str(kind).strip(), str(code).strip(), source if isinstance(source, str) and source.strip() else "config/aliases.csv"))
    seen: dict[tuple[str, str], str] = {}
    out = []
    for alias_norm, kind, code, source in rows:
        if not alias_norm:
            continue
        previous = seen.get((alias_norm, kind))
        if previous is None:
            seen[(alias_norm, kind)] = code
            out.append((alias_norm, kind, code, source))
        elif previous != code:
            raise ValueError(f"alias '{alias_norm}' ({kind}) maps to both {previous} and {code}: fix config/aliases.csv")
    return pd.DataFrame(out, columns=["alias_norm", "entity_type", "canonical_id", "source"])


def unknown_codes(rows: Iterable[str], known: set[str]) -> list[str]:
    """Codes in rows that are not known (used to check aliases point at real codes)."""
    return sorted({r for r in rows if r not in known})
