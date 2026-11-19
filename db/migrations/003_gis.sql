-- 003_gis: open context layers (owner F2), e.g. protected areas, roads, districts, loaded
-- from data/open/layers/. Applied once.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        RAISE EXCEPTION 'PostGIS is not installed in this database: db/init must create it (or use gridatlas_template)';
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS gis;

CREATE TABLE gis.layer_feature (
    feature_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id   bigint NOT NULL REFERENCES meta.import_batch (batch_id) ON DELETE CASCADE,
    layer      text NOT NULL,                -- e.g. protected_area, road, district
    name       text,
    attrs      jsonb NOT NULL DEFAULT '{}'::jsonb,
    geom       geometry(Geometry, 4326) NOT NULL
);
CREATE INDEX layer_feature_layer_idx ON gis.layer_feature (layer);
CREATE INDEX layer_feature_geom_idx ON gis.layer_feature USING gist (geom);
