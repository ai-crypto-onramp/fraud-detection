from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Fraud Detection")

# Dependency probe stubs. In production each would perform a real
# round-trip to the named service; here they report healthy so the
# readiness endpoint can be exercised end-to-end.
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