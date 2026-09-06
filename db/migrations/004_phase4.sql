-- Phase 4 AI forecast registry. Applied after 003_phase3.sql.
-- Does not store model weights. Status stays NOT_TRAINED until VALIDATED.

CREATE TABLE IF NOT EXISTS ml_datasets (
    dataset_version TEXT PRIMARY KEY,
    track TEXT NOT NULL,
    label_kind TEXT NOT NULL,
    n_samples INTEGER,
    split_spec TEXT,
    source_refs TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    data_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ml_training_runs (
    run_id TEXT PRIMARY KEY,
    dataset_version TEXT REFERENCES ml_datasets (dataset_version),
    model_kind TEXT NOT NULL,
    seed INTEGER,
    config_hash TEXT,
    metrics JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ml_models (
    model_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT REFERENCES ml_training_runs (run_id),
    dataset_version TEXT,
    checkpoint_uri TEXT,
    accuracy_claim TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    note TEXT
);

INSERT INTO ml_models (
    model_id, title, kind, status, run_id, dataset_version,
    checkpoint_uri, accuracy_claim, created_at, note
) VALUES (
    'ai-forecast',
    'AI Forecast',
    'AI',
    'NOT_TRAINED',
    NULL,
    NULL,
    NULL,
    NULL,
    NOW(),
    'No validated AI flood model is deployed.'
)
ON CONFLICT (model_id) DO NOTHING;
