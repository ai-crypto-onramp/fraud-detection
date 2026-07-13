from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource, ValueType
from feast.infra.online_stores.redis import RedisOnlineStoreConfig
from feast.repo_config import RepoConfig
from feast.types import Float32, Int64, String

user = Entity(name="user_id", value_type=ValueType.STRING, description="user identifier")
device = Entity(name="device_id", value_type=ValueType.STRING, description="device fingerprint")
tx = Entity(name="tx_id", value_type=ValueType.STRING, description="transaction id")

user_velocity_view = FeatureView(
    name="user_velocity",
    entities=[user],
    ttl=timedelta(days=30),
    schema=[
        Field(name="tx_count_1h", dtype=Int64),
        Field(name="tx_count_24h", dtype=Int64),
        Field(name="tx_count_7d", dtype=Int64),
        Field(name="tx_sum_24h", dtype=Float32),
        Field(name="distinct_cards_24h", dtype=Int64),
        Field(name="distinct_devices_24h", dtype=Int64),
        Field(name="distinct_ips_24h", dtype=Int64),
    ],
    online=True,
)

payment_history_view = FeatureView(
    name="payment_history",
    entities=[user],
    ttl=timedelta(days=90),
    schema=[
        Field(name="success_fail_ratio_30d", dtype=Float32),
        Field(name="avg_ticket_30d", dtype=Float32),
        Field(name="first_payment_age_days", dtype=Int64),
    ],
    online=True,
)

device_view = FeatureView(
    name="device",
    entities=[device],
    ttl=timedelta(days=60),
    schema=[
        Field(name="fingerprint_hash", dtype=String),
        Field(name="new_to_user", dtype=Int64),
        Field(name="known_bad", dtype=Int64),
        Field(name="emulator", dtype=Int64),
        Field(name="rooted", dtype=Int64),
    ],
    online=True,
)

geolocation_view = FeatureView(
    name="geolocation",
    entities=[user],
    ttl=timedelta(days=30),
    schema=[
        Field(name="ip_country", dtype=String),
        Field(name="distance_from_billing_km", dtype=Float32),
        Field(name="vpn_proxy", dtype=Int64),
        Field(name="geo_velocity_kmh", dtype=Float32),
    ],
    online=True,
)

feature_views = [
    user_velocity_view,
    payment_history_view,
    device_view,
    geolocation_view,
]

entities = [user, device, tx]

repo_config = RepoConfig(
    project="fraud_detection",
    registry="data/registry.db",
    provider="local",
    offline_store=None,
    online_store=RedisOnlineStoreConfig(connection_string="redis://redis:6379"),
)
