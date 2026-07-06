from fastapi import FastAPI

from fraud_detection.connections import ready_state

app = FastAPI(title="Fraud Detection")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, dict[str, bool]]:
    return {"status": ready_state()}