-- PostGIS schema for FLOODLENS-X platform entities.
-- Apply on PostgreSQL 14+ with CREATE EXTENSION postgis;
-- The application uses an equivalent in-memory store when PostGIS is unavailable.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    organization_id TEXT REFERENCES organizations(id),
    username TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('general', 'emergency', 'researcher', 'admin')),
    password_hash TEXT
);

CREATE TABLE IF NOT EXISTS aois (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    name TEXT NOT NULL,
    geom GEOMETRY(POLYGON, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS places (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    label TEXT NOT NULL,
    city_id TEXT,
    geom GEOMETRY(POINT, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS rivers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city_id TEXT
);

CREATE TABLE IF NOT EXISTS river_segments (
    id TEXT PRIMARY KEY,
    river_id TEXT REFERENCES rivers(id),
    from_node TEXT,
    to_node TEXT,
    geom GEOMETRY(LINESTRING, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    name TEXT NOT NULL,
    geom GEOMETRY(GEOMETRY, 4326) NOT NULL,
    properties JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS data_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    simulated BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES data_sources(id),
    variable TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    geom GEOMETRY(POINT, 4326),
    quality TEXT
);

CREATE TABLE IF NOT EXISTS model_versions (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    version TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    city_id TEXT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT,
    result JSONB
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    uri TEXT NOT NULL,
    city_id TEXT,
    model_version_id TEXT,
    bounds JSONB,
    crs TEXT,
    recorded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    city_id TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    channel TEXT NOT NULL DEFAULT 'in-app',
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    model_version TEXT,
    body JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS shares (
    id TEXT PRIMARY KEY,
    report_id TEXT REFERENCES reports(id),
    generated_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL,
    artifact_ids JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL,
    actor TEXT,
    action TEXT NOT NULL,
    detail JSONB
);
