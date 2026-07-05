from fastapi import FastAPI

app = FastAPI(title="Fraud Detection")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}