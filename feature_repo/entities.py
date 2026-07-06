"""Entity definitions for the Fraud Detection feature store.

Entities correspond to the join keys used across feature views. The README
data model describes three entity families — `user`, `device`, and `tx` —
which are referenced by the feature groups documented in README.md.
"""

from feast import Entity
from feast.value_type import ValueType

# A user is the account that initiates a payment. Feature views keyed on the
# user entity model payment history, velocity, and chargeback behaviour.
user = Entity(
    name="user",
    join_keys=["user_id"],
    value_type=ValueType.STRING,
    description="A user account initiating one or more payments.",
)

# A device is the physical/browser fingerprint associated with a payment.
device = Entity(
    name="device",
    join_keys=["device_id"],
    value_type=ValueType.STRING,
    description="A device fingerprint observed on a payment.",
)

# A transaction (tx) is the atomic scoring unit; a single payment_id maps to
# a single fraud score and is the join key used for the feature snapshot that
# is persisted alongside each score.
tx = Entity(
    name="tx",
    join_keys=["tx_id"],
    value_type=ValueType.STRING,
    description="A single payment transaction.",
)

entities = [user, device, tx]