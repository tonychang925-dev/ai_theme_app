# AT-R5 Contract + Fault Injection Matrix

Status: AT-R5 verification layer. Frozen schema `ai-theme-adapter/1.0` remains unchanged.

## Complete 18-Case Matrix

| # | Case | Test evidence | Expected result |
|---:|---|---|---|
| 1 | snapshot normal success | `TC-AT-R5-001` | `success + normal` |
| 2 | alerts normal success | `TC-AT-R5-002` | `success + normal` |
| 3 | optional source failure -> partial | `TC-AT-R5-003` | `partial` with explicit failure |
| 4 | required dependency failure -> unavailable | `TC-AT-R5-004` | `unavailable + empty` |
| 5 | provider exception -> error | `TC-AT-R5-005` | `error + empty` |
| 6 | provider exception != success + empty | `TC-AT-R5-006` | never fabricated empty success |
| 7 | legitimate no data -> success + empty | `TC-AT-R5-007` | `success + empty` only after source success |
| 8 | stale source -> stale explicit | `TC-AT-R5-008` | `data_state=stale`, freshness stale |
| 9 | upstream timeout | `TC-AT-R5-009` | `UPSTREAM_TIMEOUT` |
| 10 | unsupported operation | `TC-AT-R5-010` | validation rejection |
| 11 | malformed arguments | `TC-AT-R5-011` | validation rejection |
| 12 | correlation metadata round-trip | `TC-AT-R5-012` | request round-trip exact |
| 13 | unsupported schema version | `TC-AT-R5-013` | validation rejection |
| 14 | health vs readiness | `TC-AT-R5-014` | health true; readiness may be false |
| 15 | secret redaction | `TC-AT-R5-015` | token/password redacted |
| 16 | deterministic dispatch / no NLP routing | `TC-AT-R5-016` | no NLP routing surface |
| 17 | no write side effects | `TC-AT-R5-017` | file set unchanged |
| 18 | golden fixture compatibility | `TC-AT-R5-018` | all fixtures parse/round-trip |

## HTTP Fault Injection Results

| HTTP case | Test evidence | Result |
|---|---|---|
| provider/domain failure remains structured envelope | `test_tc_at_r5_http_provider_failure_remains_structured_envelope` | HTTP 200 with `DomainObservationEnvelope.status=error`, not generic transport failure |
| partial response preserves successful material and failures | `test_tc_at_r5_http_partial_preserves_success_material_and_failures` | payload/source success records and failures survive JSON |
| readiness may fail while health succeeds | `TC-AT-R5-014` | `health.ready=true`, `ready.ready=false` |
| serialization preserves status/data_state/source_records/failures/freshness/correlation | `test_tc_at_r5_http_serialization_preserves_correlation_and_freshness` | round-trip exact fields |

## Golden Fixtures

- `adapter_request_market_snapshot.json`
- `market_alerts_empty.json`
- `market_alerts_success.json`
- `market_snapshot_empty.json`
- `market_snapshot_error.json`
- `market_snapshot_partial.json`
- `market_snapshot_stale.json`
- `market_snapshot_success.json`
- `market_snapshot_unavailable.json`

## Proof Statements

- Provider/domain failure remains provider data when represented as `DomainObservationEnvelope`; the HTTP layer does not turn it into generic transport failure.
- Partial responses preserve both successful material and failures.
- Required dependency failure can produce `health=true`, `ready=false`.
- `status`, `data_state`, `source_records`, `failures`, `freshness`, `correlation_id`, and `provider_request_id` survive HTTP serialization.
- Standalone client imports only Python stdlib and does not import Julia Core or ai_theme_app packages.
- No write side effects are observed in the adapter facade read path test.

## Schema Change Assessment

Schema changed: **No**.

The AT-R5 test suite includes a SHA-256 guard for `docs/integration/JULIA_ADAPTER_SCHEMA_v1.json`.

## Gate Recommendation

AT-R5 recommendation: **PASS / READY FOR GATE REVIEW**.

S3 Golden Fixture Freeze remains separate and should not be considered closed by AT-R5.
