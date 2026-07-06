"""Stage 1 smoke tests.

These tests assert that:

* the initial migration SQL is parseable (a `psql --dry-run`-equivalent is not
  trivially available in unit environments, so we sanity-check the file via a
  lightweight ``sqlglot`` parse when it is installed and otherwise fall back to
  a structural grep of the documented tables/indexes);
* the Feast feature repo compiles — i.e. ``feature_repo`` imports cleanly and
  exposes the documented entities and feature groups, and ``feast apply``
  succeeds against an ephemeral local registry (no live Redis required because
  the views are schema-only).

Live-Postgres / live-Redis integration is gated behind ``FRAUD_IT`` so the
default CI runner (which has neither dependency) skips them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "migrations" / "001_initial_schema.sql"

# Tables the README "Data Model (PostgreSQL)" section documents.
EXPECTED_TABLES = {
    "fraud_scores",
    "model_versions",
    "feature_values",
    "chargeback_events",
}

# Feature groups the README "Feature Groups (Feast)" section documents.
EXPECTED_FEATURE_GROUPS = {
    "user_velocity",
    "device",
    "geolocation",
    "payment_history",
    "chargeback_history",
}

EXPECTED_ENTITIES = {"user", "device", "tx"}


def test_migration_file_exists() -> None:
    assert MIGRATION.is_file(), f"missing migration at {MIGRATION}"


def test_migration_contains_documented_tables() -> None:
    sql = MIGRATION.read_text()
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, (
            f"migration missing CREATE TABLE for {table}"
        )


def test_migration_has_indexes() -> None:
    sql = MIGRATION.read_text()
    # Each documented table should have at least one supporting index.
    assert "CREATE INDEX IF NOT EXISTS fraud_scores_" in sql
    assert "CREATE INDEX IF NOT EXISTS model_versions_" in sql
    assert "CREATE INDEX IF NOT EXISTS feature_values_" in sql
    assert "CREATE INDEX IF NOT EXISTS chargeback_events_" in sql


def test_migration_is_parseable() -> None:
    sqlglot = pytest.importorskip(
        "sqlglot", reason="sqlglot not installed; skipping parse check"
    )
    parsed = sqlglot.parse(sql=MIGRATION.read_text(), read="postgres")
    statements = [s for s in parsed if s is not None]
    # One CREATE TABLE per documented table + their indexes => at least a
    # handful of statements.
    assert len(statements) >= len(EXPECTED_TABLES), (
        f"expected at least {len(EXPECTED_TABLES)} statements, got {len(statements)}"
    )


def test_feature_repo_exposes_documented_objects() -> None:
    from feature_repo import entities, feature_views

    # Feast auto-injects an `__dummy` entity for the "entityless" case; the
    # repo's own declarations are the three documented entities.
    declared = {e.name for e in entities.entities}
    assert declared == EXPECTED_ENTITIES
    # The repo declares the five documented feature groups plus an internal
    # `tx_features` stub view used as a tx-keyed lookup target.
    declared_fvs = {v.name for v in feature_views.feature_views}
    assert EXPECTED_FEATURE_GROUPS.issubset(declared_fvs)
    assert "tx_features" in declared_fvs


def test_feature_views_have_schema_features() -> None:
    from feature_repo import feature_views

    for fv in feature_views.feature_views:
        feats = [f.name for f in fv.features]
        assert feats, f"feature view {fv.name} declares no features"


def test_feature_store_config_targets_redis_online_store() -> None:
    cfg_path = REPO_ROOT / "feature_repo" / "feature_store.yaml"
    text = cfg_path.read_text()
    assert "project: fraud_detection" in text
    assert "type: redis" in text
    assert "offline_store:" in text


def test_feast_apply_succeeds(tmp_path, monkeypatch) -> None:
    # Point the registry at a throwaway sqlite db so we don't mutate the
    # committed one. We do this by copying the feature_repo dir.
    pytest.importorskip("feast", reason="feast not installed")
    import shutil

    src = REPO_ROOT / "feature_repo"
    dst = tmp_path / "feature_repo"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("data", "__pycache__"))
    # Rewrite registry path to a tmp location.
    cfg = dst / "feature_store.yaml"
    cfg.write_text(
        cfg.read_text().replace(
            "registry: data/registry.db", f"registry: {tmp_path / 'registry.db'}"
        )
    )

    from feast import FeatureStore
    from feast.repo_operations import parse_repo

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(dst.parent))

    store = FeatureStore(repo_path=str(dst))
    repo = parse_repo(dst)
    objects = (
        list(repo.entities)
        + list(repo.feature_views)
        + list(repo.data_sources)
        + list(repo.feature_services)
        + list(repo.on_demand_feature_views)
        + list(repo.stream_feature_views)
        + list(repo.label_views)
    )
    store.apply(objects)

    # The committed registry may persist a `__dummy` entityless placeholder;
    # only assert the documented entities are present.
    listed_entities = {e.name for e in store.list_entities()}
    assert EXPECTED_ENTITIES.issubset(listed_entities)
    listed_fvs = {v.name for v in store.list_feature_views()}
    assert EXPECTED_FEATURE_GROUPS.issubset(listed_fvs)
    assert "tx_features" in listed_fvs


# --- Integration tests (require live Postgres / Redis) ----------------------


def _it_enabled() -> bool:
    return os.environ.get("FRAUD_IT") == "1"


@pytest.mark.skipif(not _it_enabled(), reason="set FRAUD_IT=1 to run integration tests")
def test_migration_applies_to_fresh_postgres() -> None:
    from fraud_detection.migrate import apply_migrations

    url = os.environ.get("DB_URL")
    assert url, "DB_URL must be set for integration test"
    applied = apply_migrations(url)
    assert "001_initial_schema.sql" in applied
    # Idempotent: running again applies nothing new.
    assert apply_migrations(url) == []


@pytest.mark.skipif(not _it_enabled(), reason="set FRAUD_IT=1 to run integration tests")
def test_online_features_respond() -> None:
    from feast import FeatureStore

    store = FeatureStore(repo_path=str(REPO_ROOT / "feature_repo"))
    result = store.get_online_features(
        features=["tx_features:amount_minor_units"],
        entity_rows=[{"tx_id": "pay_smoke"}],
    )
    assert result.to_dict()["tx_id"] == ["pay_smoke"]