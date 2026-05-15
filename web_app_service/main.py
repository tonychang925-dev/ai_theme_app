from __future__ import annotations

import os as _os
from pathlib import Path

import httpx
import passlib.hash as passlib_hash
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, Response, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import Scope
from starlette.responses import Response as StarletteResponse


class _NoCacheStaticFiles(StaticFiles):
    async def __call__(self, scope: Scope, receive, send):
        async def _send(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"cache-control"] = b"no-store, no-cache, must-revalidate, max-age=0"
                headers[b"pragma"] = b"no-cache"
                headers[b"expires"] = b"0"
                message["headers"] = list(headers.items())
            await send(message)
        await super().__call__(scope, receive, _send)

from web_app_service.api.routes import router
from web_app_service.auth import create_token, verify_token
from web_app_service.services.jyhf_cdp_manager import JyhfCdpManager
from web_app_service.services.realtime_stack_manager import RealtimeStackManager

app = FastAPI(title="web_app_service", version="0.1.0")


@app.on_event("startup")
async def _startup_cdp_manager() -> None:
    project_root = Path(__file__).resolve().parents[1]
    app.state.cdp_manager = JyhfCdpManager(
        project_root=str(project_root),
        port=int(_os.getenv("JYHF_CDP_SERVICE_PORT", "8095")),
    )
    app.state.realtime_stack_manager = RealtimeStackManager(
        project_root=str(project_root),
        web_port=int(_os.getenv("WEB_PORT", "8000")),
        sps_port=int(_os.getenv("SPS_PORT", "8090")),
    )


@app.on_event("shutdown")
async def _shutdown_cdp_manager() -> None:
    """CDP lifecycle on BFF shutdown.

    Default: do NOT kill the CDP service. The CDP is a long-running
    process that serves DOM capture independently of this BFF instance.
    Killing it on every BFF restart creates a "collector start → BFF
    shutdown → CDP killed → restart → collector start" loop that can
    last minutes before the frontend stabilizes.

    Controlled by env JYHF_CDP_STOP_ON_BFF_SHUTDOWN:
      0 (default) — leave CDP alive; new BFF instance will detect it as external
      1           — restore old behavior: kill managed CDP on BFF shutdown
    """
    stop_on_shutdown = _os.getenv("JYHF_CDP_STOP_ON_BFF_SHUTDOWN", "0").lower() in {"1", "true", "yes", "on"}
    if not stop_on_shutdown:
        return

    manager = getattr(app.state, "cdp_manager", None)
    if manager is not None:
        await manager.stop_service()

# ── API 路由最先注册 ──
app.include_router(router, prefix="/api/v2")

# ── JWT 认证 ──
security = HTTPBearer(auto_error=False)

async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if credentials and credentials.credentials:
        payload = verify_token(credentials.credentials)
        if payload:
            return payload
    return None


# ── 移动端 Token 中间件 ──
MOBILE_ACCESS_TOKEN = _os.getenv("MOBILE_ACCESS_TOKEN", "").strip()

@app.middleware("http")
async def mobile_token_middleware(request: Request, call_next):
    path = request.url.path
    if MOBILE_ACCESS_TOKEN and any(path.startswith(p) for p in ("/mobile", "/api/v2/mobile", "/api/mobile")):
        token = request.headers.get("X-Mobile-Access-Token", "")
        if token != MOBILE_ACCESS_TOKEN:
            return JSONResponse(status_code=401, content={"detail": "mobile access token missing or invalid"})
    return await call_next(request)


# ── Health ──
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "web_app_service"}


# ── Ready (深度就绪检查) ──
_SPS_BASE_URL = _os.getenv("STOCK_PROCESSING_READ_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
_REDIS_URL = _os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()


@app.get("/readyz")
async def readyz():
    checks: dict[str, str] = {}
    fatal: list[str] = []
    degraded: list[str] = []

    # 1. PostgreSQL (connect directly to avoid internal pool access)
    try:
        import asyncpg
        db_url = _os.getenv("DATABASE_URL", "postgresql://localhost:5432/stock_data_test")
        conn = await asyncpg.connect(db_url, timeout=5)
        await conn.fetchval("SELECT 1")
        await conn.close()
        checks["postgres"] = "connected"
    except Exception as exc:
        checks["postgres"] = f"unavailable: {exc}"
        fatal.append("postgres")

    # 2. Redis (degraded on failure, not fatal)
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(_REDIS_URL, socket_connect_timeout=3)
        await r.ping()
        await r.aclose()
        checks["redis"] = "connected"
    except Exception as exc:
        checks["redis"] = f"unavailable: {exc}"
        degraded.append("redis")

    # 3. SPS upstream (fatal)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_SPS_BASE_URL}/healthz")
        if resp.status_code == 200:
            checks["sps_upstream"] = "healthy"
        else:
            checks["sps_upstream"] = f"unhealthy (status={resp.status_code})"
            fatal.append("sps_upstream")
    except Exception as exc:
        checks["sps_upstream"] = f"unreachable: {exc}"
        fatal.append("sps_upstream")

    # 4. Frontend dist (fatal)
    if _SERVE_STATIC:
        checks["frontend_dist"] = "mounted"
    else:
        checks["frontend_dist"] = f"missing (looked in {_DIST_DIR})"
        fatal.append("frontend_dist")

    # 5. Version
    checks["version"] = "0.1.0"

    if fatal:
        status = "failed"
    elif degraded:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "checks": checks,
        "fatal": fatal,
        "degraded": degraded,
    }


# ── Auth API 必须在 SPA fallback 之前 ──

class LoginRequest(BaseModel):
    email: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str = "user"


async def _get_gw():
    from database_service.config import DatabaseConfig, DatabaseType
    from database_service.gateway import DatabaseGateway
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL)
    return await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)


@app.post("/api/v2/auth/login")
async def auth_login(payload: LoginRequest):
    email = payload.email.strip().lower()
    password = payload.password.strip()
    gw = await _get_gw()
    try:
        user = await gw.get_user_by_email(email)
        if not user or not user.get("is_active"):
            raise HTTPException(status_code=401, detail="邮箱或密码错误")
        if not passlib_hash.bcrypt.verify(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="邮箱或密码错误")
        await gw.update_user_last_login(user["id"])
        token = create_token(user["id"], email, user["role"])
        return {"token": token, "user": {"id": user["id"], "email": email, "role": user["role"]}}
    finally:
        await gw.close()


@app.get("/api/v2/auth/me")
async def auth_me(user: dict | None = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {"user": {"id": int(user["sub"]), "email": user["email"], "role": user["role"]}}


@app.put("/api/v2/auth/password")
async def auth_change_password(payload: ChangePasswordRequest, user: dict | None = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    gw = await _get_gw()
    try:
        db_user = await gw.get_user_by_email(user["email"])
        if not db_user or not passlib_hash.bcrypt.verify(payload.old_password, db_user["password_hash"]):
            raise HTTPException(status_code=400, detail="原密码错误")
        if len(payload.new_password) < 6:
            raise HTTPException(status_code=400, detail="新密码至少 6 位")
        new_hash = passlib_hash.bcrypt.hash(payload.new_password)
        async with gw._client.pool.acquire() as conn:
            await conn.execute("UPDATE user_accounts SET password_hash = $1 WHERE id = $2", new_hash, int(user["sub"]))
        return {"ok": True}
    finally:
        await gw.close()


@app.post("/api/v2/admin/users")
async def admin_create_user(payload: CreateUserRequest, user: dict | None = Depends(get_current_user)):
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    email = payload.email.strip().lower()
    password = payload.password.strip()
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    gw = await _get_gw()
    try:
        existing = await gw.get_user_by_email(email)
        if existing:
            raise HTTPException(status_code=409, detail="该邮箱已注册")
        pwd_hash = passlib_hash.bcrypt.hash(password)
        new_user = await gw.create_user(email, pwd_hash, payload.role)
        return {"user": {"id": new_user["id"], "email": email, "role": new_user["role"]}}
    finally:
        await gw.close()


@app.get("/api/v2/admin/users")
async def admin_list_users(user: dict | None = Depends(get_current_user)):
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    gw = await _get_gw()
    try:
        async with gw._client.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, email, role, is_active, created_at, last_login FROM user_accounts ORDER BY id")
        return {"users": [dict(r) for r in rows]}
    finally:
        await gw.close()


# ── 根路径 → SPA（由 React AuthGate 处理未登录跳转） ──
@app.get("/")
async def root_spa():
    """Serve SPA at root. Auth redirect is handled client-side by AuthGate."""
    if _SERVE_STATIC:
        return HTMLResponse(open(_os.path.join(_DIST_DIR, "index.html"), "r").read())
    return {"status": "ok", "service": "web_app_service"}


# ── 前端静态文件 + SPA fallback（最后注册，匹配所有未处理的路径） ──
_DIST_DIR = _os.getenv("FRONTEND_DIST_DIR", "").strip()
if not _DIST_DIR:
    _DIST_DIR = str(Path(__file__).resolve().parents[1] / "frontend" / "dist")

_SERVE_STATIC = _os.path.isdir(_os.path.join(_DIST_DIR, "assets"))

if _SERVE_STATIC:
    app.mount("/assets", _NoCacheStaticFiles(directory=_os.path.join(_DIST_DIR, "assets")), name="assets")

    _NO_CACHE_HEADERS = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    # Also serve static files from dist root (e.g. login-bg.png, favicon.ico)
    _STATIC_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2", ".ttf", ".json", ".txt"}

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if not full_path:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/login", status_code=302)
        stripped = full_path
        ext = _os.path.splitext(stripped)[1].lower()
        if ext in _STATIC_EXTS:
            file_path = _os.path.join(_DIST_DIR, stripped)
            if _os.path.isfile(file_path):
                return FileResponse(file_path, headers=_NO_CACHE_HEADERS)
            raise HTTPException(status_code=404)
        if ext and ext != ".html":
            raise HTTPException(status_code=404)
        return HTMLResponse(
            open(_os.path.join(_DIST_DIR, "index.html"), "r").read(),
            headers=_NO_CACHE_HEADERS,
        )
