"""Skeleton feature view definitions for the Fraud Detection feature store.

Each feature group below corresponds to a row in the "Feature Groups (Feast)"
table in README.md. They are deliberately skeleton-only here — Stage 1 stands
up the store and schema; Stage 2 fills in the aggregations and the backfill
pipeline. Each view exposes a single placeholder feature so that ``feast
apply`` succeeds and ``get_online_features`` returns a response for the stub
feature view, which is one of this stage's acceptance criteria.

The views are declared with an explicit ``schema`` (and no offline ``source``)
so they are applyable without any Parquet source files existing yet — the
online store is populated directly via ingestion once Stage 2 ships. This
keeps Stage 1 self-contained.
"""

from feast import Entity, FeatureView, Field
from feast.types import Bool, Float64, Int64, String

from feature_repo.entities import device, tx, user


def _view(
    name: str,
    entity: Entity,
    feature: str,
    dtype: object,
) -> FeatureView:
    return FeatureView(
        name=name,
        schema=[Field(name=feature, dtype=dtype)],
        entities=[entity],
        online=True,
        offline=False,
        tags={"stage": "1-skeleton", "group": name},
    )


# Each view mirrors a row in README.md's "Feature Groups (Feast)" table. The
# feature set is intentionally minimal; Stage 2 expands these with the full
# documented feature list and wires them to offline sources.
user_velocity_fv = _view("user_velocity", user, "tx_count_24h", Int64)
device_fv = _view("device", device, "new_to_user_flag", Bool)
geolocation_fv = _view("geolocation", user, "ip_country", String)
payment_history_fv = _view("payment_history", user, "success_fail_ratio_30d", Float64)
chargeback_history_fv = _view("chargeback_history", user, "chargeback_rate_30d", Float64)
# A tx-keyed view so the stub feature view has a tx-keyed lookup target,
# which ``get_online_features`` exercises in the Stage 1 smoke test.
tx_features_fv = _view("tx_features", tx, "amount_minor_units", Int64)

feature_views = [
    user_velocity_fv,
    device_fv,
    geolocation_fv,
    payment_history_fv,
    chargeback_history_fv,
    tx_features_fv,
]