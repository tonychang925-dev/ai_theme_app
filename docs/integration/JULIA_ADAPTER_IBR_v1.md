# Julia Domain Adapter IBR v1.0

Status: AT-R1 provider-native wire contract. This is not a Julia Core canonical schema.

## Ownership

ai_theme_app owns provider-native market-domain payloads, source records, freshness, and source/dependency failures.
Julia Core owns cognition, authorization, CapabilityRequest, CapabilityCall, ToolResult, Evidence, Trace, Context OS, identity, memory, persona, and relationship state.

## Supported Operations

Required v1 operations:

- `market.snapshot`
- `market.alerts`

Forbidden in v1:

- natural-language intent routing
- `market.intent.resolve`
- answer composition for Julia
- Julia authorization
- Julia ToolResult / Evidence / Trace classes
- trading or write operations
- MCP transport

## AdapterRequest

```json
{
  "operation": "market.snapshot",
  "arguments": {},
  "correlation_id": "corr-20260826-001",
  "idempotency_key": "idem-20260826-001",
  "requested_at": "2026-08-26T10:00:00+08:00",
  "schema_version": "1.0",
  "trace_metadata": {
    "turn_id": "opaque-turn-id",
    "capability_request_id": "opaque-capability-request-id"
  }
}
```

Rules:

- `operation` is required and must be an exact operation ID.
- `arguments` must be an object.
- `trace_metadata` is opaque correlation metadata; ai_theme_app must not derive Julia semantic state from it.
- Unsupported `schema_version` fails validation.

## DomainObservationEnvelope

```json
{
  "operation": "market.snapshot",
  "status": "success",
  "data_state": "normal",
  "correlation_id": "corr-20260826-001",
  "provider_request_id": "ai-theme-req-001",
  "observed_at": "2026-08-26T15:30:00+08:00",
  "payload": {},
  "source_records": [],
  "failures": [],
  "diagnostics": {},
  "schema_version": "1.0"
}
```

## Status Semantics

- `success`: operation completed and there are no source/dependency failures.
- `partial`: useful payload exists, but one or more non-critical sources/dependencies failed. Failures must be explicit.
- `unavailable`: a required dependency is unavailable and meaningful execution cannot complete.
- `error`: request validation or internal/provider execution failed.

Hard invariant:

```text
provider/dependency exception MUST NOT become success + empty payload
```

## Data State Semantics

- `normal`: useful current data.
- `empty`: valid execution with no observations/results.
- `stale`: useful data exists but is older than the freshness policy.

Valid empty example:

```text
status=success
data_state=empty
failures=[]
```

Dependency failure example:

```text
status=unavailable or error
data_state=empty
failures=[...]
```

## SourceRecord

Provider-native source material. Julia may map it to C-12 Evidence later, but it is not Evidence.

Fields:

- `source_type`
- `source_name`
- `source_ref`
- `as_of`
- `observed_at`
- `freshness`
- `status`
- `provenance`
- optional `failure`

## SourceFailure

Fields:

- `code`
- `message`
- `source_name`
- `retryable`
- `details`

Error codes:

- `INVALID_ARGUMENT`
- `OPERATION_NOT_SUPPORTED`
- `UPSTREAM_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `SCHEMA_MISMATCH`
- `INTERNAL_ERROR`

Diagnostics and failure messages must redact password/token/secret/API-key-like values.

## Health and Readiness

Health and readiness are distinct:

- health: process can respond.
- readiness: required provider dependencies are available for meaningful adapter execution.

DB unavailable may be health-ok but readiness-false.

## Julia Mapping Guidance

Provider envelope fields map to Julia-owned concepts as follows:

- `status` + `payload` -> Julia ToolResult
- `source_records` -> Julia C-12 Evidence
- `correlation_id` / `provider_request_id` -> Julia Trace

These map to Julia objects; they are not Julia canonical objects.
