"""Tests for engine/profiles.py: calendar, SCADA shapes, standard-shape fit, generation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from conftest import HOLIDAY, MONTH, base_inputs, scada_frame, scada_hour_value, scada_points
from engine import profiles as pr


def test_day_type_counts_without_holidays():
    assert pr.day_type_counts(MONTH, None) == {"WD": 22, "NWD": 9}


def test_day_type_counts_respect_holidays():
    hols = pd.DataFrame({"day": [pd.Timestamp(HOLIDAY).date()]})
    assert pr.day_type_counts(MONTH, hols) == {"WD": 21, "NWD": 10}


def test_holiday_on_a_weekend_changes_nothing():
    hols = pd.DataFrame({"day": [pd.Timestamp("2026-03-08").date()]})  # a Sunday
    assert pr.day_type_counts(MONTH, hols) == {"WD": 22, "NWD": 9}


def test_fit_hits_energy_and_peak_exactly():
    sigma = pr.load_standard_profiles()
    sigma = sigma[sigma["class"] == "mixed"].reset_index(drop=True)
    counts = {"WD": 21, "NWD": 10}
    energy, peak = 0.85 * 24 * 31 * 60.0, 60.0  # load factor 0.85: a feasible fit
    rows = pr.standard_shape_rows("EXA", sigma, counts, energy, peak, 0.3)
    got_energy = sum(counts[dt] * rows.loc[rows["day_type"] == dt, "p_mw"].sum() for dt in pr.DAY_TYPES)
    assert got_energy == pytest.approx(energy, rel=1e-12)
    assert rows["p_mw"].max() == pytest.approx(peak, rel=1e-12)
    assert "fit fit" in rows["note"].iloc[0]
    assert np.allclose(rows["q_mvar"], rows["p_mw"] * 0.3)


def test_fit_a_negative_branch_keeps_energy():
    # A very peaky month: energy only 30% of 24*D*Pmax, so a would be negative.
    n_days, peak = 31, 100.0
    s_sum = 0.75 * 24 * n_days
    energy = 0.3 * 24 * n_days * peak
    a, b, branch = pr.fit_standard_shape(energy, peak, s_sum, n_days)
    assert branch == "a_clipped"
    assert a == 0.0
    assert b * s_sum == pytest.approx(energy)


def test_fit_formula_values():
    a, b, branch = pr.fit_standard_shape(energy_mwh=600.0, peak_mw=40.0, s_sum=18.0, n_days=1)
    # b = (600 - 24*40) / (18 - 24) = 60, a = 40 - 60 < 0 -> clipped
    assert branch == "a_clipped" and b == pytest.approx(600 / 18)
    a, b, branch = pr.fit_standard_shape(energy_mwh=840.0, peak_mw=40.0, s_sum=18.0, n_days=1)
    assert branch == "fit"
    assert b == pytest.approx((840 - 960) / (18 - 24)) and a == pytest.approx(40 - b)


def test_fit_edge_cases():
    assert pr.fit_standard_shape(100.0, None, 20.0, 1)[2] == "energy_only"
    assert pr.fit_standard_shape(2000.0, 40.0, 18.0, 1)[2] == "flat"  # load factor above 1
    assert pr.fit_standard_shape(480.0, 40.0, 24.0, 1) == (20.0, 0.0, "flat")


def test_standard_profiles_cover_all_classes():
    sp = pr.load_standard_profiles()
    assert set(sp["class"]) == {"urban_commercial", "urban_residential", "industrial", "mixed"}
    assert (sp.groupby("class")["sigma"].max() == 1.0).all()
    assert (sp.groupby(["class", "day_type"]).size() == 24).all()


def test_select_load_points_prefers_bsp():
    pts = pr.select_load_points(scada_points())
    assert set(pts["point_id"]) == {"EXA.F1.P", "EXA.F1.Q"}
    assert (pts["sign"] == 1.0).all()


def test_select_load_points_uses_lowest_kv_transformers():
    pts = pd.DataFrame({
        "point_id": ["T1", "T2", "T3", "T4"],
        "substation_code": ["EXA"] * 4,
        "element_type": ["transformer"] * 4,
        "winding": ["hv", "hv", "hv", "lv"],
        "voltage_kv": [220.0, 132.0, 132.0, 33.0],
        "quantity": ["P"] * 4,
        "sign_convention": [None, None, "+ = from the transformer to the busbar", None],
    })
    chosen = pr.select_load_points(pts).set_index("point_id")
    assert list(chosen.index) == ["T2", "T3"]
    assert chosen.loc["T3", "sign"] == -1.0


def test_scada_shapes_average_by_day_type(scada_inputs):
    shapes = pr.scada_shapes(scada_inputs, MONTH)
    wd = shapes[(shapes["ss_code"] == "EXA") & (shapes["day_type"] == "WD")].set_index("hour")
    nwd = shapes[(shapes["ss_code"] == "EXA") & (shapes["day_type"] == "NWD")].set_index("hour")
    assert wd.loc[20, "p_mw"] == pytest.approx(scada_hour_value("2026-03-10", 20))
    assert wd.loc[5, "p_mw"] == pytest.approx(scada_hour_value("2026-03-10", 5))  # bad row ignored
    assert nwd.loc[3, "p_mw"] == pytest.approx(scada_hour_value("2026-03-15", 3))
    assert wd.loc[20, "q_mvar"] == pytest.approx(0.3 * wd.loc[20, "p_mw"])


def test_missing_day_type_uses_ncc_sample_day():
    frame = scada_frame()
    frame = frame[frame["timestamp"].dt.day == 10]  # only the weekday
    inputs = base_inputs(scada_points=scada_points(), scada_frames={MONTH: frame})
    shapes = pr.scada_shapes(inputs, MONTH)
    nwd = shapes[shapes["day_type"] == "NWD"].set_index("hour")
    assert nwd.loc[7, "p_mw"] == pytest.approx(scada_hour_value("2026-03-10", 7))
    assert "copied" in nwd["note"].iloc[0]


def test_profile_sources(scada_inputs):
    prof = pr.substation_profiles(scada_inputs, MONTH)
    src = prof.groupby("ss_code")["profile_source"].first()
    assert src.to_dict() == {"EXA": "scada", "EXB": "standard"}


def test_borrowed_shape_from_nearest_month():
    feb = scada_frame().assign(timestamp=lambda d: d["timestamp"] - pd.Timedelta(days=28))  # 10 and 15 Feb
    inputs = base_inputs(scada_points=scada_points(), scada_frames={"2026-02": feb})
    prof = pr.substation_profiles(inputs, MONTH)
    exa = prof[prof["ss_code"] == "EXA"]
    assert (exa["profile_source"] == "borrowed").all()
    assert "2026-02" in exa["note"].iloc[0]


def test_gen_profiles_solar_energy_and_slack_excluded(inputs):
    gp = pr.gen_profiles(inputs, MONTH)
    assert set(gp["gen_id"]) == {"G-SOL-1"}
    counts = pr.day_type_counts(MONTH, inputs.holidays)
    energy = sum(counts[dt] * gp.loc[gp["day_type"] == dt, "p_mw"].sum() for dt in pr.DAY_TYPES)
    assert energy == pytest.approx(3000.0)
    night = gp[gp["hour"].isin([0, 3, 19, 23])]
    assert (night["p_mw"] == 0).all()
    assert gp["p_mw"].max() == pytest.approx(gp[gp["hour"].isin([11, 12])]["p_mw"].max())


def test_gen_profiles_flat_for_non_solar(inputs):
    inputs.generation_monthly = inputs.generation_monthly.assign(technology="thermal")
    gp = pr.gen_profiles(inputs, MONTH)
    assert np.allclose(gp["p_mw"], 3000.0 / 31 / 24)
