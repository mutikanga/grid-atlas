I have what I need. Here is the design.

# Grid Atlas MVP: implementation design

## 0. Facts I checked that changed the design

**Dev machine**
- It is Apple Silicon (arm64, macOS 14.5). Docker Engine 29.5.2 runs in a Colima VM (aarch64, `vz`, `rosetta: false`, 6 CPU, 12 GB). Compose is 5.6.0.
- buildx 0.38.0 exists only at `/opt/homebrew/opt/docker-buildx/bin/docker-buildx`. `docker buildx` is not installed as a plugin.
- Host GDAL is broken: `ogr2ogr`/`gdal` fail with a dyld error loading abseil. Host `psql` is 14.12. `python3` points at a missing Python 3.9.

**Grid Monitor** (`/Users/markryanmutikanga/Documents/IEC Project/grid-monitor/compose.yaml` and `DEPLOYMENT.md`)
- The App VM runs Ubuntu 22.04/24.04 on x86_64, with a minimum of 4 vCPU and 8 GB.
- It has two network cards: control room, and a substation network with no gateway.
- Its collector reaches substation gateways on TCP 2404, so the host routes into the SCADA network.
- It publishes 8000 and 8100 on `WEB_BIND_IP`, and 5432/6379 on loopback only. There is no internet.
- Images are deployed by USB drive: `docker buildx --platform linux/amd64`, then `docker save | gzip`, splitting files for FAT32.
- It already vendors Chart.js 4.4.7.

**Consequences for the design**
- **SCADA route.** Any Atlas container on an ordinary bridge network could reach the SCADA gateways through NAT. The database, API and worker therefore go on an `internal: true` network, and Nginx gets an egress DROP rule.
- **pypowsybl is x86_64 only.** pypowsybl 1.16.1 publishes Linux wheels for x86_64 only. The arm64 dev image leaves it out, the amd64 server image includes it, and PSS/E and DIgSILENT conversion runs on the server.
- **PostGIS image is amd64 only.** The official `postgis/postgis:16-3.5/3.6` images have no arm64 build. We build `postgres:16-bookworm` plus the PGDG `postgresql-16-postgis-3` package, which works on both architectures.
- **Basemap tooling.** The basemap and hillshade are built in `ghcr.io/osgeo/gdal:ubuntu-small-3.13.3` (`gdal raster tile` exists from GDAL 3.11), not with host GDAL.
- **Memory.** RAM may be 8 GB shared with Grid Monitor. Every service gets a hard memory limit, `oom_score_adj: 500` so Atlas is killed before Grid Monitor, and BLAS threads are set to 1.
- **No `make`.** `make` may not exist on the offline Ubuntu VM, so the entry point is a POSIX script `./atlas`, not a Makefile.

**Version pins** (verified on PyPI, npm and Docker Hub today)

| Component | Pin | Note |
|---|---|---|
| Python base | `python:3.12-slim-bookworm` (3.12.15), pinned by digest | |
| pandapower | 3.5.6 (7 Oct 2026) | Requires `pandas~=2.3`, `numpy<2.5`, `scipy>=1.15`. Version 4.0 is upcoming, so do not float. |
| pandas / numpy | 2.3.3 / 2.4.4 | pandas 3.1 is out but pandapower 3.5.6 excludes it. |
| geopandas / rasterio | 1.2.0 / 1.5.2 | rasterio has cp312 manylinux wheels for aarch64 and x86_64. |
| psycopg[binary] / SQLAlchemy / GeoAlchemy2 | 3.3.6 / 2.0.x / lock-resolved | SQLAlchemy is only the engine for `read_sql` and `to_postgis`. |
| openpyxl / XlsxWriter | 3.1.5 (same as Grid Monitor) / 3.3.1 | |
| fastapi / uvicorn | 0.162.0 / 0.54.0 | |
| pypowsybl | `1.16.1 ; platform_machine == "x86_64"` | Reads PSS/E RAW v33/v35 and RAWX, PowerFactory DGS (import only), CGMES and MATPOWER. Writes MATPOWER, PSS/E and CGMES. |
| PostGIS image | `postgres:16-bookworm` + `postgresql-16-postgis-3` | |
| Nginx | `nginx:1.28.0-alpine` | Same tag as Grid Monitor. |
| Leaflet / Chart.js | 1.9.4 / 4.4.7 | Leaflet 2.0 is still alpha and ESM-only. Chart.js 4.4.7 is Grid Monitor's file, sha256 `206b6e8b…`; 4.6.1 is the latest. |
| swagger-ui-dist | 5.x, vendored | FastAPI's `/docs` loads from a CDN by default. |

- Do **not** install `pandapower[converter]`: it pulls in pypowsybl and fails on arm64.
- The lock is made with `uv pip compile --universal --generate-hashes` inside a python:3.12 container. The image installs it with `pip install --require-hashes --only-binary=:all:`.

---

## 1. Repo tree (`/Users/markryanmutikanga/Documents/ERA Project`)

```
README.md                         quick start (dev, server); the provenance rule
atlas                             POSIX entry point: init up down synth load run pin test verify bench templates basemap bundle firewall psql dump demo-check reset
docker-compose.yml                db, worker, api, web; networks core(internal)+edge; volume pgdata
.env.example                      passwords, ATLAS_VERSION, ATLAS_BIND_IP/HTTP_PORT/ALLOW_CIDR, subnets, *_MEM, BOOTSTRAP, ALLOW_SYNTHETIC
.gitignore .gitattributes         data/**, .env, *.raw *.sav *.dgs *.pfd *.dump, xlsx outside templates/; LF endings (copy Grid Monitor's)
.githooks/pre-commit              sh: refuse data/, .env, xlsx outside templates/, files >2 MB
VERSION                           release id + git commit (written by bundle; stored in every run)
docker/py.Dockerfile              python:3.12-slim + locked deps, uid 10001; code is MOUNTED, not baked
docker/requirements.in|.lock      pins above; universal hashed lock
db/Dockerfile                     postgres:16-bookworm + postgis (multi-arch)
db/init/00_roles.sh               first boot: CREATE EXTENSION postgis, roles, gridatlas_test DB
db/migrations/001_meta.sql        datasets, import_batch/issue, run, run_input, run_stage, settings, signoff
db/migrations/002_ref.sql         substation, alias, element, route, month, holiday
db/migrations/003_net.sql         canonical network model (versioned, dated)
db/migrations/004_ts.sql          NCC, SCADA, commercial, plants, feeders, planned, sites, growth, explanations
db/migrations/005_gis.sql         source GIS + open layers
db/migrations/006_results.sql     engine outputs keyed by run_id
db/migrations/900_api_views.sql   read contract (CREATE OR REPLACE each migrate) + grants
config/engine.toml                criteria, colour thresholds, loss buckets, recon basis order, R temperature, growth, kawanda, sites, runtime
config/scoring.json               the SOW's "config.json": 9 factors, weights, breakpoints, per-load-type overrides
config/load_types.csv             data centre, pharma, coffee, light mfg, food & beverage, cold chain: MW, LF, pf, needs_firm
config/conductors.csv             ACSR/ACCC R(20°C)/R(75°C)/X/B per km at 132/220 kV, ampacity — "typical, verify"
config/remedies.toml              reconductoring UGX/km, compensation UGX/MVAr (from team lead's line-loss analysis)
config/reliability.toml           default outage rates/durations (replaced by NCC event stats when present)
config/boundary_points.csv        metering perimeter for reconciliation
config/reconfig_options.csv       switching options proposed by mentors (empty = none)
config/aliases.csv                public name variants -> canonical codes
config/holidays_ug.csv            2025-2030 public holidays (day-type weights)
config/profiles/standard_profiles.csv  fallback 24 h shapes, WD/NWD x class
templates/spec.toml               ONE source of every sheet/column/unit/range/enum: generates xlsx AND validates loads
templates/build_templates.py      writes T01-T12 from spec.toml
templates/README.md               cover-note text, contacts, accepted alternatives, handling statement
templates/T01..T12_*.xlsx         generated, committed (Monday attachments)
data/ (gitignored)                synthetic/ real/ scrubbed/ open/ basemap/ logs/ backups/ ; README.md only in git
loaders/base.py                   manifest, sha256, batch+issue logging, spec validation, provenance
loaders/names.py                  normalise(), alias lookup, difflib suggestions, line-name parser
loaders/units.py                  pu<->ohm, B<->C, MVA<->kA, R(T) correction, range checks
loaders/network_excel.py          T01 -> net.*
loaders/network_pypowsybl.py      PSS/E RAW, DGS, CGMES -> canonical (amd64 image)
loaders/network_pandapower.py     pandapower JSON (PowerFactory converter, MATPOWER) -> canonical
loaders/network_handbuilt.py      T12 schedules + conductors.csv -> canonical (approximate)
loaders/gis.py                    T02 -> gis.* -> ref.substation / ref.route (attribute, then spatial match)
loaders/{ncc_monthly,scada,commercial,plants,feeders,planned,sites,growth,explanations,open_data}.py
loaders/adapters/                 one file per native layout, e.g. ncc_pss_native.py -> template-shaped frames
engine/cli.py                     python -m engine.cli worker|migrate|synth|load|run|pin|report|bench
engine/db.py                      engine, COPY, migrate, advisory lock, run registry
engine/provenance.py              table->dataset dependency map; level computation
engine/network/build.py           canonical -> pandapower net (as_of date, status filter)
engine/network/checks.py          islands, impedance/rating outliers, GIS length check, flat-start test
engine/profiles.py                SCADA -> profiles; borrowed/standard fallback; energy & peak fits
engine/cases.py                   snapshots (month x day type x hour), peak cases, 2030 cases, weights
engine/loadflow.py                run_pf retry ladder + result extraction (shared with API live trip)
engine/losses.py                  element/month MWh, kW/km, Central totals, LLF cross-check
engine/reconcile.py               basis selection, metered vs modelled, diagnostics
engine/remedies.py                top-10, reconductoring, reconfiguration, compensation, payback
engine/contingency.py             N-1 loop, islanding, severity, post-contingency loadings
engine/forecast.py                2030 network, loads, 12-month loss estimate
engine/kawanda.py                 element set, measured vs modelled, lambda sweeps, suppressed demand
engine/sites.py                   raw factor metrics, hosting, grid effect, margin, EUE, developments
engine/replay.py                  stretch: 14 June replay
engine/synthetic/generate.py      writes data/synthetic in template formats
engine/synthetic/spec_*.csv       synthetic substations, lines, plants, sites
api/main.py                       app, routers, self-hosted /api/docs, GET only
api/db.py                         atlas_ro engine, query -> DataFrame
api/tables.py                     table registry: view, columns, units, decimals, filters, provenance deps
api/render.py                     single path for JSON, CSV, XLSX (rounding, provenance column, README sheet)
api/scoring.py                    applies scoring.json (the only scorer)
api/live.py                       live trip: cached case nets, timeout, fallback
api/routers/                      meta network losses constraints kawanda industry dashboard export
web/index.html                    map; losses.html n1.html kawanda.html sites.html dashboard.html imports.html about.html
web/css/atlas.css, web/js/common.js (banner, watermark, tables, downloads), map.js losses.js n1.js kawanda.js sites.js dashboard.js imports.js
web/vendor/                       leaflet-1.9.4, chartjs-4.4.7, swagger-ui-5.x, VERSIONS.md (sha256, licences)
nginx/default.conf.template       static, /api /export proxy, /tiles /basemap /methods, gzip, CSP, GET-only, allow-list
scripts/verify.sh                 acceptance checks
scripts/bundle.sh                 amd64 build, docker save, checksums, code + git bundle, open data -> USB folder
scripts/install_offline.sh        server: verify checksums, docker load, chown data, compose up --no-build
scripts/firewall.sh + gridatlas-firewall.service   DOCKER-USER (or nft) rules, re-applied after docker on boot
scripts/make_basemap.sh           Mac only: DEM -> hillshade tiles; OSM/admin -> GPKG + simplified GeoJSON
scripts/page_timing.sh, scripts/demo_check.sh
tests/unit/ integration/ converters/ (amd64-only, marked) perf/ golden/ conftest.py
docs/architecture.md runbook-server.md data-requests.md provenance.md demo-script.md open-data-sources.md
docs/decisions/                   ADRs (as Grid Monitor): mounted code, canonical workbook, server-side scoring, provenance, perimeter, egress
docs/methods/01..09-*.md + signoffs.csv   one note per feature: inputs, method, assumptions, known gaps, validation, sign-off
docs/_private/                    SOW .docx and scanned board paper: gitignored (internal board document)
```

---

## 2. docker-compose.yml design (problem 8)

```yaml
name: gridatlas
x-logging: &logging {driver: json-file, options: {max-size: 10m, max-file: "3"}}
x-pyenv: &pyenv {TZ: Africa/Kampala, PYTHONPATH: /app, PYTHONDONTWRITEBYTECODE: "1",
                 OMP_NUM_THREADS: "1", OPENBLAS_NUM_THREADS: "1", MKL_NUM_THREADS: "1", ATLAS_ENV: "${ATLAS_ENV:-dev}"}
x-py: &py
  image: gridatlas-py:${ATLAS_VERSION:?set ATLAS_VERSION}
  build: {context: ., dockerfile: docker/py.Dockerfile}
  logging: *logging
  restart: unless-stopped
  read_only: true
  tmpfs: [/tmp]
  user: "10001:10001"
  oom_score_adj: 500          # kernel kills Atlas before Grid Monitor
  cpu_shares: 512             # Grid Monitor wins CPU contention
services:
  db:
    image: gridatlas-db:${ATLAS_VERSION}
    build: ./db
    environment: {POSTGRES_DB: gridatlas, POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?}",
                  ATLAS_RW_PASSWORD: "${ATLAS_RW_PASSWORD:?}", ATLAS_RO_PASSWORD: "${ATLAS_RO_PASSWORD:?}"}
    command: [postgres, -c, shared_buffers=128MB, -c, effective_cache_size=512MB, -c, work_mem=8MB,
              -c, maintenance_work_mem=64MB, -c, max_connections=30]
    volumes: [pgdata:/var/lib/postgresql/data, ./db/init:/docker-entrypoint-initdb.d:ro]
    networks: [core]                       # never published
    healthcheck: {test: [CMD-SHELL, "pg_isready -U postgres -d gridatlas"], interval: 5s, timeout: 5s, retries: 30}
    deploy: {resources: {limits: {memory: "${DB_MEM:-768m}", cpus: "1.0"}}}
    shm_size: 128m
    logging: *logging
    restart: unless-stopped
    oom_score_adj: 500
  worker:
    <<: *py
    command: [python, -m, engine.cli, worker]   # wait db -> migrate -> optional bootstrap -> idle
    environment: {<<: *pyenv, DATABASE_URL: "postgresql+psycopg://atlas_rw:${ATLAS_RW_PASSWORD}@db/gridatlas",
                  BOOTSTRAP: "${BOOTSTRAP:-none}", ALLOW_SYNTHETIC: "${ALLOW_SYNTHETIC:-0}", ATLAS_JOBS: "${WORKER_JOBS:-1}"}
    volumes: [./loaders:/app/loaders:ro, ./engine:/app/engine:ro, ./config:/app/config:ro, ./templates:/app/templates:ro,
              ./db/migrations:/app/db/migrations:ro, ./tests:/app/tests:ro, ./VERSION:/app/VERSION:ro, ./data:/data]
    networks: [core]
    depends_on: {db: {condition: service_healthy}}
    healthcheck: {test: [CMD, test, -f, /tmp/atlas-worker-ready], interval: 10s, start_period: 900s, retries: 3}
    deploy: {resources: {limits: {memory: "${WORKER_MEM:-1536m}", cpus: "${WORKER_CPUS:-1.5}"}}}
  api:
    <<: *py
    command: [uvicorn, api.main:app, --host, 0.0.0.0, --port, "8000", --workers, "1", --proxy-headers]
    environment: {<<: *pyenv, DATABASE_URL: "postgresql+psycopg://atlas_ro:${ATLAS_RO_PASSWORD}@db/gridatlas",
                  SCORING_CONFIG: /app/config/scoring.json}
    volumes: [./api:/app/api:ro, ./engine:/app/engine:ro, ./config:/app/config:ro, ./VERSION:/app/VERSION:ro]  # no data/
    networks: [core]
    depends_on: {db: {condition: service_healthy}}
    healthcheck: {test: [CMD, python, -c, "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"],
                  interval: 15s, retries: 5, start_period: 30s}
    deploy: {resources: {limits: {memory: "${API_MEM:-512m}", cpus: "1.0"}}}
  web:
    image: nginx:1.28.0-alpine
    environment: {ATLAS_ALLOW_CIDR: "${ATLAS_ALLOW_CIDR:-127.0.0.1/32}"}
    volumes: [./nginx/default.conf.template:/etc/nginx/templates/default.conf.template:ro,
              ./web:/usr/share/nginx/html:ro, ./data/basemap:/usr/share/nginx/basemap:ro,
              ./docs/methods:/usr/share/nginx/methods:ro]
    ports: ["${ATLAS_BIND_IP:-127.0.0.1}:${ATLAS_HTTP_PORT:-8090}:80"]
    networks: [edge, core]
    depends_on: {api: {condition: service_healthy}}
    healthcheck: {test: [CMD, wget, -qO-, http://127.0.0.1/healthz], interval: 15s}
    deploy: {resources: {limits: {memory: 64m, cpus: "0.25"}}}
    logging: *logging
    restart: unless-stopped
    oom_score_adj: 500
networks:
  core: {internal: true, ipam: {config: [{subnet: "${ATLAS_CORE_SUBNET:-172.30.90.0/28}"}]}}
  edge:
    driver: bridge
    driver_opts: {com.docker.network.bridge.enable_ip_masquerade: "false"}
    ipam: {config: [{subnet: "${ATLAS_EDGE_SUBNET:-172.30.90.16/28}"}]}
volumes:
  pgdata: {}
```

**The worker** is a long-lived container, so `docker compose up` shows four running containers as SOW §9 requires.
- On start it waits for the database, then applies `db/migrations` in order. Files 001–899 are applied once and tracked in `meta.schema_migration`; 900 is re-applied every time.
- With `BOOTSTRAP=synthetic` (dev default) and an empty database, it runs synth, load and a full run with `--pin`.
- It then writes `/tmp/atlas-worker-ready` and sleeps.
- Jobs run as `./atlas run …`, which is `docker compose exec -T worker python -m engine.cli run …`. `--bg` uses `exec -d` and logs to `/data/logs/`.
- A PostgreSQL advisory lock stops two concurrent loads or runs.
- On the server `BOOTSTRAP=none`, and synthetic loads are refused unless `ALLOW_SYNTHETIC=1`.

**Code is mounted, not baked.** The image carries only dependencies, which rarely change. Code updates reach the offline VM as a few-MB folder or `git bundle` on the USB stick, not a rebuilt 400 MB image. The run records `VERSION` plus a sha256 of the mounted `.py` tree. This deliberately differs from Grid Monitor and is recorded as an ADR. Data mounts must be chowned to uid 10001 on the server.

**Offline delivery** (`scripts/bundle.sh` on the Mac, mirroring DEPLOYMENT.md §2):
1. Cross-build: `docker-buildx build --platform linux/amd64 -t gridatlas-py:$V --load`, and the same for `gridatlas-db`.
2. Pull `nginx:1.28.0-alpine` for amd64.
3. `docker save --platform linux/amd64 … | gzip > images/atlas-images.tar.gz`. Expect about 0.5–0.6 GB, which is under the FAT32 4 GB limit, so no split is needed.
4. Copy `git ls-files` with rsync plus a `git bundle`, then `data/basemap` and `data/open`, then `sha256sum`.
5. On the server: `install_offline.sh` checks sums, runs `docker load` and `chown 10001 data/`, then `docker compose up -d --no-build`.

**Basemap and hillshade without internet.** These are built once on the Mac inside the GDAL 3.13.3 container (`scripts/make_basemap.sh`):
- DEM: Copernicus GLO-30 tiles for lon 31–34, lat −1 to 2. They need no login; SRTM is equally acceptable. Steps: `gdalwarp` to EPSG:3857, `gdaldem hillshade -multidirectional`, then `gdal raster tile` for z7–13 in XYZ convention. That is about 3–4k PNGs, roughly 50–100 MB.
- Slope: `gdaldem slope -p` in EPSG:32636 for terrain scoring.
- Vector basemap: Geofabrik Uganda `.osm.pbf` (trunk/primary/secondary roads, water, rail, towns) and HDX COD-AB districts. These become GPKGs (loaded into PostGIS for site metrics) and simplified GeoJSON (served statically).
- Leaflet then shows the hillshade tiles plus GeoJSON lakes, districts, roads and towns. There are no OSM raster tiles: bulk-downloading them breaks OSM's tile policy, and nothing goes to a CDN.

**No CDN.** All libraries are vendored. Nginx sends `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'`, so any external URL fails loudly in dev. `/api/docs` gets a relaxed CSP for Swagger's inline init script, and the Swagger assets are self-hosted per FastAPI's "Self-Hosting" how-to.

**Ports and firewall**
- Default port is 8090, avoiding 80/443, 8000/8100 (Grid Monitor) and 8080/8443 (its LLM proxy). Check it with `ss -ltnp` on the VM.
- The port is published only on `ATLAS_BIND_IP`, which is the same control-room address as Grid Monitor's `WEB_BIND_IP`.
- Docker's NAT rules bypass ufw INPUT, and with firewalld Docker adds an ACCEPT `docker` zone. So filtering goes in `DOCKER-USER`, which `scripts/firewall.sh` applies idempotently and a systemd unit re-applies after `docker.service` on boot:
  ```sh
  iptables -I DOCKER-USER -s "$ATLAS_EDGE_SUBNET" -m conntrack --ctstate NEW -j DROP   # nginx may answer, never initiate
  iptables -I DOCKER-USER -p tcp -m conntrack --ctorigdst "$ATLAS_BIND_IP" --ctorigdstport "$ATLAS_HTTP_PORT" \
           ! -s "$ATLAS_ALLOW_CIDR" -j DROP                                            # pre-DNAT port, per Docker docs
  ```
- Under Docker 29's experimental nftables backend there is no DOCKER-USER chain. The script instead creates `table ip gridatlas { chain forward { type filter hook forward priority filter - 1; … } }` with the same two rules, using `ct state new` and `ct original proto-dst`. Check which backend is active with `docker info`.
- The rules match only Atlas subnets, so Grid Monitor (host-networked collector, its own bridge) is untouched.
- Choose `ATLAS_*_SUBNET` with the network team so it cannot overlap control-room or substation ranges.

**Result:** `api`, `worker` and `db` have no default route (`/proc/net/route` has no `00000000` destination). Nginx cannot open connections, and its masquerade is off as defence in depth.

**Memory**
- The limits total about 2.9 GB. Idle use is about 0.6 GB, because the worker sleeps.
- Before installing, measure `free -m` and Grid Monitor's `docker stats`. If headroom is under 3 GB, set `WORKER_MEM=1g`, run jobs at night, and keep `WORKER_JOBS=1`.

---

## 3. PostGIS schema

Every input row carries `batch_id`, and every result row carries `run_id`.

**meta**
- `dataset(code, criticality critical|high|medium|low)`
- `import_batch(batch_id, dataset, source_file, sha256, adapter, provenance synthetic|approximate|open|real, received_from, received_on, loaded_at, code_version, rows_read, rows_loaded, rows_failed, status)`
- `import_issue(batch_id, sheet, row_num, column, severity error|warning|info, code, message, raw_value, suggestion)`
- `run(run_id, started_at, finished_at, status, code_version, config_snapshot jsonb, config_sha256, model_version_id, provenance_level, provenance_detail jsonb)`
- `run_input(run_id, batch_id)`
- `run_stage(run_id, stage, started_at, finished_at, n_loadflows, n_failed)`
- `settings(key, value)`, holding `pinned_run_id` and `active_model_version`
- `signoff(note, signed_by, role, signed_on, code_version)`
- View `v_current_run`: the pinned run, otherwise the latest successful one.

**ref**
- `substation(ss_code, name, district, kv_levels int[], in_central, geom Point 4326, geom_source)`
- `alias(alias_norm, entity_type, canonical_id, source)`
- `element(element_id, element_type line|trafo2w|trafo3w|gen|load|shunt|ext_grid, name, from_ss, to_ss, kv, circuit, in_central, is_equivalent, loss_bucket line_132|line_220|trafo_220_132|trafo_132_33, route_id)`
- `route(route_id, geom LineString, geom_simpl, length_gis_km)`
- `month(month_id, start_date, days, hours, n_wd, n_nwd, is_forecast)`, seeded with 2025-09 to 2026-09 and 2030
- `holiday(date, name)`

**net** (canonical network, versioned by `model_version_id`; every element has `status existing|committed|planned`, `commission_date`, `decommission_date`, `param_source model|nameplate|typical`, `project_id`)
- `model_version(id, source_kind psse|cgmes|dgs|excel|handbuilt|synthetic, case_name, base_mva, perimeter central|national, batch_id)`
- `bus(bus_id, ss_code, vn_kv, zone, v_min_pu, v_max_pu, source_bus_no)`
- `line(line_id, from_bus, to_bus, circuit, length_km, conductor, r_ohm_per_km, x_ohm_per_km, b_us_per_km, r_temp_c, rate_a_mva, rate_b_mva, tower_group)`, one row per circuit
- `trafo2w(trafo_id, hv_bus, lv_bus, sn_mva, vn_hv_kv, vn_lv_kv, vk_percent, vkr_percent, pfe_kw, i0_percent, shift_degree, tap_side, tap_min, tap_max, tap_neutral, tap_step_percent, tap_pos, rate_b_mva)`
- `trafo3w(…)`
- `gen(gen_id, bus, plant_code, technology, p_max_mw, p_min_mw, q_min_mvar, q_max_mvar, vm_pu, control)`
- `load_point(load_id, bus, ss_code, share, pf_default)`
- `shunt(shunt_id, bus, q_mvar)`
- `switch(switch_id, bus, element_id, closed, normally_open)`
- `boundary(boundary_id, bus, kind slack|pv|fixed_p, vm_pu, p_source)`
- `project(project_id, name, type, status, cod, relief_for, source_doc)`

**ts** (inputs)
- `ncc_system_monthly`
- `ncc_losses_by_voltage(month_id, scope, voltage_kv, losses_mwh, how_computed)`
- `ncc_substation_monthly(month_id, ss_code, point, metering_kv, energy_mwh, peak_mw, peak_at, peak_mvar, min_mw, quality)`
- `ncc_generation_monthly`
- `ncc_boundary_meter_monthly(month_id, meter_point, element_id, direction, energy_mwh, meter_class)`
- `ncc_deemed_unserved`
- `ncc_sample_day(month_id, peak_day, offpeak_day)`
- `event(start_at, end_at, element_id, event_type, mw_lost, cause)`
- `scada_point(point_id, ss_code, bay, element_id, quantity, unit, sign)`
- `scada_hourly(ts timestamptz, point_id, value, quality)`, primary key `(ts, point_id)`
- `tariff`, `bsp_billed`, `deemed_invoice`
- `curtailment(start_at, end_at, customer_category, customer_ref, ss_code, mw, reason)`
- `deferred_connection(application_date, customer_category, requested_mw, ss_code, status, reason)`
- `plant`, `feeder_monthly`, `planned_load`, `growth_rate`
- `site(site_id, name, district, status, area_ha, geom)`, `site_metric_override`
- `recon_explanation(month_id, basis, cause_code, explanation, quantified_mwh, evidence, author, reviewed_by, review_date)`

**gis**
- Source layers: `substation_src`, `line_route_src`, each with `attrs jsonb`, `matched_id` and `match_method`.
- Open layers: `lake`, `district`, `road(class)`, `rail`, `town`, `port`, `protected_area`, `wetland`, `flood_zone`, `industrial_park`, `population_subcounty`.

**results** (all with `run_id`)
- `case(case_id, kind hour|month_peak|forecast_peak|sweep|site, month_id, day_type, hour, weight_h, total_load_mw, slack_mw, converged, init_used, profile_source, net_json)`. `net_json` is stored only for N-1 base cases.
- `element_snapshot(case_id, element_id, p_from_mw, q_from_mvar, i_ka, loading_pct, loss_mw)`, about 62k rows per run
- `bus_snapshot(case_id, bus_id, vm_pu, va_deg)`
- `element_month(month_id, element_id, loss_mwh, loss_kw_per_km, max_loading_pct, peak_loading_pct, energy_through_mwh)`
- `central_month(month_id, load_mwh, gen_mwh, loss_mwh_total, loss_line_132, loss_line_220, loss_trafo_220_132, loss_trafo_132_33, loss_pct, value_ugx, llf, llf_check_mwh, profile_source, scada_days)`
- `recon_month(month_id, basis, metered_loss_mwh, modelled_loss_mwh, gap_mwh, gap_pct, within_tolerance, diagnostics jsonb)`
- `remedy(element_id, remedy_type, option, capex_ugx, delta_loss_mwh_yr, value_ugx_yr, payback_yr, n1_effect)`
- `n1_result(case_id, contingency_id, tripped text[], converged, method, load_lost_mw, max_loading_pct, max_loading_element, min_vm_pu, min_vm_bus, overload_mva, severity_class, severity_rank)`
- `n1_violation(case_id, contingency_id, object_type, object_id, kind, value, limit, base_value)`
- `n1_post_loading(case_id, contingency_id, element_id, loading_pct)`
- `kawanda_element(element_id, hypothesis H1_transformers|H2_lines)`
- `kawanda_monthly(month_id, element_id, measured_max_pct, measured_p95_pct, modelled_peak_pct, n1_worst_pct, n1_worst_contingency)`
- `kawanda_headroom(variant before|after_relief, criterion N-0|N-1, lambda_star, extra_mw, binding_element, binding_contingency, years_to_exhaust)`
- `kawanda_verdict(binding_hypothesis, agreement, evidence jsonb)`
- `kawanda_suppressed(month_id, reason, curtailed_mwh, curtailed_ugx, deferred_mw)`
- `site_hosting(site_id, case now|2030, bus, mw_n0, mw_n1, binding_element, binding_contingency, preexisting jsonb)`
- `site_effect(site_id, load_type, p_mw, dloss_mw_peak, dloss_per_mw, dloss_mwh_yr, dloss_ugx_yr, top_affected jsonb, new_n1_violations, firm_margin_now_mw, firm_margin_2030_mw, eue_mwh_yr, eue_ugx_yr)`
- `site_metric(site_id, load_type, metric, value, unit, source)`
- `site_development(site_id, load_type, item, reason)`
- `forecast(year, peak_mw, growth_factor, projects text[], loss_mwh_yr)`

**api views** (the only objects `atlas_ro` can read; the API and exports read nothing else)
- `v_provenance`, `v_months`
- `v_substations_geo`, `v_routes_geo`, `v_route_month` (worst circuit per route), `v_element_detail`
- `v_losses_monthly`, `v_element_losses`, `v_recon`, `v_top10_losses`, `v_remedies`
- `v_n1_cases`, `v_n1_results`, `v_n1_violations`, `v_n1_post_loading`, `v_case_model`
- `v_kawanda_loading`, `v_kawanda_headroom`, `v_kawanda_trips`, `v_kawanda_verdict`, `v_kawanda_suppressed`
- `v_site_inputs` (raw metrics, hosting, effect, margin, EUE)
- `v_dashboard_kpis`, `v_import_batches`, `v_import_issues`

All are filtered to `meta.v_current_run`.

**Roles and grants**
```sql
-- db/init/00_roles.sh (first boot, superuser; passwords via psql variables)
CREATE EXTENSION postgis;
CREATE ROLE atlas_rw LOGIN PASSWORD :'rw';                       -- worker: owns all schemas
CREATE ROLE atlas_ro LOGIN PASSWORD :'ro' CONNECTION LIMIT 20;   -- API
ALTER ROLE atlas_ro SET default_transaction_read_only = on;
ALTER ROLE atlas_ro SET statement_timeout = '5s';
REVOKE ALL ON DATABASE gridatlas FROM PUBLIC;
GRANT CONNECT ON DATABASE gridatlas TO atlas_rw, atlas_ro;
GRANT CREATE ON DATABASE gridatlas TO atlas_rw;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- 900_api_views.sql (as atlas_rw)
GRANT USAGE ON SCHEMA api TO atlas_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO atlas_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO atlas_ro;
-- atlas_ro has no USAGE on meta/ref/net/ts/gis/results: views execute with the owner's rights.
```
The `postgres` superuser is used only by init and break-glass `./atlas psql`. Port 5432 is never published.

---

## 4. Data contracts (problem 7)

**One source of truth.** `templates/spec.toml` defines each sheet: columns, type, unit, required flag, min/max (warn/error), enums and an example. `build_templates.py` writes the xlsx files from it: a README sheet, headers, unit comments on header cells, and data-validation dropdowns. The loaders validate against the same spec, so templates and loaders cannot drift.

**Ask for native formats too.** Every cover note says "send what you already have, in its native format; the template is the minimum field list". A native layout costs us one adapter in `loaders/adapters/`, with no other code change.

**Example rows.** These use dummy names ("Example A") so nobody reads them as our estimate of real values. Timestamps are EAT.

**T01 network_model.xlsx (Planning).** Needed only if no RAW, CGMES or DGS is available. With a RAW file, fill just `ratings` and `names`.

| Sheet | Columns (unit) | Example |
|---|---|---|
| README | source system/version, case name/date, base MVA, rating basis (ambient °C, conductor °C), contact | — |
| buses | bus_id, name, substation, vn_kv (kV), zone, in_service (Y/N), v_min_pu, v_max_pu, source_bus_no | EXA-132-1, Example A 132 kV 1, Example A, 132, Central, Y, 0.95, 1.05, 1301 |
| lines (one row per circuit) | line_id, from_bus, to_bus, circuit, length_km (km), conductor, r_ohm_per_km (Ω/km), x_ohm_per_km (Ω/km), b_us_per_km (µS/km), r_temp_c (°C), rate_a_mva (MVA normal), rate_b_mva (MVA emergency), shares_towers_with, in_service, status, in_service_date (YYYY-MM) | EXA-EXB-132-1, EXA-132-1, EXB-132-1, 1, 16.4, ACSR Bear, 0.136, 0.401, 2.85, 75, 137, 160, EXA-EXB-132-2, Y, existing, 2003-01. Alternatively r/x/b in pu on 100 MVA. |
| transformers_2w | trafo_id, hv_bus, lv_bus, sn_mva (MVA), vn_hv_kv, vn_lv_kv (kV), vk_percent (%), vkr_percent (%) or load_loss_kw (kW), pfe_kw (kW), i0_percent (%), vector_group, tap_side, tap_min, tap_max, tap_neutral, tap_step_percent (%), tap_pos, rate_b_mva, in_service, status, in_service_date | EXA-T1, EXA-220-1, EXA-132-1, 150, 220, 132, 12.5, 0.30, –, 85, 0.05, YNyn0, hv, −10, 10, 0, 1.25, 0, 165, Y, existing, 2012-01 |
| transformers_3w | as above per winding pair | — |
| generators | gen_id, bus, plant, technology, p_max_mw, p_min_mw (MW), q_min_mvar, q_max_mvar (MVAr), vm_pu, control (PV/PQ), in_service, status | EXA-G1, EXA-11-1, Example Thermal, HFO, 50, 10, −20, 30, 1.01, PV, Y, existing |
| loads | load_id, bus, substation, share (0–1), pf_default | EXA-D1, EXA-33-1, Example A, 0.6, 0.95 |
| shunts | shunt_id, bus, q_mvar (MVAr; + reactor, − capacitor), steps, in_service | EXA-C1, EXA-33-1, −10, 2, Y |
| switches | switch_id, bus, element_id, closed, normally_open | — |
| boundary | bus, kind (slack/pv/fixed_p), vm_pu, note | EXB-220-1, slack, 1.02, Nile injection |
| ratings, names | for RAW cases: element, rate_a/b_mva; bus number → substation name | — |

**T02 GIS spec (GIS unit).** Preferred format is GeoPackage, then zipped Shapefile with `.prj`, GeoJSON, then KML/KMZ. Any declared CRS is accepted (EPSG:4326, 21096, 32636).
- substations (Point): ss_code, name, kv_levels, status, survey_date. Example: `EXA, Example A, 220/132/33, existing, 2024-05`.
- routes (LineString): route_id, name, from_ss, to_ss, kv, circuits, status.

**T03 ncc_monthly.xlsx (NCC).** One workbook for all months, or one per month.

| Sheet | Columns (unit) | Example |
|---|---|---|
| sample_days | month, peak_day, offpeak_day, note | 2026-03, 2026-03-12, 2026-03-15, peak = monthly max |
| system_summary | month, generated_mwh, imported_mwh, exported_mwh, sent_out_mwh, delivered_mwh, losses_mwh, peak_mw, peak_at, unserved_mwh, deemed_mwh | 2026-03, 520400, 3200, 18900, 515600, 489000, 26600, 1350, 2026-03-12 20:00, 2100, 9800 |
| losses_by_voltage | month, scope (national/Central/…), voltage (220/132/total), losses_mwh, losses_pct, how_computed (which meters) | 2026-03, national, 132, 21400, 3.9, "132 kV injection meters minus 33 kV BSP meters" |
| substation_monthly | month, substation, point (blank/transformer/feeder group), metering_kv, energy_mwh, peak_mw, peak_at, peak_mvar, min_mw, quality | 2026-03, Example A, T1+T2 LV, 33, 41250, 82.4, 2026-03-12 20:00, 21.0, 31.5, actual |
| generation_monthly | month, plant, sent_out_mwh, peak_mw, availability_pct | 2026-03, Example Solar, 3900, 19.6, 98 |
| boundary_meters | month, meter_point, line_or_tx, direction (import/export), energy_mwh, meter_class, quality | 2026-03, Example A – line to Example B 1, EXA-EXB-220-1, import, 152300, 0.2S, actual |
| deemed_unserved | month, category (deemed/unserved/load_shed), plant_or_substation, energy_mwh, amount_ugx, cause, constraint_element | — |
| events | start_at, end_at, element, event_type, mw_lost, cause, notes | 2026-04-03 19:12, 2026-04-03 22:40, Example A–B 1, forced trip, 35, protection, — |

**T04 SCADA (NCC historian).** CSV, one file per sample day, hourly averages (half-hourly accepted). Columns: `timestamp, substation, bay, quantity (P|Q|V|I), value, unit (MW|MVAr|kV|A), quality`. Example: `2026-03-12T20:00:00+03:00,Example A,Line to Example B 1,P,92.4,MW,good`.
- `scada_points.xlsx` maps bay to element and states the sign convention: + means flow from the busbar into the bay.
- Priority points: every Kawanda bay; boundary ties; every 132/33 kV transformer LV bay; 132 and 220 kV busbar kV.
- Ask for whole months of hourly data on these points if the export is easy. The engine uses as many days as it receives.

**T05 commercial.xlsx (Commercial).**
- tariffs: effective_from, effective_to, tariff_code, ugx_per_kwh, era_ref
- bsp_billed: month, bulk_supply_point, customer, energy_kwh, amount_ugx
- deemed_invoices: month, plant, deemed_kwh, amount_ugx, cause_category, constraint_location
- curtailments: start_at, end_at, customer_category, customer_ref (anonymised, no names), substation, mw_curtailed, reason (Kawanda/generation/other)
- deferred_connections: application_date, customer_category, customer_ref, requested_mw, substation_or_area, status, reason

**T06 plants.xlsx (UEGCL/ERA register).** plant, owner, technology, installed_mw, firm_mw, availability_pct, connection_substation, connection_kv, cod, status, lat, lon, deemed_clause.

**T07 uedcl_feeders.xlsx.** month, substation, feeder, kv, peak_mw, energy_mwh, industrial_share_pct, embedded_gen_mw, deemed_mwh_33kv.

**T08 planned_projects.xlsx (Planning/MEMD).**
- projects: project_id, name, type, status, cod (YYYY-MM), from_ss, to_ss, kv, circuits, length_km, conductor, mva, relief_for, source_document
- planned_loads: load_id, name, category, substation, mw, pf, status, cod

**T09 candidate_sites (UIA and team).** Boundaries as GPKG/KML. The xlsx has sheet `sites` (site_id, name, district, status, owner, area_ha, lat/lon if no polygon) and sheet `site_metric_override` (site_id, metric, value, unit, source).

**T10 growth.xlsx.** scope, substation, year_from, year_to, rate_pct_per_yr, scenario, source.

**T11 recon_explanations.xlsx (internal).** month, basis, cause_code (data_gap / meter_error / outage_topology / boundary_flow_unknown / metering_perimeter / station_service / model_parameter / event / other), explanation, quantified_mwh, evidence_ref, author, reviewed_by, review_date.

**T12 handbuilt_network.xlsx (internal fallback).**
- line_schedule: from_ss, to_ss, kv, circuits, length_km, conductor, conductors_per_phase, source
- transformer_schedule: substation, units, mva_each, hv_kv, lv_kv, vk_percent, source

**Questions attached to the requests** (these decide the reconciliation):
1. How does NCC compute "losses by voltage level", and at which meters?
2. Are bulk supply point meters on the HV or LV side of the 132/33 kV transformers?
3. Which Central boundary points have energy meters?
4. What is the SCADA sign convention?
5. Do Kawanda ratings mean normal or emergency, and at what ambient temperature?
6. What is the planned Kawanda relief, and when is it due in service?
7. Does the Planning model cover the whole network?

**Name matching**
- `normalise()` upper-cases, strips punctuation, removes tokens (SUBSTATION, S/S, SS, POWER STATION, KV, voltage numbers such as 132 or 33/11) and collapses spaces. "Kawanda S/S 132kV" becomes `KAWANDA`.
- An exact match on `ref.alias` gives a 3-letter `ss_code`.
- Line names are split on `-`, `–`, `/` and "to". Circuit comes from 1/2, I/II or "Ckt", and kV from text or the common bus voltage. The ID is `L-<A>-<B>-<kV>-<ckt>` with endpoints in alphabetical order.
- Model buses map through bus name or number to `ss_code`. GIS routes match by attributes, otherwise by endpoints within 1 km of substation points; double circuits share a `route_id`.
- Anything unmatched is an error row (not loaded) logged with a difflib suggestion (ratio ≥ 0.8). Suggestions are never auto-applied: a person adds the alias to `config/aliases.csv` through a reviewed commit.
- SCADA tag maps stay in `data/real/` because tag names are sensitive.

**Import log**
- Each file in `data/<source>/manifest.toml` lists dataset, adapter, provenance, sender, date received and sha256. The loader refuses unlisted or changed files.
- Each load opens a batch, validates against the spec and runs cross-checks:
  - Σ substation energy vs NCC delivered, within ±5%
  - monthly load factor between 0.3 and 0.95
  - x/r ratio between 1.5 and 10
  - model length vs GIS length, within 15%
  - unit sanity (kWh entered as MWh)
- Failures go to `import_issue`. Reloads replace the dataset's rows for the same keys inside one transaction, so they are idempotent.
- `imports.html` shows it. "Zero failed rows for critical datasets" (network, GIS, NCC monthly) is a computed tick.

---

## 5. Network-model ingestion (problem 1)

pandapower 3.5.6 converts PYPOWER, MATPOWER (`from_mpc`), PowerFactory (only inside PowerFactory's Python API, so it needs a licence), CGMES/CIM, UCTE, JAO and OpenDSS. It has no PSS/E reader. Every path below therefore ends in the canonical `net.*` tables, which can also be exported as a T01 workbook for Planning to review. One builder, `engine/network/build.py`, makes the pandapower net from those tables.

| Source | Path to canonical tables | Notes |
|---|---|---|
| PSS/E RAW v33/v35 (preferred) | `pypowsybl.network.load()` → dataframes (buses, voltage levels, lines, 2W/3W transformers, generators, loads, shunts, operational limits) → `network_pypowsybl.py` | Ohm/siemens values are converted to per-km values and to vk%/vkr%/pfe/i0 on the rated base. Current limits become MVA (√3·V·I). Very low impedance branches become closed switches. Taps are fixed at the case position. Runs on the amd64 server. |
| RAW v29–32 or v34 | Ask for "save as v33". Fallback: VeraGridEngine (pure Python, reads RAW v29–35 and DGS) | Pin it only if used. |
| DIgSILENT PowerFactory | (a) Planning exports PSS/E RAW from PowerFactory, then the row above; (b) DGS → pypowsybl `POWER-FACTORY` importer (import only, partial coverage); (c) CGMES → pypowsybl or pandapower CIM; (d) pandapower's PF converter run on Planning's licensed PC → JSON → `network_pandapower.py`; (e) PF tabular export into T01 | Ask for (a) first. |
| Excel | T01 → `network_excel.py` | |
| Hand-built | T12 line and transformer schedules + `config/conductors.csv` (typical per-km R, X, B and ampacity per conductor and voltage) + default transformer impedances by MVA class → `network_handbuilt.py` | Flagged `param_source=typical` and `provenance=approximate`. |

**Validation of any converted model** (results go into method note 01):
1. Run pandapower and compare with the voltages stored in the solved RAW case: |ΔV| < 0.005 pu.
2. Compare with pypowsybl OpenLoadFlow (`run_ac`) on the same case: branch flows within 2% or 1 MW.
3. Apply `checks.py`.
4. Produce a Central element list for the Planning mentor to confirm (week 1 task).

**Perimeter.** If the Planning model covers the whole network, run it whole (`model.perimeter="national"`) and report only Central. That is still under a second per load flow, and it avoids distorted boundary flows. For a Central-only model:
- Bujagali 220 kV is the slack.
- Nalubaale 132 kV is a PV injection with measured P.
- Mbarara is a fixed-P tie.
- External equivalents are flagged `is_equivalent` and excluded from reporting and N-1.

**R temperature.** Line R is corrected to `r_temperature_c` (default 50 °C): `R_T = R_20·(1+0.00403·(T−20))`. A 20 °C vs 50 °C error alone is about 12%, which is bigger than the whole 10% gate.

---

## 6. Engine algorithms

### 6.1 Monthly MWh losses (problem 2)

1. **Day types.** For month m, `n_WD` is weekdays minus holidays and `n_NWD = D − n_WD`. NCC's peak day represents WD and its off-peak day represents NWD. With more SCADA days, each sampled day represents an equal share of its type, so full-month data gives exact weights.
2. **Profiles from SCADA.** `p_s,τ(h)` and `q_s,τ(h)` for each substation s, day type τ and hour h.
3. **Energy scaling.** `k_s = E_NCC,s,m / Σ_τ n_τ Σ_h p_s,τ(h)`, giving `P = k·p` and `Q = k·q`, with a warning if |k−1| > 0.25. Plants use the same method with sent-out energy. Boundary flows come from SCADA, otherwise from boundary-meter energy, otherwise the slack residual.
4. **48 snapshots** (2 × 24), each with weight `w_τ = n_τ` hours. Test: `Σ w = 24·D`.
5. **Load flow.** `runpp(algorithm="nr", init="results", numba=False)`.
6. **Losses per element.** `E_e,m = Σ_τ Σ_h w_τ · pl_mw_e(τ,h)`. Lines use `res_line`; transformers use `res_trafo`, so iron losses are included. Loss density is `1000·E_e,m / (H_m·L_e)` kW/km.
7. **Peak and N-1 cases.** Use the unscaled SCADA coincident peak hour. Otherwise use NCC substation peaks × coincidence factor (system peak / Σ substation peaks).
8. **Fallback when SCADA is missing** (recorded as `profile_source`):
   - Borrow normalised shapes from the same substation's other months (`scada-borrowed`).
   - Otherwise use standard shapes σ with a two-parameter fit to NCC energy E and peak P̂: `P(h) = a + b·σ(h)`, `b = (E − 24·D·P̂)/(S − 24·D)`, `a = P̂ − b`, where `S = Σ_τ n_τ Σ_h σ_τ(h)`. If a < 0, set a = 0 and b = E/S (`standard-shape`).
   - If NCC energy is also missing for a substation, use its share of adjacent months (`interpolated`, warning).
   - Missing Q uses `pf_default`.
9. **Cross-check on every month.** `LF = E/(P̂·H)`, `LLF = 0.3·LF + 0.7·LF²`, `E_LLF = ΔP_peak·LLF·H`. A large divergence flags a profile problem.
10. **Known gaps** (stated in method note 02): two-day sampling understates load variance, there is no OLTC control, and corona and station service are not modelled.

### 6.2 Loss reconciliation (problem 3)

**Like with like.** The modelled losses are summed over the same perimeter and the same voltage/transformer buckets as the metered figure, using `ncc_132_bucket` in `engine.toml`, which the NCC answers confirm.

For each month, the basis is the first available of:
1. `ncc_regional`: NCC already reports Central.
2. `metered_boundary`: `L_met = Σ boundary imports + Σ Central plant sent-out − Σ BSP deliveries − Σ exports`. `L_mod` sums elements with both ends inside the meter perimeter (`config/boundary_points.csv`).
3. `national`: the national model's 132 kV losses vs NCC national 132 kV losses.
4. `not_testable`: show only a loss-rate plausibility check. **Never** allocate national losses to Central by modelled share; that is circular.

The gap is `(L_mod − L_met)/L_met`. Status is PASS if |gap| ≤ 10%. Otherwise it is EXPLAINED if a T11 row exists with mentor `reviewed_by`, else UNEXPLAINED. The gate is #PASS ≥ 10 and #UNEXPLAINED = 0.

**How "the gap is explained" is recorded.** Each T11 row carries a cause code, a quantified MWh where possible, an evidence reference and the reviewer. The engine adds automatic diagnostics beside it: SCADA missing and fallback used; outage hours from `ts.event`; boundary meter gaps; LLF divergence; and loss sensitivity to conductor temperature (±10 °C).

**Second, independent check.** Where both ends of a line are metered, compare measured with modelled flow.

### 6.3 Top-10 and remedies

The ten lines with the highest 13-month MWh are listed. Annual figures are 13-month figures × 12/13.

- **Reconductoring** (ACSR to ACCC): `ΔE = E_e·(1 − R_new/R_old)`, verified by one re-run at the peak (flagged if more than 5% off). `capex = UGX/km × km × circuits`.
- **Compensation:** `Q_c = min(Q at the receiving bus, 20) MVAr` in 5 MVAr steps. Re-run the peak and off-peak snapshots for every month, then `ΔE ≈ Σ_m E_C,m · ΔP_loss,m / P_loss,m`.
- **Reconfiguration:** only options listed in `reconfig_options.csv`, using the same ratio method. An option is rejected if it creates a new N-1 class A–C.
- **Payback** = `capex / (ΔE × BST of the month)`. NPV at 12% is optional.

### 6.4 N-1 (problem 4)

**Elements.** Every in-service Central line circuit and transformer, about 40 in the synthetic network. Equivalents are excluded. An optional "common tower" N-2 uses `tower_group`.

**Cases.** The 13 monthly coincident peaks plus the 2030 peak. The off-peak high-solar case is optional (overvoltage).

**Criteria** (in `engine.toml`): post-contingency loading ≤ 100% of `n1_rating` (rate A by default, rate B selectable). Buses at 132 kV and above: V ≥ 0.95 pu (configurable, for example 0.90 if the Grid Code says so). N-0 violations are reported separately. A contingency counts only new violations, or violations worsened by more than 1 percentage point.

**Loop.** For each contingency: set `in_service=False`, run the retry ladder, restore. The ladder is:
1. `init=results`
2. `init=dc`, 30 iterations
3. `init=flat`, 50 iterations
4. `rundcpp`, used as a thermal-only estimate marked `method=dc`

**Islanding.** pandapower sets isolated buses to NaN. Load lost = Σ load on NaN buses. For example, a radial substation reports "loss of supply X MW", not an overload.

**Severity classes**, sorted lexicographically:
- A: no solution
- B: loss of supply, ranked by MW
- C: over 120%, or V < 0.90
- D: 100–120%, or V below the limit
- E: secure

Within C and D, rank by overload MVA `Σ_e max(0, S_e − S_lim)`, then by minimum V.

**Demo "trip Kawanda–Mutundwe".** Every contingency for every case is precomputed into `n1_post_loading`.
- Clicking a line, then "Trip circuit 1" or "Trip both (tower)", repaints the map from `/api/n1/contingency`. That is deterministic and under 200 ms.
- `/api/n1/simulate` also recomputes live in the API: it loads the case's `net_json` (cached per run), trips, and runs `loadflow.run_pf` with a 3 s timeout. The response says `source: live|precomputed` and the compute time. On any failure it returns the precomputed answer.
- The run is pinned before the demo, and `demo_check.sh` asserts the expected overload, response times and that the screen recording exists.

### 6.5 2030 case (problem 6a)

- **Network:** `build_net(as_of=2030-12-31, statuses=[existing, committed, planned])`.
- **Loads:** `P_s,2030 = P_s,base·(1+g_s)^(2030−2026) + Σ planned loads at s with COD ≤ 2030`. g comes from T10 (Central default, per-substation override). Until the NDP IV / Compact rate is confirmed, the placeholder is labelled.
- **Generation:** planned plants added; the slack balances.
- **Runs:** re-run Oct 2025–Sep 2026 with scaled loads on the 2030 network, giving 2030 annual losses per element. The 2030 peak gets N-1 and site hosting. The slider's 2030 stop shows peak loading and annual losses, labelled "forecast".

### 6.6 Kawanda page (problem 6b)

- **Element set K:** automatic from `ss_code=KAW`. All Kawanda transformers form H1 and all lines ending at Kawanda form H2. Config can override.
- **Measured evidence:**
  - Per element per month: maximum and 95th-percentile loading from SCADA.
  - Transformer N-1 margin straight from measurements: `(Σ ratings − largest rating)·f_emerg − Σ S_meas`.
  - Line post-contingency estimate: `measured base flow × (modelled post / modelled base)`.
  - Count of NCC events per element.
- **Model evidence:** N-0 and N-1 per month, and a λ sweep. Scale all Central loads (P and Q) by λ in [1, 3], bisecting to 0.005. λ* is the largest λ with every K element within limits under N-0 and under the relevant contingencies (all of K plus any contingency putting a K element above 80%). Extra MW = `(λ*−1)·P_Central`. The binding element and contingency at λ*+ are recorded. Years to exhaustion = `ln λ* / ln(1+g)`.
- **Verdict:** the type of the binding element decides H1 or H2, with the runner-up margin shown. Agreement with the measured evidence is reported as consistent / model only / measured only / conflict.
- **Relief:** re-run the sweep with projects where `relief_for=KAW`. Show the before and after MW, and whether the binding element moves to the other hypothesis.
- **What trips it:** contingencies that overload any K element, plus actual NCC events.
- **Suppressed demand:** `Σ MW×h` of curtailments with reason Kawanda, by month, × tariff (UGX). Deferred data-centre MW is compared with post-relief headroom.

### 6.7 Industry sites (problem 5)

- **Connection:** the nearest substation bus, at 33 kV if the site is 20 MW or less, otherwise 132 kV. The new connection line is a "development", not modelled.
- **MW now and 2030** (hosting capacity), on the base peak and 2030 peak cases:
  - Bisect P in [0, 300] MW to 1 MW. Non-firm uses N-0 only. Firm uses N-0 plus the relevant contingencies: elements within 3 hops, plus the base case's 10 worst, capped at 20.
  - Feasible means no new violation, and pre-existing violations worsen by at most 1 percentage point.
  - The binding element and contingency are recorded, for example "limited by KAW T1 when T2 trips".
- **Effect on the grid:**
  - `dloss_per_mw = (L(10 MW) − L(0))/10` at the peak, which goes into scoring.
  - For the recommended type at its typical MW: 48 weighted snapshots of the peak month with the type's load profile, giving ΔMWh/yr and UGX/yr; the top three affected elements before and after; new N-1 violations. A negative Δ, for a load near generation, is shown as a benefit.
- **Unserved-energy risk:**
  - The SOW's figure as a margin: `firm_margin = MW_firm − committed pipeline at the bus − P_type`. Negative means load is shed under N-1 at peak.
  - Plus an indicative EUE: `Σ_c f_c·r_c·max(0, P − H^(c)) + U_gen·P` in MWh/yr and UGX/yr (lost-sales value). f and r come from NCC events, else `reliability.toml` defaults. U_gen is NCC unserved MWh divided by the average Central load.
  - Risk class thresholds are in config.
- **Nine factors.** The worker stores raw metrics; the API applies `scoring.json` on every request (`api/scoring.py`, the only scorer), so editing a weight and refreshing re-ranks the page and the exports identically.

| Factor | Raw metric(s) |
|---|---|
| power | firm MW now ÷ type MW; km to substation; EUE % |
| terrain | mean slope %; % of area in flood zone |
| people | working-age population within 20 km; poverty rate (direction configurable) |
| economy | district GDP share; raw-material match (type × district); existing industry nearby |
| logistics | km to trunk road, SGR/rail, port |
| policy | gazetted park or free zone flag |
| limits | % overlap with protected areas or wetlands (hard exclusion above 5%); km to the nearest |
| grid effect | dloss_per_mw; new N-1 violations |
| demand and markets | road km to Kampala CBD; population within 50 km |

Utility `u = interp(x, breakpoints)` gives 0–100. The score is `S(i,t) = Σ w_f(t)·u_f / Σ w_f(t)`. The recommended type is the highest-scoring feasible type (feasible means MW_firm,2030 ≥ min MW or MW_n0,now ≥ min MW). Sites rank by best S; ties go by firm MW, then site_id.

- **Sensitivity panel:** for each factor, whether halving or doubling its weight changes the top-3 order. This lets a mentor run the acceptance edit knowingly.
- **Developments:** rule-based, for example "new 33 kV feeder X km", "132 kV bay plus line", "reinforce <binding element>", "depends on <project> (COD)", "gazettement", "flood protection", "access road".

### 6.8 Run-time (problem 10)

| Job | Load flows | Estimate |
|---|---|---|
| Losses, 13 months (Central model, about 40 buses, 20–50 ms per load flow on one core) | 13 × 48 = 624 | under 1 min |
| N-1 | about 40 × 14 = 560 | under 1 min |
| Kawanda sweeps | about 450 | |
| Sites | about 4,000 | about 3 min |
| Remedies | about 800 | |

- The full pipeline is under 8 minutes on one core. A national model of about 300 buses is 2–4× slower and still inside the targets.
- `--jobs N` (ProcessPool by month) is for dev or night runs. `numba` is off and not installed.
- Results are written with COPY.
- Pages read precomputed views. Route geometry is pre-simplified to about 20 m, served gzipped, and cached with an ETag of run_id plus config hash. Measured targets are API p95 under 500 ms and page plus its API calls under 2 s.

---

## 7. Synthetic Central network and inputs

**Generation.** `./atlas synth --seed 42 --variant base|trafo-bound|line-bound|national|dirty` runs `engine/synthetic/generate.py`. It writes `data/synthetic/` in exactly the T01–T11 formats and GeoJSON, so the real loaders are exercised end to end.

**The network** (14 substations):
- Substations: BUJ (slack, 220 kV), NAL (PV, 132 kV), MBR (fixed-P tie), KAW 220/132/33, MSK 220/132/33, and MUT, LUG, KNO, QWY, NMV, MUK, KAP, KBS, NKG at 132/33.
- Size: about 38 buses, 19 line circuits and 22 transformers.
- Lines include BUJ–KAW 220 kV ×2, KAW–MSK 220 kV, KAW–MUT 132 kV ×2, the KAW–KNO–LUG–QWY–MUT ring, NAL–LUG ×2, the NAL–MUK–NMV–LUG chain, a western loop MUT–KBS–NKG–MSK, and KAW–KAP radial.
- Generation: Namanve 50 MW thermal plus three 20 MW solar plants.
- Load: coincident Central peak about 600 MW.
- Coordinates are approximate town locations; routes are straight segments with jitter.
- Parameters come from `conductors.csv`.

**Planted features**, so every code path runs:
- Tripping KAW–MUT circuit 1 overloads circuit 2 at peak.
- KAW T1 trip overloads T2. In the base variant the transformers bind first; `line-bound` reverses that.
- KAP is radial (islanding test).
- A 5-day outage on KAW–KNO in 2026-04.
- SCADA is absent for 2026-01 and 2026-06 (fallback path).
- Synthetic "NCC-reported" losses come from a truth model: R at 60 °C, 0.3% station service, ±2% meter noise, and a +15% meter error in 2026-02 with a T11 explanation. The expected result is 11/13 PASS, 2 EXPLAINED.
- Name variants such as "Kawanda S/S" and "Kampala Nth" exercise the alias table.
- Curtailments for two anonymised data-centre customers (reasons Kawanda and generation), two deferred 20 MW applications, a planned Kawanda T3 (2027) and a second KAW–KNO circuit (2028), 10 candidate sites and 7% growth.
- `truth.json` stores the expected outcomes for the golden tests.
- `national` adds about 250 buses for performance tests. `dirty` injects misspellings, kWh-for-MWh and duplicates for the loader tests.

**Labelling**
- `SYNTHETIC_` file prefix, a README sheet, the workbook property `gridatlas-synthetic`, and `provenance=synthetic` in the manifest.
- The generator writes only under `data/synthetic`.
- The loader refuses a file carrying the synthetic marker under `data/real`, and refuses any synthetic load on the server unless `ALLOW_SYNTHETIC=1`.
- IDs follow the same scheme as real data, so config and demo pins survive the switch. Provenance travels with every row instead.

## 8. Provenance and keeping data out of git (problem 9)

**Levels.**
- Each batch is synthetic, approximate (hand-built or standard shapes), open, or real.
- Each table has a fixed dataset dependency list in `engine/provenance.py`. A table's level is the worst of its inputs: SYNTHETIC, PARTLY SYNTHETIC (with the list of synthetic inputs), APPROXIMATE, REAL – UNVERIFIED, or REAL – VERIFIED (method note signed in `signoffs.csv`).

**Every API response** carries a `provenance` object. GeoJSON carries it as a foreign member.

**Every page**
- `common.js` draws a fixed top banner whenever the level is not REAL – VERIFIED.
- The map gets a diagonal watermark as a Leaflet control.
- Each Chart.js chart gets a global plugin that draws "SYNTHETIC DATA – NOT UETCL", so screenshots carry the label.
- The footer shows the run id.

**Every export**
- CSV: the filename is prefixed `SYNTHETIC_` or `PARTLY-SYNTHETIC_`, and the first column `provenance` repeats the level on every row.
- XLSX: a README sheet with the run, inputs and sha256 values, a red merged banner row, red sheet tabs, and the same level in the document properties.
- Real outputs say "model estimate, not an official UETCL figure" until signed.

**Policy** in `docs/provenance.md`: no synthetic number in any slide, paper or ERA material. The demo runs only at APPROXIMATE or above.

**Git**
- `.gitignore` excludes `data/**` and model formats.
- The pre-commit hook (sh, enabled by `./atlas init` through `core.hooksPath`) refuses `data/`, `.env`, xlsx outside `templates/`, and files over 2 MB.
- Tests generate their own synthetic fixtures.
- The bundle copies only `git ls-files`.
- Real data is processed on the server. For laptop adapter work, `./atlas scrub` produces structure-only copies with randomised numbers.
- Move the SOW and the scanned board paper to `docs/_private/` (gitignored), especially if the remote is GitHub.

---

## 9. API, pages, exports

**Endpoints** (GET only; one router per program; tables return `{provenance, columns[{key,label,unit,decimals}], rows, export:{csv,xlsx}}`)
- **meta:** `/api/health`, `/api/meta/provenance?table=`, `/api/meta/runs`, `/api/meta/months`, `/api/meta/imports`, `/api/meta/imports/{batch}/issues`, `/api/meta/config`
- **network:** `/api/network/substations`, `/api/network/routes?month=&metric=loading|loss_density`, `/api/network/elements/{id}`
- **losses:** `/api/losses/monthly`, `/api/losses/elements?month=`, `/api/losses/reconciliation`, `/api/losses/top10`, `/api/losses/remedies?element=`
- **constraints:** `/api/n1/cases`, `/api/n1/results?case=`, `/api/n1/envelope?case=`, `/api/n1/contingency?case=&trip=`, `/api/n1/simulate?case=&trip=a,b`
- **kawanda:** `/api/kawanda/summary`, `/api/kawanda/loading`, `/api/kawanda/trips?case=`, `/api/kawanda/headroom`, `/api/kawanda/suppressed`
- **industry:** `/api/sites`, `/api/sites/{id}`, `/api/sites/geojson`
- **dashboard:** `/api/dashboard/summary?month=`
- **export:** `/export/{table}.csv|.xlsx?<same filters>`, `/export/all.xlsx`
- **docs:** `/api/docs` and `/api/openapi.json`, self-hosted Swagger, with method and units in the docstrings.

**Pages**
- **index.html (Map):** hillshade and vector basemap; substations; routes coloured green/amber/red by loading or loss density with a legend; month slider with 13 stops plus 2030; popups showing ratings and a 13-month mini chart; a KPI box. N-1 mode shows the envelope colouring and Trip/Restore buttons. A sites layer can be toggled on.
- **losses.html:** modelled vs metered chart with gap %; the reconciliation table with status and explanations and a gate summary ("11/13 within ±10%, 0 unexplained"); element losses by month; top-10 with best remedy and payback.
- **n1.html:** case selector; counts by severity class; ranked contingency table; violations on row click; link to the map.
- **kawanda.html:** H1/H2 verdict card; monthly loading chart (measured dashed, modelled solid); "what trips it"; headroom bars before and after relief with the binding element and year of exhaustion; suppressed MWh and UGX; deferred MW against headroom.
- **sites.html:** ranked table (type, score, firm and non-firm MW now and 2030, Δ losses, max loading after, margin, EUE class, developments); factor stacked bars; weights in use with their hash and the sensitivity panel; mini-map.
- **dashboard.html:** KPI tiles, losses per month, top-10 lines, contingency count by class, top sites; every table has CSV and Excel buttons.
- **imports.html:** the import log. **about.html:** runs, inputs, licences and links to `/methods/*.md`.

**Exports.** `api/tables.py` maps each export name to its view, columns, units, decimals and filters. One function in `api/render.py` rounds the DataFrame and then serialises it as JSON, as CSV (UTF-8 BOM, provenance column) or as XLSX (XlsxWriter, README sheet). The screen only displays API values and does no client-side arithmetic, so the numbers match the screen by construction. A test enforces it.

---

## 10. Tests and end-to-end verification on the dev machine

**Unit tests** (`docker compose run --rm --no-deps worker pytest tests/unit -p no:cacheprovider`) cover:
- name normalisation and line parsing
- unit conversions
- profile fits (energy exact, peak exact, a<0 branch)
- snapshot weights summing to 24·D
- loss aggregation and LLF
- the retry ladder (mocked)
- severity ordering
- hosting bisection on a 3-bus network with an analytic answer
- scoring (breakpoints, exclusions, a weight edit that flips the ranking)
- the provenance worst-of rule
- the Kawanda verdict on the `trafo-bound` and `line-bound` variants

**Builder round trip.** pandapower `case9` and `example_simple` go to canonical tables, are rebuilt, and the load flow must match the original within 1e-6 pu.

**Integration tests** (using the `gridatlas_test` database):
- migrate → synth → load → run with 2 months
- every `api.*` view returns rows
- `test_readonly_role`: INSERT, CREATE and UPDATE as `atlas_ro` all fail
- `test_exports_match_json` for every table
- `test_provenance_everywhere`
- `test_no_cdn`: grep `web/` for `http(s)://`; CSP header present
- golden synthetic outcomes: 11/13 PASS, KAW–MUT overload, verdict H1

**Converters** (amd64 image only): synthetic network → pypowsybl → RAW v33 → adapter → canonical must equal the original; IEEE-14 RAW must match OpenLoadFlow.

**Performance:** `./atlas bench` on `base` and `national` asserts under 10 minutes and under 5 minutes. `page_timing.sh` asserts every page plus its API calls in under 2 s. Browser devtools are checked manually once per release.

**E2E sequence on the Mac**
1. `./atlas init` (`.env` with random passwords, `BIND_IP=127.0.0.1`, `BOOTSTRAP=synthetic`).
2. `docker compose build` (native arm64).
3. `docker compose up -d`, then `docker compose ps` until all four are healthy.
4. Open `http://127.0.0.1:8090` and check the SYNTHETIC banner.
5. `./atlas test`.
6. `./atlas verify`. It checks:
   - four containers running
   - no default route in api/worker/db
   - a socket to a test IP on 2404 fails from api and web
   - the read-only role refuses writes
   - all endpoints answer 200 with provenance
   - exports equal JSON
   - 13 months loaded with zero failed critical rows
   - the reconciliation gate
   - every Central element has an N-1 result
   - at least 8 sites scored
   - page timing
7. Edit one weight in `config/scoring.json` and refresh: the ranking changes.
8. Trip KAW–MUT circuit 1 on the map: live and precomputed agree.
9. `docker compose down && up`: data persists.
10. `./atlas bundle 2026.11.06`, then `docker load` on a scratch Colima profile to check the bundle (QEMU, slow but valid).

On the server, the same `verify` runs after `firewall.sh apply`, using a real substation gateway IP for the no-route test.

---

## 11. Build order

About 15 person-days a week: 5 trainees at 60%. Roles: L = lead/server, P = power systems, D = data/GIS, W = web, E = economics/sites.

| # | When | Milestone | Who | Effort | Exit check |
|---|---|---|---|---|---|
| M0 | Sun 1 – Mon 2 Nov, before noon | Data-request pack: cover notes per holder (Planning, GIS, NCC, Commercial; UEGCL, UEDCL, UIA through the introductions), question list, handling statement, `spec.toml` and generated T01–T11 via `docker run python:3.12-slim … build_templates.py`. Add T08 (Kawanda relief) and curtailment records to Monday's list. | L, D, P, E | 2 pd | Requests sent Monday. If the xlsx slips, the field lists go in the email body and the xlsx follows by evening. |
| M1 | Mon 2 – Tue 3 | Repo, `./atlas`, compose with four healthy containers, roles, migrations 001–003, Nginx with vendored Leaflet and Chart.js, banner stub, hooks | L, W | 2.5 pd | `verify` (partial) passes on the Mac |
| M2 | Tue 3 – Wed 4 | Synthetic generator v1; spec-driven loaders for T01–T04; import log and page | D, P | 4 pd | Zero failed rows on synthetic; dirty variant gives the expected issues |
| M3 | Thu 5 | **First end-to-end run:** builder, checks, one month × 48 snapshots, element losses, coloured map, generic export | P, W, D | 2.5 pd | Map shows a synthetic month; CSV and XLSX download |
| M4 | Fri 6 | Server dry run: amd64 bundle, USB, App VM, firewall, `verify`; Friday mentor demo; load real GIS if it has arrived | L | 1.5 pd | `verify` passes on the server |
| M5 | 9 – 11 Nov | 13 months, fallback profiles, reconciliation with T11, slider; NCC native adapter on arrival; PSS/E or hand-built path | P, D, W | 7 pd | Reconciliation table on real or partly real data |
| M6 | 11 – 13 Nov | Top-10, remedies, payback; dashboard v1; exports for all tables; method notes 01–04; mentor first look | P, W, D, E | 6 pd | Mentor corrections logged |
| M7 | 16 – 18 Nov | N-1 engine, table, map mode, live trip; as-of-date builder and 2030 network (moved up from week 4) | P, W | 6 pd | Every element has a result; KAW constraint visible |
| M8 | 18 – 20 Nov | Kawanda page; candidate sites, open-data loaders, raw metrics, `scoring.json`, API scoring | P, W, E, D | 7 pd | Verdict and headroom before and after relief |
| M9 | 23 – 25 Nov | Hosting, effect, margin, EUE, developments; ranked table and layer; dashboard final; all export tests; performance on the server; method notes 05–09 | P, E, W, D, L | 9 pd | Acceptance list green |
| M10 | 25 – 26 Nov | Mentor sign-off, `verify` on the server, two rehearsals, `demo_check`, recording, pinned run, **freeze Thursday 26 Nov** | All | 3 pd | Demo ready; replay only if M9 is done by Wednesday |

The total is about 51 pd against about 60 available.

**Cut order if late:** replay, then EUE (keep the margin), then reconfiguration, then live recompute (keep precomputed trip), then sites cut to 8 and 4 factors as the SOW allows.

---

## 12. Risks, assumptions, and where I disagree with the SOW

**Risks**

| Risk | Rating | Mitigation |
|---|---|---|
| Network model late or incomplete | High | Synthetic and hand-built paths; validate on the best-data months first |
| NCC losses available only nationally | High | Basis logic; Monday questions; request boundary meter data; national-model option |
| SCADA partial | Medium/High | Fallbacks; LLF check |
| Demo venue outside the UETCL LAN, so the server is unreachable | Medium/High | Confirm the venue in week 1. If off-site, get written approval for a laptop copy of the pinned run (results only, via `./atlas dump`), otherwise rely on the recording. |
| Real data barred from laptops | Medium | Server-side processing; scrubbed copies for adapter work |
| App VM memory | Medium (SOW says Low) | Limits, `oom_score_adj`, measure in week 1 |
| arm64/amd64 mismatch | Medium | pypowsybl only on amd64; server dry run on Friday 6 Nov; optionally turn on Colima Rosetta so amd64 images run usably fast on the Mac |
| Non-convergence on real data | Medium | Checks, retry ladder, reduced model, OpenLoadFlow cross-check |
| Model does not reproduce Kawanda | Medium | Measured-evidence leg; verify ratings with the mentor; report honestly |
| Synthetic numbers leak into external material | Medium likelihood, high impact | Provenance design and policy |
| Docker subnet collides with UETCL ranges | Low likelihood, high impact | Agree subnets with the network team |
| pandapower 4.0 lands mid-build | Low | Exact pins and hashed lock |
| WDPA terms are non-commercial | Low | Internal use with attribution |

**Assumptions**
- The App VM is as Grid Monitor documents it (Ubuntu x86_64, Docker 24+, iptables backend).
- Port 8090 is free and the control-room subnet is known.
- About 3 GB of RAM is free.
- NCC has monthly substation energy and peaks in Excel.
- The Planning model includes ratings.
- The team lead's ACSR-to-ACCC analysis supplies `remedies.toml`.
- The Mac has internet for builds and open data.

**Disagreements with the SOW**
1. **The §9 loss gate cannot be tested as written** if NCC reports losses only nationally. Restate it as "modelled vs metered on the same perimeter and the same voltage/transformer buckets": the Central boundary balance, or national model vs national. Never allocate national losses by modelled share.
2. **"A pandapower load flow per month" cannot give MWh.** Use weighted day-type snapshots plus the LLF check (still cheap), and correct R for temperature.
3. **Boundary injections for the Nile plants distort N-1 and loop flows.** If Planning has the national case, run it whole and report Central.
4. **N-1 limits.** Applying 100% of normal rating and 0.95 pu after a contingency over-reports. Make the rating basis and voltage limits configurable and agree them with Planning against the Grid Code. Report N-0 separately, and report radial loss of supply as a class of its own.
5. **"MW it can take now" needs firm (N-1) and non-firm (N-0) figures.** Data centres need firm supply.
6. **"Unserved-energy risk (firm capacity minus committed load)" is a MW margin, not a risk.** Keep it as the headline and add an indicative EUE.
7. **`config.json` belongs in `config/scoring.json`, read by the API**, so exports rank exactly as the screen. A browser-side scorer would break "numbers match the screen". Update the acceptance wording to name the file.
8. **"`docker compose up` on a clean clone" cannot build offline.** The criterion should read "clean clone plus images loaded from the release bundle". The worker stays long-lived so four containers are up.
9. **"Containers bound to the LAN only" is not sufficient.** The host has a leg on the substation network, so the egress controls in section 2 are required. Longer term, recommend a VM without the substation NIC.
10. **Order and scope of requests.** Build the as-of-date network builder in week 1. Request planned projects (row 8) and curtailment records on Monday, not later: the Kawanda "after relief" figure and suppressed demand depend on them.
11. **Data sources and libraries.** Copernicus GLO-30 is easier to fetch than SRTM 30 m and equivalent. Do not attempt MapLibre terrain offline in the MVP. Keep Leaflet 1.9.4; Chart.js 4.4.7 is the same file Grid Monitor already uses.
12. **Use more SCADA where it is cheap.** Two SCADA days a month are a minimum. Ask for whole months on about 40 priority points; it tightens the 10% gate considerably.

---

## Sources
- [pandapower on PyPI](https://pypi.org/pypi/pandapower/json), [pandapower converters](https://pandapower.readthedocs.io/en/latest/converter.html), [pandapower changelog](https://github.com/e2nIEE/pandapower/blob/develop/CHANGELOG.rst)
- [pypowsybl 1.16.1 files](https://pypi.org/pypi/pypowsybl/1.16.1/json), [PowSyBl PSS/E import](https://powsybl.readthedocs.io/projects/powsybl-core/en/latest/grid_exchange_formats/psse/import.html), [pypowsybl v1.15 docs (import/export formats)](https://powsybl.readthedocs.io/_/downloads/pypowsybl/en/v1.15.0/pdf/), [PowSyBl grid exchange formats](https://powsybl.readthedocs.io/projects/powsybl-core/en/latest/grid_exchange_formats/index.html)
- [VeraGrid file operations](https://veragrid.readthedocs.io/en/latest/md_source/file_operations.html)
- [rasterio 1.5.2](https://pypi.org/pypi/rasterio/1.5.2/json), [geopandas](https://pypi.org/pypi/geopandas/json), [pandas 2.3.3](https://pypi.org/pypi/pandas/2.3.3/json), [numpy 2.4.4](https://pypi.org/pypi/numpy/2.4.4/json), [psycopg](https://pypi.org/pypi/psycopg/json), [fastapi](https://pypi.org/pypi/fastapi/json), [uvicorn](https://pypi.org/pypi/uvicorn/json), [XlsxWriter](https://pypi.org/pypi/XlsxWriter/json)
- [Leaflet on npm](https://registry.npmjs.org/leaflet), [Chart.js on npm](https://registry.npmjs.org/chart.js)
- [postgis/postgis tags (architectures)](https://hub.docker.com/v2/repositories/postgis/postgis/tags?page_size=25&name=16-3), [GDAL container versions](https://github.com/OSGeo/gdal/pkgs/container/gdal/versions?filters%5Bversion_type%5D=tagged), [gdal raster tile](https://gdal.org/programs/gdal_raster_tile.html), [GDAL 3.11 release note](https://lists.osgeo.org/pipermail/gdal-dev/2025-May/060547.html)
- [Docker packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/), [Docker with iptables (DOCKER-USER)](https://docs.docker.com/engine/network/firewall-iptables/), [Docker with nftables](https://docs.docker.com/engine/network/firewall-nftables/), [bridge driver options](https://docs.docker.com/engine/network/drivers/bridge/)
- [FastAPI self-hosting docs assets](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/)

### Critical Files for Implementation
- /Users/markryanmutikanga/Documents/ERA Project/docker-compose.yml
- /Users/markryanmutikanga/Documents/ERA Project/templates/spec.toml
- /Users/markryanmutikanga/Documents/ERA Project/engine/network/build.py
- /Users/markryanmutikanga/Documents/ERA Project/engine/losses.py
- /Users/markryanmutikanga/Documents/ERA Project/db/migrations/900_api_views.sql
