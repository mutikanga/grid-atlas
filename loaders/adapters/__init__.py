"""Adapters for data that arrives in a holder's native layout instead of our template.

A dataset's manifest.toml names its adapter (`adapter = "template"` for our own
workbooks). Any other value names a module here, `loaders/adapters/<name>.py`, or one of
the network converters listed in NETWORK_CONVERTERS. Each adapter turns the native files
into the template's tables (for the network: T01-shaped `net_*` DataFrames), so the
generic loader can validate and load them like any template.
"""

from __future__ import annotations

import importlib
from types import ModuleType

# Network converters live beside the other network loaders; these names reach them.
NETWORK_CONVERTERS = {
    "pypowsybl": "loaders.network_pypowsybl",   # PSS/E RAW v33/v35, CGMES, DGS -> T01 (to_t01)
    "psse": "loaders.network_pypowsybl",
    "cgmes": "loaders.network_pypowsybl",
    "dgs": "loaders.network_pypowsybl",
    "handbuilt": "loaders.network_handbuilt",   # T12 -> T01 (to_net_tables)
}


def load_adapter(name: str) -> ModuleType:
    """Import the adapter module a manifest names. Raises ValueError for 'template'
    (no adapter needed) and ModuleNotFoundError for an unknown name."""
    key = name.strip().lower()
    if key == "template":
        raise ValueError("'template' data needs no adapter")
    # The name comes from a manifest file, so only a plain module name is accepted:
    # no dots, so it cannot reach a module outside loaders/adapters/.
    if key not in NETWORK_CONVERTERS and not key.isidentifier():
        raise ValueError(f"adapter name {name!r} is not a plain module name")
    return importlib.import_module(NETWORK_CONVERTERS.get(key, f"loaders.adapters.{key}"))
