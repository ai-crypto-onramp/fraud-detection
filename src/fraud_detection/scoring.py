from __future__ import annotations

import hashlib
import os
import pickle
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import numpy as np

from .models.routing import pick_variant, resolve_split, risk_band
from .models.schemas import ScoreRequest, ScoreResponse, TopFeature


class StubModel:
    """Deterministic stub model: score = weighted combination of features.

    Reproducible without xgboost/sklearn installed so the happy path is
    testable in CI without heavy ML deps.
    """

    name = "chargeback-xgb"
    version = "v3.2.0-stub"

    feature_names = [
        "tx_count_24h", "tx_sum_24h", "distinct_devices_24h",
        "distinct_ips_24h", "known_bad", "new_to_user", "emulator",
        "rooted", "vpn_proxy", "distance_from_billing_km", "geo_velocity_kmh",
        "session_duration_ms", "keystroke_entropy", "tap_variance",
    ]

    weights = {
        "tx_count_24h": 0.02,
        "tx_sum_24h": 0.00001,
        "distinct_devices_24h": 0.04,
        "distinct_ips_24h": 0.04,
        "known_bad": 0.30,
        "new_to_user": 0.15,
        "emulator": 0.10,
        "rooted": 0.10,
        "vpn_proxy": 0.15,
        "distance_from_billing_km": 0.002,
        "geo_velocity_kmh": 0.001,
        "session_duration_ms": 0.0,
        "keystroke_entropy": -0.10,
        "tap_variance": -0.05,
    }

    def predict_proba(self, X: np.ndarray | list[list[float]]) -> list[float]:
        arr = np.asarray(X, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        scores: list[float] = []
        for row in arr:
            s = 0.0
            for i, name in enumerate(self.feature_names):
                w = self.weights.get(name, 0.0)
                v = float(row[i]) if i < len(row) else 0.0
                s += w * v
            s = 1.0 / (1.0 + np.exp(-s)) if not np.isnan(s) else 0.5
            scores.append(float(min(0.99, max(0.01, s))))
        return scores

    def shap_contributions(self, X: np.ndarray | list[list[float]]) -> list[dict[str, float]]:
        arr = np.asarray(X, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        out: list[dict[str, float]] = []
        for row in arr:
            contribs: dict[str, float] = {}
            for i, name in enumerate(self.feature_names):
                w = self.weights.get(name, 0.0)
                v = float(row[i]) if i < len(row) else 0.0
                contribs[name] = w * v
            out.append(contribs)
        return out


class StubVelocityModel(StubModel):
    name = "velocity-isoforest"
    version = "v1.4.0-stub"


def default_model_for_name(name: str) -> StubModel:
    if name == "velocity-isoforest":
        return StubVelocityModel()
    return StubModel()


class ModelLoader:
    def __init__(self, registry_url: str | None = None) -> None:
        self.registry_url = registry_url
        self._cache: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()
        self._stage_index: dict[str, dict[str, str]] = {}

    def get(self, name: str, version: str) -> Any:
        key = (name, version)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            model = self._load(name, version)
            self._cache[key] = model
            return model

    def invalidate(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._cache.clear()
                self._stage_index.clear()
            else:
                for k in list(self._cache):
                    if k[0] == name:
                        del self._cache[k]
                self._stage_index.pop(name, None)

    def _load(self, name: str, version: str) -> Any:
        path = os.environ.get(f"MODEL_PATH_{name.upper().replace('-', '_')}_{version.upper().replace('.', '_')}")
        if path and os.path.exists(path):
            with open(path, "rb") as fh:
                return pickle.load(fh)
        return default_model_for_name(name)

    def register_stage(self, name: str, stage: str, version: str) -> None:
        with self._lock:
            self._stage_index.setdefault(name, {})
            self._stage_index[name][stage] = version

    def stage_of(self, name: str, stage: str) -> str | None:
        with self._lock:
            return self._stage_index.get(name, {}).get(stage)


def now_utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def feature_vector(features: Mapping[str, Any], feature_names: list[str]) -> list[float]:
    return [float(features.get(n, 0) or 0) for n in feature_names]


def top_shap_features(contribs: Mapping[str, float], k: int = 3) -> list[TopFeature]:
    items = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [TopFeature(name=n, shap=round(float(v), 4)) for n, v in items[:k]]


def score_request(
    req: ScoreRequest,
    *,
    features: Mapping[str, Any],
    model: Any,
    model_version: str,
    threshold_high: float,
    threshold_medium: float,
    challenger_fraction: float,
    traffic_split: Mapping[str, float] | None = None,
    force_variant: str | None = None,
    salt: str = "",
) -> ScoreResponse:
    tx_id = req.tx_id or req.payment_id
    vec = feature_vector(features, model.feature_names)
    scores = model.predict_proba([vec])
    raw = float(scores[0])
    band = risk_band(raw, threshold_high, threshold_medium)
    contribs = model.shap_contributions([vec])[0]
    variant = pick_variant(
        tx_id,
        challenger_fraction=resolve_split(traffic_split, default_challenger_fraction=challenger_fraction),
        force_variant=force_variant,
        salt=salt,
    )
    return ScoreResponse(
        score=round(raw, 4),
        risk_band=band,
        model_version=model_version,
        variant=variant,
        top_features=top_shap_features(contribs),
        scored_at=now_utc_iso(),
    )


def deterministic_score(features: Mapping[str, Any], salt: str = "") -> float:
    h = hashlib.sha256((salt + json_sorted(features)).encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") / float(1 << 32)


def json_sorted(features: Mapping[str, Any]) -> str:
    import json
    return json.dumps(features, sort_keys=True, default=str)
