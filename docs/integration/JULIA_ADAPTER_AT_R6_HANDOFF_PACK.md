# AT-R6 Julia Core Integration Handoff Pack

Status: AT-R6 handoff artifact for `ai-theme-adapter/1.0`.

Frozen adapter HEAD: `55d92281ddbf93c717f35032d359dcd4bf2f5373`
Frozen schema SHA-256: `baf4d21efd2681009d3eeab899e7320624c05fe6397fa4aa4ef713f009451497`

This pack is for future Julia Core integration. It does not change adapter schema, response fixture semantics, domain behavior, MCP, or Julia Core code.

## 1. Adapter Identity

- Adapter identity: `ai-theme-adapter/1.0`
- Provider: `ai_theme_app`
- Contract type: provider-native HTTP/JSON domain intelligence boundary
- Required operations:
  - `market.snapshot`
  - `market.alerts`
- Optional future operations are not frozen in v1.

## 2. Handoff Artifact List

| Artifact | Purpose |
|---|---|
| `docs/integration/JULIA_ADAPTER_SCHEMA_v1.json` | Frozen JSON Schema |
| `docs/integration/JULIA_ADAPTER_IBR_v1.md` | Integration Boundary Record |
| `docs/integration/JULIA_ADAPTER_OPERATION_CATALOG_v1.md` | Operation catalog |
| `docs/integration/JULIA_ADAPTER_S2_CROSS_CODEX_MAPPING_REVIEW.md` | Provider-to-Julia semantic mapping review |
| `docs/integration/JULIA_ADAPTER_AT_R3_DEGRADATION_PROVENANCE.md` | Degradation/provenance semantics |
| `docs/integration/JULIA_ADAPTER_AT_R4_TRANSPORT.md` | HTTP transport contract |
| `docs/integration/JULIA_ADAPTER_AT_R5_CONTRACT_FAULT_MATRIX.md` | 18-case fault matrix |
| `docs/integration/JULIA_ADAPTER_S3_GOLDEN_FIXTURE_MANIFEST_v1.json` | Fixture SHA-256 manifest |
| `docs/integration/fixtures/julia_domain_adapter/*.json` | Frozen response fixtures and request examples |
| `scripts/julia_domain_adapter_client.py` | Standalone stdlib HTTP client |

## 3. Frozen JSON Schema

Path:

```text
docs/integration/JULIA_ADAPTER_SCHEMA_v1.json
```

SHA-256:

```text
baf4d21efd2681009d3eeab899e7320624c05fe6397fa4aa4ef713f009451497
```

Schema change rule:

```text
Do not modify frozen schema without reopening cross-repo compatibility review.
```

## 4. S3 Golden Fixture Inventory

Canonical manifest:

```text
docs/integration/JULIA_ADAPTER_S3_GOLDEN_FIXTURE_MANIFEST_v1.json
```

Golden response fixtures are compatibility artifacts. Request examples are handoff examples.

| Fixture | Kind | SHA-256 | Semantic purpose |
|---|---|---|---|
| `adapter_request_market_snapshot.json` | request example | `ac208bf336dfd7605415455f4ef961978ff0aa06fe946a4f9bd2c2c1d5e92315` | Example market.snapshot AdapterRequest |
| `adapter_request_market_alerts.json` | additive request example | `bb5737d76d55d16021d608b9b5ffeea7ace79a2d4a37534c4b2078bae6efd2b8` | Additive AT-R6 market.alerts AdapterRequest example; no response semantic change |
| `market_alerts_empty.json` | golden response | `1fa5cb20203bdb865fd89714c898a9f5e9ce496e12184c21ed7963e044220bb8` | Valid zero alerts: `success + empty` |
| `market_alerts_success.json` | golden response | `2c60b7c4d2b386b95499bd0439c0bed091a7d9a275a4ef19b63ae3f7e109dcd6` | Matching high-attention alert: `success + normal` |
| `market_snapshot_empty.json` | golden response | `2436d6905c5db66e92cd5c7e9caede23545b2b175adbab4845599a4d3680c9ce` | Legitimate zero snapshot rows: `success + empty` |
| `market_snapshot_error.json` | golden response | `e7692d3d1d0dc309ef6d5889d984e88ecef364450ba9883586e0311cc06f329e` | Provider/internal failure: `error + empty` |
| `market_snapshot_partial.json` | golden response | `aa1115cd6bbf9dd5dc38fb63c155234ff8d5695af0769698ce5bc4860f35cf7c` | Useful payload plus failed source: `partial + normal` |
| `market_snapshot_stale.json` | golden response | `c86b5c1475776658dddb1bf32bee1d171b4031aaaa7fac4802a74df0e97386c7` | Stale usable data: `success + stale` |
| `market_snapshot_success.json` | golden response | `270384c2a95747dfac05b8c3eb4ad6a43230f75db0d1f69a9772b5a6ca8fdfdf` | Normal snapshot: `success + normal` |
| `market_snapshot_unavailable.json` | golden response | `dc8959dfaca54fe5dd557bcf7c35006a7b49d2dfc64b7f10aa611b04e80784f4` | Required dependency unavailable: `unavailable + empty` |

## 5. Operation Catalog

### `market.snapshot`

Purpose: return read-only market-domain facts and summary context.

Input arguments:

- `trade_date` optional ISO date string.
- future provider-native freshness arguments may be additive only if schema-compatible.

Provider result:

- `DomainObservationEnvelope.operation = market.snapshot`
- `payload.market_state`
- `payload.themes`
- `payload.quality`
- `source_records`
- `failures`

### `market.alerts`

Purpose: return read-only high-importance provider-native claims/alerts.

Input arguments:

- `trade_date` optional ISO date string.
- `min_attention_level` optional: `CRITICAL | HIGH | MEDIUM | LOW`.

Provider result:

- `DomainObservationEnvelope.operation = market.alerts`
- `payload.alerts`
- `payload.claim_count`
- `payload.min_attention_level`
- `source_records`
- `failures`

## 6. Status/Data-State Semantics

Legal matrix:

| status | legal data_state | semantics |
|---|---|---|
| `success` | `normal` | successful execution with usable current payload |
| `success` | `empty` | successful execution with legitimate zero result |
| `success` | `stale` | successful execution with usable stale payload |
| `partial` | `normal` | useful current payload plus explicit non-critical failures |
| `partial` | `stale` | useful stale payload plus explicit non-critical failures |
| `unavailable` | `empty` | required dependency/source unavailable; no meaningful payload |
| `error` | `empty` | validation/internal/provider execution failure; no meaningful payload |

Hard interpretation order:

```text
status first, then data_state
```

Invariants:

- `UNAVAILABLE != DENIED`
- `ERROR != EMPTY`
- `PARTIAL != SUCCESS`
- `STALE != FRESH`

## 7. Mapping Guide for Julia Core

| Provider-native field | Future Julia Core mapping | Rule |
|---|---|---|
| `status` | ToolResult status/degradation semantic | Do not map to AuthorizationDecision |
| `data_state` | ToolResult data state / Context OS freshness hint | Interpret jointly with status |
| `payload` | ToolResult payload | Julia decides model-visible interpretation |
| `source_records` | C-12 Evidence candidates | SourceRecord maps to Evidence; it is not Evidence |
| `failures` | ToolResult degradation/failure metadata | Preserve codes/details/retryable |
| `correlation_id` | Trace correlation key | Opaque round-trip metadata |
| `provider_request_id` | provider invocation span/id | Distinct from Julia CapabilityCall ID unless mapped by Core |
| `provenance` | Evidence provenance metadata | Preserve provider-native structure |
| `freshness` | Evidence/Context OS freshness annotation | Do not convert stale to fresh |

## 8. Error-Code Catalog

- `INVALID_ARGUMENT`: malformed/invalid provider request arguments.
- `OPERATION_NOT_SUPPORTED`: operation is outside frozen v1 catalog.
- `UPSTREAM_TIMEOUT`: provider dependency timed out.
- `UPSTREAM_UNAVAILABLE`: required/optional upstream source unavailable.
- `SCHEMA_MISMATCH`: source or wire payload violates expected schema/parse contract.
- `INTERNAL_ERROR`: adapter/provider internal execution failure.

## 9. Timeout Semantics

Timeout maps to:

```text
status = unavailable
data_state = empty
failure.code = UPSTREAM_TIMEOUT
failure.retryable = true
```

Timeout must not become `success + empty`.

## 10. HTTP Contract

### Execute

```text
POST /adapter/v1/execute
```

Input: AdapterRequest JSON.
Output: DomainObservationEnvelope JSON.

Provider/domain failure represented as DomainObservationEnvelope remains HTTP 200, because the transport succeeded and the provider result is structured.

Malformed HTTP/request DTO returns HTTP 400.

### Health

```text
GET /adapter/v1/health
```

Process/route health only.

### Ready

```text
GET /adapter/v1/ready
```

Dependency readiness. May return `ready=false` while health is true.

## 11. Standalone Client Instructions

```bash
python3 scripts/julia_domain_adapter_client.py \
  --base-url http://127.0.0.1:8000 \
  --operation market.snapshot \
  --trade-date 2026-08-26 \
  --correlation-id corr-standalone-001
```

The standalone client imports only Python stdlib and is Julia-independent.

## 12. Compatibility / Change Control

Frozen without compatibility review:

- response fixture schema/semantics;
- JSON Schema v1.0;
- operation IDs `market.snapshot`, `market.alerts`;
- status/data_state matrix;
- SourceRecord/SourceFailure field meanings.

Allowed additive changes without reopening schema only if tests prove compatibility:

- additional request examples;
- new docs;
- new tests;
- additive diagnostics fields that do not change existing semantics.

Requires cross-repo compatibility review:

- schema field addition/removal/rename;
- status/data_state meaning change;
- response fixture semantic/hash change;
- new required operation;
- changing SourceRecord into Julia Evidence or ToolResult-shaped output;
- transport behavior that changes provider status semantics.

## 13. Known Limitations

1. Optional operations `market.theme.details` and `market.symbol.context` remain outside frozen required v1.
2. Current HTTP readiness is lightweight and does not execute live market queries.
3. Exact freshness thresholds are not yet policy-rich; current contract preserves `fresh/stale` explicitly.
4. HTTP authentication is not implemented in AT-R6; future auth must not be confused with Julia AuthorizationDecision.
5. Live production E2E against a running service is not part of this handoff pack; current evidence is local contract/transport tests.
6. Repository still has unrelated pre-existing dirty/untracked files recorded by AT-R0; adapter scoped files are clean after each commit.

## 14. AT-R6 Gate Recommendation

Recommendation: **AT-R6 READY FOR GATE REVIEW**.

No schema changes required.
No response fixture semantics changed.
