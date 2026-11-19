-- 900_api_core: the API's read contract for the core tables (owner F2).
-- Re-applied on every migrate, after all other migrations, so every view here is
-- dropped and re-created. The api schema is the ONLY schema atlas_ro can read; views are
-- owned by atlas_rw, so atlas_ro reads through them without seeing the tables.
-- Every run-dependent view filters to meta.v_current_run.

CREATE SCHEMA IF NOT EXISTS api;

-- The current run: the pinned run (meta.settings pinned_run_id) if set, otherwise the
-- latest run with status ok. Zero rows when there is none.
CREATE OR REPLACE VIEW meta.v_current_run AS
SELECT run_id
FROM (
    SELECT COALESCE(
        (SELECT r.run_id
           FROM meta.settings s
           JOIN meta.run r ON s.value ~ '^[0-9]+$' AND r.run_id = s.value::bigint
          WHERE s.key = 'pinned_run_id'),
        (SELECT r.run_id FROM meta.run r WHERE r.status = 'ok' ORDER BY r.run_id DESC LIMIT 1)
    ) AS run_id
) current_run
WHERE run_id IS NOT NULL;

DROP VIEW IF EXISTS api.v_provenance CASCADE;
CREATE VIEW api.v_provenance AS
SELECT r.run_id,
       COALESCE(r.provenance_level, 'synthetic') AS level,
       CASE COALESCE(r.provenance_level, 'synthetic')
           WHEN 'synthetic'   THEN 'SYNTHETIC: NOT UETCL DATA'
           WHEN 'approximate' THEN 'APPROXIMATE: HAND-BUILT OR STANDARD-SHAPE INPUTS'
           ELSE 'TRAINEE SHOWCASE: NOT OFFICIAL UETCL FIGURES'
       END AS label,
       COALESCE(r.provenance_level, 'synthetic') = 'synthetic' AS synthetic,
       r.provenance_detail AS detail,
       r.code_version,
       r.started_at,
       r.finished_at
FROM meta.run r
JOIN meta.v_current_run c ON c.run_id = r.run_id;

DROP VIEW IF EXISTS api.v_runs CASCADE;
CREATE VIEW api.v_runs AS
SELECT r.run_id,
       r.started_at,
       r.finished_at,
       round(extract(epoch FROM (r.finished_at - r.started_at))::numeric, 1)::double precision AS duration_s,
       r.status,
       r.stages,
       r.code_version,
       r.config_sha256,
       r.provenance_level,
       r.message,
       (r.run_id = (SELECT run_id FROM meta.v_current_run)) IS TRUE AS is_current,
       EXISTS (SELECT 1 FROM meta.settings s
                WHERE s.key = 'pinned_run_id' AND s.value = r.run_id::text) AS is_pinned,
       (SELECT count(*) FROM meta.run_input i WHERE i.run_id = r.run_id)::integer AS n_inputs,
       (SELECT json_agg(json_build_object(
                    'stage', st.stage, 'status', st.status, 'started_at', st.started_at,
                    'finished_at', st.finished_at, 'n_loadflows', st.n_loadflows,
                    'n_failed', st.n_failed, 'message', st.message) ORDER BY st.started_at)
          FROM meta.run_stage st WHERE st.run_id = r.run_id) AS stage_detail
FROM meta.run r;

DROP VIEW IF EXISTS api.v_months CASCADE;
CREATE VIEW api.v_months AS
SELECT CASE WHEN m.is_forecast THEN to_char(m.month, 'YYYY') ELSE to_char(m.month, 'YYYY-MM') END AS month,
       m.label,
       m.is_forecast,
       m.days,
       m.hours,
       m.n_wd,
       m.n_nwd
FROM ref.month m;

DROP VIEW IF EXISTS api.v_import_batches CASCADE;
CREATE VIEW api.v_import_batches AS
SELECT b.batch_id,
       b.dataset,
       b.template,
       b.root,
       b.provenance,
       b.received_from,
       b.received_on,
       b.adapter,
       b.files,
       b.started_at,
       b.finished_at,
       b.status,
       b.rows_read,
       b.rows_loaded,
       b.rows_rejected,
       (SELECT count(*) FROM meta.import_issue i WHERE i.batch_id = b.batch_id AND i.severity = 'error')::integer   AS n_errors,
       (SELECT count(*) FROM meta.import_issue i WHERE i.batch_id = b.batch_id AND i.severity = 'warning')::integer AS n_warnings,
       (SELECT count(*) FROM meta.import_issue i WHERE i.batch_id = b.batch_id AND i.severity = 'info')::integer    AS n_info,
       EXISTS (SELECT 1 FROM meta.run_input ri JOIN meta.v_current_run c ON c.run_id = ri.run_id
                WHERE ri.batch_id = b.batch_id) AS in_current_run,
       b.code_version,
       b.message
FROM meta.import_batch b;

DROP VIEW IF EXISTS api.v_import_issues CASCADE;
CREATE VIEW api.v_import_issues AS
SELECT i.issue_id,
       i.batch_id,
       b.dataset,
       b.template,
       b.provenance,
       i.sheet,
       i.row_num,
       i.column_name,
       i.severity,
       i.rule,
       i.message,
       i.raw_value,
       i.suggestion,
       i.raw_row,
       i.severity = 'error' AS rejected
FROM meta.import_issue i
JOIN meta.import_batch b ON b.batch_id = i.batch_id;

DROP VIEW IF EXISTS api.v_substations CASCADE;
CREATE VIEW api.v_substations AS
SELECT s.ss_code,
       s.name,
       array_to_string(s.kv_levels, '/') AS kv_levels,
       s.district,
       s.in_central,
       COALESCE(ST_X(s.geom), s.lon) AS lon,
       COALESCE(ST_Y(s.geom), s.lat) AS lat,
       s.source
FROM ref.substation s;

-- Network elements of the current run. geojson is the surveyed route from
-- ts.gis_circuit when its model_branch_id matches, otherwise a straight line between the
-- two substations (lines), or the substation point (other elements).
DROP VIEW IF EXISTS api.v_elements CASCADE;
CREATE VIEW api.v_elements AS
SELECT e.run_id,
       e.element_type,
       e.element_id,
       e.name,
       e.ss_from,
       e.ss_to,
       e.kv,
       e.length_km,
       e.in_central,
       e.is_equivalent,
       e.rate_mva,
       e.rate_basis,
       e.commissioning_year,
       CASE WHEN e.commissioning_year IS NOT NULL
            THEN extract(year FROM current_date)::integer - e.commissioning_year END AS age_years,
       e.status,
       CASE WHEN route.geom IS NOT NULL THEN 'gis'
            WHEN a.geom IS NOT NULL AND b.geom IS NOT NULL AND e.ss_from <> e.ss_to THEN 'straight'
            WHEN a.geom IS NOT NULL THEN 'point'
            ELSE 'none' END AS geom_source,
       ST_AsGeoJSON(COALESCE(
           route.geom,
           -- a transformer, generator or load has ss_from = ss_to: show the point, not a
           -- zero-length line
           CASE WHEN a.geom IS NOT NULL AND b.geom IS NOT NULL AND e.ss_from <> e.ss_to
                THEN ST_MakeLine(a.geom, b.geom) END,
           a.geom
       ), 6)::json AS geojson
FROM results.element e
JOIN meta.v_current_run c ON c.run_id = e.run_id
LEFT JOIN ref.substation a ON a.ss_code = e.ss_from
LEFT JOIN ref.substation b ON b.ss_code = e.ss_to
LEFT JOIN LATERAL (
    SELECT g.geom
      FROM ts.gis_circuit g
     WHERE g.model_branch_id = e.element_id AND g.geom IS NOT NULL
     ORDER BY g.batch_id DESC
     LIMIT 1
) route ON e.element_type = 'line';

-- The API role reads the api schema and nothing else. Default privileges cover views
-- that later 9NN migrations create; engine/migrate.py also re-grants after them.
GRANT USAGE ON SCHEMA api TO atlas_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO atlas_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT SELECT ON TABLES TO atlas_ro;
