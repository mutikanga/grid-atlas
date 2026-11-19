"""The synthetic Central network: substations, buses, lines, transformers, plants and loads.

This module holds the one definition of the fake network that every synthetic file is
derived from (T01, T02, T12, SCADA point lists, and so on), and builds the "truth"
pandapower model used to simulate the year.

The layout follows docs/dev/contracts.md section 2 and the build plan:
- BUJ 220 kV is the slack (Nile infeed); NAL 132 kV is a PV infeed;
- KAR 400 kV feeds Kawanda through two 400/220 kV transformers;
- MBR is a fixed-P export tie at Masaka 220 kV, modelled as a load;
- KAW is 400/220/132/33 kV, MSK 220/132/33 kV, the other Central sites 132/33 kV.

Parameters are typical values (from config/conductors.csv and
config/transformer_defaults.csv as they stood on 1 Nov 2026). They are NOT UETCL data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandapower as pp

VARIANTS = ("base", "line_bound", "dirty")

# Line resistance temperature coefficient for aluminium, per degree C.
ALPHA_AL = 0.00403
# Conductor temperature of the truth model. The engine defaults to 50 C: a deliberate small error.
TRUTH_R_TEMP_C = 60.0
# Route length = straight-line distance x this factor (lines rarely run straight).
ROUTE_FACTOR = 1.12

# --------------------------------------------------------------------------- substations
# code: (name, district, in_central, lat, lon, model voltage levels in kV)
# Names and coordinates match config/substations.csv (F2's synthetic defaults).
SUBSTATIONS: dict[str, tuple[str, str, bool, float, float, tuple[int, ...]]] = {
    "KAW": ("Kawanda", "Wakiso", True, 0.4170, 32.5350, (400, 220, 132, 33)),
    "MUT": ("Mutundwe", "Wakiso", True, 0.2880, 32.5470, (132, 33)),
    "LUG": ("Lugogo", "Kampala", True, 0.3290, 32.6010, (132, 33)),
    "KNO": ("Kampala North", "Kampala", True, 0.3470, 32.5760, (132, 33)),
    "QWY": ("Queensway", "Kampala", True, 0.3060, 32.5860, (132, 33)),
    "NMV": ("Namanve", "Mukono", True, 0.3570, 32.6890, (132, 33)),
    "MUK": ("Mukono", "Mukono", True, 0.3530, 32.7550, (132, 33)),
    "KAP": ("Kapeeka", "Nakaseke", True, 0.7830, 32.3830, (132, 33)),
    "KBS": ("Kabulasoke", "Gomba", True, 0.0900, 31.9700, (132, 33)),
    "NKG": ("Nkonge", "Sembabule", True, -0.0300, 31.7400, (132, 33)),
    "MSK": ("Masaka", "Masaka", True, -0.3350, 31.7150, (220, 132, 33)),
    "BUJ": ("Bujagali", "Jinja", False, 0.4960, 33.1400, (220,)),
    "NAL": ("Nalubaale", "Jinja", False, 0.4440, 33.1840, (132,)),
    "MBR": ("Mbarara", "Mbarara", False, -0.6000, 30.6500, (220,)),
    "KAR": ("Karuma", "Kiryandongo", False, 2.2440, 32.2440, (400,)),
}
CENTRAL = [c for c, s in SUBSTATIONS.items() if s[2]]

# --------------------------------------------------------------------------- conductors
# (conductor, kV): r at 20 C (ohm/km per circuit), x (ohm/km), b (uS/km), continuous rating (MVA), bundle.
CONDUCTORS: dict[tuple[str, int], tuple[float, float, float, float, int]] = {
    ("ACSR Wolf", 132): (0.1828, 0.4170, 2.720, 98.3, 1),
    ("ACSR Lynx", 132): (0.1576, 0.4123, 2.752, 107.5, 1),
    ("ACSR Bear", 132): (0.1093, 0.4008, 2.833, 137.2, 1),
    ("ACSR Twin Bear", 220): (0.05465, 0.3088, 3.634, 457.3, 2),
    # Not in config/conductors.csv yet (F3a asked to add it): a typical quad 400 kV bundle.
    ("ACSR Quad Bersfort", 400): (0.0112, 0.2640, 4.300, 1500.0, 4),
}
EMERG_FACTOR_LINE = 1.10
EMERG_FACTOR_TRAFO = 1.20

# --------------------------------------------------------------------------- lines
# (end A, end B, kV, circuit, conductor, commissioning year, tower group, status)
LINES: list[tuple[str, str, int, int, str, int, str, str]] = [
    ("BUJ", "KAW", 220, 1, "ACSR Twin Bear", 2007, "BUJ-KAW-220", "existing"),
    ("BUJ", "KAW", 220, 2, "ACSR Twin Bear", 2007, "BUJ-KAW-220", "existing"),
    ("KAW", "MSK", 220, 1, "ACSR Twin Bear", 2018, "KAW-MSK-220", "existing"),
    ("KAW", "MSK", 220, 2, "ACSR Twin Bear", 2018, "KAW-MSK-220", "existing"),
    ("MBR", "MSK", 220, 1, "ACSR Twin Bear", 2017, "MBR-MSK-220", "existing"),
    ("KAR", "KAW", 400, 1, "ACSR Quad Bersfort", 2024, "KAR-KAW-400", "existing"),
    ("KAW", "MUT", 132, 1, "ACSR Wolf", 1993, "KAW-MUT-132", "existing"),
    ("KAW", "MUT", 132, 2, "ACSR Wolf", 1993, "KAW-MUT-132", "existing"),
    ("KAW", "KNO", 132, 1, "ACSR Bear", 2001, "KAW-KNO-132-A", "existing"),
    ("KNO", "LUG", 132, 1, "ACSR Bear", 1995, "KNO-LUG-132", "existing"),
    ("LUG", "QWY", 132, 1, "ACSR Bear", 1990, "LUG-QWY-132", "existing"),
    ("MUT", "QWY", 132, 1, "ACSR Wolf", 1992, "MUT-QWY-132", "existing"),
    ("LUG", "NAL", 132, 1, "ACSR Bear", 1990, "LUG-NAL-132", "existing"),
    ("LUG", "NAL", 132, 2, "ACSR Bear", 1990, "LUG-NAL-132", "existing"),
    ("MUK", "NAL", 132, 1, "ACSR Bear", 2004, "MUK-NAL-132", "existing"),
    ("MUK", "NMV", 132, 1, "ACSR Lynx", 2008, "MUK-NMV-132", "existing"),
    ("LUG", "NMV", 132, 1, "ACSR Bear", 2010, "LUG-NMV-132", "existing"),
    ("KBS", "MUT", 132, 1, "ACSR Lynx", 2012, "KBS-MUT-132", "existing"),
    ("KBS", "NKG", 132, 1, "ACSR Lynx", 2014, "KBS-NKG-132", "existing"),
    ("MSK", "NKG", 132, 1, "ACSR Lynx", 2014, "MSK-NKG-132", "existing"),
    ("KAP", "KAW", 132, 1, "ACSR Wolf", 2020, "KAP-KAW-132", "existing"),
    # Planned: a second Kapeeka - Kawanda circuit that ends the radial supply (T08 project SP-03, 2029).
    ("KAP", "KAW", 132, 2, "ACSR Wolf", 2029, "KAP-KAW-132-B", "planned"),
    # Planned: the second Kawanda - Kampala North circuit (T08 project SP-02, 2028).
    ("KAW", "KNO", 132, 2, "ACSR Bear", 2028, "KAW-KNO-132-B", "planned"),
]

# --------------------------------------------------------------------------- transformers
# (id, substation, hv kV, lv kV, MVA, commissioning year, status, tap position)
TRAFOS: list[tuple[str, str, int, int, float, int, str, int]] = [
    ("T-KAW-1", "KAW", 220, 132, 250, 1998, "existing", 0),
    ("T-KAW-2", "KAW", 220, 132, 250, 2009, "existing", 0),
    ("T-KAW-3", "KAW", 220, 132, 250, 2027, "planned", 0),  # T08 project SP-01, relief for KAW
    ("T-KAW-4", "KAW", 400, 220, 350, 2024, "existing", 0),
    ("T-KAW-5", "KAW", 400, 220, 350, 2024, "existing", 0),
    ("T-KAW-6", "KAW", 132, 33, 90, 2003, "existing", -2),
    ("T-KAW-7", "KAW", 132, 33, 90, 2015, "existing", -2),
    ("T-MSK-1", "MSK", 220, 132, 125, 2018, "existing", 0),
    ("T-MSK-2", "MSK", 220, 132, 125, 2021, "existing", 0),
    ("T-MSK-3", "MSK", 132, 33, 63, 1996, "existing", -3),
    ("T-MSK-4", "MSK", 132, 33, 63, 2012, "existing", -3),
    ("T-MUT-1", "MUT", 132, 33, 150, 1993, "existing", -3),
    ("T-MUT-2", "MUT", 132, 33, 150, 2006, "existing", -3),
    ("T-LUG-1", "LUG", 132, 33, 100, 1991, "existing", -2),
    ("T-LUG-2", "LUG", 132, 33, 100, 2011, "existing", -2),
    ("T-KNO-1", "KNO", 132, 33, 80, 1995, "existing", -2),
    ("T-KNO-2", "KNO", 132, 33, 80, 2013, "existing", -2),
    ("T-QWY-1", "QWY", 132, 33, 80, 1990, "existing", -2),
    ("T-QWY-2", "QWY", 132, 33, 80, 2005, "existing", -2),
    ("T-NMV-1", "NMV", 132, 33, 63, 2008, "existing", 0),
    ("T-NMV-2", "NMV", 132, 33, 63, 2016, "existing", 0),
    ("T-MUK-1", "MUK", 132, 33, 63, 2004, "existing", -1),
    ("T-KAP-1", "KAP", 132, 33, 40, 2020, "existing", -4),
    ("T-KBS-1", "KBS", 132, 33, 40, 2012, "existing", -4),
    ("T-NKG-1", "NKG", 132, 33, 40, 2014, "existing", -4),
]
# The line_bound variant makes the Kawanda 220/132 kV units big enough that the
# Kawanda - Mutundwe lines bind first in the Kawanda sweep.
LINE_BOUND_KAW_MVA = 400.0
KAW_220_132 = ("T-KAW-1", "T-KAW-2", "T-KAW-3")

# Typical transformer data by size, from config/transformer_defaults.csv:
# (MVA from, MVA to, vk %, vkr %, iron loss % of rating, no-load current %)
TRAFO_DEFAULTS = [
    (0, 20, 10.0, 0.60, 0.10, 0.15),
    (20, 40, 10.5, 0.45, 0.08, 0.10),
    (40, 80, 12.5, 0.35, 0.06, 0.08),
    (80, 160, 12.5, 0.30, 0.05, 0.06),
    (160, 400, 14.0, 0.25, 0.04, 0.05),
    (400, 10000, 15.0, 0.20, 0.03, 0.04),
]

# --------------------------------------------------------------------------- plants
# (gen id, plant code, plant name, substation, kV, technology, control, p_max, p_min, q_min, q_max, vm_pu, year)
GENS: list[tuple] = [
    ("G-BUJH-1", "BUJH", "Bujagali", "BUJ", 220, "hydro", "slack", 255.0, 0.0, -150.0, 150.0, 1.04, 2012),
    ("G-NALH-1", "NALH", "Nalubaale/Kiira", "NAL", 132, "hydro", "PV", 380.0, 40.0, -150.0, 200.0, 1.03, 1954),
    ("G-KARH-1", "KARH", "Karuma", "KAR", 400, "hydro", "PV", 600.0, 0.0, -300.0, 300.0, 1.04, 2024),
    ("G-NMVT-1", "NMVT", "Namanve thermal", "NMV", 33, "thermal", "PQ", 50.0, 0.0, -20.0, 30.0, None, 2008),
    ("G-KBSS-1", "KBSS", "Kabulasoke solar", "KBS", 33, "solar", "PQ", 20.0, 0.0, 0.0, 0.0, None, 2019),
    ("G-NKGS-1", "NKGS", "Nkonge solar", "NKG", 33, "solar", "PQ", 20.0, 0.0, 0.0, 0.0, None, 2021),
    ("G-KAPS-1", "KAPS", "Kapeeka solar", "KAP", 33, "solar", "PQ", 20.0, 0.0, 0.0, 0.0, None, 2022),
]

# --------------------------------------------------------------------------- loads
# Substation: (peak MW in Sep 2026 at the class's own peak hour, load class, power factor)
# The coincident Central peak comes out at about 600 MW.
LOADS: dict[str, tuple[float, str, float]] = {
    "KAW": (72.0, "mixed", 0.95),
    "MUT": (127.0, "urban_residential", 0.94),
    "LUG": (92.0, "urban_commercial", 0.95),
    "KNO": (64.0, "urban_commercial", 0.95),
    "QWY": (68.0, "urban_commercial", 0.95),
    "NMV": (42.0, "industrial", 0.92),
    "MUK": (31.0, "mixed", 0.94),
    "KAP": (23.0, "mixed", 0.95),
    "KBS": (17.0, "mixed", 0.95),
    "NKG": (14.0, "mixed", 0.95),
    "MSK": (48.0, "mixed", 0.94),
}
# The MBR export tie, modelled as a load at Mbarara 220 kV (positive = power leaving Central).
MBR_LOAD_ID = "D-MBR-1"

# Shunts: (id, bus, q_mvar in pandapower convention: + absorbs, - injects)
SHUNTS: list[tuple[str, str, float]] = [
    ("C-KAW-1", "KAW-400-1", 60.0),   # 400 kV line reactor, absorbs the long line's charging
    ("C-KAW-2", "KAW-33-1", -20.0),   # 33 kV capacitor banks
    ("C-MUT-1", "MUT-33-1", -30.0),
    ("C-LUG-1", "LUG-33-1", -25.0),
    ("C-KNO-1", "KNO-33-1", -15.0),
    ("C-QWY-1", "QWY-33-1", -15.0),
    ("C-MSK-1", "MSK-33-1", -15.0),
    ("C-KBS-1", "KBS-33-1", -5.0),
    ("C-KAP-1", "KAP-33-1", -5.0),
]


# --------------------------------------------------------------------------- helpers
def bus_id(ss: str, kv: int, n: int = 1) -> str:
    """Canonical bus id, for example KAW-132-1."""
    return f"{ss}-{kv}-{n}"


def line_id(a: str, b: str, kv: int, ckt: int) -> str:
    """Canonical line id with the two ends in alphabetical order, for example L-KAW-MUT-132-1."""
    x, y = sorted((a, b))
    return f"L-{x}-{y}-{kv}-{ckt}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two points given in degrees."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def route_km(a: str, b: str) -> float:
    """Route length between two substations: straight distance x ROUTE_FACTOR, to 0.1 km."""
    sa, sb = SUBSTATIONS[a], SUBSTATIONS[b]
    return round(haversine_km(sa[3], sa[4], sb[3], sb[4]) * ROUTE_FACTOR, 1)


def trafo_typical(sn_mva: float) -> tuple[float, float, float, float]:
    """vk %, vkr %, iron loss kW and no-load current % for a transformer of this size."""
    for lo, hi, vk, vkr, pfe_pct, i0 in TRAFO_DEFAULTS:
        if lo <= sn_mva < hi:
            return vk, vkr, round(pfe_pct / 100 * sn_mva * 1000, 1), i0
    raise ValueError(f"no transformer default for {sn_mva} MVA")


def r_at(r20: float, temp_c: float) -> float:
    """Resistance at temp_c from the 20 C value: R_T = R_20 (1 + alpha (T - 20))."""
    return r20 * (1 + ALPHA_AL * (temp_c - 20.0))


def rate_to_ka(rate_mva: float, kv: float) -> float:
    """Thermal current limit in kA for a rating in MVA at a nominal voltage."""
    return rate_mva / (math.sqrt(3) * kv)


# --------------------------------------------------------------------------- the network tables
@dataclass
class Network:
    """The synthetic network as plain tables (one row per element, canonical ids)."""

    variant: str
    substations: pd.DataFrame
    buses: pd.DataFrame
    lines: pd.DataFrame
    trafos: pd.DataFrame
    gens: pd.DataFrame
    loads: pd.DataFrame
    shunts: pd.DataFrame

    def central_line_ids(self) -> list[str]:
        """Lines with BOTH ends in Central: the ones inside the boundary-meter perimeter."""
        m = self.lines["a_central"] & self.lines["b_central"]
        return self.lines.loc[m, "line_id"].tolist()

    def tie_lines(self) -> pd.DataFrame:
        """Lines crossing the Central boundary (exactly one end in Central)."""
        m = self.lines["a_central"] ^ self.lines["b_central"]
        return self.lines[m & (self.lines["status"] == "existing")]


def build_network(variant: str = "base") -> Network:
    """Assemble the network tables for a variant (base, line_bound or dirty).

    'dirty' only changes the files written, not the network, so it equals 'base' here.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANTS}")
    subs = pd.DataFrame(
        [
            {"ss_code": c, "name": s[0], "district": s[1], "in_central": s[2], "lat": s[3], "lon": s[4],
             "kv_levels": "/".join(str(k) for k in s[5])}
            for c, s in SUBSTATIONS.items()
        ]
    )
    buses = pd.DataFrame(
        [
            {"bus_id": bus_id(c, kv), "ss_code": c, "vn_kv": float(kv), "in_central": s[2]}
            for c, s in SUBSTATIONS.items()
            for kv in s[5]
        ]
    )
    line_rows = []
    for a, b, kv, ckt, cond, year, tower, status in LINES:
        r20, x, bb, rate, bundle = CONDUCTORS[(cond, kv)]
        x_, y_ = sorted((a, b))
        line_rows.append(
            {
                "line_id": line_id(a, b, kv, ckt), "ss_a": x_, "ss_b": y_, "kv": kv, "circuit": ckt,
                "from_bus": bus_id(x_, kv), "to_bus": bus_id(y_, kv), "length_km": route_km(a, b),
                "conductor": cond, "bundle": bundle, "r20_ohm_per_km": r20, "x_ohm_per_km": x,
                "b_us_per_km": bb, "rate_cont_mva": rate, "rate_emerg_mva": round(rate * EMERG_FACTOR_LINE, 1),
                "commissioning_year": year, "tower_group": tower, "status": status,
                "a_central": SUBSTATIONS[x_][2], "b_central": SUBSTATIONS[y_][2],
            }
        )
    lines = pd.DataFrame(line_rows)
    trafo_rows = []
    for tid, ss, hv, lv, sn, year, status, tap in TRAFOS:
        if variant == "line_bound" and tid in KAW_220_132:
            sn = LINE_BOUND_KAW_MVA
        vk, vkr, pfe, i0 = trafo_typical(sn)
        trafo_rows.append(
            {
                "trafo_id": tid, "ss_code": ss, "hv_bus": bus_id(ss, hv), "lv_bus": bus_id(ss, lv),
                "vn_hv_kv": float(hv), "vn_lv_kv": float(lv), "sn_mva": float(sn), "vk_percent": vk,
                "vkr_percent": vkr, "pfe_kw": pfe, "i0_percent": i0, "tap_pos": tap,
                "rate_cont_mva": float(sn), "rate_emerg_mva": round(sn * EMERG_FACTOR_TRAFO, 1),
                "commissioning_year": year, "status": status,
            }
        )
    trafos = pd.DataFrame(trafo_rows)
    gens = pd.DataFrame(
        [
            {"gen_id": g[0], "plant_code": g[1], "plant": g[2], "ss_code": g[3], "bus": bus_id(g[3], g[4]),
             "connection_kv": float(g[4]), "technology": g[5], "control": g[6], "p_max_mw": g[7],
             "p_min_mw": g[8], "q_min_mvar": g[9], "q_max_mvar": g[10], "vm_pu": g[11], "cod_year": g[12]}
            for g in GENS
        ]
    )
    load_rows = [
        {"load_id": f"D-{ss}-1", "ss_code": ss, "bus": bus_id(ss, 33), "peak_mw": v[0], "load_class": v[1],
         "pf": v[2], "in_central": True}
        for ss, v in LOADS.items()
    ]
    load_rows.append({"load_id": MBR_LOAD_ID, "ss_code": "MBR", "bus": bus_id("MBR", 220), "peak_mw": 45.0,
                      "load_class": "export", "pf": 0.98, "in_central": False})
    loads = pd.DataFrame(load_rows)
    shunts = pd.DataFrame([{"shunt_id": s[0], "bus": s[1], "q_mvar": s[2]} for s in SHUNTS])
    return Network(variant, subs, buses, lines, trafos, gens, loads, shunts)


# --------------------------------------------------------------------------- the truth model
@dataclass
class TruthNet:
    """A pandapower net plus the index maps from canonical ids to pandapower rows."""

    net: pp.pandapowerNet
    bus: dict[str, int]
    line: dict[str, int]
    trafo: dict[str, int]
    load: dict[str, int]
    gen: dict[str, int]      # PV generators (pandapower gen table)
    sgen: dict[str, int]     # PQ plants (pandapower sgen table)
    slack_gen_id: str


def build_truth_net(nw: Network, *, r_temp_c: float = TRUTH_R_TEMP_C, include_planned: bool = False) -> TruthNet:
    """Build the pandapower model the synthetic 'reality' is simulated with.

    Line R is taken at r_temp_c (60 C for the truth). Planned elements are left out
    unless include_planned is True (the 2030 case).
    """
    net = pp.create_empty_network(name=f"SYNTHETIC truth ({nw.variant})", f_hz=50.0, sn_mva=100.0)
    bus = {}
    for r in nw.buses.itertuples():
        bus[r.bus_id] = pp.create_bus(net, vn_kv=r.vn_kv, name=r.bus_id, max_vm_pu=1.1, min_vm_pu=0.9)
    line = {}
    for r in nw.lines.itertuples():
        if r.status == "planned" and not include_planned:
            continue
        line[r.line_id] = pp.create_line_from_parameters(
            net, bus[r.from_bus], bus[r.to_bus], length_km=r.length_km,
            r_ohm_per_km=r_at(r.r20_ohm_per_km, r_temp_c), x_ohm_per_km=r.x_ohm_per_km,
            c_nf_per_km=r.b_us_per_km / (2 * math.pi * 50.0) * 1000.0,
            max_i_ka=rate_to_ka(r.rate_cont_mva, r.kv), name=r.line_id,
        )
    trafo = {}
    for r in nw.trafos.itertuples():
        if r.status == "planned" and not include_planned:
            continue
        trafo[r.trafo_id] = pp.create_transformer_from_parameters(
            net, bus[r.hv_bus], bus[r.lv_bus], sn_mva=r.sn_mva, vn_hv_kv=r.vn_hv_kv, vn_lv_kv=r.vn_lv_kv,
            vkr_percent=r.vkr_percent, vk_percent=r.vk_percent, pfe_kw=r.pfe_kw, i0_percent=r.i0_percent,
            shift_degree=0.0, tap_side="hv", tap_neutral=0, tap_min=-10, tap_max=10,
            tap_step_percent=1.25, tap_pos=int(r.tap_pos), tap_changer_type="Ratio", name=r.trafo_id,
        )
    load = {}
    for r in nw.loads.itertuples():
        load[r.load_id] = pp.create_load(net, bus[r.bus], p_mw=0.0, q_mvar=0.0, name=r.load_id)
    for r in nw.shunts.itertuples():
        pp.create_shunt(net, bus[r.bus], q_mvar=r.q_mvar, p_mw=0.0, name=r.shunt_id)
    gen, sgen, slack = {}, {}, ""
    for r in nw.gens.itertuples():
        if r.control == "slack":
            pp.create_ext_grid(net, bus[r.bus], vm_pu=r.vm_pu, name=r.gen_id)
            slack = r.gen_id
        elif r.control == "PV":
            gen[r.gen_id] = pp.create_gen(net, bus[r.bus], p_mw=0.0, vm_pu=r.vm_pu, name=r.gen_id,
                                          min_q_mvar=r.q_min_mvar, max_q_mvar=r.q_max_mvar)
        else:
            sgen[r.gen_id] = pp.create_sgen(net, bus[r.bus], p_mw=0.0, q_mvar=0.0, name=r.gen_id)
    return TruthNet(net, bus, line, trafo, load, gen, sgen, slack)


def set_injections(tn: TruthNet, load_p: dict[str, float], load_q: dict[str, float], gen_p: dict[str, float]) -> None:
    """Write one hour's load P/Q and generator P into the truth net (ids not given are left as they are)."""
    net = tn.net
    for lid, p in load_p.items():
        net.load.at[tn.load[lid], "p_mw"] = p
        net.load.at[tn.load[lid], "q_mvar"] = load_q[lid]
    for gid, p in gen_p.items():
        if gid in tn.gen:
            net.gen.at[tn.gen[gid], "p_mw"] = p
        elif gid in tn.sgen:
            net.sgen.at[tn.sgen[gid], "p_mw"] = p


def central_element_mask(nw: Network, tn: TruthNet) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks over the truth net's line and trafo rows: inside the Central meter perimeter."""
    inside = set(nw.central_line_ids())
    lmask = np.array([name in inside for name in tn.net.line["name"]])
    central_ss = {c for c in CENTRAL}
    tss = dict(zip(nw.trafos["trafo_id"], nw.trafos["ss_code"]))
    tmask = np.array([tss[name] in central_ss for name in tn.net.trafo["name"]])
    return lmask, tmask
