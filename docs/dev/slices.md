# Wave-3 feature slices: cross-slice contract

Each slice owns its files end to end (`docs/dev/contracts.md` §11).

Slices run in parallel, so whatever one slice **produces for another** is fixed here: the table names, view names, function signatures and endpoints. Produce exactly these, and consume only these. Anything not listed is private to the slice and may be named freely.

All results tables carry `run_id` (§7 of the contracts). All `api.*` views expose `run_id` and do NOT filter (contracts §13.2); the API filters by run. Stages read every threshold from `ctx.cfg` and honour `ctx.actions` (§13.2). All months are `date` (first of month) in tables and `'YYYY-MM'` text in API output.

## S3 losses (210 / 910)
- **Tables:**
  - `results.loss_element_month(run_id, month, element_type, element_id, loss_mwh, loss_kw_per_km, max_loading_pct, peak_loading_pct, energy_through_mwh, profile_source)`, PK (run_id, month, element_type, element_id)
  - `results.loss_zone_month(run_id, month, zone, bucket, loss_mwh)`, PK (run_id, month, zone, bucket)
    - zone: `central` or `model`
    - bucket: `line_400`, `line_220`, `line_132`, `trafo_400_220`, `trafo_220_132`, `trafo_132_33`, `other`, `total`
  - The stage also fills the core `results.case` / `element_result` / `bus_result` for every snapshot and every monthly peak. Case keys are `YYYY-MM|WD|HH`, `YYYY-MM|NWD|HH`, `YYYY-MM|peak` and `YYYY-MM|min`.
- **Views:** `api.v_loss_monthly`, `api.v_loss_elements`, `api.v_loss_map`, `api.v_loss_top` (13-month totals per element, ranked), `api.v_loss_element_series` (one element, month by month).
- **Endpoints:**
  - `/api/losses/monthly`
  - `/api/losses/elements?month=`
  - `/api/losses/map?month=`: `{provenance, month, elements: [{element_type, element_id, peak_loading_pct, loss_mwh, loss_kw_per_km}]}`
  - `/api/losses/top?n=10`
  - `/api/losses/series?element_id=`
- **Function** for other slices: `engine.losses.valuation_range(loss_mwh_by_month: DataFrame, tariffs: DataFrame, energy_charges: DataFrame) -> DataFrame[month, low_ugx, high_ugx]`. The low end is the avoidable energy charge, zero where the energy would have been deemed. The high end is the approved BST. S5 and S10 reuse it.

## S4 validation and reconciliation (220 / 920)
- **Tables:**
  - `results.validation_point(run_id, case_key, point_id, element_type, element_id, quantity, measured, modelled, abs_error, rel_error, within)`
  - `results.validation_summary(run_id, case_key, n_points, n_within, share_within, passed)`
  - `results.recon_month(run_id, month, basis, metered_loss_mwh, modelled_loss_mwh, gap_mwh, gap_pct, status, explanation, cause_code, reviewed_by, diagnostics jsonb)`. status is `PASS`, `EXPLAINED`, `UNEXPLAINED` or `NOT_TESTABLE`.
  - `results.recon_gate(run_id, basis, n_months, n_pass, n_explained, n_unexplained, gate_passed)`
- **Views:** `api.v_validation_summary`, `api.v_validation_points`, `api.v_recon`, `api.v_recon_gate`.
- **Endpoints:** `/api/validation/summary`, `/api/validation/points?case=`, `/api/validation/recon`, `/api/validation/gate`.

## S5 remedies (230 / 930)
- **Tables:** `results.remedy(run_id, rank, element_id, remedy_type, option, capex_ugx, delta_loss_mwh_yr, value_low_ugx_yr, value_high_ugx_yr, payback_low_yr, payback_high_yr, note)`. Payback is low/high because the value is a range.
- **Views:** `api.v_remedies`, `api.v_remedies_top10`.
- **Endpoints:** `/api/remedies/top10`, `/api/remedies/options?element_id=`.

## S6 contingency (240 / 940)
- **Function** that S7 and S9 reuse:
  ```
  engine.contingency.n1_scan(net, outages: DataFrame[element_type, element_id], cfg: dict, case_key: str)
    -> dict[str, DataFrame] with keys 'n0_violation', 'n1_result', 'n1_violation', 'n1_post_loading'
  ```
  It runs N-0 first, then each outage with the retry ladder (`engine.loadflow.run_pf`). It reports only new violations, or ones worsened by more than `cfg['worsen_pp']`. It counts islanded load as loss of supply, and assigns severity classes A–E.
  - `engine.contingency.default_outages(net) -> DataFrame`: every in-service Central line circuit and transformer, excluding equivalents.
  - `engine.contingency.max_secure_load(net, bus, outages, cfg, firm: bool, upper_mw=300, tol_mw=1) -> (mw, binding_element, binding_contingency)`: bisection on a load added at `bus`, used by S8 and S9.
- **Tables:**
  - `results.n0_violation(run_id, case_key, object_type, object_id, kind, value, limit)`
  - `results.n1_result(run_id, case_key, contingency_id, outage_type, outage_id, converged, method, load_lost_mw, max_loading_pct, max_loading_element, min_vm_pu, min_vm_bus, max_vm_pu, overload_mva, severity_class, severity_rank)`
  - `results.n1_violation(run_id, case_key, contingency_id, object_type, object_id, kind, value, limit, base_value)`
  - `results.n1_post_loading(run_id, case_key, contingency_id, element_type, element_id, loading_pct)`
  - `results.n1_benchmark(run_id, study_id, contingency, atlas_found, atlas_value, planning_value, agreement, note)`
- **Views:** `api.v_n1_cases`, `api.v_n1_summary` (per case: counts by class, worst contingency), `api.v_n1_results`, `api.v_n1_violations`, `api.v_n0_issues`, `api.v_n1_benchmark`, `api.v_n1_post_loading`.
- **Endpoints:**
  - `/api/n1/cases`
  - `/api/n1/summary`
  - `/api/n1/results?case=`
  - `/api/n1/violations?case=&contingency=`
  - `/api/n1/n0?case=`
  - `/api/n1/benchmark`
  - `/api/n1/map?case=&trip=`: `{provenance, case, trip, elements: [{element_type, element_id, loading_pct, violation}], buses: [{bus_id, vm_pu}], islanded_mw}`
- **Cases:**
  - `YYYY-MM|peak` for every study month (taken from S3's peak snapshots, rebuilt with `engine.cases.peak_snapshot`)
  - `YYYY-MM|min` for the month with the lowest load
  - `kawanda|binding`: the hour Kawanda bound, with the curtailed MW restored. S6 builds it from `ts.ops_constraint_hour` and `ts.ops_curtailment`.
  - `2030|peak` is added by S7 using `n1_scan`.

## S7 forecast 2030 (250 / 950)
- **Function:** `engine.forecast.net_2030(ctx, scenario="base") -> pandapowerNet`, the 2030 network with peak loads applied, used by S9.
  - It uses Planning's `planning_2030` case if one exists.
  - Otherwise it builds the as-of-2030 network, adds the `ts.plan_project` elements with approximate parameters, and grows loads by `ts.team_growth_rate` (or the config default) plus `ts.plan_committed_load` with COD ≤ 2030.
- **Tables:**
  - `results.forecast_summary(run_id, scenario, peak_mw, growth_factor, projects text[], annual_loss_mwh, note)`
  - `results.forecast_element(run_id, scenario, element_type, element_id, peak_loading_pct, annual_loss_mwh)`
  - It also writes `n1_scan` output for case `2030|peak` into S6's tables.
- **Views:** `api.v_forecast_summary`, `api.v_forecast_map`.
- **Endpoints:**
  - `/api/forecast/summary`
  - `/api/forecast/map`: the same shape as `/api/losses/map`, with `month: "2030"` and `peak_loading_pct` and `loss_mwh` for the year.

## S8 Kawanda (260 / 960)
- **Tables:**
  - `results.kawanda_element(run_id, element_type, element_id, hypothesis)`. hypothesis is `H1_transformers` or `H2_lines`.
  - `results.kawanda_monthly(run_id, month, element_type, element_id, measured_max_pct, measured_p95_pct, modelled_peak_pct, n1_worst_pct, n1_worst_contingency)`
  - `results.kawanda_headroom(run_id, variant, criterion, lambda_star, extra_mw, binding_element, binding_contingency, years_to_exhaust)`. variant is `before_relief` or `after_relief`; criterion is `N-0` or `N-1`.
  - `results.kawanda_verdict(run_id, binding_hypothesis, agreement, evidence jsonb, constraint_id, limit_mva)`
  - `results.kawanda_suppressed(run_id, month, curtailed_mwh, curtailed_low_ugx, curtailed_high_ugx, deferred_mw, n_events)`
- **Views:** `api.v_kawanda_verdict`, `api.v_kawanda_loading`, `api.v_kawanda_trips`, `api.v_kawanda_headroom`, `api.v_kawanda_suppressed`.
- **Endpoints:** `/api/kawanda/summary`, `/api/kawanda/loading`, `/api/kawanda/trips`, `/api/kawanda/headroom`, `/api/kawanda/suppressed`.

## S9 headroom, sites and scoring (270 / 970)
- **Tables:**
  - `results.substation_headroom(run_id, ss_code, year, bus_id, kv, firm_mw, nonfirm_mw, binding_element, binding_contingency)`, with year `2026` or `2030`
  - `results.site_metric(run_id, site_id, load_type, metric, value, unit, source)`
  - `results.site_effect(run_id, site_id, load_type, mw, connection_ss, connection_kv, connection_km, firm_mw_now, nonfirm_mw_now, firm_mw_2030, nonfirm_mw_2030, firm_headroom_mw, dloss_mw_per_mw, dloss_mwh_yr, max_loading_after_pct, new_n1_violations, developments text[])`
  - `results.site_exclusion(run_id, site_id, reason)`
- **Views:** `api.v_substation_headroom`, `api.v_site_inputs` (metrics and effects; scoring happens in the API), `api.v_sites_geo`.
- **Endpoints:**
  - `/api/sites` (ranked, using `config/scoring.json`, optional `?weights=` JSON override for "what if")
  - `/api/sites/{site_id}`
  - `/api/sites/geo`
  - `/api/sites/headroom`
  - `/api/sites/weights` (the weights in use, with their hash)
- **The only scorer** is `api/scoring.py`. The dashboard calls `api.scoring.rank_sites(df, weights)` and must not re-implement it.

## S10 incidents, asset age and dashboard (280 / 980)
- **Tables:**
  - `results.incident_month(run_id, month, n_incidents, n_constraint_related, mw_lost, mwh_unserved)`
  - `results.asset_age(run_id, element_type, element_id, commissioning_year, age_years, age_band)`
- **Views:** `api.v_incidents_monthly`, `api.v_incidents_timeline`, `api.v_asset_age`, and `api.v_dashboard_kpis`. The KPI view reads only views listed in this file: `v_loss_monthly`, `v_recon_gate`, `v_n1_summary`, `v_kawanda_headroom`, `v_kawanda_suppressed`, `v_forecast_summary`, `v_incidents_monthly`. Write each reference so the view still works when another slice's view returns no rows.
- **Endpoints:** `/api/dashboard/kpis`, `/api/incidents/monthly`, `/api/incidents/timeline`.

## S11 map (front end only)
It consumes `/api/network/geo`, `/api/meta/months`, `/api/losses/map`, `/api/losses/series`, `/api/forecast/map`, `/api/n1/cases`, `/api/n1/map`, `/api/sites/geo`, `/api/sites/headroom` and `/api/incidents/timeline`.

Every call must degrade gracefully, with a short "not available yet" note, when an endpoint returns 404 or no rows.

## Shared rules
- Read inputs with `ctx.table("ts.<table>")`. Name columns have resolved `<col>_code` companions, for example `substation_code` and `plant_code`.
- Read upstream results with `ctx.read("select ... from results.<table> where run_id = :r", {"r": ctx.run_id})`. A stage must still finish, logging a warning, when an upstream slice produced nothing.
- Register every table you expose with `api.tables.register(TableSpec(...))` so it can be exported. The view is the only source for both the screen and the export.
- Write `config/engine/<slice>.toml` with every threshold your slice uses, each with a one-line comment and its source (Grid Code, Planning, typical value).
- Write your method note `docs/methods/NN-<slice>.md` with these headings: Purpose, Inputs (table and source), Method (with formulas), Assumptions, Validation, Known gaps, and a Sign-off table (name, role, date, version), left blank.
