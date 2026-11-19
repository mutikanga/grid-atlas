# Grid Atlas

Grid Atlas is an offline, geospatial grid-planning tool for UETCL's Central region. It runs in Docker on the NCC application VM, next to Grid Monitor, and covers three programmes:

- **Transmission losses**: monthly losses for each line, reconciled to NCC totals, with a top-10 list and remedy paybacks.
- **N-1 constraints**: N-0 and N-1 load-flow runs, with the Kawanda constraint as the case study.
- **Industry sites**: scores candidate industrial sites on MW now and in 2030, grid effect and firm headroom, using editable weights.

It also has a 2030 demand forecast, a dashboard, and CSV/XLSX export of every table.

Every result carries a provenance label: `REAL`, `PUBLIC`, `APPROXIMATE` or `SYNTHETIC`. A result's label is the lowest level among its inputs.

## Architecture

```
templates (T01–T13) + manifests ──> loaders/ ──> PostgreSQL/PostGIS (ts.*)
                                                   │
                                     engine/ stages (pandapower) ──> results.*
                                                   │
                                     api/ (FastAPI, read-only role) ──> api.* views
                                                   │
                                     web/ (static HTML/JS, Leaflet, Chart.js) via nginx :8090
```

| Service  | Role |
|----------|------|
| `db`     | Postgres 16 + PostGIS. Its port is never published. |
| `worker` | Python engine: migrations, data loads, analysis runs (`python -m engine.cli`). |
| `api`    | FastAPI, connecting as the read-only `atlas_ro` role. |
| `web`    | nginx serving `web/` and proxying `/api` and `/export`. Accepts GET and HEAD only. |

`db`, `worker` and `api` sit on an internal network with no route out. Only nginx is on the edge network.

## Quick start (dev)

You need Docker with Compose.

```sh
./atlas init      # create .env with random passwords, enable the git hooks
./atlas build     # build the images
./atlas up        # start the stack
./atlas test      # run the test suite
```

Then open http://127.0.0.1:8090.

Other commands: `down`, `ps`, `logs`, `psql`, `templates`, `lock`, `reset` (dev only). Run `./atlas` with no arguments for help.

Inside the worker, `python -m engine.cli` provides `migrate`, `synth`, `load`, `run [--stages] [--pin]`, `pin`, `report` and `worker`.

## Repository layout

| Path | Contents |
|------|----------|
| `api/` | FastAPI app, routers, CSV/XLSX rendering |
| `engine/` | Analysis stages, network build and load flow, synthetic data generator |
| `loaders/` | Template and spec validation, unit and name normalisation, network converters |
| `db/` | Database image, role setup, SQL migrations |
| `templates/` | Data-request templates T01–T13 and their specs (`spec/*.toml`) |
| `config/` | Reference data (substations, plants, conductors, holidays) and engine settings |
| `web/` | Frontend pages, CSS, JS, vendored libraries |
| `nginx/` | nginx config template |
| `docker/` | Python image and the pinned requirements |
| `tests/` | Unit and integration tests |
| `docs/` | Build plan, implementation design, contracts, data requests, contingency plan |

## Data and secrets

No data goes into git. The `data/` folder (synthetic, public, real, the database files), `.env`, internal documents (PDF/DOCX) and spreadsheets outside `templates/` are excluded by `.gitignore` and refused by the pre-commit hook in `.githooks/`. `./atlas init` turns the hook on.

## Status

| Area | State |
|------|-------|
| Platform: Docker stack, database, migrations, loaders, network model and load flow, synthetic data, API core, export, imports and about pages | Done, with unit tests |
| Analysis stages: losses, reconciliation, remedies, contingency (N-1), forecast, Kawanda, sites, incidents | Placeholders, not yet implemented |
| Frontend: map, dashboard, losses, N-1, Kawanda and sites pages | Not yet implemented |
| Server delivery: `scripts/` (verify, bundle, firewall), runbook | Not yet implemented |

Before any server deploy, set `ATLAS_ALLOW_CIDR` to the control-room subnet. It defaults to `0.0.0.0/0`.

## Documentation

- [docs/build-plan.md](docs/build-plan.md): milestones and plan
- [docs/dev/implementation-design.md](docs/dev/implementation-design.md): design
- [docs/dev/contracts.md](docs/dev/contracts.md): interfaces between components
- [docs/dev/slices.md](docs/dev/slices.md): work slices
- [docs/dev/template-columns.md](docs/dev/template-columns.md): template columns
- [docs/contingency-plan.md](docs/contingency-plan.md): demo fallback if data is late
- [docs/data-requests/](docs/data-requests/): the 15 data requests
