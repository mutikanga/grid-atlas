-- 002_ref: reference registers (owner F2). Filled from config/*.csv and the calendar on
-- every load and run (loaders/generic.py load_registers). Applied once.

CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE ref.substation (
    ss_code    text PRIMARY KEY CHECK (ss_code ~ '^[A-Z]{3}$'),
    name       text NOT NULL,
    kv_levels  integer[],                    -- highest first, e.g. {220,132,33}
    district   text,
    in_central boolean NOT NULL DEFAULT false,
    lat        double precision CHECK (lat BETWEEN -90 AND 90),
    lon        double precision CHECK (lon BETWEEN -180 AND 180),
    geom       geometry(Point, 4326),
    source     text
);
CREATE INDEX substation_geom_idx ON ref.substation USING gist (geom);

-- Normalised names (loaders/names.py normalise) mapped to canonical codes.
CREATE TABLE ref.alias (
    alias_norm   text NOT NULL,
    entity_type  text NOT NULL CHECK (entity_type IN ('substation', 'plant')),
    canonical_id text NOT NULL,
    source       text,
    PRIMARY KEY (alias_norm, entity_type)
);

CREATE TABLE ref.plant (
    plant_code    text PRIMARY KEY,
    name          text NOT NULL,
    technology    text,
    ss_code       text REFERENCES ref.substation (ss_code),
    connection_kv double precision,
    source        text
);

-- The study months plus one row per forecast year (month = 1 January, is_forecast).
CREATE TABLE ref.month (
    month       date PRIMARY KEY CHECK (extract(day FROM month) = 1),
    label       text NOT NULL,
    days        integer NOT NULL,
    hours       integer NOT NULL,
    n_wd        integer NOT NULL,            -- working weekdays
    n_nwd       integer NOT NULL,            -- weekend days and public holidays
    is_forecast boolean NOT NULL DEFAULT false,
    CHECK (n_wd + n_nwd = days)
);

CREATE TABLE ref.holiday (
    day  date PRIMARY KEY,
    name text NOT NULL
);
