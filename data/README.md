# data/

Everything the Atlas reads or produces at run time lives here. **Nothing in `data/` goes into git**, except this README. `.gitignore` ignores the folder, and the pre-commit hook refuses any file under it, even one added with `git add -f`.

Real UETCL data stays on the NCC server. Never copy it to a laptop, a container image, a USB stick that leaves the building, or git.

## Layout

| Folder | What it holds | Written by |
|---|---|---|
| `synthetic/<dataset>/` | Synthetic Central-region data in the template formats, with a `manifest.toml`. Always labelled synthetic. | `./atlas synth` |
| `real/<dataset>/` | Deliveries from UETCL holders, one folder per dataset, each with a `manifest.toml`. Synthetic files are refused here. | the team, on the server |
| `open/layers/` | Open context layers (protected areas, roads, districts and so on), with a `manifest.toml`. | the team |
| `basemap/` | Offline hillshade tiles and simplified GeoJSON, served at `/basemap/`. | `./atlas basemap` |
| `logs/` | Worker job logs. | the worker |
| `backups/` | Database dumps (`*.dump`). | operations scripts |
| `pgdata/` | The PostgreSQL data files. Do not touch them by hand. | the `db` container |
| `auth/` | Optional `htpasswd` for basic auth (see `.env.example`). | the team, on the server |

`<dataset>` is the template's slug: `network_model`, `gis`, `ncc_monthly`, `scada`, `ncc_operations`, `commercial`, `uedcl_feeders`, `projects_and_loads`, `sites`, `growth`, `recon_explanations`, `handbuilt_network`, `planning_studies`. The manifest format is in `docs/dev/contracts.md`, section 8.

## Rules
- `./atlas init` creates the folders.
- On the server (Linux), `synthetic/` and `logs/` must belong to uid 10001, the user the worker runs as; `./atlas init` and `./atlas up` set this. `pgdata/` belongs to the `postgres` user inside the db container (uid 999), which sets it on first boot. Other folders only need to be readable.
- `pgdata/` is a plain folder, not a Docker volume, so `docker compose down -v` cannot delete it. To start the database again from empty in dev, use `./atlas reset`.
- Back up `pgdata/` only while the stack is stopped. Better still, use a dump in `backups/`.
