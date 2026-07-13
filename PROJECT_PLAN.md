# Project Plan — Fraud Detection

This plan breaks the Fraud Detection service (ML-powered risk scoring layer for
the crypto on-ramp) into logically ordered implementation stages, derived from
the system requirements in `README.md`. Each stage is independently shippable
and tracked as a GitHub issue. Stages are ordered so that foundational data
plumbing (feature store, schema) precedes the scoring surface, which precedes
ML Ops (registry, A/B, drift), feedback loops, async ingestion, audit, and
finally hardening (tests, coverage, Docker). Stages 1–10 are tracked as
GitHub issues.

## Stage 1: Feature Store Setup & Schema

**Goal:** Stand up the Feast feature store and PostgreSQL schema so the service
has a place to read features from and persist scores, model versions, and
feedback labels.

**Tasks:**
- [x] Add Postgres migrations for `fraud_scores`, `model_versions`, `feature_values`, `chargeback_events` tables per README data model.
- [x] Bootstrap Feast feature repo (`feature_repo/`) with Redis online store config.
- [x] Define entity definitions (`user`, `device`, `tx`) and skeleton feature group files.
- [x] Add connection helpers for Postgres (`DB_URL`) and Redis (`REDIS_URL`/`FEATURE_STORE_URL`) with health checks.
- [x] Wire config loading from environment variables (12-factor) in `app/config.py`.
- [x] Add a `make migrate` target and a smoke test that applies migrations against a containerized Postgres.

**Acceptance criteria:**
- Migrations apply cleanly to a fresh Postgres and tables match the README data model.
- `feast apply` succeeds and the Redis online store responds to `get_online_features` for a stub feature view.
- Config module exposes all required env vars from the README with defaults.

## Stage 2: Feature Engineering Pipeline — Velocity, Device & Geolocation

**Goal:** Build the `user_velocity`, `payment_history`, `device`, and
`geolocation` feature groups plus a backfill pipeline that populates offline +
online stores from historical events.

**Tasks:**
- [x] Define `user_velocity` feature view (tx count/sum last 1h, 24h, 7d; distinct cards/devices/IPs).
- [x] Define `payment_history` feature view (success/fail ratio, avg ticket, first-payment age).
- [x] Define `device` feature view (fingerprint hash, new-to-user flag, known-bad flag, emulator/rooted).
- [x] Define `geolocation` feature view (IP country, distance from billing, VPN/proxy flag, geo-velocity).
- [x] Implement `app/features/backfill.py` CLI (`--since YYYY-MM-DD`) that reads historical events and materializes features.
- [x] Integrate a known-bad device list source (configurable; stubbed for tests).
- [x] Add IP enrichment helper (country, proxy detection) with a swappable provider.
- [x] Add unit tests for aggregation windows, distinct-count, new-to-user detection, geo-velocity, and distance computation.
- [x] Document local backfill command in README dev section.

**Acceptance criteria:**
- `uv run python -m app.features.backfill --since 2026-01-01` populates Redis online store and a Parquet offline store for all four feature groups.
- Feature values match expected aggregates for a synthetic event fixture.
- Online lookups return the documented fields; known-bad flag matches the stubbed list.
- p99 online lookup for a single entity is < 50 ms in a local benchmark.
- Tests cover edge cases (first-seen device, missing IP, proxy flag).

## Stage 3: Scoring Endpoint (REST)

**Goal:** Implement `POST /v1/fraud/score` returning score, risk band,
model_version, top SHAP features, and `scored_at`.

**Tasks:**
- [x] Scaffold FastAPI app (`app/main.py`) with `/healthz` and `/readyz`.
- [x] Implement request/response Pydantic models matching README examples.
- [x] Wire feature fetch from Feast online store into the scoring path.
- [x] Load a stub model (pickle) and compute a deterministic score for the happy path.
- [x] Compute risk_band from `SCORE_THRESHOLD_HIGH`/`SCORE_THRESHOLD_MEDIUM`.
- [x] Compute SHAP top-3 features for the response.
- [x] Persist the score row to `fraud_scores` and a snapshot to `feature_values`.
- [x] Add integration test with a fixture model and stubbed feature store.

**Acceptance criteria:**
- `POST /v1/fraud/score` returns 200 with the documented JSON shape on a valid request.
- Risk band thresholds match env-configured cut-offs.
- p99 score latency < 200 ms in a local load test against stubbed dependencies.
- Score row is persisted immutably to `fraud_scores`.

## Stage 4: Model Registry & Versioning (MLflow)

**Goal:** Integrate MLflow as the model registry, with `GET /v1/fraud/models`
listing registered models, versions, stages, and A/B traffic split metadata.

**Tasks:**
- [x] Add MLflow client wired to `MODEL_REGISTRY_URL`.
- [x] Implement model loading by name + version with caching and hot-reload on stage transition.
- [x] Persist registered model metadata into `model_versions` table.
- [x] Implement `GET /v1/fraud/models` returning champion/challenger and traffic_split per README shape.
- [x] Stage transitions (`staging → champion → archived`) are audited (log + table row).
- [x] Add training entrypoints `app/training/train_chargeback.py` and `train_velocity.py` that log params, metrics (AUC, PR-AUC, calibration), and feature snapshot URI.

**Acceptance criteria:**
- A trained model is registered, appears in `GET /v1/fraud/models`, and is loadable by the scoring endpoint.
- Rolling back a champion via MLflow stage transition is reflected in the API in < 5 min (hot-reload).
- Training scripts emit the documented metrics to MLflow.

## Stage 5: Chargeback Feedback Ingestion

**Goal:** Implement `POST /v1/fraud/feedback` and the `chargeback_events` table
as the label source for the retraining pipeline.

**Tasks:**
- [x] Implement `POST /v1/fraud/feedback` endpoint with Pydantic validation (`outcome ∈ {chargeback, fraud, clean}`).
- [x] Persist rows to `chargeback_events` (idempotent on `tx_id` + `reported_at`).
- [x] Add a query helper to fetch labeled samples since a watermark for retraining.
- [x] Wire the daily (velocity) and weekly (chargeback) retrain schedules to pull labels and register a candidate.
- [x] Add promotion gate (human approval) before a candidate becomes challenger/champion.

**Acceptance criteria:**
- `POST /v1/fraud/feedback` returns 204 on valid input and 422 on invalid `outcome`.
- Duplicate submission for the same `tx_id` + `reported_at` is a no-op.
- Retrain job produces a registered candidate model with computed metrics.

## Stage 6: A/B Champion/Challenger Routing

**Goal:** Route scoring traffic between champion and challenger by stable hash
of `tx_id` according to configurable per-model traffic splits.

**Tasks:**
- [x] Implement stable hash routing over `tx_id` (deterministic, unit-tested).
- [x] Resolve active traffic split per model name from the registry; default via `CHALLENGER_TRAFFIC_FRACTION`.
- [x] Log which variant scored each request; emit `variant` field in audit payload.
- [x] Expose per-variant online metrics (score distribution, alert rate) for comparison.
- [x] Add a config knob to force a single variant for canary/debug.

**Acceptance criteria:**
- Over 10k synthetic requests, observed split matches configured fraction within ±1%.
- Same `tx_id` always routes to the same variant for a given split config.
- Variant assignment is visible in `fraud_scores`/audit payloads.

## Stage 7: Drift Monitoring

**Goal:** Daily PSI/KS drift checks on input features and score distribution per
model, breaching `DRIFT_PSI_THRESHOLD` to open an alert.

**Tasks:**
- [x] Implement PSI and KS statistic helpers with unit tests.
- [x] Add a scheduled job comparing the current day's feature/score distribution against the training baseline.
- [x] Persist drift metrics and breach flags to a `drift_metrics` table (or extension).
- [x] Emit `fraud.alert.raised` on breach and surface in `GET /v1/fraud/models` health.
- [x] Wire optional auto-trigger of retraining on repeated breach.

**Acceptance criteria:**
- Drift job runs daily and writes per-feature PSI/KS with timestamps.
- A synthetic shifted distribution triggers `fraud.alert.raised` and is visible in the models endpoint.
- PSI threshold is configurable via `DRIFT_PSI_THRESHOLD`.

## Stage 8: Kafka Consumer for Payment Events

**Goal:** Async ingestion of `payment.authorized`, `payment.captured`, and
`chargeback.received`, emitting `fraud.scored`, `fraud.alert.raised`, and
`fraud.audit`.

**Tasks:**
- [x] Add `aiokafka` consumer worker consuming `payment.*` and `chargeback.*` topics with group `fraud-detection`.
- [x] Reuse the scoring path to score consumed payments.
- [x] Emit `fraud.scored` for every score; `fraud.alert.raised` when score ≥ `SCORE_THRESHOLD_HIGH`.
- [x] Emit `fraud.audit` (immutable) for every score for the Audit / Event Log consumer.
- [x] Handle `chargeback.received` by routing to the feedback path (Stage 5).
- [x] Add consumer lag and throughput Prometheus metrics.
- [x] Integration test with an in-process Kafka (or testcontainers) fixture.

**Acceptance criteria:**
- Consumer processes `payment.authorized` events end-to-end and emits `fraud.scored` + `fraud.audit`.
- High-band scores produce `fraud.alert.raised`.
- Sustained throughput ≥ 2,000 scores/sec in a local benchmark with stubbed model.

## Stage 9: Audit Emission

**Goal:** Emit an immutable `fraud.audit` event for every score (sync + async)
and ensure the audit trail is complete enough for compliance replay.

**Tasks:**
- [x] Define `fraud.audit` Avro/JSON schema with tx_id, user_id, score, risk_band, model_version, variant, top_features, feature snapshot URI, scored_at.
- [x] Emit audit on every scoring path (REST + Kafka consumer) exactly-once per score.
- [x] Persist a local audit copy to `fraud_scores` (retained 7 years) for replay/debug.
- [x] Add a replay tool (`app/replay.py`) that reconstructs scores from audit + feature snapshots.
- [x] Tests assert audit emission for both paths and idempotency.

**Acceptance criteria:**
- Every score (sync and async) emits exactly one `fraud.audit` event.
- Replay tool reproduces the original score for a sampled tx_id from stored audit + snapshot.
- Audit payload contains all fields required for compliance.

## Stage 10: Tests, Coverage & Docker

**Goal:** Harden the service with comprehensive tests, coverage gating, and a
production-ready Docker image plus compose stack.

**Tasks:**
- [x] Raise unit + integration test coverage to ≥ 80% (enforced via Codecov).
- [x] Add `ruff` and `mypy` to CI; gate merges on green.
- [x] Finalize `Dockerfile` (multi-stage, non-root user, healthcheck).
- [x] Add `docker-compose.yml` with Postgres, Redis, Kafka, MLflow, and the service.
- [x] Add a Makefile target `make up` / `make test` / `make lint` / `make train`.
- [x] Document the full local dev loop in README.

**Acceptance criteria:**
- `uv run pytest` passes with ≥ 80% coverage and Codecov upload works.
- `docker compose up` brings the full stack up and `/healthz` returns 200.
- `make lint` and `make typecheck` run clean.