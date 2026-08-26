# AT-R8 ai-theme-adapter/1.0 Freeze Candidate

Status: AT-R8 freeze candidate package. This document is not a normative final freeze declaration; it records the pre-freeze audit disposition and package evidence for Owner review.

## 1. Protocol Identity

- Protocol identity: `ai-theme-adapter/1.0`
- Provider owner: `ai_theme_app`
- Consumer target: future Julia Core provider client
- Transport: HTTP/JSON
- Required operations:
  - `market.snapshot`
  - `market.alerts`
- Non-goals:
  - Julia Core canonical classes
  - Julia AuthorizationDecision
  - Julia ToolResult/Evidence/Trace ownership
  - Context OS
  - MCP
  - natural-language routing
  - write/trading actions

## 2. Implementation Identity

- Baseline SHA: `2b9058056d36046c0e0ec8686757829c9325bc57`
- Freeze-candidate implementation SHA: `067060d5e93478374981e6e4d12273f75c3ce0a6`
- S3 frozen adapter HEAD: `55d92281ddbf93c717f35032d359dcd4bf2f5373`
- S4 live E2E repository mutation: none

## 3. Frozen Schema

- Schema path: `docs/integration/JULIA_ADAPTER_SCHEMA_v1.json`
- SHA-256: `baf4d21efd2681009d3eeab899e7320624c05fe6397fa4aa4ef713f009451497`
- Schema change required by S4 readiness audit: no

## 4. S3 Golden Fixture Manifest

Manifest path: `docs/integration/JULIA_ADAPTER_S3_GOLDEN_FIXTURE_MANIFEST_v1.json`

| Fixture | SHA-256 | Purpose |
| --- | --- | --- |
| `adapter_request_market_snapshot.json` | `ac208bf336dfd7605415455f4ef961978ff0aa06fe946a4f9bd2c2c1d5e92315` | canonical snapshot request example |
| `adapter_request_market_alerts.json` | `bb5737d76d55d16021d608b9b5ffeea7ace79a2d4a37534c4b2078bae6efd2b8` | additive alerts request handoff example |
| `market_alerts_empty.json` | `1fa5cb20203bdb865fd89714c898a9f5e9ce496e12184c21ed7963e044220bb8` | legitimate zero alerts: `success + empty` |
| `market_alerts_success.json` | `2c60b7c4d2b386b95499bd0439c0bed091a7d9a275a4ef19b63ae3f7e109dcd6` | alerts happy path |
| `market_snapshot_empty.json` | `2436d6905c5db66e92cd5c7e9caede23545b2b175adbab4845599a4d3680c9ce` | legitimate zero snapshot observations |
| `market_snapshot_error.json` | `e7692d3d1d0dc309ef6d5889d984e88ecef364450ba9883586e0311cc06f329e` | internal/provider execution error |
| `market_snapshot_partial.json` | `aa1115cd6bbf9dd5dc38fb63c155234ff8d5695af0769698ce5bc4860f35cf7c` | partial source failure preserving successful material |
| `market_snapshot_stale.json` | `c86b5c1475776658dddb1bf32bee1d171b4031aaaa7fac4802a74df0e97386c7` | explicit stale data semantics |
| `market_snapshot_success.json` | `270384c2a95747dfac05b8c3eb4ad6a43230f75db0d1f69a9772b5a6ca8fdfdf` | snapshot happy path |
| `market_snapshot_unavailable.json` | `dc8959dfaca54fe5dd557bcf7c35006a7b49d2dfc64b7f10aa611b04e80784f4` | required dependency/source unavailable |

## 5. Operation Catalog

| Operation | Required v1 | Side effect policy | Dispatch |
| --- | --- | --- | --- |
| `market.snapshot` | yes | read-only | exact operation ID only |
| `market.alerts` | yes | read-only | exact operation ID only |

Forbidden in v1: semantic intent resolution, answer-user operations, MCP-only operations, and write/trading operations.

## 6. Status and Data State Semantics

`status` is primary. `data_state` is interpreted only together with `status`.

| Provider state | Meaning |
| --- | --- |
| `success + normal` | operation completed and useful current payload exists |
| `success + empty` | operation completed and positively established legitimate zero business data |
| `success + stale` | operation completed but available data is stale |
| `partial + normal/stale` | useful material exists and explicit non-critical failures are preserved |
| `unavailable + empty` | required usable dependency/source is unavailable; payload absence is not business emptiness |
| `error + empty` | request/adapter/provider/parsing-contract failure; payload absence is not business emptiness |

Hard invariants:

- `UNAVAILABLE != DENIED`
- `ERROR != EMPTY`
- `PARTIAL != SUCCESS`
- `STALE != FRESH`
- provider/dependency failure must not become `success + empty`

## 7. Error Catalog

- `INVALID_ARGUMENT`
- `OPERATION_NOT_SUPPORTED`
- `UPSTREAM_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `SCHEMA_MISMATCH`
- `INTERNAL_ERROR`

All failures are represented as provider-native `SourceFailure` records and may include retryability and redacted diagnostic details.

## 8. Provenance and Julia Mapping

| Provider-native object | Future Julia mapping | Ownership note |
| --- | --- | --- |
| `DomainObservationEnvelope.status/data_state/payload` | ToolResult semantics | Provider status is not Julia AuthorizationDecision |
| `SourceRecord` | C-12 Evidence candidate | SourceRecord is not Julia Evidence |
| `SourceFailure` | ToolResult degradation/failure details | Failure reason must remain explicit |
| `correlation_id/provider_request_id/trace_metadata` | Trace correlation metadata | ai_theme treats Julia trace metadata as opaque |

## 9. Timeout Semantics

HTTP execute wraps adapter execution in a configurable timeout:

- config: `JULIA_ADAPTER_EXECUTE_TIMEOUT_SECONDS`
- timeout result: structured `DomainObservationEnvelope`
- status: `unavailable`
- data_state: `empty`
- failure code: `UPSTREAM_TIMEOUT`
- retryable: `true`

Timeout is a provider/domain unavailability result, not a generic transport failure.

## 10. Health and Readiness Semantics

### 10.1 `/adapter/v1/health`

`/health` is process-level health. It means the HTTP route and contract module can respond.

`HealthReport.ready` in `/health` means the health endpoint itself is serving from a live process. It is not an operation-readiness assertion and must not be used as a substitute for `/ready`.

### 10.2 `/adapter/v1/ready`

`/ready` is lightweight provider dependency readiness. It checks that required provider infrastructure is configured/present enough to attempt operations without executing full market queries.

Current readiness scope:

| Dependency | Operation | Readiness check | Does `/ready` require dated business data? |
| --- | --- | --- | --- |
| database/gateway pool | `market.snapshot` | gateway pool present, injected adapter present, or database not required by config | no |
| Redis | deployment-specific | only required if `JULIA_ADAPTER_REDIS_REQUIRED=true` | no |
| analyst workbench store | `market.alerts` | configured base directory exists | no |

### 10.3 S4 Readiness Audit Disposition

Observed S4 live state:

- `/ready` returned `ready=true`.
- `market.snapshot` returned `unavailable + empty` with `no_data_source_available`.
- `market.alerts` returned `unavailable + empty` because dated `session.json` was missing.

Disposition: contract-correct; documentation clarified in this AT-R8 package.

Reason:

- The missing snapshot/export data and missing dated workbench `session.json` are operation-specific data availability/source-state outcomes for a concrete request date.
- `/ready` intentionally does not execute full market queries and does not prove that every requested trade date has source material.
- `/ready=true` promises that configured provider infrastructure is present enough to attempt execution, not that each operation will return `success`.
- A real operation may truthfully return `unavailable`, `partial`, or `error` after `/ready=true` when dated data/source material is absent, invalid, stale, or unavailable.

No schema or field removal is required.

## 11. Deployment / Configuration Model

Environment variables:

| Variable | Purpose |
| --- | --- |
| `AI_THEME_APP_ROOT` | portable app root override |
| `JULIA_ADAPTER_WORKBENCH_BASE_DIR` | analyst workbench base directory |
| `JULIA_ADAPTER_EXECUTE_TIMEOUT_SECONDS` | execute timeout |
| `JULIA_ADAPTER_MAX_REQUEST_BYTES` | request payload bound |
| `JULIA_ADAPTER_MAX_RESPONSE_BYTES` | response payload bound |
| `JULIA_ADAPTER_DATABASE_REQUIRED` | readiness requirement for snapshot DB/gateway |
| `JULIA_ADAPTER_REDIS_REQUIRED` | deployment-specific Redis readiness requirement |
| `REDIS_URL` | Redis URL, redacted in DTO diagnostics |

HTTP auth is not included in v1 and remains a deployment limitation unless an explicit deployment requirement is added.

## 12. AT-R5 Fault Matrix Evidence

Command:

```bash
./.venv/bin/pytest tests/julia_domain_adapter/ -q
```

AT-R5 result at acceptance time: `59 passed`.

The 18-case matrix covered snapshot/alerts success, optional failure, required failure, provider exception, exception-not-empty-success, legitimate empty, stale, timeout, unsupported operation, malformed arguments, correlation round-trip, unsupported schema version, health/readiness, secret redaction, deterministic dispatch, no write side effects, and golden fixture compatibility.

## 13. S4 Live E2E Evidence

Real service command:

```bash
cd /Users/admin/Desktop/ai_theme_app
SPS_ENABLE_W2S_ALERT_LOOP=false \
SPS_AUTO_START_REALTIME_STACK=false \
SPS_ENABLE_JYHF_MARKET_AUTO_START=false \
SPS_ENABLE_STOCK_MATCH_ENGINE=false \
JULIA_ADAPTER_DATABASE_REQUIRED=false \
JULIA_ADAPTER_REDIS_REQUIRED=false \
JULIA_ADAPTER_EXECUTE_TIMEOUT_SECONDS=5 \
JULIA_ADAPTER_MAX_REQUEST_BYTES=262144 \
JULIA_ADAPTER_MAX_RESPONSE_BYTES=1048576 \
./.venv/bin/uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 18180 --log-level info
```

Observed live results:

| Call | Result |
| --- | --- |
| `GET /adapter/v1/health` | `ok=true`, `ready=true`, `status=ok` |
| `GET /adapter/v1/ready` | `ok=true`, `ready=true`, `status=ready` |
| `POST market.snapshot` | `status=unavailable`, `data_state=empty`, `UPSTREAM_UNAVAILABLE`, retryable |
| `POST market.alerts` | `status=unavailable`, `data_state=empty`, `UPSTREAM_UNAVAILABLE`, retryable |
| process timeout harness | `status=unavailable`, `UPSTREAM_TIMEOUT`, retryable |
| oversized response harness | `status=error`, bounded `INTERNAL_ERROR` envelope |

Correlation was observed from client request to server structured log to provider response.

Standalone client was executed from `/tmp` with Julia Core absent and no sibling-repository stitching.

## 14. Non-adapter Startup Observations

S4 startup surfaced existing app-level Redis cleanup warnings:

- `Redis.execute_command was never awaited`
- `ZOMBIE_CONSUMER_CLEANUP`

These are not part of the adapter contract and did not alter frozen adapter semantics. They should remain tracked as non-adapter operational observations if production deployment hardening expands beyond this lane.

## 15. Current Regression Evidence

Current full adapter regression:

```text
67 passed
```

Latest observed command:

```bash
./.venv/bin/pytest tests/julia_domain_adapter/ -q
```

Latest observed result:

```text
67 passed in 1.55s
```

## 16. Compatibility and Change Control

The following require cross-repo compatibility review before modification:

- schema shape or required fields
- operation catalog
- status/data_state semantics
- SourceRecord semantics
- SourceFailure/error-code semantics
- golden response fixture schema/semantics
- mapping assumptions into Julia ToolResult / C-12 Evidence / Trace

Additive examples may be added only when they do not change schema or response semantics.

## 17. Known Limitations

1. `/ready=true` does not guarantee that a given trade date has snapshot/workbench business data.
2. v1 does not include HTTP authentication.
3. v1 does not include MCP transport.
4. v1 required operations are limited to `market.snapshot` and `market.alerts`.
5. Theme/symbol context operations remain out of frozen required v1 due prior hard-coded path risk.
6. S4 live environment returned unavailable business outcomes; this is valid truth-preserving behavior, not a business-success demonstration.

## 18. Freeze Candidate Recommendation

Recommendation: `AT-R8 FREEZE CANDIDATE READY FOR OWNER REVIEW`.

Normative final freeze should remain Owner-controlled.
