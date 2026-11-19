"""RunContext: what a stage receives. It hides the database behind a few small methods.

A stage reads inputs with ctx.table / ctx.read, gets the cached inputs and a fresh
pandapower network from ctx.inputs / ctx.net, and writes results with ctx.write, which
stamps every row with the run id. Stages never open their own connections.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import text

from engine import db

# Builder statuses per scenario. 'base' is the network as operated in the study period.
SCENARIO_STATUSES: dict[str, tuple[str, ...]] = {
    "base": ("existing", "committed"),
    "existing": ("existing",),
    "planned": ("existing", "committed", "planned"),
    "forecast": ("existing", "committed", "planned"),
}


def scenario_settings(network_cfg: dict[str, Any], scenario: str,
                      as_of: date | None = None) -> tuple[tuple[str, ...], date | None]:
    """(statuses, as_of) for a network scenario.

    config/engine/network.toml [scenarios.<name>] wins (statuses, as_of), so the 2030
    network really includes planned projects; SCENARIO_STATUSES is the fallback. An
    explicit as_of argument beats the configured one. An unknown scenario is an error:
    silently building the base network for it would give wrong answers.
    """
    configured = ((network_cfg or {}).get("scenarios") or {}).get(str(scenario))
    if configured is None and scenario not in SCENARIO_STATUSES:
        known = sorted(set(SCENARIO_STATUSES) | set((network_cfg or {}).get("scenarios") or {}))
        raise ValueError(f"unknown network scenario {scenario!r}; known: {', '.join(known)}")
    configured = configured or {}
    statuses = tuple(configured.get("statuses") or SCENARIO_STATUSES.get(scenario, SCENARIO_STATUSES["base"]))
    if as_of is None and configured.get("as_of"):
        raw = configured["as_of"]
        as_of = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    return statuses, as_of


def quote_table(name: str) -> str:
    """'results.case' -> '"results"."case"' (case is an SQL keyword, so always quote)."""
    db.check_table_name(name)
    schema, table = name.split(".")
    return f'"{schema}"."{table}"'


@dataclass
class RunContext:
    """Everything a stage needs for one run."""

    run_id: int
    cfg: dict[str, Any]
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("atlas.run"))
    url: str | None = None
    # What-if actions for a scenario run (contracts 13.2: extra loads, outages, early
    # projects), as the list of dicts stored in meta.scenario.actions. Empty for a baseline.
    actions: list[dict[str, Any]] = field(default_factory=list)
    # Load-flow counters for the stage now running; the run framework records them in
    # meta.run_stage and resets them between stages.
    n_loadflows: int = 0
    n_failed: int = 0
    _inputs: Any = field(default=None, repr=False)
    _nets: dict[tuple, Any] = field(default_factory=dict, repr=False)

    # ---- reading -------------------------------------------------------------------
    def read(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        """Run a SELECT (with :name placeholders) and return a DataFrame."""
        return db.read_df(sql, params, url=self.url)

    def table(self, name: str, where: str = "", params: dict[str, Any] | None = None) -> pd.DataFrame:
        """Read a whole table, optionally filtered: ctx.table("ts.ncc_substation_monthly", "month >= :m", {"m": d}).

        Reading a results table returns this run's rows only.
        """
        sql = f"SELECT * FROM {quote_table(name)}"
        clauses = [f"({where})"] if where else []
        params = dict(params or {})
        if name.startswith("results."):
            clauses.append("run_id = :_run_id")
            params["_run_id"] = self.run_id
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self.read(sql, params)

    # ---- writing -------------------------------------------------------------------
    def write(self, table: str, df: pd.DataFrame) -> int:
        """Add run_id and bulk-copy df into results.<table>. Returns the number of rows."""
        name = table if "." in table else f"results.{table}"
        if not name.startswith("results."):
            raise ValueError(f"stages write only to results.*, not {name}")
        if df is None or df.empty:
            return 0
        out = df.drop(columns=["run_id"], errors="ignore").copy()
        out.insert(0, "run_id", self.run_id)
        return db.copy_df(name, out, url=self.url)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Run one statement (for example a DELETE before a stage re-writes its rows)."""
        with db.get_engine(self.url).begin() as conn:
            return conn.execute(text(sql), params or {}).rowcount

    def count_loadflows(self, n: int, n_failed: int = 0) -> None:
        """Record load flows run by the current stage (shown in meta.run_stage)."""
        self.n_loadflows += int(n)
        self.n_failed += int(n_failed)

    # ---- inputs and networks (built by F3a / F3b modules) --------------------------
    @property
    def inputs(self) -> Any:
        """The cached engine.inputs.Inputs, loaded on first use."""
        if self._inputs is None:
            from engine.inputs import load_inputs  # imported late: written by another owner
            self._inputs = load_inputs(self)
        return self._inputs

    def net(self, case_id: str | None = None, as_of: date | None = None, scenario: str = "base") -> Any:
        """A fresh deep copy of the pandapower network, built once per (case, date, scenario).

        Stages may change the copy freely (trip lines, scale loads); the cached original
        is never touched.
        """
        network_cfg = self.cfg.get("network", {}) or {}
        statuses, as_of = scenario_settings(network_cfg, scenario, as_of)
        key = (case_id, as_of, statuses)
        if key not in self._nets:
            from engine.network.build import build_net  # imported late: written by another owner
            inputs = self.inputs
            self._nets[key] = build_net(
                inputs.net_tables,
                case_id or inputs.case_id,
                inputs.substations,
                as_of=as_of,
                statuses=statuses,
                r_temp_c=float(network_cfg.get("r_temp_c", 50.0)),
                rating_set=str(network_cfg.get("rating_set", "cont")),
                line_in_central=str(network_cfg.get("line_in_central", "any")),
            )
        return copy.deepcopy(self._nets[key])
