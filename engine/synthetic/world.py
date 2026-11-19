"""The simulated synthetic world and the monthly figures every output file is cut from.

``build_world`` runs the truth simulation once; the helpers then give monthly energy,
peaks, sample days, boundary-meter flows and the planted reconciliation figures.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from engine.synthetic.network import CENTRAL, SUBSTATIONS, Network, build_network
from engine.synthetic.timeseries import MONTHS, TruthSeries, make_series, rng_for
from engine.synthetic.truth import TruthResult, simulate

# Names NCC uses in its reports. Most are canonical; a few are deliberate variants that
# config/aliases.csv must resolve (reported to the F2 owner).
NCC_SS_NAMES = {"KAW": "Kawanda S/S", "KNO": "Kampala Nth", "QWY": "Queensway S/S", "MUK": "Mukono S/S"}
NCC_PLANT_NAMES = {
    "BUJH": "Bujagali Hydro", "NALH": "Nalubaale and Kiira", "KARH": "Karuma HPP",
    "NMVT": "Namanve Power Plant", "KBSS": "Kabulasoke Solar Plant", "NKGS": "Nkonge Solar Plant",
    "KAPS": "Kapeeka Solar Plant",
}
# Planted reconciliation errors (see truth.json): month -> kind
PLANTED_METER_ERROR_MONTH = "2026-02"      # +15 % of the Central loss: an over-reading import meter
PLANTED_ESTIMATED_MONTH = "2025-12"        # an estimated boundary reading 12 % below the true value
METER_ERROR_SHARE = 0.15
ESTIMATED_READING_ERROR = -0.12
ESTIMATED_METER = "MSK-M01"                # the MBR tie export meter at Masaka
METER_ERROR_METER = "KAW-M03"              # the Karuma 400 kV import meter at Kawanda
BALANCING_METER = "KAW-M01"                # absorbs the rounding so the loss lands on its target
NOISE_PCT = 2.0                            # meter noise on the Central loss in normal months
ENGINE_SAFE_PCT = 6.0                      # keep normal months' expected engine gap inside this


def ss_name(code: str) -> str:
    """Canonical substation name (config/substations.csv)."""
    return SUBSTATIONS[code][0]


def ncc_name(code: str) -> str:
    """The name NCC writes for a substation (sometimes a variant)."""
    return NCC_SS_NAMES.get(code, ss_name(code))


@dataclass
class Meter:
    """A boundary meter at the Central end of a tie line."""

    meter_id: str
    line_id: str
    ss: str          # Central end
    far: str         # outside end
    kv: int
    at_from: bool    # True if the Central end is the line's from bus


@dataclass
class World:
    """Everything derived from one truth simulation."""

    seed: int
    variant: str
    nw: Network
    ts: TruthSeries
    tr: TruthResult
    load_col: dict[str, int] = field(default_factory=dict)
    gen_col: dict[str, int] = field(default_factory=dict)
    line_col: dict[str, int] = field(default_factory=dict)
    trafo_col: dict[str, int] = field(default_factory=dict)
    bus_col: dict[str, int] = field(default_factory=dict)
    meters: list[Meter] = field(default_factory=list)
    recon: pd.DataFrame | None = None
    meter_month: pd.DataFrame | None = None

    # ---------------------------------------------------------------- basic series
    @property
    def cal(self):
        return self.ts.cal

    def central_load(self) -> np.ndarray:
        """Hourly sum of the 11 Central substation loads (MW)."""
        cols = [self.load_col[f"D-{c}-1"] for c in CENTRAL]
        return self.ts.load_p[:, cols].sum(axis=1)

    def month_mask(self, month: str) -> np.ndarray:
        return self.cal.month == month

    def peak_hour(self, month: str) -> int:
        """Hour position of the month's coincident Central peak."""
        sel = np.where(self.month_mask(month))[0]
        return int(sel[self.central_load()[sel].argmax()])

    def min_hour(self, month: str) -> int:
        sel = np.where(self.month_mask(month))[0]
        return int(sel[self.central_load()[sel].argmin()])

    def sample_days(self, month: str) -> tuple[date, date]:
        """NCC's sample days: the day of the monthly peak, and the day with the lowest energy."""
        cl = self.central_load()
        sel = self.month_mask(month)
        days = np.unique(self.cal.day_index[sel])
        energy = np.array([cl[self.cal.day_index == d].sum() for d in days])
        peak_day = self.cal.days[self.cal.day_index[self.peak_hour(month)]].date()
        low_day = self.cal.days[days[energy.argmin()]].date()
        return peak_day, low_day

    def end_flow(self, line_id: str, ss: str) -> tuple[np.ndarray, np.ndarray]:
        """Hourly P and Q at the given end of a line, + = from that busbar into the line."""
        row = self.nw.lines.set_index("line_id").loc[line_id]
        k = self.line_col[line_id]
        if row["ss_a"] == ss:  # ss_a is the from bus
            return self.tr.line_p_from[:, k], self.tr.line_q_from[:, k]
        return self.tr.line_p_to[:, k], self.tr.line_q_to[:, k]

    def gen_p(self, gen_id: str) -> np.ndarray:
        """Hourly MW of a generator (the slack comes from the load flow)."""
        if gen_id == "G-BUJH-1":
            return self.tr.slack_p
        return self.ts.gen_p[:, self.gen_col[gen_id]]


def _meters(nw: Network) -> list[Meter]:
    """One meter per tie line, at its Central end, numbered per substation."""
    out, count = [], {}
    for r in nw.tie_lines().itertuples():
        ss, far = (r.ss_a, r.ss_b) if r.a_central else (r.ss_b, r.ss_a)
        count[ss] = count.get(ss, 0) + 1
        out.append(Meter(f"{ss}-M{count[ss]:02d}", r.line_id, ss, far, r.kv, at_from=r.a_central))
    return out


def build_world(variant: str, seed: int) -> World:
    """Simulate the synthetic year for a variant and index the results."""
    nw = build_network(variant)
    ts = make_series(nw, seed)
    tr = simulate(nw, ts)
    w = World(seed, variant, nw, ts, tr)
    w.load_col = {lid: i for i, lid in enumerate(ts.load_ids)}
    w.gen_col = {gid: i for i, gid in enumerate(ts.gen_ids)}
    w.line_col = {n: i for i, n in enumerate(tr.line_names)}
    w.trafo_col = {n: i for i, n in enumerate(tr.trafo_names)}
    w.bus_col = {n: i for i, n in enumerate(tr.bus_names)}
    w.meters = _meters(nw)
    w.meter_month, w.recon = reconciliation_design(w)
    return w


# --------------------------------------------------------------------------- reconciliation
def truth_meter_month(w: World) -> pd.DataFrame:
    """True monthly import/export MWh and MVArh at each boundary meter."""
    rows = []
    for m in w.meters:
        p, q = w.end_flow(m.line_id, m.ss)
        imp, exp = np.clip(-p, 0, None), np.clip(p, 0, None)
        qi, qe = np.clip(-q, 0, None), np.clip(q, 0, None)
        for month in MONTHS:
            sel = w.month_mask(month)
            rows.append({"month": month, "meter_id": m.meter_id, "direction": "import",
                         "energy_mwh": imp[sel].sum(), "energy_mvarh": qi[sel].sum()})
            rows.append({"month": month, "meter_id": m.meter_id, "direction": "export",
                         "energy_mwh": exp[sel].sum(), "energy_mvarh": qe[sel].sum()})
    return pd.DataFrame(rows)


def central_plants(w: World) -> list[str]:
    """Generators connected inside Central (their sent-out counts in the boundary balance)."""
    g = w.nw.gens
    return g.loc[g["ss_code"].isin(CENTRAL), "gen_id"].tolist()


def engine_emulation(w: World) -> dict[str, float]:
    """A stand-in for the engine's monthly Central loss estimate, per month (MWh).

    It does what the engine is specified to do, in miniature: R at 50 C, the peak day
    for weekdays and the lowest day for weekends/holidays, each substation's hours scaled
    to its monthly energy. Months with full SCADA use every day. It lets truth.json state
    the expected gap and keeps the planted PASS months robust.
    """
    out = {}
    cal = w.cal
    full_months = {"2026-07", "2026-08", "2026-09"}
    for month in MONTHS:
        sel = w.month_mask(month)
        if month in full_months:
            hrs = np.where(sel)[0]
            weights = np.ones(len(hrs))
        else:
            pk, lo = w.sample_days(month)
            n_wd = len(np.unique(cal.day_index[sel & cal.is_wd]))
            n_nwd = len(np.unique(cal.day_index[sel & ~cal.is_wd]))
            hp = np.where(sel & (cal.hours.normalize() == pd.Timestamp(pk)))[0]
            hl = np.where(sel & (cal.hours.normalize() == pd.Timestamp(lo)))[0]
            hrs = np.concatenate([hp, hl])
            weights = np.concatenate([np.full(len(hp), n_wd), np.full(len(hl), n_nwd)]).astype(float)
        ts2 = copy.copy(w.ts)
        ts2.load_p = w.ts.load_p.copy()
        ts2.load_q = w.ts.load_q.copy()
        energy = w.ts.load_p[sel].sum(axis=0)
        sampled = (w.ts.load_p[hrs] * weights[:, None]).sum(axis=0)
        k = np.where(sampled > 0, energy / sampled, 1.0)
        ts2.load_p[hrs] = w.ts.load_p[hrs] * k
        ts2.load_q[hrs] = w.ts.load_q[hrs] * k
        res = simulate(w.nw, ts2, r_temp_c=50.0, hours=hrs, with_outage=False)
        out[month] = float((res.central_loss * weights).sum())
    return out


def reconciliation_design(w: World) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Decide every reported meter figure so the Central balance gives the planted loss.

    Normal months: reported loss = truth x (1 + noise), noise within +-2 %, nudged so the
    expected engine gap stays inside +-6 %. 2026-02: +15 % of the loss through an
    over-reading import meter. 2025-12: an estimated export reading 12 % below its true value.
    Returns (meter_month with reported energies, one row per month of the recon design).
    """
    rng = rng_for(w.seed, "recon")
    mm = truth_meter_month(w)
    mm["reported_mwh"] = mm["energy_mwh"].copy()
    mm["estimated"] = "N"
    mm["note"] = ""
    # Small independent meter noise on every non-balancing meter (0.05 %).
    noise = 1 + 0.0005 * rng.standard_normal(len(mm))
    mm.loc[mm["meter_id"] != BALANCING_METER, "reported_mwh"] *= noise[mm["meter_id"] != BALANCING_METER]
    emul = engine_emulation(w)
    cplants = central_plants(w)
    rows = []
    for month in MONTHS:
        sel = w.month_mask(month)
        truth = float(w.tr.central_loss[sel].sum())
        deliveries = {f"D-{c}-1": float(w.ts.load_p[sel, w.load_col[f'D-{c}-1']].sum()) for c in CENTRAL}
        plants = {g: float(w.gen_p(g)[sel].sum()) for g in cplants}
        rep_deliv = {k: v * (1 + 0.001 * rng.standard_normal()) for k, v in deliveries.items()}
        rep_plant = {k: v * (1 + 0.002 * rng.standard_normal()) for k, v in plants.items()}
        g_emul = emul[month] / truth - 1
        eps = rng.uniform(-NOISE_PCT, NOISE_PCT) / 100
        lo = (1 + g_emul) / (1 + ENGINE_SAFE_PCT / 100) - 1
        hi = (1 + g_emul) / (1 - ENGINE_SAFE_PCT / 100) - 1
        eps = float(np.clip(eps, max(lo, -NOISE_PCT / 100), min(hi, NOISE_PCT / 100)))
        planted = ""
        target = truth * (1 + eps)
        mrows = mm["month"] == month
        if month == PLANTED_METER_ERROR_MONTH:
            planted = "meter_error"
            target = truth * (1 + eps + METER_ERROR_SHARE)
        # Balance: L = sum(import) - sum(export) + plants - deliveries; solve for the balancing import.
        others = mm[mrows & ~((mm["meter_id"] == BALANCING_METER) & (mm["direction"] == "import"))]
        net_other = others.loc[others["direction"] == "import", "reported_mwh"].sum() - \
            others.loc[others["direction"] == "export", "reported_mwh"].sum()
        bal = target - net_other - sum(rep_plant.values()) + sum(rep_deliv.values())
        if month == PLANTED_METER_ERROR_MONTH:
            # Move the error from the balancing meter onto the Karuma import meter.
            err = METER_ERROR_SHARE * truth
            bal -= err
            k = mrows & (mm["meter_id"] == METER_ERROR_METER) & (mm["direction"] == "import")
            mm.loc[k, "reported_mwh"] += err
            mm.loc[k, "note"] = "Synthetic planted error: over-read after a CT ratio change (see T11)"
        k = mrows & (mm["meter_id"] == BALANCING_METER) & (mm["direction"] == "import")
        mm.loc[k, "reported_mwh"] = bal
        if month == PLANTED_ESTIMATED_MONTH:
            planted = "estimated_boundary"
            k = mrows & (mm["meter_id"] == ESTIMATED_METER) & (mm["direction"] == "export")
            true_val = float(mm.loc[k, "energy_mwh"].iloc[0])
            mm.loc[k, "reported_mwh"] = true_val * (1 + ESTIMATED_READING_ERROR)
            mm.loc[k, "estimated"] = "Y"
            mm.loc[k, "note"] = "Estimated: meter data lost, reading estimated by NCC (see T11)"
        got = mm[mrows]
        reported = (got.loc[got["direction"] == "import", "reported_mwh"].sum()
                    - got.loc[got["direction"] == "export", "reported_mwh"].sum()
                    + sum(rep_plant.values()) - sum(rep_deliv.values()))
        rows.append({
            "month": month, "truth_loss_mwh": truth, "reported_loss_mwh": float(reported),
            "reported_vs_truth_pct": 100 * (reported / truth - 1), "meter_noise_pct": 100 * eps,
            "engine_emulated_mwh": emul[month], "engine_emulated_vs_truth_pct": 100 * g_emul,
            "expected_gap_pct": 100 * (emul[month] / reported - 1), "planted": planted,
            "reported_deliveries": rep_deliv, "reported_plants": rep_plant,
        })
    return mm, pd.DataFrame(rows)
