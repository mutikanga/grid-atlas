#!/bin/sh
# First boot only: the postgres image runs this once, as the postgres superuser, when
# ./data/pgdata is empty. It creates the two login roles and the databases.
#
#   atlas_rw            the worker. Owns every schema (created later by the migrations)
#                       and may create scratch databases (./atlas scratch NAME).
#   atlas_ro            the API. Read-only, 5 s statement timeout, 20 connections at most.
#                       It may read only the api.* views (granted by the migrations).
#   gridatlas_template  PostGIS already installed and public schema locked down. Every
#                       Atlas database (the main one and each scratch one) is a copy of it.
#   gridatlas           the main database, owned by atlas_rw.
#
# Passwords come from the environment (ATLAS_RW_PASSWORD, ATLAS_RO_PASSWORD) and are
# handed to psql as variables; :'name' quotes them safely as SQL literals, so a password
# is never pasted into the SQL text by the shell.
set -eu

: "${ATLAS_RW_PASSWORD:?ATLAS_RW_PASSWORD is not set}"
: "${ATLAS_RO_PASSWORD:?ATLAS_RO_PASSWORD is not set}"

# The quoted 'SQL' heredoc means the shell changes nothing inside it.
psql -v ON_ERROR_STOP=1 --no-psqlrc --username postgres --dbname postgres \
     -v rw_password="$ATLAS_RW_PASSWORD" \
     -v ro_password="$ATLAS_RO_PASSWORD" <<'SQL'
-- Roles ------------------------------------------------------------------------
CREATE ROLE atlas_rw LOGIN CREATEDB PASSWORD :'rw_password';
CREATE ROLE atlas_ro LOGIN CONNECTION LIMIT 20 PASSWORD :'ro_password';
ALTER ROLE atlas_ro SET default_transaction_read_only = on;
ALTER ROLE atlas_ro SET statement_timeout = '5s';

-- Template: PostGIS installed once, nobody may create objects in public ----------
CREATE DATABASE gridatlas_template;
\connect gridatlas_template
CREATE EXTENSION IF NOT EXISTS postgis;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
\connect postgres
-- IS_TEMPLATE lets any role with CREATEDB (atlas_rw) copy it. Nobody else connects to
-- it, because a copy fails while another session is connected to the template.
ALTER DATABASE gridatlas_template IS_TEMPLATE true;
REVOKE ALL ON DATABASE gridatlas_template FROM PUBLIC;

-- Main database ------------------------------------------------------------------
CREATE DATABASE gridatlas OWNER atlas_rw TEMPLATE gridatlas_template;
REVOKE ALL ON DATABASE gridatlas FROM PUBLIC;
GRANT CONNECT ON DATABASE gridatlas TO atlas_ro;

-- The maintenance database: the worker may use it (to create and drop scratch
-- databases); the API role has no business there.
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
GRANT CONNECT ON DATABASE postgres TO atlas_rw;
SQL

echo "00_roles.sh: roles atlas_rw and atlas_ro, databases gridatlas_template and gridatlas created"
