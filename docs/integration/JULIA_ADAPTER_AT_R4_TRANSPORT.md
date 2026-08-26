# AT-R4 External Transport Boundary

Status: AT-R4 HTTP/JSON transport. This phase exposes the already-frozen provider-native contract without changing schema semantics.

## Transport framework/location

Framework: existing FastAPI app.

Files:

- `stock_processing_service/ports/julia_domain_adapter_http.py`
- registered from `stock_processing_service/api_app.py`
- standalone stdlib client: `scripts/julia_domain_adapter_client.py`

## Endpoint Contract

### `POST /adapter/v1/execute`

Input: frozen `AdapterRequest` JSON.

Output: frozen `DomainObservationEnvelope` JSON for valid provider requests.

Transport invariant: the HTTP layer only serializes/deserializes. It does not normalize:

- `partial -> success`
- `unavailable/error -> success + empty`
- `stale -> fresh`

Malformed request DTOs return HTTP 400 with schema version metadata; they do not mutate the provider wire schema.

### `GET /adapter/v1/health`

Process-level health. Returns `HealthReport` with `ok=true` when the route and contract module are alive.

### `GET /adapter/v1/ready`

Dependency readiness. Checks operation-specific provider availability without executing market operations.

Readiness can be false while health is true.

## Standalone client / curl proof

Standalone client:

```bash
python3 scripts/julia_domain_adapter_client.py \
  --base-url http://127.0.0.1:8000 \
  --operation market.snapshot \
  --trade-date 2026-08-26 \
  --correlation-id corr-standalone-001
```

The client uses only Python stdlib modules and imports no Julia Core or ai_theme_app packages.

Curl equivalent:

```bash
curl -sS http://127.0.0.1:8000/adapter/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "operation":"market.snapshot",
    "arguments":{"trade_date":"2026-08-26"},
    "correlation_id":"corr-curl-001",
    "idempotency_key":"idem-curl-001",
    "requested_at":"2026-08-26T10:00:00+08:00",
    "schema_version":"1.0",
    "trace_metadata":{}
  }'
```

## Authentication boundary

HTTP/API authentication, when added later, is not Julia AuthorizationDecision.

Provider status maps to ToolResult semantics. It does not map to Julia authorization.

## Scope audit

AT-R4 does not add:

- MCP registration
- Julia Core import
- Julia canonical ToolResult/Evidence/Trace classes
- NLP/semantic routing
- LLM operation selection
- write/trading operations
- market algorithm changes
- sibling-repository import

## Gate recommendation

AT-R4 should pass if transport tests prove round-trip preservation for success, partial, unavailable, error, and stale responses, plus health/readiness separation and standalone client independence.
