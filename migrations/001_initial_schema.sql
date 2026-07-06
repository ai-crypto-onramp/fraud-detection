-- Initial schema for the Fraud Detection service.
-- Tables match the data model documented in README.md.
--
-- All tables use immutable-append design where applicable (fraud_scores,
-- chargeback_events) so the audit trail can be replayed for compliance.

CREATE TABLE IF NOT EXISTS fraud_scores (
    id              BIGSERIAL PRIMARY KEY,
    tx_id           TEXT        NOT NULL,
    user_id         TEXT        NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    risk_band       TEXT        NOT NULL CHECK (risk_band IN ('low', 'medium', 'high')),
    model_version   TEXT        NOT NULL,
    top_features    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Append-only audit columns.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fraud_scores_tx_id_uniq UNIQUE (tx_id, scored_at)
);

CREATE INDEX IF NOT EXISTS fraud_scores_user_id_idx      ON fraud_scores (user_id);
CREATE INDEX IF NOT EXISTS fraud_scores_scored_at_idx    ON fraud_scores (scored_at);
CREATE INDEX IF NOT EXISTS fraud_scores_risk_band_idx    ON fraud_scores (risk_band);
CREATE INDEX IF NOT EXISTS fraud_scores_model_version_idx ON fraud_scores (model_version);

CREATE TABLE IF NOT EXISTS model_versions (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT        NOT NULL,
    version     TEXT        NOT NULL,
    stage       TEXT        NOT NULL CHECK (stage IN ('champion', 'challenger', 'archived')),
    metrics     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    trained_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT model_versions_name_version_uniq UNIQUE (name, version)
);

CREATE INDEX IF NOT EXISTS model_versions_name_stage_idx ON model_versions (name, stage);

CREATE TABLE IF NOT EXISTS feature_values (
    id            BIGSERIAL PRIMARY KEY,
    tx_id         TEXT        NOT NULL,
    feature_group TEXT        NOT NULL,
    payload       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS feature_values_tx_id_idx         ON feature_values (tx_id);
CREATE INDEX IF NOT EXISTS feature_values_feature_group_idx ON feature_values (feature_group);

CREATE TABLE IF NOT EXISTS chargeback_events (
    id          BIGSERIAL PRIMARY KEY,
    tx_id       TEXT        NOT NULL,
    outcome     TEXT        NOT NULL CHECK (outcome IN ('chargeback', 'fraud', 'clean')),
    reason_code TEXT,
    reported_at TIMESTAMPTZ NOT NULL,
    source      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Idempotent on (tx_id, reported_at): a duplicate submission is a no-op.
    CONSTRAINT chargeback_events_tx_id_reported_at_uniq UNIQUE (tx_id, reported_at)
);

CREATE INDEX IF NOT EXISTS chargeback_events_tx_id_idx    ON chargeback_events (tx_id);
CREATE INDEX IF NOT EXISTS chargeback_events_outcome_idx  ON chargeback_events (outcome);
CREATE INDEX IF NOT EXISTS chargeback_events_reported_at_idx ON chargeback_events (reported_at);