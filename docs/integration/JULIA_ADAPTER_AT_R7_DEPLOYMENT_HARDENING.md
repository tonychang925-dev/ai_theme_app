# AT-R7 Deployment Hardening

Status: AT-R7 deployment/portability hardening for `ai-theme-adapter/1.0`.

## Configuration Model

New config module:

```text
stock_processing_service/ports/julia_domain_adapter_config.py
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `AI_THEME_APP_ROOT` | repository root derived from module path | root for portable default paths |
| `JULIA_ADAPTER_WORKBENCH_BASE_DIR` | `${AI_THEME_APP_ROOT}/tmp/analyst_workbench` | workbench store path |
| `JULIA_ADAPTER_EXECUTE_TIMEOUT_SECONDS` | `5.0` | HTTP execute timeout |
| `JULIA_ADAPTER_MAX_REQUEST_BYTES` | `262144` | request body limit |
| `JULIA_ADAPTER_MAX_RESPONSE_BYTES` | `1048576` | response body limit |
| `JULIA_ADAPTER_DATABASE_REQUIRED` | `true` | readiness requirement for market.snapshot |
| `JULIA_ADAPTER_REDIS_REQUIRED` | `false` | deployment-specific Redis readiness requirement |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis config validation when required |

## Path Portability Audit

Adapter runtime paths are resolved from environment or module location. No source-path modification is required when working directory changes.

- No hard-coded `/Users/admin/...` adapter runtime path.
- No sibling repository import.
- No runtime `sys.path` mutation in adapter package, HTTP port, or standalone client.

## Alternate-CWD / Startup Proof

AT-R7 test `TC-AT-R7-002` imports the config module from an alternate cwd using repository `PYTHONPATH`, proving startup/import does not depend on process cwd.

## DB / Redis Readiness Behavior

`GET /adapter/v1/health` remains process-level health.

`GET /adapter/v1/ready` now reports:

- database/gateway readiness for `market.snapshot`;
- analyst workbench store readiness for `market.alerts`;
- Redis configuration readiness when `JULIA_ADAPTER_REDIS_REQUIRED=true`.

`/ready` does not execute full market queries.

## Timeout / Cancellation Behavior

`POST /adapter/v1/execute` wraps adapter execution in `asyncio.wait_for`.

Timeout result:

```text
status=unavailable
data_state=empty
failure.code=UPSTREAM_TIMEOUT
failure.retryable=true
```

Cancellation is logged and re-raised, not swallowed.

## Payload Limit Behavior

- Request body exceeding `JULIA_ADAPTER_MAX_REQUEST_BYTES` returns HTTP 413.
- Response body exceeding `JULIA_ADAPTER_MAX_RESPONSE_BYTES` returns a structured `DomainObservationEnvelope` with `status=error`, preserving correlation/provider IDs.

## Logging / Secret Redaction

HTTP execute emits structured start/end log lines with operation, correlation_id, idempotency_key, status, data_state, and failure_count.

Secret redaction remains enforced by `SourceFailure` / DTO serialization.

## Invariant Audit

Preserved:

- frozen schema unchanged;
- S3 frozen response fixture hashes unchanged;
- operation catalog unchanged;
- provider status semantics unchanged;
- no Julia Core imports;
- no sibling sys.path stitching;
- no NLP/semantic routing;
- no write/trading behavior.

## Known Limitations

- HTTP authentication remains out of scope and is not implemented.
- Readiness is credible configuration/dependency presence validation, not a full market query.
- Live provider E2E remains S4 and is not part of AT-R7.

## Gate Recommendation

AT-R7 recommendation: **PASS / READY FOR GATE REVIEW**.
