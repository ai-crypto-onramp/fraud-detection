import os
from pathlib import Path

import psycopg
import pytest

from fraud_detection.config import Settings
from fraud_detection.db import SCHEMA_SQL_PATH, PostgresStore, RedisStore


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    dsn = os.environ.get("TEST_PG_DSN", "postgresql://postgres:postgres@localhost:5432/postgres")
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("postgres not available")
    return dsn


def test_postgres_store_apply_and_insert(pg_dsn) -> None:
    store = PostgresStore(pg_dsn)
    store.apply_migrations()
    with store.conn.cursor() as cur:
        cur.execute("TRUNCATE fraud_scores, model_versions, feature_values, chargeback_events, drift_metrics")
    store.insert_score("tx_1", "u1", 0.82, "high", "m@v1", "champion",
                       [{"name": "a", "shap": 0.1}], "2026-07-13T10:00:00Z")
    store.insert_feature_values("tx_1", "user_velocity", {"tx_count_24h": 5})
    store.insert_model_version("chargeback-xgb", "v9", "champion", {"auc": 0.9},
                               {"champion": 1.0}, "2026-07-13T10:00:00Z")
    inserted = store.upsert_chargeback("tx_1", "chargeback", "10.4", "api", "2026-07-13T10:00:00Z")
    assert inserted is True
    inserted2 = store.upsert_chargeback("tx_1", "chargeback", "10.4", "api", "2026-07-13T10:00:00Z")
    assert inserted2 is False

    score = store.fetch_score("tx_1")
    assert score is not None and score["score"] == 0.82
    assert score["variant"] == "champion"

    versions = store.list_model_versions()
    assert any(v["name"] == "chargeback-xgb" and v["version"] == "v9" for v in versions)

    labels = store.fetch_labeled_since("2026-01-01T00:00:00Z")
    assert any(rec["tx_id"] == "tx_1" for rec in labels)

    scores = store.fetch_scores_since("2026-01-01T00:00:00Z")
    assert any(s["tx_id"] == "tx_1" for s in scores)

    store.insert_drift_metric("chargeback-xgb", "f1", 0.5, 0.2, True)
    with store.conn.cursor() as cur:
        cur.execute("DELETE FROM fraud_scores WHERE tx_id='tx_1'")
        cur.execute("DELETE FROM model_versions WHERE name='chargeback-xgb' AND version='v9'")
        cur.execute("DELETE FROM chargeback_events WHERE tx_id='tx_1'")
        cur.execute("DELETE FROM feature_values WHERE tx_id='tx_1'")
        cur.execute("DELETE FROM drift_metrics WHERE model_name='chargeback-xgb'")


def test_postgres_store_ping_false_without_dsn() -> None:
    store = PostgresStore(None)
    assert store.ping() is False


def test_redis_store_ping_false_without_url() -> None:
    store = RedisStore(None)
    assert store.ping() is False


def test_schema_file_exists() -> None:
    assert Path(SCHEMA_SQL_PATH).exists()
