# PostgreSQL 16 with PostGIS. Built on postgres:16 because the official
# postgis/postgis images are published for amd64 only, and the team develops on
# Apple Silicon. The postgres image already carries the PGDG apt repository.
FROM postgres:16-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-postgis-3 \
 && rm -rf /var/lib/apt/lists/*
