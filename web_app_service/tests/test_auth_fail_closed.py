from __future__ import annotations

import importlib
from datetime import datetime, timezone

import jwt
import pytest


@pytest.fixture()
def auth(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "auth-test-canonical-secret")
    module = importlib.reload(importlib.import_module("web_app_service.auth"))
    yield module
    monkeypatch.setenv("JWT_SECRET", "auth-test-isolation-secret")
    importlib.reload(module)


def _reload_auth(monkeypatch):
    return importlib.reload(importlib.import_module("web_app_service.auth"))


def test_missing_canonical_secret_fails_closed_without_generated_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_DEV_MODE", "1")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY", "ambiguous-name-must-not-authorize")
    module = _reload_auth(monkeypatch)

    assert module.JWT_SECRET is None
    with pytest.raises(RuntimeError, match="JWT_SECRET is required"):
        module.create_token(7, "service@example.test", "analyst")
    assert module.verify_token("any-token") is None


def test_canonical_secret_roundtrip_and_invalid_tokens_fail(auth):
    token = auth.create_token(7, "service@example.test", "analyst")
    payload = auth.verify_token(token)

    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["email"] == "service@example.test"
    assert payload["role"] == "analyst"
    assert auth.verify_token(token + "tampered") is None

    expired = jwt.encode(
        {
            "sub": "7",
            "email": "service@example.test",
            "role": "analyst",
            "exp": datetime(2000, 1, 1, tzinfo=timezone.utc),
        },
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )
    assert auth.verify_token(expired) is None


def test_dev_fixture_secret_cannot_become_production_authority(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_DEV_MODE", "1")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    module = _reload_auth(monkeypatch)

    assert module.JWT_SECRET != "ai_theme_jwt_secret_dev_only"
    assert module.JWT_SECRET is None


def test_canonical_config_name_has_no_silent_alias_and_revalidation_is_fresh(
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_DEV_MODE", "0")
    monkeypatch.setenv("JWT_SECRET_KEY", "old-ambiguous-secret")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    first = _reload_auth(monkeypatch)

    assert first.JWT_SECRET is None
    monkeypatch.setenv("JWT_SECRET", "first-canonical-secret")
    first = _reload_auth(monkeypatch)
    first_token = first.create_token(7, "service@example.test", "analyst")
    monkeypatch.setenv("JWT_SECRET", "second-canonical-secret")
    second = _reload_auth(monkeypatch)
    second_token = second.create_token(7, "service@example.test", "analyst")

    assert second.verify_token(second_token) is not None
    assert second.verify_token(first_token) is None


def test_op02a_service_principal_spec_is_frozen_and_least_privilege(auth):
    spec = auth.OP02A_SERVICE_PRINCIPAL_AUTHORITY_SPEC

    assert spec["principal_count"] == 1
    assert spec["process_scope"] == "single_process"
    assert spec["principal_kind"] == "dedicated_service"
    assert spec["least_privilege_role"] == "analyst"
    assert spec["authorization_input"] == "one_explicit_launch_time_bearer"
    assert spec["credential_retention"] == "normalized_approval_principal_identity_only"
    assert spec["principal_selection_override"] is False
    assert spec["validation_cadence"] == "fresh_every_process_start"
    assert spec["in_process_refresh"] is False
    assert spec["fallback_authority"] is False
    assert spec["provider_lifetime_limit"] == "validated_token_expiry"
    assert spec["close_scope"] == "provider_binding_only"
    assert spec["revocation_mechanism"] == "hs256_global_key_rotation"
    assert spec["issuer_validation"] is False
    assert spec["audience_validation"] is False
    assert spec["jti_validation"] is False
    assert spec["per_token_revocation"] is False


def test_g2b_require_approval_principal_remains_fail_closed(auth):
    from stock_processing_service.application.services.analyst_workbench.approval_contract import (
        ApprovalAuthorizationError,
        require_approval_principal,
    )

    valid = auth.create_token(7, "Service@Example.Test", "analyst")
    principal = require_approval_principal(f"Bearer {valid}")
    assert principal.identity == "user:7:service@example.test"

    wrong_role = auth.create_token(7, "service@example.test", "user")
    missing_email = jwt.encode(
        {"sub": "7", "role": "analyst"},
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )
    missing_sub = jwt.encode(
        {"email": "service@example.test", "role": "analyst"},
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )

    with pytest.raises(ApprovalAuthorizationError, match="not authorized"):
        require_approval_principal(f"Bearer {wrong_role}")
    for token in (missing_email, missing_sub):
        with pytest.raises(ApprovalAuthorizationError, match="incomplete"):
            require_approval_principal(f"Bearer {token}")
