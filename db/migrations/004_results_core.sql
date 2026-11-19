-- 004_results_core: the network register and load-flow results shared by all slices
-- (owner F2; filled by the network stage and the slices). Applied once.
-- Every results table carries run_id; deleting a run deletes its results.

CREATE SCHEMA IF NOT EXISTS results;

-- Network elements as built for the run (one row per element).
CREATE TABLE results.element (
    run_id             bigint NOT NULL REFERENCES meta.run (run_id) ON DELETE CASCADE,
    element_type       text NOT NULL CHECK (element_type IN ('line', 'trafo', 'trafo3w', 'gen', 'load', 'shunt')),
    element_id         text NOT NULL,
    name               text,
    ss_from            text,
    ss_to              text,
    kv                 double precision,
    length_km          double precision,
    in_central         boolean,
    is_equivalent      boolean NOT NULL DEFAULT false,
    rate_mva           double precision,
    rate_basis         text,
    commissioning_year integer,
    tower_group        text,
    status             text,
    PRIMARY KEY (run_id, element_type, element_id)
);

CREATE TABLE results.bus (
    run_id     bigint NOT NULL REFERENCES meta.run (run_id) ON DELETE CASCADE,
    bus_id     text NOT NULL,
    ss_code    text,
    vn_kv      double precision,
    in_central boolean,
    PRIMARY KEY (run_id, bus_id)
);

-- One row per load-flow case. case_key is readable: '2026-03|WD|20', '2026-03|peak',
-- '2030|peak', '2026-03|n1|L-KAW-MUT-132-1'.
CREATE TABLE results."case" (
    run_id         bigint NOT NULL REFERENCES meta.run (run_id) ON DELETE CASCADE,
    case_key       text NOT NULL,
    kind           text NOT NULL,             -- hour, peak, min, n1, forecast_peak, sweep, ...
    month          date,                      -- first of month; 1 January for a forecast year
    day_type       text CHECK (day_type IS NULL OR day_type IN ('WD', 'NWD')),
    hour           integer CHECK (hour IS NULL OR hour BETWEEN 0 AND 23),
    weight_h       double precision,          -- hours this snapshot stands for in the month
    scenario       text NOT NULL DEFAULT 'base',
    total_load_mw  double precision,
    total_gen_mw   double precision,
    converged      boolean,
    method         text,                      -- which rung of the retry ladder solved it
    profile_source text,
    note           text,
    PRIMARY KEY (run_id, case_key)
);
CREATE INDEX case_month_idx ON results."case" (run_id, month, kind);

CREATE TABLE results.element_result (
    run_id       bigint NOT NULL REFERENCES meta.run (run_id) ON DELETE CASCADE,
    case_key     text NOT NULL,
    element_type text NOT NULL,
    element_id   text NOT NULL,
    p_from_mw    double precision,
    q_from_mvar  double precision,
    p_to_mw      double precision,
    q_to_mvar    double precision,
    pl_mw        double precision,
    ql_mvar      double precision,
    i_ka         double precision,
    loading_pct  double precision,
    PRIMARY KEY (run_id, case_key, element_type, element_id)
);
CREATE INDEX element_result_element_idx ON results.element_result (run_id, element_type, element_id);

CREATE TABLE results.bus_result (
    run_id   bigint NOT NULL REFERENCES meta.run (run_id) ON DELETE CASCADE,
    case_key text NOT NULL,
    bus_id   text NOT NULL,
    vm_pu    double precision,
    va_deg   double precision,
    p_mw     double precision,
    q_mvar   double precision,
    PRIMARY KEY (run_id, case_key, bus_id)
);
CREATE INDEX bus_result_bus_idx ON results.bus_result (run_id, bus_id);
