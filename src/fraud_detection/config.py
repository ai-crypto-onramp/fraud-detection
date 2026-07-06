"""12-factor configuration for the Fraud Detection service.

All environment variables documented in README.md "Configuration" are exposed
here with their documented defaults. Values are read once at import time so
callers can simply ``from fraud_detection.config import settings``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    return value if value is not None else default


@dataclass(frozen=True)
class Settings:
    # HTTP
    port: int = 8080

    # Storage / infra (no defaults — required at runtime)
    db_url: Optional[str] = None
    redis_url: Optional[str] = None
    kafka_brokers: Optional[str] = None
    model_registry_url: Optional[str] = None

    # Feature store
    feature_store_url: str = "redis://redis:6379"

    # Kafka consumer
    kafka_consumer_group: str = "fraud-detection"

    # Scoring thresholds
    score_threshold_high: float = 0.75
    score_threshold_medium: float = 0.40

    # A/B routing
    challenger_traffic_fraction: float = 0.10

    # Retrain schedules
    retrain_velocity_cron: str = "0 3 * * *"
    retrain_chargeback_cron: str = "0 4 * * 1"

    # Drift
    drift_psi_threshold: float = 0.2

    # Observability
    log_level: str = "info"
    otel_exporter_otlp_endpoint: Optional[str] = field(default=None)

    def is_ready(self) -> bool:
        """True when all *required* env vars (no README default) are set."""
        return all(
            (
                self.db_url,
                self.redis_url,
                self.kafka_brokers,
                self.model_registry_url,
            )
        )


def load_settings() -> Settings:
    """Build a :class:`Settings` from the process environment."""

    def _f(name: str, default: float) -> float:
        raw = _env(name)
        return float(raw) if raw is not None else default

    def _i(name: str, default: int) -> int:
        raw = _env(name)
        return int(raw) if raw is not None else default

    return Settings(
        port=_i("PORT", 8080),
        db_url=_env("DB_URL"),
        redis_url=_env("REDIS_URL"),
        kafka_brokers=_env("KAFKA_BROKERS"),
        model_registry_url=_env("MODEL_REGISTRY_URL"),
        feature_store_url=_env("FEATURE_STORE_URL", "redis://redis:6379") or "redis://redis:6379",
        kafka_consumer_group=_env("KAFKA_CONSUMER_GROUP", "fraud-detection") or "fraud-detection",
        score_threshold_high=_f("SCORE_THRESHOLD_HIGH", 0.75),
        score_threshold_medium=_f("SCORE_THRESHOLD_MEDIUM", 0.40),
        challenger_traffic_fraction=_f("CHALLENGER_TRAFFIC_FRACTION", 0.10),
        retrain_velocity_cron=_env("RETRAIN_VELOCITY_CRON", "0 3 * * *") or "0 3 * * *",
        retrain_chargeback_cron=_env("RETRAIN_CHARGEBACK_CRON", "0 4 * * 1") or "0 4 * * 1",
        drift_psi_threshold=_f("DRIFT_PSI_THRESHOLD", 0.2),
        log_level=_env("LOG_LEVEL", "info") or "info",
        otel_exporter_otlp_endpoint=_env("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )


settings = load_settings()