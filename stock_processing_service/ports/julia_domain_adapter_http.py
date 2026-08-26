"""AT-R4 HTTP/JSON boundary for the provider-native Julia Domain Adapter.

Thin transport only. It exposes the frozen AdapterRequest /
DomainObservationEnvelope semantics and does not implement Julia authorization,
MCP, natural-language routing, or market algorithms.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from stock_processing_service.application.services.analyst_workbench.derived_context_reader import DerivedContextReader
from stock_processing_service.application.services.analyst_workbench.market_context_exporter import MarketContextExporter
from stock_processing_service.application.services.julia_domain_adapter import DomainIntelligenceAdapter
from stock_processing_service.application.services.julia_domain_adapter.contracts import (
    ADAPTER_SCHEMA_VERSION,
    AdapterRequest,
    HealthReport,
    SourceFailure,
    ValidationError,
)

router = APIRouter(prefix="/adapter/v1", tags=["julia-domain-adapter"])


@router.post("/execute")
async def execute_adapter_request(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """Execute a frozen provider-native AdapterRequest.

    The HTTP layer only serializes/deserializes JSON. It must not normalize
    partial/unavailable/error/stale states into success/fresh semantics.
    """
    try:
        adapter_request = AdapterRequest.from_dict(body)
        adapter = _adapter_for_request(request)
        result = await adapter.execute(adapter_request)
        return result.to_dict()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "schema_version": ADAPTER_SCHEMA_VERSION}) from exc


@router.get("/health")
async def adapter_health() -> dict[str, Any]:
    """Process-level health: route is alive and contract module imports."""
    return HealthReport(
        ok=True,
        ready=True,
        status="ok",
        dependencies={"process": {"status": "ok"}},
        schema_version=ADAPTER_SCHEMA_VERSION,
    ).to_dict()


@router.get("/ready")
async def adapter_ready(request: Request) -> dict[str, Any]:
    """Dependency readiness distinct from health.

    This endpoint is read-only and does not execute market operations. It checks
    whether operation-specific providers appear constructible/present.
    """
    failures: list[SourceFailure] = []
    dependencies: dict[str, Any] = {}

    gateway = getattr(request.app.state, "gateway", None)
    pool = _pool_from_gateway(gateway)
    workbench_base = _workbench_base_dir(request)

    dependencies["market_context_exporter"] = {
        "required_for": ["market.snapshot"],
        "ready": bool(pool or getattr(request.app.state, "julia_domain_adapter", None)),
        "source": "injected_adapter" if getattr(request.app.state, "julia_domain_adapter", None) else "gateway_pool" if pool else "missing",
    }
    if not dependencies["market_context_exporter"]["ready"]:
        failures.append(SourceFailure(
            code="UPSTREAM_UNAVAILABLE",
            message="market snapshot exporter/gateway pool not configured",
            source_name="market_context_exporter",
            retryable=True,
            details={"required_for": "market.snapshot"},
        ))

    dependencies["analyst_workbench_store"] = {
        "required_for": ["market.alerts"],
        "ready": workbench_base.exists(),
        "path": str(workbench_base),
    }
    if not workbench_base.exists():
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


def _workbench_base_dir(request: Request) -> Path:
    configured = getattr(request.app.state, "julia_domain_adapter_workbench_base_dir", None)
    if configured:
        return Path(str(configured))
    return Path(__file__).resolve().parents[2] / "tmp" / "analyst_workbench"


def register_julia_domain_adapter_routes(app: Any) -> None:
    """Register AT-R4 HTTP routes on an existing FastAPI app."""
    app.include_router(router)


__all__ = ["router", "register_julia_domain_adapter_routes"]
