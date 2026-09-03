"""AT-R7 HTTP/JSON boundary for the provider-native Julia Domain Adapter.

Thin transport only. It exposes the frozen AdapterRequest /
DomainObservationEnvelope semantics and does not implement Julia authorization,
MCP, natural-language routing, or market algorithms.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from stock_processing_service.application.services.analyst_workbench.derived_context_reader import DerivedContextReader
from stock_processing_service.application.services.analyst_workbench.market_context_exporter import MarketContextExporter
from stock_processing_service.application.services.julia_domain_adapter import DomainIntelligenceAdapter
from stock_processing_service.application.services.julia_domain_adapter.contracts import (
    ADAPTER_SCHEMA_VERSION,
    AdapterErrorCode,
    AdapterRequest,
    DomainObservationEnvelope,
    HealthReport,
    SourceFailure,
    ValidationError,
)
from stock_processing_service.ports.julia_domain_adapter_config import JuliaDomainAdapterHTTPConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/adapter/v1", tags=["julia-domain-adapter"])


@router.post("/execute")
async def execute_adapter_request(request: Request) -> dict[str, Any]:
    """Execute a frozen provider-native AdapterRequest.

    The HTTP layer only serializes/deserializes JSON. It must not normalize
    partial/unavailable/error/stale states into success/fresh semantics.
    """
    config = _config(request)
    body_bytes = await request.body()
    if len(body_bytes) > config.max_request_bytes:
        raise HTTPException(
            status_code=413,
            detail={"error": "adapter request payload too large", "schema_version": ADAPTER_SCHEMA_VERSION},
        )

    try:
        body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        adapter_request = AdapterRequest.from_dict(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={"error": f"invalid JSON: {exc.msg}", "schema_version": ADAPTER_SCHEMA_VERSION}) from exc
    except UnicodeError as exc:
        raise HTTPException(status_code=400, detail={"error": f"invalid UTF-8: {exc}", "schema_version": ADAPTER_SCHEMA_VERSION}) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "schema_version": ADAPTER_SCHEMA_VERSION}) from exc

    adapter = _adapter_for_request(request)
    logger.info(
        "julia_domain_adapter.execute.start operation=%s correlation_id=%s idempotency_key=%s",
        adapter_request.operation,
        adapter_request.correlation_id,
        adapter_request.idempotency_key,
    )

    try:
        result = await asyncio.wait_for(adapter.execute(adapter_request), timeout=config.execute_timeout_seconds)
    except asyncio.TimeoutError as exc:
        failure = SourceFailure(
            code=AdapterErrorCode.UPSTREAM_TIMEOUT.value,
            message="adapter execution timed out",
            source_name="adapter_http_execute",
            retryable=True,
            details={"timeout_seconds": config.execute_timeout_seconds},
        )
        result = DomainObservationEnvelope(
            operation=adapter_request.operation,
            status="unavailable",
            data_state="empty",
            correlation_id=adapter_request.correlation_id,
            provider_request_id=adapter_request.idempotency_key,
            observed_at=adapter_request.requested_at,
            payload={},
            source_records=[],
            failures=[failure],
            diagnostics={"transport_timeout": True},
        )
    except asyncio.CancelledError:
        logger.warning(
            "julia_domain_adapter.execute.cancelled operation=%s correlation_id=%s",
            adapter_request.operation,
            adapter_request.correlation_id,
        )
        raise

    response = result.to_dict()
    if len(json.dumps(response, ensure_ascii=False, default=str).encode("utf-8")) > config.max_response_bytes:
        failure = SourceFailure(
            code=AdapterErrorCode.INTERNAL_ERROR.value,
            message="adapter response payload too large",
            source_name="adapter_http_execute",
            retryable=False,
            details={"max_response_bytes": config.max_response_bytes},
        )
        response = DomainObservationEnvelope(
            operation=adapter_request.operation,
            status="error",
            data_state="empty",
            correlation_id=adapter_request.correlation_id,
            provider_request_id=adapter_request.idempotency_key,
            observed_at=adapter_request.requested_at,
            payload={},
            source_records=[],
            failures=[failure],
            diagnostics={"response_payload_too_large": True},
        ).to_dict()

    logger.info(
        "julia_domain_adapter.execute.end operation=%s correlation_id=%s status=%s data_state=%s failure_count=%d",
        adapter_request.operation,
        adapter_request.correlation_id,
        response.get("status"),
        response.get("data_state"),
        len(response.get("failures", [])),
    )
    return response


@router.get("/health")
async def adapter_health(request: Request) -> dict[str, Any]:
    """Process-level health: route is alive and contract module imports."""
    config = _config(request)
    return HealthReport(
        ok=True,
        ready=True,
        status="ok",
        dependencies={
            "process": {"status": "ok"},
            "config": {
                "execute_timeout_seconds": config.execute_timeout_seconds,
                "max_request_bytes": config.max_request_bytes,
                "max_response_bytes": config.max_response_bytes,
            },
        },
        schema_version=ADAPTER_SCHEMA_VERSION,
    ).to_dict()


@router.get("/ready")
async def adapter_ready(request: Request) -> dict[str, Any]:
    """Dependency readiness distinct from health.

    This endpoint is read-only and does not execute market operations. It checks
    whether operation-specific providers appear constructible/present.
    """
    config = _config(request)
    failures: list[SourceFailure] = []
    dependencies: dict[str, Any] = {}

    gateway = getattr(request.app.state, "gateway", None)
    pool = _pool_from_gateway(gateway)
    injected_adapter = getattr(request.app.state, "julia_domain_adapter", None)
    workbench_base = _workbench_base_dir(request)

    db_ready = bool(pool or injected_adapter or not config.database_required)
    dependencies["database"] = {
        "required_for": ["market.snapshot"],
        "required": config.database_required,
        "ready": db_ready,
        "source": "injected_adapter" if injected_adapter else "gateway_pool" if pool else "not_required" if not config.database_required else "missing",
    }
    if not db_ready:
        failures.append(SourceFailure(
            code="UPSTREAM_UNAVAILABLE",
            message="database/gateway pool not configured for market.snapshot",
            source_name="database",
            retryable=True,
            details={"required_for": "market.snapshot"},
        ))

    redis_ready = config.redis_url_valid()
    dependencies["redis"] = {
        "required_for": [],
        "required": config.redis_required,
        "ready": redis_ready if config.redis_required else True,
        "configured": redis_ready,
        "note": "not a required adapter v1 dependency unless JULIA_ADAPTER_REDIS_REQUIRED=true",
    }
    if config.redis_required and not redis_ready:
        failures.append(SourceFailure(
            code="UPSTREAM_UNAVAILABLE",
            message="redis configuration invalid or unavailable for required deployment",
            source_name="redis",
            retryable=True,
            details={"required_for": "deployment_readiness"},
        ))

    dependencies["analyst_workbench_store"] = {
        "required_for": ["market.alerts"],
        "required": True,
        "ready": workbench_base.exists() and workbench_base.is_dir(),
        "path": str(workbench_base),
    }
    if not dependencies["analyst_workbench_store"]["ready"]:
        failures.append(SourceFailure(
            code="UPSTREAM_UNAVAILABLE",
            message="analyst workbench store not found",
            source_name="analyst_workbench_store",
            retryable=True,
            details={"required_for": "market.alerts"},
        ))

    return HealthReport(
        ok=True,
        ready=not failures,
        status="ready" if not failures else "not_ready",
        dependencies=dependencies,
        failures=failures,
        schema_version=ADAPTER_SCHEMA_VERSION,
    ).to_dict()


def _adapter_for_request(request: Request) -> DomainIntelligenceAdapter:
    injected = getattr(request.app.state, "julia_domain_adapter", None)
    if injected is not None:
        return injected

    gateway = getattr(request.app.state, "gateway", None)
    pool = _pool_from_gateway(gateway)
    exporter = MarketContextExporter(reader=DerivedContextReader(pool=pool)) if pool is not None else None
    return DomainIntelligenceAdapter(
        market_context_exporter=exporter,
        workbench_base_dir=str(_workbench_base_dir(request)),
    )


def _pool_from_gateway(gateway: Any) -> Any:
    client = getattr(gateway, "_client", None)
    return getattr(client, "pool", None) if client is not None else None


def _config(request: Request) -> JuliaDomainAdapterHTTPConfig:
    injected = getattr(request.app.state, "julia_domain_adapter_config", None)
    if injected is not None:
        return injected
    return JuliaDomainAdapterHTTPConfig.from_env()


def _workbench_base_dir(request: Request) -> Path:
    configured = getattr(request.app.state, "julia_domain_adapter_workbench_base_dir", None)
    if configured:
        return Path(str(configured))
    return _config(request).workbench_base_dir


def register_julia_domain_adapter_routes(app: Any) -> None:
    """Register AT-R7 HTTP routes on an existing FastAPI app."""
    app.include_router(router)


__all__ = ["router", "register_julia_domain_adapter_routes"]
