"""Connection helpers for the Fraud Detection service dependencies.

Provides lazy accessors for the PostgreSQL connection pool and Redis client,
plus health-check helpers used by ``/readyz``. The connection helpers are
intentionally lightweight (``psycopg``/``redis-py`` are imported lazily) so
that the module imports cleanly in environments without a live dependency
(e.g. the unit-test runner, which guards these paths via env-var skips).
"""

from __future__ import annotations

from typing import Any, Optional

from fraud_detection.config import settings


def check_postgres() -> bool:
    """Return True if Postgres at ``DB_URL`` answers ``SELECT 1``."""

    if not settings.db_url:
        return False
    try:
        import psycopg  # type: ignore
    except ImportError:
        return False
    try:
        with psycopg.connect(settings.db_url) as conn:  # type: ignore[attr-defined]
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
                return bool(row and row[0] == 1)
    except Exception:
        return False


def check_redis() -> bool:
    """Return True if Redis at ``REDIS_URL`` answers ``PING``."""

    if not settings.redis_url:
        return False
    try:
        import redis  # type: ignore
    except ImportError:
        return False
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=1)
        return bool(client.ping())
    except Exception:
        return False


def check_feature_store() -> bool:
    """Return True if the Feast online store is reachable.

    This is a thin wrapper around the Redis check because the configured
    online store backend for this service is Redis (see
    ``feature_repo/feature_store.yaml``).
    """

    return check_redis()


def ready_state() -> dict[str, bool]:
    """Aggregate dependency health for ``/readyz``."""

    return {
        "postgres": check_postgres(),
        "redis": check_redis(),
        "feature_store": check_feature_store(),
    }


__all__: list[str] = [
    "check_feature_store",
    "check_postgres",
    "check_redis",
    "ready_state",
]

_unused: Optional[Any] = None