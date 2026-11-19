"""The network model: build a pandapower net from T01 tables, and check it.

Public functions:
- build_net(net_tables, case_id, substations, ...) -> pandapowerNet
- build_from_inputs(inputs, cfg, case_id=None, as_of=None, scenario="base") -> pandapowerNet,
  the call RunContext.net() makes, with settings from config/engine/network.toml
- element_register(net), bus_register(net): rows for results.element and results.bus
- check_net(net) -> DataFrame(severity, element_type, element_id, message)
"""

from __future__ import annotations

from datetime import date

from engine.network.build import build_net, bus_register, element_register
from engine.network.checks import check_net

__all__ = ["build_net", "build_from_inputs", "bus_register", "element_register", "check_net",
           "scenario_settings"]


def scenario_settings(cfg: dict, scenario: str = "base") -> dict:
    """as_of and statuses for a scenario from cfg["network"]["scenarios"].

    base: existing and committed elements; 2030: planned ones too, as at 2030-12-31.
    """
    scenarios = (cfg.get("network", {}) or {}).get("scenarios", {}) or {}
    s = scenarios.get(scenario) or scenarios.get(str(scenario)) or {}
    as_of = s.get("as_of")
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    return {"as_of": as_of, "statuses": tuple(s.get("statuses", ("existing", "committed")))}


def build_from_inputs(inputs, cfg: dict, case_id: str | None = None, as_of: date | None = None,
                      scenario: str = "base", extra=None):
    """Build the net for a run from engine.inputs.Inputs and the merged config.

    An explicit as_of wins over the scenario's. extra holds additional T01-shaped elements
    (the 2030 projects).
    """
    net_cfg = cfg.get("network", {}) or {}
    s = scenario_settings(cfg, scenario)
    return build_net(inputs.net_tables, case_id or inputs.case_id, inputs.substations,
                     as_of=as_of or s["as_of"], statuses=s["statuses"],
                     r_temp_c=float(net_cfg.get("r_temp_c", 50.0)),
                     rating_set=str(net_cfg.get("rating_set", "cont")),
                     line_in_central=str(net_cfg.get("line_in_central", "any")), extra=extra)
