-- fraud-detection schema: fraud_scores, model_versions, feature_values, chargeback_events, drift_metrics
-- Applied by `make migrate`. Idempotent on re-apply.
-- Conventions: UUID PKs (app-generated UUIDv7, no DB default), UPPER_CASE enum
-- TEXT (no CHECK), created_at + updated_at on every table, no DB triggers.

CREATE TABLE IF NOT EXISTS fraud_scores (
    id            UUID PRIMARY KEY,
    tx_id         TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    score         DOUBLE PRECISION NOT NULL,
    risk_band     TEXT NOT NULL,
    model_version TEXT NOT NULL,
    variant       TEXT NOT NULL,
    top_features  JSONB NOT NULL,
    scored_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tx_id, scored_at)
);

CREATE INDEX IF NOT EXISTS ix_fraud_scores_user_id ON fraud_scores (user_id);
CREATE INDEX IF NOT EXISTS ix_fraud_scores_model_version ON fraud_scores (model_version);
CREATE INDEX IF NOT EXISTS ix_fraud_scores_scored_at ON fraud_scores (scored_at);
CREATE INDEX IF NOT EXISTS ix_fraud_scores_variant ON fraud_scores (variant);

CREATE TABLE IF NOT EXISTS model_versions (
    id            UUID PRIMARY KEY,
    name          TEXT NOT NULL,
    version       TEXT NOT NULL,
    stage         TEXT NOT NULL,
    metrics       JSONB NOT NULL DEFAULT '{}'::jsonb,
    traffic_split JSONB NOT NULL DEFAULT '{}'::jsonb,
    trained_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, version)
);

CREATE INDEX IF NOT EXISTS ix_model_versions_stage ON model_versions (stage);

CREATE TABLE IF NOT EXISTS feature_values (
    id            UUID PRIMARY KEY,
    tx_id         TEXT NOT NULL,
    feature_group TEXT NOT NULL,
    payload       JSONB NOT NULL,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tx_id, feature_group)
);

CREATE TABLE IF NOT EXISTS chargeback_events (
    id          UUID PRIMARY KEY,
    tx_id       TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    reason_code TEXT,
    source      TEXT NOT NULL DEFAULT 'API',
    reported_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tx_id, reported_at)
);

CREATE INDEX IF NOT EXISTS ix_chargeback_events_outcome ON chargeback_events (outcome);
CREATE INDEX IF NOT EXISTS ix_chargeback_events_reported_at ON chargeback_events (reported_at);

CREATE TABLE IF NOT EXISTS drift_metrics (
    id           UUID PRIMARY KEY,
    model_name   TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    psi          DOUBLE PRECISION NOT NULL,
    ks           DOUBLE PRECISION NOT NULL,
    breached     BOOLEAN NOT NULL DEFAULT FALSE,
    measured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_drift_metrics_model ON drift_metrics (model_name);
CREATE INDEX IF NOT EXISTS ix_drift_metrics_measured_at ON drift_metrics (measured_at);