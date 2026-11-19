# Grid Atlas MVP: document review and build plan

## Context

`docs/` holds two documents:
- **Board paper, UETCL Grid Atlas (15 Oct 2026)**: an 18-page scan with the team's handwritten revisions. The revisions reframe the vision as "optimise resource positioning/allocation to cut economic loss from deemed/unserved energy and long-distance technical losses". They extend the data period to Sep 2025 to Sep 2026, strike the Jinja–Lugazi worked example and the event-replay emphasis, add the Kawanda constraint (suppressed data-centre demand), and add "identify all possible data needs", asset age, incidents due to constraints, spreadsheets of analysed data, and NDP IV / Energy Policy 2023 / Vision 2040. The implementation plan and financials are marked "to be re-examined" and "discuss as team".
- **MVP Scope of Work (30 Oct 2026)**: a four-week build for the Central region only. It covers three programs (transmission losses, N-1 capacity and constraints, future industry site scoring) on four Docker containers (PostGIS, Python/pandapower worker, FastAPI, Nginx with static HTML, Leaflet and Chart.js) on the NCC Ubuntu server. The demo is at the ERA SDP session, assumed to be the last week of November. Acceptance criteria are in §9.

Today is Sun 1 Nov 2026. Build week 1 and the data requests start **tomorrow**. The project folder contains only `docs/`, is not a git repo, and holds no real data.

**Decisions from the team lead (this session):**
- Build a **runnable MVP skeleton**: the full SOW stack working end to end on a clearly labelled synthetic Central network, so real data drops in as it arrives.
- **No real inputs on hand yet.** Build against agreed input templates and synthetic data.
- **Kawanda bottleneck unknown.** Model both the transformers and the lines at Kawanda, and confirm with NCC in week 1.

**The target server.** Facts read, without changes, from Grid Monitor's `compose.yaml` and `DEPLOYMENT.md`. The "NCC Ubuntu server" is Grid Monitor's App VM:
- Ubuntu x86_64, 4 vCPU, 8 GB, **no internet at any time**.
- Two network cards: control room, and the **substation network**. Grid Monitor's collector reaches IEC-104 gateways on TCP 2404 from this host.
- Ports already taken: 8000 and 8100 on the control-room address, 5432 and 6379 on loopback.
- Images are built on this Mac with `/opt/homebrew/opt/docker-buildx/bin/docker-buildx --platform linux/amd64` and carried on USB.

**This Mac.** Apple Silicon, Docker 29.5 in a Colima aarch64 VM (12 GB), Compose 5.6. Host GDAL is broken and `python3` is a dead link, so all Python and GDAL run in containers.

## Ground rule: everything lives in this folder (team lead's instruction)
- Every file the Atlas needs or produces lives under `/Users/markryanmutikanga/Documents/ERA Project`: code, config, templates, docs, synthetic and real data, open-data downloads, the basemap, logs, the database's data files, and the USB release bundle.
- **Database data** goes in a bind mount at `./data/pgdata`, not a Docker named volume. If Colima's file sharing refuses Postgres's ownership or permissions, I stop and tell you before using anything else.
- **USB bundle** is written to `./dist/`. You copy that folder to the drive.
- **Temporary files** go in `./tmp/`, not the system scratchpad.
- All three are git-ignored.
- **Nothing is written anywhere else.**
  - Nothing in the Grid Monitor / IEC Project folder.
  - No `brew` or `pip` installs and no global git config. The hooks path is set in the repo's own `.git/config`, and every tool runs in a container.
  - Vendored JS/CSS is downloaded straight into `web/vendor/`.
  - The Atlas docs carry their own full server runbook rather than pointing at Grid Monitor's.
- **Two things outside the folder that I can't avoid:**
  - Docker's image cache inside the Colima VM.
  - Claude Code's own session files under `~/.claude`, which include this plan and the review transcripts. Copies go into `docs/` (`docs/build-plan.md`, `docs/review/`), so the project holds everything.

## Part A: Review findings

**How the review was done.**
- Four independent reviewers each read both documents in full: power systems; data, GIS and governance; delivery and demo; faithfulness to the margin notes.
- A second agent per reviewer tried to disprove every finding against the page images and public sources.
- A final pass looked for what all four missed.

**Result.** 58 findings stand and 1 was refuted. All 77 handwritten notes were transcribed and checked against the SOW: 25 captured, 24 partly, 21 paper-only, 4 contradicted, 3 missing. The full write-up goes into `docs/review/` (step 1b).

### A1. The finding that matters most (all four reviewers found it on their own)
**The 10% loss gate (SOW §9 criterion 3) cannot be tested as written.**
- NCC reports losses for the whole network by voltage level, not for Central.
- One load flow a month gives MW at one instant, not monthly MWh. Losses scale with the square of the flow, so a peak snapshot reads about 2× high and an average-load snapshot reads about 14% low.

Fix:
1. **Compare like with like.** Either compare a national model with NCC's national losses by voltage level, or build a Central balance from boundary meters if NCC can supply them. Report Central from the model either way, and never scale national losses down by modelled share.
2. **Compute monthly MWh from hourly data.**
3. **Add a check that does not depend on loss figures.** Modelled bus voltages within ±0.02 pu, and branch flows within ±5% (or 5 MW) of SCADA, at three or more hours.
4. **Fix the method before the first comparison.** Power factor, loss factor, slack and boundary rules are set in the method note first, so the result cannot be tuned month by month.

### A2. Other high-impact findings
| Topic (finding IDs) | Problem | Fix |
|---|---|---|
| Kawanda (PS-2, DG-5, DL-11, BF-3) | "Tx" may mean transformer. Nobody has been asked for the limiting element, its limit, the curtailment records or the relief project. Loads recorded after curtailment hide the constraint. | Ask NCC on Monday. Model both readings and restore the curtailed MW in the case. Choose the demo's trip only after NCC confirms the element. |
| Model scope (PS-3, DG-11) | Bujagali–Kawanda is listed both as internal and as an injection. The 400 kV Karuma–Kawanda infeed and the slack bus are missing. The district list omits Nakaseke (Kapeeka) and Gomba (Kabulasoke). | Request Planning's national solved cases at all voltages and report Central. Define the boundary twice: a district polygon for open data, and a bus set for metering. |
| Converter (PS-5, DG-2, DL-5) | pandapower has no PSS/E reader, and "it converges" is not validation. | Ask for RAW v33/35 or CGMES, plus Planning's own solved voltages and flows. Accept the model only when it reproduces them (±0.005 pu, 1–2% on flows). |
| N-1 (PS-6, CC-3, CC-8) | No loading case, rating basis or post-contingency voltage limit. No N-0 check. No benchmark. | Run N-0 first. Take criteria from the Grid Code / Planning. Cases: peak, minimum load, and a Kawanda-binding hour. Benchmark against Planning's own studies, with the Planning mentor signing the table. |
| Schedule and demo (DL-1, DL-2, BF-2, BF-8, CC-1) | Build week 4 is the assumed demo week and holds two of the five must-show items. A LAN-only server can't be reached from an ERA venue. The script omits the reconciliation and the downloads. Nobody clears what ERA sees. | Confirm date, venue and network with ERA SDP on Monday. Have all five items working by Fri 20 Nov and hold a **management preview** that day. Precompute every result and record a fallback. Ask ICT whether a results-only laptop copy is allowed. |
| Server security (DL-7, DL-9, DL-12, DG-6, DL-13) | Docker ports bypass ufw, and the VM has a substation network card. There are six hidden internet dependencies. Data custody, repo hosting and access to /export are undefined. | The B2 design, an allow-list or basic auth, an internal git host, and a handling note sent with every request. |
| Data routes (DG-7, BF-6, DL-4) | UEGCL is not among the introductions, and the Central plants are probably IPPs whose PPAs sit with UETCL Commercial. §4 and §7 list different Monday requests. There are no due dates or escalation. | One sponsor-signed memo with due dates and escalation. Plant data from Commercial. UEDCL made non-blocking. |
| Valuation (PS-8, PS-10, CC-5, CC-7) | Deemed and unserved energy are mixed up. Losses are valued at the bulk tariff in a surplus system. ACCC cuts a line's losses by only about 20–30%. The opening slide's UGX 85 bn uses the tariff the SOW rejects. | Define three metrics separately. Value losses as a range, from avoidable purchase cost up to the approved BST. Rebuild the opening slide from the 13 months, showing low, base and high. |
| Sites (PS-7, BF-4, CC-6, CC-4) | The outputs are undefined. The paper has 8 factors, not 9 ("effect to grid" sits under Power, and Limits is an exclusion). Candidates are hand-picked near sources, which is the struck vision. 33 kV generation may be counted twice. | Compute firm and non-firm headroom per substation, now and 2030, and let each site inherit it. Treat Limits as a hard exclusion. Add a net/gross rule for embedded plants. Rule-based candidates as a stretch. |

**Margin notes the SOW misses or contradicts.**
- The event replay is kept, although the notes struck it four times and asked instead for "total number of incidents due to constraints".
- Asset age ("constraints & age of assets").
- Cost of grid reinforcements.
- N-1 on the 2030 case.
- The 400 kV network is dropped.
- §2 brings back "a better average cost of supply", a benefit the notes struck.

**Fix before the paper or SOW is circulated.**
- The paper still carries Recommendation 7 (Jinja–Lugazi), the June–September basis, the 6.5 BCR / UGX 32.8 bn / 1.34% figures, and "pays for itself quickly".
- The SOW still has "the user's existing line-loss analysis", an empty name column, "nine factors", and a question about naming a heat-map view that does not exist.

**What holds up.** The stack, the one-region scope, the read-only stance, the run-time targets (easy at this network size) and config-driven scoring are all sound. The problems are definitions and data, not tools.

### A3. Revised Monday requests (replace the SOW §4/§7 lists)
| # | To | Key asks | Due |
|---|---|---|---|
| 1 | Head of Network Operations (sponsor) | Sign one covering memo that cites the approval it rests on, names a contact per dataset and gives an escalation route. Book the management preview for Fri 20 Nov. | Mon |
| 2 | Planning | National solved cases in native format at all voltages: as-operated peak near Sep 2026, light load, and 2030. Include rating sets, generator Q limits, Planning's own solved voltages and flows, and network changes since Sep 2025. | Fri 6 Nov |
| 3 | Planning (mentor) | Latest Central contingency studies and criteria; Kawanda relief scope and date; commissioning years; standard unit costs. | Fri 13 Nov |
| 4 | Planning GIS | Substations, and one feature per circuit with the model branch ID, kV, conductor, length and commissioning year. EPSG code stated; no landowner fields. | Fri 6 Nov |
| 5 | NCC reporting | 13 Power System Summaries in Excel, plus how losses by voltage are derived; deemed and unserved kept apart; incidents due to constraints. | Fri 6 Nov |
| 6 | NCC SCADA | Hourly MW/MVAr per measurement point and bus kV for all 13 months (two days a month at minimum), with the point list and sign convention. | Fri 6 Nov |
| 7 | NCC metering | Monthly MWh at every Central boundary meter (including the 400 kV Kawanda infeed), every Central generator and every BSP, with accuracy class, and whether substation loads are net or gross of embedded plant. | Fri 6 Nov |
| 8 | NCC operations | The Kawanda constraint: element, limit, hours it bound, MW curtailed, deferred connections. Also other Central limits and the outage log. | Fri 6 Nov |
| 9 | Commercial | Approved BST by month; deemed energy per plant; energy per BSP; PPA summary for the Central plants (replaces the UEGCL route). | Fri 13 Nov |
| 10 | Planning connections and Commercial | Committed and pending large loads in Central; ILDS anchor sites; SGR traction points. | Fri 13 Nov |
| 11 | ERA SDP secretariat | Date, slot, venue, network access, whether remote presenting is allowed, audience, evaluation criteria, recording rules. | Mon |
| 12 | ICT / InfoSec and the DPO | Data classification; conditions for hosting beside Grid Monitor; an internal Git host; whether a results-only laptop copy or a remote demo is allowed. | Fri 6 Nov |
| 13 | UIA | Park boundaries with CRS stated, status, hectares available, allocated loads. | Fri 13 Nov |
| 14 | UEDCL (aggregate, non-blocking) | 33 kV feeders per Central BSP, with monthly peak and MWh, and the generators on each feeder. | Fri 13 Nov |
| 15 | The team (open data) | UBOS boundaries and Census 2024 population; UWA/NFA protected areas and MWE/NEMA wetlands (Protected Planet only with permission); Copernicus or SRTM DEM; OSM roads, with attribution. | Week 1 |

The paper cites NCC's June–September 2026 summaries, so someone on the team probably holds four real months already. Once they are on the server, write the NCC adapter against them in week 1.

## Part B: What gets built (runnable MVP skeleton)

The stack is SOW §6, adjusted to the server facts above. Version pins were checked today. Everything that differs from the SOW is listed in B7.

**Division of labour.** I build the whole pipeline working end to end on synthetic data. The team's four weeks then go on real data, mentor validation of the 10% gate, and the demo, not on plumbing. Stretch items (live re-computation of a trip, an expected-unserved-energy figure, a weight-sensitivity panel, rule-based candidate sites) are built last, and only if the rest is green. The 14 June replay is dropped because the notes struck it. The notes' replacement, a count of incidents due to constraints, is built instead.

**How I'll build it.** I lay the foundations myself, in order: repo, compose, schema, `spec.toml`, the synthetic generator and the API view contract. The engine modules, API routers and pages then go to parallel agents working against those fixed contracts, and I integrate and run Part C. Nothing is committed to git unless you ask.

### B0. Order of work after approval
| Step | Output | Done when |
|---|---|---|
| 1 (tonight) | **Monday data-request pack** in `docs/data-requests/`: the sponsor's covering memo (due dates, escalation); one request note per holder for the 15 requests in A3; a one-page data-handling note; `templates/spec.toml` generating `T01–T13 *.xlsx` | Every request names its holder, exact fields, format and due date; the workbooks open in Excel |
| 1b (tonight) | **Review write-up** in `docs/review/`: findings with evidence and fixes; the 77-note margin table; a section-by-section list of SOW changes, including acceptance criteria rewritten as tests; the paper clean-up list | Every finding is traceable to a page or section |
| 2 | Repo and stack: `git init`, `./atlas`, compose with four services, DB image, roles, migrations, Nginx with vendored Leaflet 1.9.4, Chart.js 4.4.7 and swagger-ui, provenance banner | `docker compose up` shows four healthy containers and a SYNTHETIC banner |
| 3 | Synthetic Central data (`./atlas synth`), spec-driven loaders, import log page | Zero failed rows on clean data; the `dirty` variant produces the expected issues |
| 4 | Engine: network builder and checks, weighted-snapshot monthly losses, model-vs-SCADA validation, reconciliation, top-10 and remedies, N-0/N-1 with the Planning benchmark, 2030, Kawanda, substation headroom and sites, incident count | Planted synthetic outcomes reproduced (golden tests) |
| 5 | API routers, pages, CSV/XLSX exports | Exports equal the JSON; every page under 2 s |
| 6 | `./atlas test`, `verify`, `bundle` (amd64 USB bundle); method-note drafts; ADRs | Part C passes |

### B1. Repo layout (`/Users/markryanmutikanga/Documents/ERA Project`)
```
atlas                     POSIX entry point (the VM may lack make): init up down synth load run test verify templates bundle psql logs
docker-compose.yml        db, worker, api, web
.env.example .gitignore .githooks/pre-commit    hook blocks data/, .env, xlsx outside templates/, files > 2 MB
docker/py.Dockerfile, requirements.in/.lock     one Python 3.12 image for worker and api; dependencies only, code mounted read-only
db/Dockerfile, db/init/, db/migrations/*.sql    postgres:16 + PostGIS (multi-arch); 900_api_views.sql is the API's read contract
config/                   engine.toml, scoring.json (the SOW's "config.json"), load_types.csv, conductors.csv, remedies.toml, aliases.csv, boundary_points.csv, holidays_ug.csv
templates/                spec.toml (one source for templates AND load validation), build_templates.py, T01–T13 *.xlsx
loaders/                  base (manifest, sha256, batch and issue log), names, units, one module per dataset, adapters/ for native layouts, network_{excel,handbuilt,pypowsybl}.py
engine/                   cli, db, provenance, network/{build,checks}, profiles, cases, loadflow, losses, validate (model vs SCADA), reconcile, remedies, contingency, forecast, kawanda, sites, synthetic/
api/                      main (GET only, self-hosted /api/docs), tables (export allow-list), render (one path for JSON, CSV, XLSX), scoring (the only scorer), routers/
web/                      index (map and slider), losses, n1, kawanda, sites, dashboard, imports, about .html; css/, js/ (vanilla), vendor/
nginx/default.conf.template   static files plus /api proxy; CSP allows 'self' only; GET only
scripts/                  verify.sh, bundle.sh, install_offline.sh, firewall.sh, make_basemap.sh
tests/                    unit/, integration/, golden synthetic outcomes
docs/                     review/ and data-requests/ (step 1), methods/ (one note per program, with a sign-off table), decisions/ (ADRs), provenance.md, runbook-server.md, demo-script.md, build-plan.md (a copy of this plan)
data/                     git-ignored: synthetic/ real/ open/ basemap/ logs/ pgdata/ (database files) backups/
dist/                     git-ignored: the USB release bundle (images, code, checksums)
tmp/                      git-ignored: temporary work files
```
The two source documents stay in `docs/` but are git-ignored, since they are internal board material. So is `docs/review/`, which quotes them, until ICT confirms the repo stays internal.

### B2. Stack decisions
- **No route to SCADA.**
  - `db`, `worker` and `api` sit only on an `internal: true` network, so they have no route out at all.
  - `web` (Nginx) alone sits on an `edge` network with masquerade off.
  - `scripts/firewall.sh` adds DOCKER-USER rules so Nginx can answer but never start a connection. These rules are applied only with NCC IT's agreement.
- **Ports.** Only Nginx is published, on `${ATLAS_BIND_IP}:8090` (the control-room address). That avoids Grid Monitor's 8000/8100 and loopback 5432/6379. The database is never published.
- **Database image.** `postgres:16-bookworm` plus `postgresql-16-postgis-3`, because the official postgis image is amd64-only. Data files sit in `./data/pgdata` inside the project, so `docker compose down -v` cannot silently delete them. Roles:
  - `atlas_rw`: the worker.
  - `atlas_ro`: the API. It runs with `default_transaction_read_only`, can SELECT only the `api.*` views, and has a 5 s statement timeout.
- **Python image.** `python:3.12-slim-bookworm` with a hashed lock: pandapower 3.5.6, pandas 2.3.3, numpy 2.4.4, geopandas 1.2.0, rasterio 1.5.2, psycopg 3.3.6, openpyxl, XlsxWriter, fastapi 0.162, uvicorn 0.54.
  - pypowsybl 1.16.1 is installed only on x86_64, because it has no arm64 Linux wheel. Its converter tests run in the amd64 image.
  - Code is **mounted, not baked**, so updates reach the VM as a small folder or `git bundle` and not a new image (ADR).
- **Worker.** Long-running, so §9's "four containers up" holds. On start it applies migrations. Jobs run through `./atlas run …` (`docker compose exec worker python -m engine.cli …`), and an advisory lock blocks concurrent runs.
- **Memory.** Limits are db 768 MB, worker 1.5 GB, api 512 MB, web 64 MB. `oom_score_adj: 500` and lower CPU shares make Grid Monitor win any contention, and BLAS runs single-threaded. Check `free -m` on the VM in week 1.
- **Offline.**
  - Every JS/CSS asset is vendored, and the CSP blocks external URLs, so a CDN slip fails loudly in dev.
  - FastAPI's docs are self-hosted.
  - The basemap is hillshade tiles plus simplified GeoJSON (lakes, districts, roads, towns), built once on the Mac in a GDAL container from Copernicus GLO-30, OSM and HDX. The map still works without it.
- **Delivery.** `scripts/bundle.sh` uses the same USB method the VM already uses: amd64 buildx, `docker save | gzip` (about 0.6 GB), code, git bundle, basemap and checksums. It writes everything to `./dist/`, and you copy that folder to the drive. `scripts/install_offline.sh` installs on the VM, and `docs/runbook-server.md` has the full procedure on its own.

### B3. Data contracts and loaders
- **One spec.** `templates/spec.toml` defines every sheet, column, unit, range and enum. It generates the workbooks and validates every load, so they cannot drift apart. Cover notes say "send your native format; the template is the minimum field list". A native layout costs one adapter.
- **Templates.** Each one is the minimum field list behind one of the A3 requests.
  - T01 network model: buses; lines per circuit with R/X/B per km, rating sets (continuous, emergency, NCC limit), conductor temperature and **commissioning year**; transformers; generators with Q limits; loads; shunts; boundary; Planning's own solved voltages and flows.
  - T02 GIS spec: one feature per circuit carrying the model's branch ID; EPSG code stated; no owner or affected-person fields.
  - T03 NCC monthly:
    - system summary;
    - losses by voltage **with how they are computed**;
    - substation energy and coincident peak, **net or gross of embedded generation**;
    - generation;
    - **boundary meters** with accuracy class;
    - deemed and unserved kept apart;
    - events with cause codes;
    - sample days.
  - T04 SCADA hourly for all 13 months (two days a month at minimum), with the point list and sign convention.
  - T05 commercial: approved BST by month; BSP billed; deemed energy per plant; **curtailments**; **deferred connections**; PPA summary per plant.
  - T06 plants (sourced from Commercial, not UEGCL). T07 UEDCL feeders (aggregate, non-blocking).
  - T08 planned projects, including **the Kawanda relief**, plus committed large loads.
  - T09 candidate sites. T10 growth. T11 reconciliation explanations. T12 hand-built line and transformer schedule.
  - T13 Planning studies: contingency results and criteria (the N-1 benchmark), and standard unit costs.
- **Names.** Normalised and mapped through `config/aliases.csv`. An unmatched row is an error with a suggested match, never applied automatically.
- **Import log.**
  - One batch per file, with sha256, sender and provenance. Received files are kept unchanged.
  - Rejected rows go to a quarantine list with the rule and the value; they are never silently dropped.
  - Columns outside each source's allow-list are discarded, so personal fields never load.
  - Cross-checks: Σ substation energy vs delivered within ±5%; load factor range; x/r range; model vs GIS length within ±15%; kWh entered as MWh; month-on-month jumps over 30%.
  - A corrected file replaces that source and period in one transaction. The screen only changes when a new run is pinned, so a reload never shifts numbers during a review.
  - `imports.html` shows the log and the quarantine. Criterion 2 becomes "every row loaded or listed with a reason, and the mentor accepts the list".
- **Network paths.** All land in one canonical `net.*` schema:
  - PSS/E RAW v33/35 through pypowsybl, on the server.
  - DIgSILENT: ask Planning for a RAW export first; DGS or CGMES through pypowsybl as the fallback.
  - Excel (T01).
  - Hand-built (T12 + `conductors.csv`), flagged approximate.

  pandapower has no PSS/E reader. One builder turns the canonical tables into a pandapower net with an as-of date (existing, committed, planned), and the same builder makes the 2030 network.

### B4. Engine methods (each written up in `docs/methods/`, fixed before the first comparison with real data)
- **Perimeter.** The engine solves whatever the model covers. With Planning's national case, the whole grid is solved and Central is the reporting zone. With a Central-only model, the ties become boundary equivalents, excluded from reporting and from N-1. Line R is corrected to conductor temperature (default 50 °C).
- **Three metrics, kept apart.** Technical losses (MWh). Deemed energy (MWh and UGX per plant). Unserved or suppressed demand (MWh).
- **Monthly losses.**
  1. Weekday and non-weekday weights come from the calendar.
  2. Every SCADA day supplied is used: all 13 months if NCC sends them, two days a month at minimum.
  3. Profiles are scaled to NCC's monthly substation energy.
  4. Weighted load flows give MWh and kW/km for every line and transformer: 48 a month with two days of data, about 720 with full data.
  5. Fallbacks are shapes borrowed from other months, then standard shapes fitted to energy and peak. `profile_source` is recorded.
  6. The LLF formula cross-checks the result.
  7. Embedded 33 kV plants sit at their 33 kV bus, and loads are seeded gross.
- **Validation, two tiers.**
  - Tier 1, the snapshot check: model vs SCADA at three or more hours (peak, off-peak, a Kawanda-binding hour). Voltages within ±0.02 pu, and branch MW within ±5% or 5 MW, on at least 90% of measured points.
  - Tier 2, monthly energy reconciliation. The basis is chosen with the NCC mentor:
    - the national model vs NCC national losses by voltage level (like for like);
    - or a Central balance from boundary meters (Σ imports + Central generation − Σ BSP deliveries − exports);
    - or NCC's own Central figure, if one exists.
  - National losses are **never** apportioned by modelled share.
  - Gate: at least 10 of 13 months within ±10%, and zero unexplained. A month is explained by a T11 row with cause, MWh, evidence and a mentor reviewer.
  - Calibration months, if any, are named and kept out of the count.
- **Remedies.**
  - The top 10 lines by MWh.
  - Reconductoring: ΔE = E·(1 − R_new/R_old), checked by a re-run.
  - Compensation, and reconfigurations listed by mentors, are checked by re-run.
  - Savings are valued as a **range**: from avoidable purchase cost (zero where the energy would have been deemed) up to the approved BST.
  - Payback = capex / value. Unit costs come from Planning's T13, or from the team lead's existing ACSR→ACCC analysis.
- **N-1.**
  - N-0 runs first. Base-case violations are listed separately as data or model issues for NCC.
  - Then every Central line circuit and transformer is tripped on the 13 monthly peaks, a minimum-load case (overvoltage), a Kawanda-binding hour with the curtailed MW restored, and the 2030 peak.
  - Criteria come from config, set from the Grid Code and Planning's criteria (rating set, post-contingency voltage band). Only new or worsened violations count.
  - A retry ladder handles non-convergence. Islanded buses count as loss of supply in MW.
  - Severity classes: A no solution; B loss of supply; C over 120% or outside the voltage band by more than 0.05 pu; D over 100%; E secure.
  - Benchmark table: the Atlas vs Planning's own contingency results (T13).
  - Everything is precomputed, so the demo "trip" is instant and repeatable.
- **2030.** Planning's 2030 case is used directly if supplied. Otherwise the model is built as of 2030 (existing, committed and planned elements), with loads grown at one documented rate plus explicit committed spot loads. Losses, N-1 (the program 4 note) and hosting are re-run, and every 2030 figure is labelled "forecast".
- **Kawanda.** Both hypotheses: H1 the Kawanda transformers, H2 the Kawanda lines.
  - Measured evidence: SCADA maximum and 95th percentile, and NCC events.
  - Model evidence: N-0 and N-1 with the curtailed MW restored, and a load-scaling sweep giving headroom MW and the binding element, before and after the T08 relief.
  - The verdict states which hypothesis binds and whether model and measurements agree.
  - Suppressed demand = curtailment records × tariff.
- **Sites.**
  - Headroom is computed **per substation** (firm under N-1, non-firm under N-0, now and 2030, with the binding element), and each site inherits it plus a connection-distance term. This is also the paper's "spare substation capacity" view.
  - Grid effect = the marginal loss sensitivity (+1 MW) plus Δloading.
  - "Unserved-energy risk" is shown as **firm headroom in MW**, its true unit.
  - The paper's factors are used: grid effect inside Power, and Limits as a hard exclusion. Factors without data are dropped and the note says so.
  - Each load type is marked firm or interruptible. Interruptible types are recommended first where firm headroom is short.
  - Scores are computed **by the API on every request** from `config/scoring.json`, so editing a weight re-ranks the screen and the exports identically.
  - MW and value are shown as low / base / high.
- **Incidents and asset age.** Incidents due to constraints are counted from T03 events, shown on the dashboard and the Kawanda page, and marked on the time slider. Asset age comes from commissioning year and is available as a map colour mode.
- **Run time.** About 6,500 load flows for a roughly 40-bus model, under 8 minutes on one core. Full hourly data on a national model is an overnight `--jobs` run.

### B5. API, pages, exports
- **API.** GET-only FastAPI, one router per program. Each table response carries provenance, units and decimals for each column, and export links.
- **Exports.** `/export/{name}.csv|.xlsx` comes from an allow-list registry, so table names never reach SQL. One render path feeds the screen and both exports:
  - CSV is rounded to the screen's decimals.
  - XLSX keeps full precision but uses the screen's number format, so it displays identically.
- **Pages.**
  - **Map:** lines coloured green/amber/red by loading, loss density or asset age (thresholds in config); a slider over the 13 months plus 2030; click-through details; an N-1 mode with trip and restore; a substation-headroom layer; a sites layer; incident markers on the timeline.
  - **Losses:** the model-vs-SCADA check, the reconciliation gate with explanations, top 10, remedies with payback ranges.
  - **N-1:** N-0 issues, the contingency table, and the comparison with Planning's studies.
  - **Kawanda:** verdict, loading, headroom before and after relief, suppressed demand, incidents.
  - **Sites:** ranked table with ranges, factor bars, the weights in use.
  - **Dashboard:** KPIs (including incidents due to constraints), charts, downloads.
  - **Imports:** the import log.
  - **About:** runs, inputs, method notes, licences.

### B6. Provenance and data safety
- **Tagging.** Every import batch is tagged synthetic, approximate, open or real. Every result inherits the worst level among its inputs.
- **Labelling.**
  - Every page shows a banner.
  - Map and charts carry a "SYNTHETIC: NOT UETCL DATA" watermark.
  - Exports carry a filename prefix, a provenance column and a README sheet.
  - Real results carry "trainee showcase: not official UETCL figures" until a mentor signs the method note and the management preview clears them for outside use.
- **Keeping data out of git.** `data/` and network-model formats are git-ignored and blocked by the pre-commit hook. Tests generate their own synthetic fixtures. Real data is processed on the VM.

### B7. Departures from the SOW (to agree with the team; the details go into `docs/review/` as SOW edits)
1. **§9 criterion 3.** Two tiers (snapshot check plus monthly energy), compared like with like, with the method fixed first. §2 and the demo script follow.
2. **§5 losses.** Weighted hourly or day-type load flows, not "a load flow per month".
3. **§2 and §4 row 1.** Request the national case at all voltages, including 400 kV, and report Central from it. The boundary is a district polygon plus a bus set.
4. **§5 and §9 criterion 4.** N-0 first; Grid Code criteria; three loading cases; Planning benchmark. The demo trip is chosen after NCC names the Kawanda element.
5. **§5 sites.** The paper's factors (grid effect inside Power, Limits as an exclusion) in place of "nine". Headroom per substation. "Unserved-energy risk" becomes firm headroom in MW.
6. **§6 and §9 criterion 5.** The weights file is `config/scoring.json`, read by the API (not the web layer), so screen and exports always agree. The test: edit a weight, reload, and the order changes.
7. **§3, §5, §7 and row 15.** The event replay is dropped, as the notes asked. Added in its place: the incident count, events on the slider, asset age, unit costs, and N-1 on 2030.
8. **§10 valuation.** Three separate metrics. Losses valued as a range. The opening slide rebuilt from the 13 months.
9. **§4 and §7 requests.** The 15 requests in A3 go under one signed memo with due dates.
10. **§6 security and §9 criteria 1 and 8.**
    - Internal networks, one published port, DOCKER-USER rules, and an allow-list or basic auth.
    - Criterion 1 reads "clean clone plus images from the bundle".
    - Criterion 8 becomes a test: connections fail from each container, and the role is read-only.
11. **§7 and §9 schedule and demo.**
    - All five must-show items working by Fri 20 Nov, followed by the management preview.
    - The demo script adds the reconciliation and a download.
    - A results-only laptop copy is used only if ICT allows it.
12. **§9 criterion 7.** One method note per program, each with a sign-off table. `/docs` is not the method check.

## Part C: Verification

**Automated, on this Mac (`./atlas test`, then `./atlas verify`).**
- **Unit tests:**
  - name normalisation and unit conversions;
  - profile fits, with snapshot weights summing to 24·D;
  - loss aggregation and the LLF check;
  - the retry ladder and severity ordering;
  - hosting bisection on a 3-bus network with an analytic answer;
  - scoring and exclusions, including a weight edit that flips the ranking;
  - the provenance worst-of rule;
  - the Kawanda verdict on the transformer-bound and line-bound synthetic variants.
- **Builder round trip:** pandapower's `case9` and `example_simple` go to canonical tables and back, with load-flow results identical within 1e-6 pu.
- **Integration:**
  - migrate → synth → load → run;
  - every `api.*` view returns rows;
  - `atlas_ro` cannot INSERT, UPDATE or CREATE;
  - every export equals its JSON;
  - provenance appears on every response;
  - no `http(s)://` in `web/`, and the CSP header is present;
  - the planted synthetic outcomes are reproduced: reconciliation 11/13 PASS with 2 EXPLAINED, KAW–MUT overload on N-1, a Kawanda verdict, the tier-1 snapshot check passes, and the dirty-data variant produces the expected quarantine.
- **`./atlas verify`, the acceptance checks as tests:**
  - four containers healthy;
  - exactly one published port, bound to `ATLAS_BIND_IP`;
  - db, api and worker have no default route, and a TCP attempt to a test address on 2404 fails from every container;
  - 13 months loaded, with rejected rows listed;
  - every Central element has an N-0 and an N-1 result;
  - at least 8 sites scored;
  - editing `config/scoring.json` re-ranks both the page and the export;
  - every page plus its API calls loads in under 2 s;
  - the 13-month run takes under 10 minutes and N-1 under 5;
  - data survives `down` and `up` (bind mount).
- **Converter round trip** (pypowsybl), run in the amd64 image under emulation: synthetic network → RAW v33 → adapter → canonical tables equal to the original.

**Manual, on this Mac.** Open `http://127.0.0.1:8090` and check:
- the SYNTHETIC banner and watermark;
- move the slider and click a red line;
- trip KAW–MUT and see the overload;
- open the Kawanda page;
- edit a weight and watch the ranking change;
- download every dashboard table as CSV and Excel and compare it with the screen.

**Bundle.** `./atlas bundle` builds the amd64 images into `./dist/` and the checksums verify. Installing on the VM, `verify` there, and the firewall step (with ICT's agreement) are the team's week-1 tasks, following `docs/runbook-server.md`.

## After approval (housekeeping)
- Save "keep everything for the Atlas inside the ERA Project folder" as a standing instruction in Claude's memory, so later sessions follow it.
- Copy this plan to `docs/build-plan.md`.
- `git init` with the hooks path set in the repo. No commits unless you ask.
