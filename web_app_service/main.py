from fastapi import FastAPI

from web_app_service.api.routes import router

app = FastAPI(title="web_app_service", version="0.1.0")
app.include_router(router, prefix="/api/v2")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "web_app_service"}
