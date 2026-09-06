-- Phase 2 spatial/data contracts. Applied after db/schema.sql.

ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS provider TEXT;
ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS url TEXT;
ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS freshness_window_s INTEGER;
ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;
ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS last_error TEXT;

CREATE TABLE IF NOT EXISTS data_snapshots (
    id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES data_sources(id),
    retrieved_at TIMESTAMPTZ NOT NULL,
    data_status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS infrastructure (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    name TEXT,
    source TEXT,
    source_osm_id TEXT,
    retrieved_at TIMESTAMPTZ,
    data_status TEXT NOT NULL DEFAULT 'DEMO',
    geom GEOMETRY(GEOMETRY, 4326)
);

CREATE UNIQUE INDEX IF NOT EXISTS infrastructure_source_osm_idx
    ON infrastructure (source, source_osm_id)
    WHERE source_osm_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS infrastructure_gist ON infrastructure USING GIST (geom);
CREATE INDEX IF NOT EXISTS infrastructure_city_type_idx ON infrastructure (city_id, asset_type);

CREATE TABLE IF NOT EXISTS terrain_datasets (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    uri TEXT NOT NULL,
    crs TEXT NOT NULL,
    west DOUBLE PRECISION,
    south DOUBLE PRECISION,
    east DOUBLE PRECISION,
    north DOUBLE PRECISION,
    nodata DOUBLE PRECISION,
    min_elevation DOUBLE PRECISION,
    max_elevation DOUBLE PRECISION,
    source TEXT,
    data_status TEXT NOT NULL,
    freshness TEXT NOT NULL DEFAULT 'STATIC',
    version TEXT
);

CREATE TABLE IF NOT EXISTS meteorological_observations (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    value_mm DOUBLE PRECISION NOT NULL CHECK (value_mm >= 0),
    unit TEXT NOT NULL DEFAULT 'mm',
    observed_at TIMESTAMPTZ NOT NULL,
    valid_at TIMESTAMPTZ NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('OBSERVED', 'FORECAST', 'SIMULATED')),
    provider TEXT NOT NULL,
    data_status TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS met_obs_time_idx ON meteorological_observations (observed_at);
CREATE INDEX IF NOT EXISTS met_obs_city_kind_idx ON meteorological_observations (city_id, kind);

CREATE TABLE IF NOT EXISTS river_observations (
    id TEXT PRIMARY KEY,
    river_id TEXT NOT NULL,
    segment_id TEXT,
    observed_at TIMESTAMPTZ,
    water_level_m DOUBLE PRECISION,
    discharge_m3s DOUBLE PRECISION,
    source TEXT,
    data_status TEXT NOT NULL DEFAULT 'UNAVAILABLE'
);

CREATE TABLE IF NOT EXISTS forecast_runs (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    model_id TEXT NOT NULL,
    data_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_points (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES forecast_runs(id),
    horizon_hours INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    valid_at TIMESTAMPTZ NOT NULL,
    probability DOUBLE PRECISION,
    expected_depth DOUBLE PRECISION,
    severity DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    confidence_kind TEXT
);

CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    rainfall_multiplier DOUBLE PRECISION NOT NULL,
    river_level_delta_m DOUBLE PRECISION NOT NULL DEFAULT 0,
    upstream_discharge_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    creator TEXT,
    model_version TEXT,
    simulation_version TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_results (
    id TEXT PRIMARY KEY,
    scenario_id TEXT REFERENCES scenarios(id),
    artifact_uri TEXT NOT NULL,
    model_version TEXT,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL
);
