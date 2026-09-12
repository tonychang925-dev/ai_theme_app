"""JWT authentication and the frozen OP02-A service-principal authority spec."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any

import jwt

OP02A_SERVICE_PRINCIPAL_AUTHORITY_SPEC = MappingProxyType(
    {
        "version": 1,
        "principal_count": 1,
        "process_scope": "single_process",
        "principal_kind": "dedicated_service",
        "least_privilege_role": "analyst",
        "authorization_input": "one_explicit_launch_time_bearer",
        "credential_retention": "normalized_approval_principal_identity_only",
        "principal_selection_override": False,
        "validation_cadence": "fresh_every_process_start",
        "in_process_refresh": False,
        "fallback_authority": False,
        "provider_lifetime_limit": "validated_token_expiry",
        "close_scope": "provider_binding_only",
        "revocation_mechanism": "hs256_global_key_rotation",
        "issuer_validation": False,
        "audience_validation": False,
        "jti_validation": False,
        "per_token_revocation": False,
    }
)

_JWT_ENVIRONMENT = os.getenv("APP_ENV", "production").strip().lower()
_JWT_DEV_MODE = os.getenv("JWT_DEV_MODE", "0").strip() == "1"
_JWT_SECRET = os.getenv("JWT_SECRET", "").strip() or None
if (
    _JWT_SECRET is None
    and _JWT_DEV_MODE
    and _JWT_ENVIRONMENT in {"development", "test"}
):
    _JWT_SECRET = "ai_theme_jwt_secret_dev_only"

JWT_SECRET: str | None = _JWT_SECRET
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72


def create_token(user_id: int, email: str, role: str) -> str:
    if JWT_SECRET is None:
        raise RuntimeError("JWT_SECRET is required but is not configured")
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    if JWT_SECRET is None:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
