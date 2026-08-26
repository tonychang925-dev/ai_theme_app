# S2 Cross-Codex Contract Mapping Review

Status: S2 mapping review after AT-R3. AT-R4 transport remains HOLD.

Repository: `ai_theme_app`
Branch: `feature/ai-theme-julia-domain-adapter-v1`
Input HEAD: `597c2368e97783149364d5e7302be3347b2db859`

This document explains how the frozen provider-native ai_theme_app adapter semantics can map losslessly into future Julia Core semantics without redefining Julia canonical objects.

## 1. Ownership Boundary

Provider-native ai_theme_app owns:

- market-domain payload material;
- provider operation status;
- `data_state`;
- source/dependency failure details;
- provider-native `SourceRecord`;
- provider freshness/provenance;
- provider request correlation IDs.

Julia Core owns:

- cognition and tool-use decision;
- authorization;
- canonical CapabilityRequest / CapabilityCall;
- ToolResult;
- C-12 Evidence;
- Trace;
- Context OS projection;
- identity, memory, persona, relationship state.

Critical ownership invariants:

- `SourceRecord` maps to C-12 Evidence.
- `SourceRecord` is not Julia Evidence.
- Provider status maps to ToolResult semantics.
- Provider status is not Julia AuthorizationDecision.
- Correlation metadata maps to Trace.
- ai_theme_app must not interpret Julia trace metadata.

## 2. Complete Provider -> Julia Mapping Table

| Provider state/material | Future Julia target semantic | Lossless mapping rule | Required Julia caution |
|---|---|---|---|
| `success + normal` | ToolResult success with usable payload | Preserve payload; map source_records to Evidence candidates; trace provider_request_id | Do not treat provider success as authorization success; auth already happened upstream |
| `success + empty` | ToolResult success with empty result | Preserve empty payload and explicit empty diagnostics | `EMPTY` means legitimate zero result only because provider status is success |
| `success + stale` | ToolResult success with stale data annotation | Preserve payload; mark ToolResult/source evidence freshness stale | STALE != FRESH; model-visible answer must disclose stale/as_of |
| `partial + normal` | ToolResult partial/degraded success | Preserve successful payload; attach failures; source_records include both success and failed sources | PARTIAL != SUCCESS; do not erase failure while using available facts |
| `partial + stale` | ToolResult partial/degraded stale result | Preserve useful stale payload, source_records, failures | Both partial and stale must survive Context OS projection |
| `unavailable + empty` | ToolResult provider unavailable / no meaningful payload | Preserve failures; no Evidence generated from absent payload except failure evidence/trace | UNAVAILABLE != DENIED and != EMPTY |
| `error + empty` | ToolResult provider error | Preserve failure code/message/details after redaction | ERROR != EMPTY; do not summarize as no market event |
| `source_records[]` | C-12 Evidence candidates / provenance records | For each SourceRecord create Evidence metadata with source_type/name/ref/as_of/observed_at/freshness/status/provenance | SourceRecord is provider-native material, not Julia Evidence class |
| `failures[]` | ToolResult failure diagnostics + trace events | Preserve every SourceFailure code/source_name/retryable/details | Do not collapse all failures into one text blob |
| `correlation_id` | Julia Trace correlation key | Store/propagate as opaque correlation ID | ai_theme_app does not derive semantics from it |
| `provider_request_id` | Julia Trace provider invocation ID | Store as provider-side request span/id | Must not become CapabilityCall ID unless Julia maps it explicitly |
| `provenance` | Evidence provenance metadata | Preserve provider-native structure under mapped Evidence metadata | Do not drop provider-specific provenance fields |
| `freshness` | Evidence/Context OS freshness annotation | Map `fresh`/`stale` without reinterpretation | STALE != FRESH |

## 3. Status/Data-State Invariant Mapping

| Invariant | Provider-side meaning | Julia-side mapping consequence |
|---|---|---|
| `UNAVAILABLE != DENIED` | Source/dependency unavailable, not an authorization decision | Julia must not map provider unavailable to AuthorizationDecision denied |
| `ERROR != EMPTY` | Provider/request/parsing failure, not a valid zero-result | Julia must not tell the model that the market has no alerts/data |
| `PARTIAL != SUCCESS` | Useful material exists but provider knows degradation happened | Julia may use payload, but must preserve degraded status/failures |
| `STALE != FRESH` | Payload exists but is older than policy/request | Julia must preserve `as_of`/freshness and avoid current-data claims |
| `success + empty` only after positive source execution | Legitimate zero observation | Julia may present no result only with status=success evidence |

## 4. Operation-Specific Mapping

### 4.1 `market.snapshot`

Provider source boundary:

```text
DomainIntelligenceAdapter
  -> MarketSnapshotOperation
  -> MarketContextExporter-like export(trade_date)
  -> DomainObservationEnvelope
```

Mapping:

| Provider field | Julia target | Note |
|---|---|---|
| `payload.market_state` | ToolResult payload / Context OS market projection input | Only projected by Julia after ToolResult validation |
| `payload.themes` | ToolResult payload / Evidence-backed market context candidates | Julia decides model-visible interpretation |
| `payload.quality` | ToolResult diagnostics / Evidence confidence adjunct | Provider quality is not Julia confidence by itself |
| `source_records` | C-12 Evidence candidates | Per-source as_of/freshness preserved |
| `failures` | ToolResult failure/degradation metadata | Needed for partial/unavailable/error decisions |
| `raw_status` diagnostics | Trace/provider diagnostics | Useful for debugging source mapping |

### 4.2 `market.alerts`

Provider source boundary:

```text
DomainIntelligenceAdapter
  -> MarketAlertsOperation
  -> workbench session.json + snapshot.json
  -> ReviewSnapshot
  -> ApprovedSnapshotValidator
  -> AnalystIntelligenceExporter
  -> attention_level filter
  -> DomainObservationEnvelope
```

Mapping:

| Provider field | Julia target | Note |
|---|---|---|
| `payload.alerts` | ToolResult payload; possible Evidence-backed observation candidates | These are ai_theme claims, not Julia observations |
| `payload.claim_count` | ToolResult diagnostics | Proves empty alerts can still come from validated source execution |
| `source_records[analyst_workbench_snapshot]` | C-12 Evidence candidate/source provenance | Includes snapshot_ref, snapshot_version/hash via provenance |
| validation failure SourceFailure | ToolResult provider unavailable/error metadata | Julia must not convert to empty alerts |
| `min_attention_level` | ToolResult argument echo/diagnostics | Provider threshold, not Julia authorization |

## 5. Dependency Criticality Table

| Dependency/source | Operation(s) | Criticality | Failure classification | Provider result | Mapping consequence |
|---|---|---|---|---|---|
| `MarketContextExporter` configured object | `market.snapshot` | required, operation-specific | missing exporter | `unavailable + empty`, `UPSTREAM_UNAVAILABLE` | ToolResult provider unavailable; no market snapshot evidence |
| `MarketContextExporter.export(trade_date)` | `market.snapshot` | required, operation-specific | timeout | `unavailable + empty`, `UPSTREAM_TIMEOUT` | retryable provider failure in Trace/ToolResult |
| `MarketContextExporter.export(trade_date)` | `market.snapshot` | required, operation-specific | connection/DB unavailable | `unavailable + empty`, `UPSTREAM_UNAVAILABLE` | dependency unavailable; not authorization denied |
| `MarketContextExporter.export(trade_date)` | `market.snapshot` | required, operation-specific | unexpected exception | `error + empty`, `INTERNAL_ERROR` | provider execution error; not empty market result |
| derived DB source: `theme_cycle_judgement_v2` | `market.snapshot` | usually required for full snapshot, may be optional if other useful payload exists | missing/failed source | `partial + normal/stale` if payload remains, otherwise `unavailable + empty` | preserve successful sources and failed source record |
| derived DB source: `money_flow_enhanced` | `market.snapshot` | optional/source-specific | missing/failed source | `partial + normal/stale` when theme/market payload exists | failure maps to degraded ToolResult, not full success |
| derived DB source: `strong_stock_watch_history` | `market.snapshot` | optional/source-specific | missing/failed source | `partial + normal/stale` when useful payload exists | stock detail absent but market payload preserved |
| Redis/stream source | `market.snapshot` if exporter reports it | optional/source-specific for AT-R3 | unavailable | `partial + normal/stale`, `UPSTREAM_UNAVAILABLE`, `dependency=redis` | Julia sees degraded source; successful DB facts remain usable |
| `tmp/analyst_workbench/{date}/session.json` | `market.alerts` | required, operation-specific | missing/unreadable | `unavailable + empty`, `UPSTREAM_UNAVAILABLE` or `INTERNAL_ERROR` | no legitimate zero alerts claim |
| `tmp/analyst_workbench/{date}/snapshot.json` | `market.alerts` | required, operation-specific | missing | `unavailable + empty`, `UPSTREAM_UNAVAILABLE` | no alert Evidence from absent snapshot |
| `snapshot.json` parse/schema | `market.alerts` | required, operation-specific | JSON/schema mismatch | `error + empty`, `SCHEMA_MISMATCH` | provider parse/contract error; not empty result |
| `ApprovedSnapshotValidator` | `market.alerts` | required, operation-specific | session not approved / snapshot not approved | `unavailable + empty`, `UPSTREAM_UNAVAILABLE` | usable approved source unavailable |
| `ApprovedSnapshotValidator` | `market.alerts` | required, operation-specific | hash/metadata/mode mismatch | `unavailable + empty`, `SCHEMA_MISMATCH` | invalid provider source; no evidence generated from claims |
| `AnalystIntelligenceExporter` | `market.alerts` | required, operation-specific | exception | `error + empty`, `INTERNAL_ERROR` unless connection-like | provider execution failure |
| alert attention filter | `market.alerts` | required, operation-specific | valid zero matching claims | `success + empty` | legitimate zero alerts; source_records prove execution success |

## 6. Source Provenance / Freshness Mapping

Provider `SourceRecord` fields must map without loss:

| SourceRecord field | Julia mapping target | Preservation requirement |
|---|---|---|
| `source_type` | Evidence metadata source category | exact string retained |
| `source_name` | Evidence source name / ToolResult source diagnostics | exact string retained |
| `source_ref` | Evidence reference / audit pointer | exact string retained; can be path/table/ref |
| `as_of` | Evidence as-of timestamp/date | exact value retained |
| `observed_at` | Trace/Evidence observation timestamp | exact value retained |
| `freshness` | Evidence freshness | `stale` must not become `fresh` |
| `status` | Evidence/source health annotation | failed source records stay failed |
| `provenance` | Evidence provenance payload | retained as provider-native object |
| `failure` | ToolResult failure + failed source metadata | retained with code/source/retryable/details |

## 7. Correlation / Trace Mapping

| Provider field | Julia Trace mapping | Rule |
|---|---|---|
| `correlation_id` | cross-system trace correlation ID | Opaque; provider echoes/stores only |
| `idempotency_key` request field | provider_request_id default/seed if used | Opaque provider execution identity |
| `provider_request_id` | provider invocation span/id | Distinct from Julia CapabilityCall ID unless Julia maps it |
| `trace_metadata` request field | Trace metadata echo/log material | ai_theme_app must not interpret for semantic routing, auth, persona, or memory |

## 8. Semantic Gaps

No lossless-mapping blocker found in the current frozen provider wire contract.

Known follow-up gaps for later phases:

1. Transport envelope is not implemented yet; AT-R4 must preserve exactly the same DTO semantics over HTTP JSON.
2. Health/readiness endpoints are not implemented yet; AT-R4/AT-R7 must separate process health from dependency readiness.
3. Optional operations `market.theme.details` and `market.symbol.context` are intentionally outside frozen required v1 until hard-coded path and data freshness issues are hardened.
4. Provider freshness policy is minimal in AT-R3; later phases may define exact staleness thresholds without changing the current `freshness`/`data_state` fields.
5. Julia Core still needs its own mapper from provider envelopes to ToolResult/Evidence/Trace; this document only defines lossless mapping semantics.

## 9. Schema Change Assessment

Schema changes required: **No**.

Reason:

- All required S2 mapping fields already exist in `DomainObservationEnvelope`, `SourceRecord`, `SourceFailure`, `AdapterRequest`, and `HealthReport`.
- Current status/data_state matrix distinguishes success, legitimate empty, stale, partial, unavailable, and error.
- Failures and source records can carry operation-specific dependency details without extending the top-level schema.
- Correlation fields are already present and treated as opaque.

## 10. S2 Recommendation

Recommendation: **S2 PASS**.

Rationale:

- Provider status can map to Julia ToolResult semantics without collapsing authorization or cognition boundaries.
- Source records can map to C-12 Evidence candidates without pretending to be Julia Evidence.
- Failures remain lossless enough for Julia to distinguish unavailable/error/partial/empty.
- Freshness/provenance survive as explicit fields.
- No provider wire contract change is required before AT-R4 transport.

Recommended next gate after owner approval:

```text
AT-R4 — External Transport Boundary
```

AT-R4 must expose the already-frozen semantics without changing them.
