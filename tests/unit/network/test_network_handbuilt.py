"""Hand-built (T12) conversion tests, the config files, and the pypowsybl guard."""

from __future__ import annotations

import math
import platform
from datetime import date

import pandas as pd
import pytest

from engine.loadflow import run_pf
from engine.network import check_net, element_register
from engine.network.build import build_net
from loaders import network_handbuilt as hb
from network_helpers import four_substation_t12


def converted():
    tables = four_substation_t12()
    return hb.to_net_tables(tables), hb.substations_register(tables)


def test_ids_follow_the_contract():
    t01, _ = converted()
    assert set(t01["net_bus"].bus_id) >= {"EXA-220-1", "EXA-132-1", "EXA-33-1", "EXB-132-1", "EXD-220-1"}
    assert "L-EXA-EXD-220-1" in set(t01["net_line"].line_id)
    assert "L-EXA-EXB-132-1" in set(t01["net_line"].line_id)
    assert set(t01["net_trafo"].trafo_id) == {"T-EXA-1", "T-EXA-2", "T-EXB-1", "T-EXB-2", "T-EXC-1", "T-EXD-1"}
    assert set(t01["net_gen"].gen_id) == {"G-EXAH-1", "G-EXAS-1"}
    assert dict(zip(t01["net_gen"].gen_id, t01["net_gen"].control)) == {"G-EXAH-1": "PV", "G-EXAS-1": "PQ"}
    assert set(t01["net_load"].load_id) == {"D-EXA-1", "D-EXB-1", "D-EXC-1", "D-EXD-1"}
    # EXD has no 132/33 kV unit in the schedule, so its load sits on its 132 kV bus.
    assert set(t01["net_load"].bus) == {"EXA-33-1", "EXB-33-1", "EXC-33-1", "EXD-132-1"}
    assert (t01["net_case"].case_id == "HANDBUILT").all()
    assert (t01["net_line"].param_source == "typical").all()


def test_line_parameters_from_conductors():
    t01, _ = converted()
    lines = t01["net_line"].set_index("line_id")
    cond = hb.read_conductors()
    bear = cond[(cond.conductor == "ACSR Bear") & (cond.kv == 132)].iloc[0]
    exb = lines.loc["L-EXA-EXB-132-1"]
    assert exb.length_km == 16.4
    assert exb.r_ohm_per_km == pytest.approx(bear.r20_ohm_per_km)
    assert exb.rate_cont_mva == pytest.approx(math.sqrt(3) * 132 * bear.ampacity_a / 1000, abs=0.1)
    # A single Bear bundled 2 per phase equals the Twin Bear row.
    twin = lines.loc["L-EXA-EXD-220-1"]
    bundled = lines.loc["L-EXA-EXD-220-2"]
    for c in ("r_ohm_per_km", "x_ohm_per_km", "b_us_per_km", "rate_cont_mva"):
        assert bundled[c] == pytest.approx(twin[c], rel=2e-3), c
    # Blank length: haversine distance times the routing factor.
    straight = hb.haversine_km(0.40, 32.50, 0.45, 33.10)
    assert twin.length_km == pytest.approx(straight * 1.2, rel=1e-3)


def test_unknown_conductor_is_a_clear_error():
    tables = four_substation_t12()
    tables["hb_line"].loc[0, "conductor"] = "ACSR Unicorn"
    with pytest.raises(KeyError, match="Unicorn"):
        hb.to_net_tables(tables)


def test_handbuilt_net_converges():
    t01, subs = converted()
    # Placeholder loads are 0 MW; give each substation a realistic demand.
    t01["net_load"]["p_mw"] = [60.0, 45.0, 30.0, 20.0]
    t01["net_load"]["q_mvar"] = t01["net_load"]["p_mw"] * 0.3
    t01["net_gen"].loc[t01["net_gen"].technology == "hydro", "p_mw"] = 40.0
    t01["net_gen"].loc[t01["net_gen"].technology == "solar", "p_mw"] = 15.0
    net = build_net(t01, "HANDBUILT", subs, as_of=date(2026, 9, 30))
    assert "L-EXA-EXC-132-2" not in set(net.line.name)  # planned 2029 line left out
    result = run_pf(net)
    assert result.converged, result.message
    solved = net.res_bus.vm_pu.dropna()
    assert len(solved) == len(net.bus) - 1  # only the unconnected EXD 33 kV bus is dead
    assert solved.between(0.9, 1.1).all()
    errors = check_net(net).query("severity == 'error'")
    assert errors.empty, errors.to_string()
    reg = element_register(net).set_index("element_id")
    assert bool(reg.loc["B-EXD-220-1", "is_equivalent"])
    assert bool(reg.loc["L-EXA-EXD-220-1", "in_central"])  # EXA is Central, EXD is not
    assert not bool(reg.loc["T-EXD-1", "in_central"])


def test_transformer_defaults_cover_all_sizes():
    defaults = hb.read_trafo_defaults()
    for mva in (5, 20, 60, 150, 250, 600):
        typ = hb.typical_trafo(mva, defaults)
        assert 0 < typ["vkr_percent"] < typ["vk_percent"] < 20
        assert typ["pfe_kw"] > 0


def test_conductors_file_is_complete():
    cond = hb.read_conductors()
    assert {"ACSR Wolf", "ACSR Lynx", "ACSR Bear", "ACSR Goat", "ACSR Zebra", "ACSR Drake",
            "ACSR Twin Bear", "ACSR Twin Goat", "ACCC Bear-size", "ACCC Drake-size"} <= set(cond.conductor)
    assert set(cond.kv) == {132, 220}
    assert cond.source.str.contains("verify against Planning data").all()
    xr = cond.x_ohm_per_km / cond.r20_ohm_per_km
    assert xr.between(1.5, 15).all()


def test_pypowsybl_missing_gives_clear_error():
    from loaders import network_pypowsybl as npp
    try:
        import pypowsybl  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="x86_64"):
            npp.to_t01("missing.raw", "X")
    else:
        pytest.skip(f"pypowsybl is installed on {platform.machine()}; converter test needs a RAW file")


def test_adapter_registry():
    from loaders.adapters import load_adapter
    assert load_adapter("handbuilt") is hb
    with pytest.raises(ValueError):
        load_adapter("template")
