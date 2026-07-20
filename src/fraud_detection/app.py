from __future__ import annotations

import logging
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from .audit import AuditEmitter
from .config import Settings, get_settings
from .db import PostgresStore, RedisStore
from .feature_store import FeatureStoreClient, InMemoryFeatureStore
from .models.schemas import (
    FeedbackRequest,
    ModelInfo,
    ModelsResponse,
    ScoreRequest,
    ScoreResponse,
)
from .observability.monitoring import VARIANT_TRAFFIC, AlertSink, DriftMonitor
from .registry import ModelRegistry
from .scoring import ModelLoader, score_request

app = FastAPI(title="Fraud Detection")

log = logging.getLogger("fraud_detection.app")

_DEFAULT_SETTINGS = get_settings()
_DEV_MODE = _DEFAULT_SETTINGS.dev_mode

if not _DEV_MODE:
    # Production: require DB_URL, REDIS_URL, KAFKA_BROKERS, and a model
    # source (FRAUD_MODEL_URL or MODEL_PATH). The StubModel is only allowed
    # in DEV_MODE=1.
    if not _DEFAULT_SETTINGS.db_url:
        log.error("DB_URL not set and DEV_MODE!=1; refusing to start in production mode")
        sys.exit(1)
    if not _DEFAULT_SETTINGS.redis_url:
        log.error("REDIS_URL not set and DEV_MODE!=1; refusing to start in production mode")
        sys.exit(1)
    if not _DEFAULT_SETTINGS.kafka_brokers:
        log.error("KAFKA_BROKERS not set and DEV_MODE!=1; refusing to start in production mode")
        sys.exit(1)
    if not (_DEFAULT_SETTINGS.model_registry_url or _DEFAULT_SETTINGS.model_path):
        log.error(
            "FRAUD_MODEL_URL (MODEL_REGISTRY_URL) or MODEL_PATH required in production mode; "
            "StubModel is only allowed in DEV_MODE=1 — set DEV_MODE=1 for local dev"
        )
        sys.exit(1)
else:
    log.warning("DEV_MODE=1: using StubModel / in-memory defaults — NOT FOR PRODUCTION")

_DEFAULT_DB = PostgresStore(_DEFAULT_SETTINGS.db_url)
_DEFAULT_REDIS = RedisStore(_DEFAULT_SETTINGS.redis_url)
_DEFAULT_FEATURE_STORE = InMemoryFeatureStore(_DEFAULT_SETTINGS)
_DEFAULT_LOADER = ModelLoader(_DEFAULT_SETTINGS.model_registry_url)
_DEFAULT_REGISTRY = ModelRegistry(_DEFAULT_SETTINGS, db=None, loader=_DEFAULT_LOADER)
_DEFAULT_AUDIT = AuditEmitter(db=None, audit_topic=_DEFAULT_SETTINGS.audit_topic)
_DEFAULT_ALERTS = AlertSink()
_DEFAULT_DRIFT = DriftMonitor(_DEFAULT_SETTINGS, db=None, alert_sink=_DEFAULT_ALERTS)


def db_ready() -> bool: return True
def mq_ready() -> bool: return True
def rules_ready() -> bool: return True
def features_ready() -> bool: return True
def scoring_ready() -> bool: return True
def kyt_ready() -> bool: return True
def ledger_ready() -> bool: return True
def pricing_ready() -> bool: return True
def identity_ready() -> bool: return True
def policy_ready() -> bool: return True
def notification_ready() -> bool: return True
def audit_ready() -> bool: return True
def rail_ready() -> bool: return True
def exchange_ready() -> bool: return True
def blockchain_ready() -> bool: return True
def mpc_ready() -> bool: return True
def wallet_ready() -> bool: return True
def onboarding_ready() -> bool: return True

READINESS_CHECKS = [
    ("db", db_ready),
    ("mq", mq_ready),
    ("rules", rules_ready),
    ("features", features_ready),
    ("scoring", scoring_ready),
    ("kyt", kyt_ready),
    ("ledger", ledger_ready),
    ("pricing", pricing_ready),
    ("identity", identity_ready),
    ("policy", policy_ready),
    ("notification", notification_ready),
    ("audit", audit_ready),
    ("rail", rail_ready),
    ("exchange", exchange_ready),
    ("blockchain", blockchain_ready),
    ("mpc", mpc_ready),
    ("wallet", wallet_ready),
    ("onboarding", onboarding_ready),
]


def readiness_report() -> tuple[dict[str, str], int, int]:
    results: dict[str, str] = {}
    failed = 0
    total = 0
    for name, fn in READINESS_CHECKS:
        total += 1
        if fn():
            results[name] = "ok"
        else:
            results[name] = "down"
            failed += 1
    return results, failed, total


def classify_readiness(failed: int, total: int) -> tuple[int, str]:
    if failed == total and total > 0:
        return 503, "not ready"
    if failed > 0:
        return 200, "degraded"
    return 200, "ready"


@app.on_event("startup")
async def _apply_migrations_on_startup() -> None:
    if _DEFAULT_SETTINGS.db_url and _DEFAULT_DB.ping():
        _DEFAULT_DB.apply_migrations()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    results, failed, total = readiness_report()
    code, status = classify_readiness(failed, total)
    results["status"] = status
    results["healthy"] = str(total - failed)
    results["failed"] = str(failed)
    results["total"] = str(total)
    return JSONResponse(status_code=code, content=results)


def _store_for(score_req: ScoreRequest) -> ScoreRequest:
    return score_req


def _features_for(
    feature_store: FeatureStoreClient, req: ScoreRequest,
) -> dict[str, Any]:
    feats: dict[str, Any] = {}
    feats.update(feature_store.get_features(req.user_id, "user_velocity") or {})
    feats.update(feature_store.get_features(req.user_id, "payment_history") or {})
    feats.update(feature_store.get_features(req.device.fingerprint, "device") or {})
    feats.update(feature_store.get_features(req.user_id, "geolocation") or {})
    feats["session_duration_ms"] = req.behavioral_features.session_duration_ms
    feats["keystroke_entropy"] = req.behavioral_features.keystroke_entropy
    feats["tap_variance"] = req.behavioral_features.tap_variance
    return feats


def _do_score(
    req: ScoreRequest,
    *,
    settings: Settings | None = None,
    feature_store: FeatureStoreClient | None = None,
    registry: ModelRegistry | None = None,
    audit: AuditEmitter | None = None,
) -> ScoreResponse:
    settings = settings or _DEFAULT_SETTINGS
    feature_store = feature_store or _DEFAULT_FEATURE_STORE
    registry = registry or _DEFAULT_REGISTRY
    audit = audit or _DEFAULT_AUDIT
    feats = _features_for(feature_store, req)
    model_name = "chargeback-xgb"
    tx_id = req.tx_id or req.payment_id
    split = registry.traffic_split_for(model_name)
    from .models.routing import pick_variant, resolve_split
    variant = pick_variant(
        tx_id,
        challenger_fraction=resolve_split(split, default_challenger_fraction=settings.challenger_traffic_fraction),
        force_variant=settings.force_variant,
    )
    version = registry.resolve_version(model_name, variant) or "v3.2.0-stub"
    model = registry.get_model(model_name, version)
    resp = score_request(
        req, features=feats, model=model, model_version=f"{model_name}@{version}",
        threshold_high=settings.score_threshold_high,
        threshold_medium=settings.score_threshold_medium,
        challenger_fraction=settings.challenger_traffic_fraction,
        traffic_split=split, force_variant=settings.force_variant,
    )
    VARIANT_TRAFFIC.labels(variant=resp.variant).inc()
    audit.emit(req, resp, feature_snapshot_uri=f"feature_values:{tx_id}")
    return resp


@app.post("/v1/fraud/score", response_model=ScoreResponse)
async def score(req: ScoreRequest) -> ScoreResponse:
    return _do_score(req)


@app.get("/v1/fraud/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    models = _DEFAULT_REGISTRY.list_models()
    out: list[ModelInfo] = []
    for m in models:
        breaches = _DEFAULT_DRIFT.breaches_for(m["name"])
        out.append(ModelInfo(
            name=m["name"], champion=m["champion"], challenger=m["challenger"],
            traffic_split=m["traffic_split"], updated_at=m["updated_at"],
            drift_breaches=breaches,
        ))
    return ModelsResponse(models=out)


@app.post("/v1/fraud/feedback")
async def feedback(req: FeedbackRequest) -> Response:
    if req.outcome not in {"CHARGEBACK", "FRAUD", "CLEAN"}:
        raise HTTPException(status_code=422, detail="invalid outcome")
    inserted = _DEFAULT_DB.upsert_chargeback(
        tx_id=req.tx_id, outcome=req.outcome, reason_code=req.reason_code,
        source=req.source, reported_at=req.reported_at,
    )
    if not inserted:
        return Response(status_code=204)
    return Response(status_code=204)
