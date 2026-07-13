import os
from pathlib import Path

import psycopg
import pytest

from fraud_detection.config import Settings
from fraud_detection.db import SCHEMA_SQL_PATH, PostgresStore
from fraud_detection.observability.monitoring import AlertSink, DriftMonitor


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


def test_drift_monitor_persists_to_db(pg_dsn) -> None:
    store = PostgresStore(pg_dsn)
    store.apply_migrations()
    with store.conn.cursor() as cur:
        cur.execute("TRUNCATE drift_metrics")
    settings = Settings()
    mon = DriftMonitor(settings, db=store, alert_sink=AlertSink())
    base = {"f1": [0.1, 0.2, 0.3, 0.4, 0.5] * 50}
    cur_ = {"f1": [0.5, 0.6, 0.7, 0.8, 0.9] * 50}
    report = mon.run("chargeback-xgb", base, cur_)
    assert report
    with store.conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM drift_metrics WHERE model_name='chargeback-xgb'")
        n = cur.fetchone()[0]
        cur.execute("DELETE FROM drift_metrics WHERE model_name='chargeback-xgb'")
    assert n >= 1


def test_drift_monitor_maybe_trigger_retraining() -> None:
    settings = Settings()
    mon = DriftMonitor(settings, db=None, alert_sink=AlertSink())
    assert not mon.maybe_trigger_retraining("m", repeat_threshold=3)
    mon._breaches_by_model["m"] = ["a", "b", "c"]
    assert mon.maybe_trigger_retraining("m", repeat_threshold=3)
