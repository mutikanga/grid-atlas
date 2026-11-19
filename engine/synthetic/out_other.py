"""T06 commercial, T07 UEDCL feeders, T08 projects and loads, T09 sites, T10 growth,
T11 reconciliation explanations, T13 Planning studies, and the synthetic open layers.

All names, owners, prices and places here are invented or approximate. Plant and
substation names reuse the canonical register (or aliases it resolves).
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from engine.synthetic.network import CENTRAL, SUBSTATIONS, haversine_km
from engine.synthetic.timeseries import MONTHS, rng_for
from engine.synthetic.world import (NCC_PLANT_NAMES, ESTIMATED_METER, METER_ERROR_METER, METER_ERROR_SHARE, PLANTED_ESTIMATED_MONTH,
                                    PLANTED_METER_ERROR_MONTH, World, ss_name)

# Plant names as Commercial writes them (aliases in config/aliases.csv).
COMMERCIAL_PLANT_NAMES = {
    "BUJH": "Bujagali HPP", "NALH": "Nalubaale and Kiira", "KARH": "Karuma Hydro",
    "NMVT": "Namanve Thermal Power Station", "KBSS": "Kabulasoke Solar Plant", "NKGS": "Nkonge Solar Plant",
    "KAPS": "Kapeeka Solar Plant",
}
ENERGY_CHARGE = {"hydro": 160.0, "solar": 330.0, "thermal": 720.0}  # UGX/kWh, invented


def month_bounds(month: str) -> tuple[date, date]:
    y, m = int(month[:4]), int(month[5:])
    first = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return first, date.fromordinal(nxt.toordinal() - 1)


def bst_tariff(month: str) -> float:
    """An invented bulk supply tariff that ERA adjusts each quarter (UGX/kWh)."""
    q = (int(month[5:]) - 1) // 3
    base = {2025: 288.0, 2026: 294.0}[int(month[:4])]
    return round(base + 2.5 * q, 2)


# --------------------------------------------------------------------------- T06
def t06_tables(w: World, t03: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    rng = rng_for(w.seed, "t06")
    tariffs, sales, deemed, charges = [], [], [], []
    sub = t03["substation_monthly"]
    gen = t03["generation_monthly"]
    du = t03["deemed_unserved"]
    for month in MONTHS:
        first, last = month_bounds(month)
        tariff = bst_tariff(month)
        tariffs.append({"effective_from": first, "effective_to": last, "tariff_code": "SYN-BST-UEDCL",
                        "ugx_per_kwh": tariff, "approval_status": "approved",
                        "era_decision_ref": f"SYN-ERA-{first.year}-Q{(first.month - 1) // 3 + 1}",
                        "era_decision_date": date(first.year, ((first.month - 1) // 3) * 3 + 1, 1).replace(day=1),
                        "notes": "SYNTHETIC tariff"})
        sel = w.month_mask(month)
        for c in CENTRAL:
            row = sub[(sub["month"] == month) & (sub["metering_point"] == f"{c} 33 kV feeders (BSP)")].iloc[0]
            energy_kwh = float(row["energy_mwh"]) * 1000
            if c == "KAW":
                dc = {k: float(v[sel].sum()) * 1000 for k, v in w.ts.dc_p.items()}
                for ref, kwh in dc.items():
                    sales.append({"month": month, "bulk_supply_point": "Kawanda 33 kV", "substation": "Kawanda",
                                  "customer_type": "direct_customer", "customer_ref": ref, "meter_id": f"KAW-{ref}",
                                  "metering_kv": 33.0, "energy_kwh": round(kwh), "amount_ugx": round(kwh * tariff * 1.05),
                                  "estimated": "N", "notes": "SYNTHETIC anonymised data-centre customer"})
                energy_kwh -= sum(dc.values())
            sales.append({"month": month, "bulk_supply_point": f"{ss_name(c)} 33 kV", "substation": ss_name(c),
                          "customer_type": "uedcl", "customer_ref": None, "meter_id": f"{c}-B01", "metering_kv": 33.0,
                          "energy_kwh": round(energy_kwh * (1 + 0.0005 * rng.standard_normal())),
                          "amount_ugx": round(energy_kwh * tariff), "estimated": "N", "notes": "SYNTHETIC"})
        for g in w.nw.gens.itertuples():
            grow = gen[(gen["month"] == month) & (gen["plant"] == NCC_PLANT_NAMES[g.plant_code])]
            mwh = float(grow["sent_out_mwh"].iloc[0])
            charge = ENERGY_CHARGE[g.technology] * (1 + 0.01 * (int(month[5:]) % 4))
            charges.append({"month": month, "plant": COMMERCIAL_PLANT_NAMES[g.plant_code],
                            "energy_charge_ugx_per_kwh": round(charge, 2), "take_or_pay": "Y" if g.technology == "hydro" else "N",
                            "energy_purchased_kwh": round(mwh * 1000),
                            "capacity_charge_ugx": round(g.p_max_mw * 9.5e6) if g.technology == "thermal" else None,
                            "notes": "SYNTHETIC"})
        d = du[(du["month"] == month) & (du["category"] == "deemed")]
        for r in d.itertuples():
            kwh = r.energy_mwh * 1000
            deemed.append({"month": month, "plant": COMMERCIAL_PLANT_NAMES["KAPS"], "deemed_kwh": round(kwh),
                           "amount_ugx": round(kwh * ENERGY_CHARGE["solar"]), "cause": "evacuation_constraint",
                           "cause_recorded": "Kapeeka - Kawanda line constrained", "constraint_location": "Kapeeka - Kawanda 132 kV",
                           "claim_status": "verified", "notes": "SYNTHETIC"})
    plants = []
    owners = {"BUJH": "Synthetic Hydro Co A", "NALH": "Synthetic Generation Co", "KARH": "Synthetic Generation Co",
              "NMVT": "Synthetic Thermal Ltd", "KBSS": "Synthetic Solar Ltd B", "NKGS": "Synthetic Solar Ltd C",
              "KAPS": "Synthetic Solar Ltd D"}
    for g in w.nw.gens.itertuples():
        plants.append({"plant": COMMERCIAL_PLANT_NAMES[g.plant_code], "owner": owners[g.plant_code], "technology": g.technology,
                       "installed_mw": g.p_max_mw, "contracted_mw": round(g.p_max_mw * 0.95, 1),
                       "dependable_mw": round(g.p_max_mw * (0.25 if g.technology == "solar" else 0.85), 1),
                       "connection_substation": ss_name(g.ss_code), "connection_kv": g.connection_kv,
                       "connection_feeder": f"{ss_name(g.ss_code)} plant feeder" if g.connection_kv == 33 else None,
                       "metering_point": f"{ss_name(g.ss_code)} {int(g.connection_kv)} kV, plant bay", "cod": f"{g.cod_year}-01",
                       "ppa_expiry": f"{g.cod_year + 20}-01", "deemed_terms": "SYNTHETIC: energy available but not taken is paid at the energy charge",
                       "operating_status": "operating", "confidential": "N", "notes": "SYNTHETIC"})
    return {"tariffs": pd.DataFrame(tariffs), "bsp_sales": pd.DataFrame(sales), "deemed_energy": pd.DataFrame(deemed),
            "energy_charges": pd.DataFrame(charges), "plants_ppa": pd.DataFrame(plants)}


# --------------------------------------------------------------------------- T07
FEEDER_SPLIT = {  # share of the UEDCL energy per feeder, and feeder type
    "KAW": [(0.45, "mixed"), (0.30, "domestic"), (0.25, "commercial")],
    "MUT": [(0.25, "domestic"), (0.25, "domestic"), (0.25, "mixed"), (0.25, "domestic")],
    "LUG": [(0.30, "commercial"), (0.30, "commercial"), (0.20, "mixed"), (0.20, "commercial")],
    "KNO": [(0.40, "commercial"), (0.35, "mixed"), (0.25, "commercial")],
    "QWY": [(0.40, "commercial"), (0.35, "industrial"), (0.25, "commercial")],
    "NMV": [(0.70, "industrial"), (0.30, "mixed")],
    "MUK": [(0.60, "mixed"), (0.40, "domestic")],
    "KAP": [(1.00, "mixed")],
    "KBS": [(1.00, "mixed")],
    "NKG": [(1.00, "mixed")],
    "MSK": [(0.50, "mixed"), (0.50, "domestic")],
}
PLANT_FEEDER = {"NMV": "G-NMVT-1", "KBS": "G-KBSS-1", "NKG": "G-NKGS-1", "KAP": "G-KAPS-1"}


def t07_tables(w: World, t03: dict[str, pd.DataFrame], t06: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    rng = rng_for(w.seed, "t07")
    rows = []
    sales = t06["bsp_sales"]
    for month in MONTHS:
        sel = np.where(w.month_mask(month))[0]
        for c in CENTRAL:
            ued = sales[(sales["month"] == month) & (sales["substation"] == ss_name(c)) & (sales["customer_type"] == "uedcl")]
            mwh = float(ued["energy_kwh"].iloc[0]) / 1000
            p = w.ts.load_p[sel, w.load_col[f"D-{c}-1"]]
            ip = sel[p.argmax()]
            for n, (share, ftype) in enumerate(FEEDER_SPLIT[c], start=1):
                rows.append({"month": month, "bulk_supply_point": ss_name(c), "feeder": f"{ss_name(c)} feeder {n}", "kv": 33.0,
                             "feeder_type": ftype, "single_customer": "N",
                             "peak_mw": round(float(p.max()) * share * float(rng.uniform(1.02, 1.08)), 2),
                             "peak_at": w.cal.hours[ip], "energy_mwh": round(mwh * share, 1), "reverse_flow_mwh": 0.0,
                             "power_factor": round(float(rng.uniform(0.90, 0.96)), 3), "load_basis": "net",
                             "quality": "actual", "notes": "SYNTHETIC"})
            if c in PLANT_FEEDER:
                g = w.gen_p(PLANT_FEEDER[c])[sel]
                plant = w.nw.gens.set_index("gen_id").loc[PLANT_FEEDER[c], "plant"]
                rows.append({"month": month, "bulk_supply_point": ss_name(c), "feeder": f"{ss_name(c)} plant feeder", "kv": 33.0,
                             "feeder_type": "generator_only", "single_customer": "Y", "peak_mw": 0.0, "peak_at": None,
                             "energy_mwh": 0.0, "reverse_flow_mwh": round(float(g.sum()), 1), "power_factor": None,
                             "load_basis": "net", "quality": "actual", "embedded_gen_mw": round(float(g.max()), 2),
                             "embedded_gen_plants": plant, "embedded_gen_mwh": round(float(g.sum()), 1),
                             "notes": "SYNTHETIC plant feeder"})
    return {"feeders": pd.DataFrame(rows)}


# --------------------------------------------------------------------------- T08
def t08_tables(w: World) -> dict[str, pd.DataFrame]:
    tr = w.nw.trafos.set_index("trafo_id")
    ln = w.nw.lines.set_index("line_id")
    projects = pd.DataFrame([
        {"project_id": "SP-01", "name": "Kawanda third 220/132 kV transformer", "type": "transformer", "status": "planned",
         "cod": "2027-06", "from_substation": "Kawanda", "to_substation": None, "kv": 220.0, "lv_kv": 132.0, "circuits": None,
         "units": 1, "length_km": None, "conductor": None, "mva": float(tr.loc["T-KAW-3", "sn_mva"]),
         "mvar": None, "vk_percent": float(tr.loc["T-KAW-3", "vk_percent"]), "existing_element": None, "relief_for": "KAW",
         "model_ref": "T-KAW-3", "source_document": "SYNTHETIC grid development plan, table 1", "notes": "SYNTHETIC: Kawanda relief"},
        {"project_id": "SP-02", "name": "Kawanda - Kampala North second 132 kV circuit", "type": "line", "status": "planned",
         "cod": "2028-06", "from_substation": "Kawanda", "to_substation": "Kampala North", "kv": 132.0, "lv_kv": None,
         "circuits": 1, "units": None, "length_km": float(ln.loc["L-KAW-KNO-132-2", "length_km"]), "conductor": "ACSR Bear",
         "mva": float(ln.loc["L-KAW-KNO-132-2", "rate_cont_mva"]), "mvar": None, "vk_percent": None,
         "existing_element": "L-KAW-KNO-132-1", "relief_for": "KNO", "model_ref": "L-KAW-KNO-132-2",
         "source_document": "SYNTHETIC grid development plan, table 2", "notes": "SYNTHETIC"},
        {"project_id": "SP-03", "name": "Kapeeka - Kawanda second 132 kV circuit", "type": "line", "status": "planned",
         "cod": "2029-06", "from_substation": "Kapeeka", "to_substation": "Kawanda", "kv": 132.0, "lv_kv": None,
         "circuits": 1, "units": None, "length_km": float(ln.loc["L-KAP-KAW-132-2", "length_km"]), "conductor": "ACSR Wolf",
         "mva": float(ln.loc["L-KAP-KAW-132-2", "rate_cont_mva"]), "mvar": None, "vk_percent": None,
         "existing_element": "L-KAP-KAW-132-1", "relief_for": "KAP", "model_ref": "L-KAP-KAW-132-2",
         "source_document": "SYNTHETIC grid development plan, table 2", "notes": "SYNTHETIC: ends the radial supply to Kapeeka"},
        {"project_id": "SP-04", "name": "Lugogo - Queensway 132 kV reconductoring to ACCC", "type": "reconductoring",
         "status": "planned", "cod": "2028-12", "from_substation": "Lugogo", "to_substation": "Queensway", "kv": 132.0,
         "lv_kv": None, "circuits": 1, "units": None, "length_km": float(ln.loc["L-LUG-QWY-132-1", "length_km"]),
         "conductor": "ACCC Bear-size", "mva": 251.5, "mvar": None, "vk_percent": None, "existing_element": "L-LUG-QWY-132-1",
         "relief_for": None, "model_ref": None, "source_document": "SYNTHETIC loss-reduction plan", "notes": "SYNTHETIC"},
        {"project_id": "SP-05", "name": "Mutundwe 33 kV capacitor bank", "type": "compensation", "status": "committed",
         "cod": "2027-03", "from_substation": "Mutundwe", "to_substation": None, "kv": 33.0, "lv_kv": None, "circuits": None,
         "units": 1, "length_km": None, "conductor": None, "mva": None, "mvar": 20.0, "vk_percent": None,
         "existing_element": None, "relief_for": None, "model_ref": None, "source_document": "SYNTHETIC",
         "notes": "SYNTHETIC"},
    ])
    loads = pd.DataFrame([
        {"load_ref": "CL-01", "category": "data_centre", "substation": "Kawanda", "connection_kv": 33.0, "mw": 20.0,
         "mw_basis": "requested", "pf": 0.97, "firm_or_interruptible": "firm", "status": "applied", "expected_date": "2027-09",
         "ilds_anchor": "N", "waiting_for": "SP-01", "notes": "SYNTHETIC: deferred application DC-3"},
        {"load_ref": "CL-02", "category": "industrial_park", "substation": "Namanve", "connection_kv": 33.0, "mw": 15.0,
         "mw_basis": "contracted", "pf": 0.92, "firm_or_interruptible": "firm", "status": "signed", "expected_date": "2028-01",
         "ilds_anchor": "Y", "waiting_for": None, "notes": "SYNTHETIC"},
        {"load_ref": "CL-03", "category": "manufacturing", "substation": "Kapeeka", "connection_kv": 33.0, "mw": 10.0,
         "mw_basis": "expected_peak", "pf": 0.93, "firm_or_interruptible": "firm", "status": "signed", "expected_date": "2029-03",
         "ilds_anchor": "N", "waiting_for": None, "notes": "SYNTHETIC"},
        {"load_ref": "CL-04", "category": "manufacturing", "substation": "Kawanda", "connection_kv": 33.0, "mw": 20.0,
         "mw_basis": "requested", "pf": 0.92, "firm_or_interruptible": "unknown", "status": "pending", "expected_date": "2027-12",
         "ilds_anchor": "N", "waiting_for": "SP-01", "notes": "SYNTHETIC: deferred application IND-7; not in the 2030 case"},
    ])
    sgr = pd.DataFrame([
        {"point_id": "SYN-SGR-01", "name": "Synthetic traction substation 1", "substation": "Mukono", "connection_kv": 132.0,
         "mw": 12.0, "expected_date": "2031-01", "status": "planned", "lat": 0.372, "lon": 32.790, "load_ref": None,
         "notes": "SYNTHETIC"},
        {"point_id": "SYN-SGR-02", "name": "Synthetic traction substation 2", "substation": "Namanve", "connection_kv": 132.0,
         "mw": 10.0, "expected_date": "2031-06", "status": "planned", "lat": 0.352, "lon": 32.700, "load_ref": None,
         "notes": "SYNTHETIC"},
    ])
    return {"projects": projects, "committed_loads": loads, "sgr_points": sgr, "ilds_sites": pd.DataFrame()}


# --------------------------------------------------------------------------- T09
SITES = [  # id, name, district, kind, status, area ha, lat, lon, allocated MW, boundary?
    ("SYN-S01", "Synthetic site 01 (Namanve area)", "Mukono", "uia_park", "serviced", 220, 0.3620, 32.7010, 25, True),
    ("SYN-S02", "Synthetic site 02 (Mukono east)", "Mukono", "gazetted_land", "gazetted", 140, 0.3700, 32.7900, 12, True),
    ("SYN-S03", "Synthetic site 03 (Kapeeka area)", "Nakaseke", "uia_park", "planned", 300, 0.7700, 32.3950, 18, True),
    ("SYN-S04", "Synthetic site 04 (Matugga)", "Wakiso", "private_estate", "proposed", 60, 0.4700, 32.5300, 8, False),
    ("SYN-S05", "Synthetic site 05 (Kawanda north)", "Wakiso", "free_zone", "serviced", 90, 0.4450, 32.5450, 20, True),
    ("SYN-S06", "Synthetic site 06 (Mpigi road)", "Mpigi", "gazetted_land", "gazetted", 180, 0.2300, 32.3300, 10, False),
    ("SYN-S07", "Synthetic site 07 (wetland edge)", "Wakiso", "private_estate", "proposed", 75, 0.3300, 32.5250, 6, True),
    ("SYN-S08", "Synthetic site 08 (Masaka)", "Masaka", "uia_park", "planned", 160, -0.3200, 31.7500, 9, False),
    ("SYN-S09", "Synthetic site 09 (Kabulasoke)", "Gomba", "gazetted_land", "proposed", 400, 0.1000, 31.9900, 5, False),
    ("SYN-S10", "Synthetic site 10 (Bweyogerere)", "Wakiso", "uia_park", "serviced", 110, 0.3550, 32.6600, 15, True),
]


def square_ha(lat: float, lon: float, area_ha: float, skew: float = 0.0) -> list:
    """A MultiPolygon square of about area_ha centred on (lat, lon), as GeoJSON coordinates."""
    side_km = math.sqrt(area_ha / 100.0)
    dlat = side_km / 2 / 110.57
    dlon = side_km / 2 / (111.32 * math.cos(math.radians(lat)))
    ring = [[lon - dlon, lat - dlat], [lon + dlon + skew, lat - dlat], [lon + dlon, lat + dlat],
            [lon - dlon - skew, lat + dlat], [lon - dlon, lat - dlat]]
    return [[ring]]


def t09_tables(w: World) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    rows, feats = [], []
    for sid, name, district, kind, status, area, lat, lon, mw, has_b in SITES:
        near = min(CENTRAL, key=lambda c: haversine_km(lat, lon, SUBSTATIONS[c][3], SUBSTATIONS[c][4]))
        rows.append({"site_id": sid, "name": name, "district": district, "kind": kind, "status": status,
                     "owner": "Synthetic agency" if kind == "uia_park" else "Synthetic owner", "area_ha": float(area),
                     "available_ha": float(round(area * 0.4)), "lat": lat, "lon": lon, "allocated_load_mw": float(mw),
                     "operating_load_mw": float(round(mw * 0.3, 1)) if status == "serviced" else 0.0,
                     "allocated_load_year": 2029, "planned_supply_point": ss_name(near),
                     "planned_supply_kv": 33.0 if mw <= 20 else 132.0, "land_confirmed": "Y" if status != "proposed" else "N",
                     "target_sectors": "agro-processing; light manufacturing", "source": "SYNTHETIC", "notes": "SYNTHETIC site"})
        if has_b:
            feats.append({"geometry": {"type": "MultiPolygon", "coordinates": square_ha(lat, lon, area, 0.001)},
                          "properties": {"site_id": sid, "name": name, "status": status, "boundary_source": "SYNTHETIC square"}})
    overrides = pd.DataFrame([
        {"site_id": "SYN-S01", "metric": "km_to_trunk_road", "value": 0.8, "unit": "km", "source": "SYNTHETIC site visit",
         "notes": "SYNTHETIC"},
        {"site_id": "SYN-S03", "metric": "mean_slope_pct", "value": 3.5, "unit": "%", "source": "SYNTHETIC survey",
         "notes": "SYNTHETIC"},
    ])
    return {"sites": pd.DataFrame(rows), "metric_overrides": overrides}, feats


# --------------------------------------------------------------------------- T10 and T11
def t10_tables() -> dict[str, pd.DataFrame]:
    rows = []
    for scen, rate in (("low", 5.0), ("base", 7.0), ("high", 9.0)):
        rows.append({"scope": "central", "substation": None, "year_from": 2026, "year_to": 2030, "rate_pct_per_yr": rate,
                     "scenario": scen, "source": "SYNTHETIC placeholder growth", "measure": "peak_demand",
                     "derivation": f"SYNTHETIC: {rate} % a year compound", "includes_spot_loads": "N",
                     "status": "placeholder", "notes": "SYNTHETIC"})
    return {"growth_rates": pd.DataFrame(rows)}


def t11_tables(w: World) -> dict[str, pd.DataFrame]:
    r = w.recon.set_index("month")
    mm = w.meter_month
    est = mm[(mm["month"] == PLANTED_ESTIMATED_MONTH) & (mm["meter_id"] == ESTIMATED_METER) & (mm["direction"] == "export")].iloc[0]
    est_err = float(est["energy_mwh"] - est["reported_mwh"])
    feb = r.loc[PLANTED_METER_ERROR_MONTH]
    dec = r.loc[PLANTED_ESTIMATED_MONTH]
    rows = [
        {"month": PLANTED_ESTIMATED_MONTH, "basis": "central_boundary", "run_id": None,
         "gap_mwh": round(dec["engine_emulated_mwh"] - dec["reported_loss_mwh"], 1), "gap_pct": round(dec["expected_gap_pct"], 1),
         "cause_code": "data_gap",
         "explanation": (f"SYNTHETIC: the Mbarara tie export meter {ESTIMATED_METER} lost data in December 2025 and NCC "
                         "estimated its reading about 12 % low, so the boundary balance overstates the Central loss."),
         "quantified_mwh": round(est_err, 1), "quantification_note": "SYNTHETIC: true export minus the estimated reading",
         "evidence_ref": f"SYNTHETIC: T03 boundary_meters {ESTIMATED_METER} estimated = Y", "author": "[SYN]",
         "reviewed_by": "[SYN-NCC]", "review_date": date(2026, 10, 30), "review_comment": "SYNTHETIC: accepted"},
        {"month": PLANTED_METER_ERROR_MONTH, "basis": "central_boundary", "run_id": None,
         "gap_mwh": round(feb["engine_emulated_mwh"] - feb["reported_loss_mwh"], 1), "gap_pct": round(feb["expected_gap_pct"], 1),
         "cause_code": "meter_error",
         "explanation": (f"SYNTHETIC: the Karuma import meter {METER_ERROR_METER} over-read after a CT ratio change in "
                         "February 2026; the boundary balance overstates the Central loss by about 15 %."),
         "quantified_mwh": round(METER_ERROR_SHARE * feb["truth_loss_mwh"], 1),
         "quantification_note": "SYNTHETIC: corrected reading from the check meter minus the main meter",
         "evidence_ref": f"SYNTHETIC: NCC meter change record for {METER_ERROR_METER}", "author": "[SYN]",
         "reviewed_by": "[SYN-NCC]", "review_date": date(2026, 10, 30), "review_comment": "SYNTHETIC: accepted"},
    ]
    return {"explanations": pd.DataFrame(rows)}


# --------------------------------------------------------------------------- T13
def t13_tables(w: World, n1: list[dict], asset_age: pd.DataFrame) -> dict[str, pd.DataFrame]:
    criteria = pd.DataFrame([
        {"criterion": "n1_rating_set", "applies_to": "all", "value": "continuous", "unit": None,
         "source": "SYNTHETIC planning manual", "notes": "SYNTHETIC"},
        {"criterion": "max_loading_pct", "applies_to": "all", "value": "100", "unit": "%", "source": "SYNTHETIC planning manual",
         "notes": "SYNTHETIC"},
        {"criterion": "v_min_pu", "applies_to": "132 kV and above", "value": "0.95", "unit": "pu",
         "source": "SYNTHETIC grid code", "notes": "SYNTHETIC"},
        {"criterion": "v_max_pu", "applies_to": "132 kV and above", "value": "1.05", "unit": "pu",
         "source": "SYNTHETIC grid code", "notes": "SYNTHETIC"},
        {"criterion": "contingency_set", "applies_to": "all", "value": "every Central line circuit and transformer",
         "unit": None, "source": "SYNTHETIC planning manual", "notes": "SYNTHETIC"},
    ])
    studies = pd.DataFrame([{"study_id": "SYN-ST-01", "title": "SYNTHETIC: Central N-1 study, September 2026 peak",
                             "study_date": date(2026, 10, 1), "case_year": 2026, "loading_condition": "peak",
                             "case_id": "SYNTH-PEAK", "tool": "other",
                             "contingency_set": "every Central 132 and 220 kV circuit and transformer",
                             "report_ref": "SYNTHETIC report, chapter 5", "notes": "SYNTHETIC"}])
    res = []
    for r in n1:
        res.append({"study_id": "SYN-ST-01", "case_id": "SYNTH-PEAK", **r})
    costs = pd.DataFrame([
        {"item": "reconductor_acsr_to_accc_per_km", "kv": 132.0, "lv_kv": None, "conductor": "ACCC Bear-size",
         "unit": "per circuit-km", "cost": 85000.0, "cost_low": 70000.0, "cost_high": 110000.0, "currency": "USD",
         "price_year": 2025, "includes": "SYNTHETIC: supply and stringing, no taxes", "source": "SYNTHETIC", "notes": None},
        {"item": "new_line_per_km", "kv": 132.0, "lv_kv": None, "conductor": "ACSR Bear", "unit": "per circuit-km",
         "cost": 180000.0, "cost_low": 150000.0, "cost_high": 240000.0, "currency": "USD", "price_year": 2025,
         "includes": "SYNTHETIC", "source": "SYNTHETIC", "notes": None},
        {"item": "transformer", "kv": 220.0, "lv_kv": 132.0, "conductor": "", "unit": "per 250 MVA unit", "cost": 4.5e6,
         "cost_low": 3.8e6, "cost_high": 5.5e6, "currency": "USD", "price_year": 2025, "includes": "SYNTHETIC: with bays",
         "source": "SYNTHETIC", "notes": None},
        {"item": "transformer", "kv": 132.0, "lv_kv": 33.0, "conductor": "", "unit": "per 63 MVA unit", "cost": 1.6e6,
         "cost_low": 1.3e6, "cost_high": 2.0e6, "currency": "USD", "price_year": 2025, "includes": "SYNTHETIC",
         "source": "SYNTHETIC", "notes": None},
        {"item": "capacitor_bank_per_mvar", "kv": 33.0, "lv_kv": None, "conductor": "", "unit": "per MVAr", "cost": 25000.0,
         "cost_low": 20000.0, "cost_high": 35000.0, "currency": "USD", "price_year": 2025, "includes": "SYNTHETIC",
         "source": "SYNTHETIC", "notes": None},
        {"item": "feeder_33kv_per_km", "kv": 33.0, "lv_kv": None, "conductor": "AAAC 150", "unit": "per km", "cost": 35000.0,
         "cost_low": 28000.0, "cost_high": 45000.0, "currency": "USD", "price_year": 2025, "includes": "SYNTHETIC",
         "source": "SYNTHETIC", "notes": None},
        {"item": "line_bay", "kv": 132.0, "lv_kv": None, "conductor": "", "unit": "per bay", "cost": 900000.0,
         "cost_low": 750000.0, "cost_high": 1.1e6, "currency": "USD", "price_year": 2025, "includes": "SYNTHETIC",
         "source": "SYNTHETIC", "notes": None},
    ])
    return {"criteria": criteria, "studies": studies, "contingency_results": pd.DataFrame(res), "unit_costs": costs,
            "commissioning_years": asset_age}


# --------------------------------------------------------------------------- open layers
def _poly(coords: list[tuple[float, float]]) -> list:
    ring = [[lon, lat] for lon, lat in coords]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return [ring]


def open_layers() -> dict[str, list[dict]]:
    """Crude, clearly synthetic context layers: lake, protected areas, wetlands, roads, towns."""
    lake = [{"geometry": {"type": "Polygon", "coordinates": _poly([
        (32.25, 0.00), (32.45, 0.05), (32.62, 0.22), (32.80, 0.27), (33.05, 0.30), (33.20, 0.40), (33.40, 0.30),
        (33.80, 0.10), (33.90, -1.00), (32.00, -1.00), (31.82, -0.60), (31.86, -0.25), (32.10, -0.05)])},
        "properties": {"name": "Synthetic lake (Lake Victoria, approximate)", "source": "SYNTHETIC"}}]
    protected = [
        {"geometry": {"type": "Polygon", "coordinates": _poly([(32.90, 0.40), (33.05, 0.40), (33.05, 0.52), (32.90, 0.52)])},
         "properties": {"name": "Synthetic forest reserve A", "designation": "forest reserve", "source": "SYNTHETIC"}},
        {"geometry": {"type": "Polygon", "coordinates": _poly([(32.15, 0.58), (32.27, 0.58), (32.27, 0.66), (32.15, 0.66)])},
         "properties": {"name": "Synthetic forest reserve B", "designation": "forest reserve", "source": "SYNTHETIC"}},
    ]
    wetlands = [
        {"geometry": {"type": "Polygon", "coordinates": _poly([(32.515, 0.322), (32.532, 0.322), (32.532, 0.338), (32.515, 0.338)])},
         "properties": {"name": "Synthetic wetland A", "source": "SYNTHETIC"}},
        {"geometry": {"type": "Polygon", "coordinates": _poly([(32.70, 0.320), (32.73, 0.320), (32.73, 0.336), (32.70, 0.336)])},
         "properties": {"name": "Synthetic wetland B", "source": "SYNTHETIC"}},
    ]
    roads = [
        {"geometry": {"type": "LineString", "coordinates": [[32.58, 0.315], [32.70, 0.355], [32.76, 0.36], [33.0, 0.40], [33.20, 0.44]]},
         "properties": {"name": "Synthetic trunk road east", "class": "trunk", "source": "SYNTHETIC"}},
        {"geometry": {"type": "LineString", "coordinates": [[32.58, 0.315], [32.40, 0.22], [32.10, 0.0], [31.73, -0.33]]},
         "properties": {"name": "Synthetic trunk road south-west", "class": "trunk", "source": "SYNTHETIC"}},
        {"geometry": {"type": "LineString", "coordinates": [[32.58, 0.315], [32.53, 0.45], [32.47, 0.84], [32.30, 1.50]]},
         "properties": {"name": "Synthetic trunk road north", "class": "trunk", "source": "SYNTHETIC"}},
        {"geometry": {"type": "LineString", "coordinates": [[32.53, 0.30], [32.55, 0.38], [32.63, 0.39], [32.70, 0.36]]},
         "properties": {"name": "Synthetic northern bypass", "class": "primary", "source": "SYNTHETIC"}},
    ]
    towns = [
        {"geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {"name": n, "population": pop, "source": "SYNTHETIC"}}
        for n, lat, lon, pop in (("Kampala (synthetic)", 0.315, 32.582, 1700000), ("Mukono (synthetic)", 0.355, 32.755, 160000),
                                 ("Entebbe (synthetic)", 0.06, 32.46, 90000), ("Masaka (synthetic)", -0.33, 31.73, 110000),
                                 ("Jinja (synthetic)", 0.43, 33.20, 80000), ("Luwero (synthetic)", 0.84, 32.47, 50000),
                                 ("Mpigi (synthetic)", 0.23, 32.31, 40000), ("Wakiso (synthetic)", 0.40, 32.48, 70000))
    ]
    return {"lake": lake, "protected_area": protected, "wetland": wetlands, "road": roads, "town": towns}
