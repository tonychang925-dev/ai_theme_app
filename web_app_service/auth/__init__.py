"""JWT 认证模块。"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

_JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not _JWT_SECRET:
    # Allow weak default in dev mode only (explicit opt-in)
    if os.getenv("JWT_DEV_MODE", "0") == "1":
        _JWT_SECRET = "ai_theme_jwt_secret_dev_only"
        print("[auth] WARNING: using dev-mode JWT_SECRET — not for production", file=sys.stderr)
    else:
        import secrets
        _JWT_SECRET = secrets.token_hex(32)
        print("[auth] JWT_SECRET not set — auto-generated ephemeral key for this session", file=sys.stderr)
        print(f"[auth] Set JWT_SECRET in .env.local for persistent sessions.", file=sys.stderr)

JWT_SECRET: str = _JWT_SECRET
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72


def create_token(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
