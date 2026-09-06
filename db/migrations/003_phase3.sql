-- Phase 3 forecast engine tables. Applied after 002_phase2.sql.

CREATE TABLE IF NOT EXISTS model_domains (
    domain_id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    crs TEXT NOT NULL,
    nx INTEGER NOT NULL,
    ny INTEGER NOT NULL,
    lx_m DOUBLE PRECISION,
    ly_m DOUBLE PRECISION,
    west DOUBLE PRECISION,
    south DOUBLE PRECISION,
    east DOUBLE PRECISION,
    north DOUBLE PRECISION,
    terrain_source TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    input_snapshot_ids TEXT,
    data_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flood_states (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    horizon_hours INTEGER,
    timestamp TIMESTAMPTZ NOT NULL,
    valid_at TIMESTAMPTZ NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    source TEXT,
    data_status TEXT NOT NULL,
    artifact_uri TEXT NOT NULL,
    max_depth_m DOUBLE PRECISION,
    flooded_area_km2 DOUBLE PRECISION,
    flood_fraction DOUBLE PRECISION,
    validation_status TEXT NOT NULL,
    model_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS flood_states_city_horizon_idx
    ON flood_states (city_id, horizon_hours);

CREATE TABLE IF NOT EXISTS historical_events (
    event_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    source TEXT,
    data_status TEXT NOT NULL DEFAULT 'UNAVAILABLE',
    metadata JSONB DEFAULT '{}'::jsonb
);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS validation_status TEXT;
