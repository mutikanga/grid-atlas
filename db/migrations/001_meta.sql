-- 001_meta: runs, imports and settings (owner F2). Applied once; never edit after it has
-- been applied anywhere: write a new 00N migration instead.

CREATE SCHEMA IF NOT EXISTS meta;

-- Which migration files have been applied (also created by engine/migrate.py before 001
-- runs, so the runner can record 001 itself).
CREATE TABLE IF NOT EXISTS meta.schema_migration (
    filename   text PRIMARY KEY,
    sha256     text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- One row per load of one dataset folder. Rows in ts.* carry its batch_id.
CREATE TABLE meta.import_batch (
    batch_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset       text NOT NULL,
    template      text,
    root          text,                      -- synthetic | real | open (the data/ sub-folder)
    provenance    text NOT NULL CHECK (provenance IN ('synthetic', 'approximate', 'open', 'real')),
    received_from text,
    received_on   date,
    adapter       text,
    files         jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{path, sha256, sheet}]
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    status        text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'partial', 'failed')),
    rows_read     integer NOT NULL DEFAULT 0,
    rows_loaded   integer NOT NULL DEFAULT 0,
    rows_rejected integer NOT NULL DEFAULT 0,
    code_version  text,
    message       text
);
CREATE INDEX import_batch_dataset_idx ON meta.import_batch (dataset, started_at);

-- Problems found while loading. A row with any 'error' issue was not loaded: this is the
-- quarantine list shown on imports.html.
CREATE TABLE meta.import_issue (
    issue_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id    bigint NOT NULL REFERENCES meta.import_batch (batch_id) ON DELETE CASCADE,
    sheet       text,
    row_num     integer,                     -- spreadsheet row number (header = 1); NULL for sheet-level issues
    column_name text,
    severity    text NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    rule        text NOT NULL,               -- short code, e.g. required, type, enum, min, unresolved_name
    message     text NOT NULL,
    raw_value   text,
    suggestion  text,
    raw_row     jsonb                        -- the row's known columns as delivered
);
CREATE INDEX import_issue_batch_idx ON meta.import_issue (batch_id, severity);

-- One row per engine run.
CREATE TABLE meta.run (
    run_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    status            text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'partial', 'failed')),
    stages            text[] NOT NULL DEFAULT '{}',
    code_version      text,
    config            jsonb,
    config_sha256     text,
    provenance_level  text CHECK (provenance_level IN ('synthetic', 'approximate', 'open', 'real')),
    provenance_detail jsonb,
    message           text
);

-- The import batches a run read.
CREATE TABLE meta.run_input (
    run_id   bigint NOT NULL REFERENCES meta.run (run_id) ON DELETE CASCADE,
    batch_id bigint NOT NULL REFERENCES meta.import_batch (batch_id) ON DELETE CASCADE,
    PRIMARY KEY (run_id, batch_id)
);

-- Timing and outcome of each stage in a run.
CREATE TABLE meta.run_stage (
    run_id      bigint NOT NULL REFERENCES meta.run (run_id) ON DELETE CASCADE,
    stage       text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed', 'skipped')),
    n_loadflows integer NOT NULL DEFAULT 0,
    n_failed    integer NOT NULL DEFAULT 0,
    message     text,
    PRIMARY KEY (run_id, stage)
);

-- Small key/value settings, e.g. pinned_run_id.
CREATE TABLE meta.settings (
    key   text PRIMARY KEY,
    value text
);

-- Method-note sign-offs by mentors.
CREATE TABLE meta.signoff (
    signoff_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note         text NOT NULL,              -- method note file, e.g. 03-losses.md
    signed_by    text NOT NULL,
    role         text,
    signed_on    date NOT NULL,
    code_version text
);
