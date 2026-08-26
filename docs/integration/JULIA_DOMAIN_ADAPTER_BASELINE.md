# AT-R0 Baseline & Dependency Audit — Julia Domain Adapter

Status: AT-R0 audit only; no adapter implementation; no production-code changes in this phase.

## 1. Baseline

- Repository: `ai_theme_app`
- AT-R0 branch: `feature/ai-theme-julia-domain-adapter-v1`
- Baseline local HEAD SHA: `2b9058056d36046c0e0ec8686757829c9325bc57`
- Branch before AT-R0 branch creation: `codex/bugfix/workbench-intelligence-binding`
- AT-R0 allowed output file: `docs/integration/JULIA_DOMAIN_ADAPTER_BASELINE.md`

## 2. Dirty State at Baseline

The working tree was already dirty before AT-R0 production work. This audit does not clean, revert, stage, or rely on those files as intentional AT-R0 changes.

Observed categories:

- Modified OCR/image artifacts under `analyst_data/7月15日_images/` and `.m8_ocr_cache/`.
- Modified analyst extraction files:
  - `analyst_data/m8_extractor.py`
  - `analyst_data/test_m8_extractor_reference.py`
- Modified launcher/config-like files:
  - `claude`
  - `claude-deep`
- Modified frontend public market artifacts:
  - `frontend/public/api/analyst-charts/2026-07-17.json`
  - `frontend/public/api/analyst-charts/trend.json`
  - `frontend/public/api/emotion-2026-07-17.json`
- Modified production MCP file already present before AT-R0:
  - `mcp_server/tools/snapshot.py`
- Many untracked artifacts/reports/data files, including analyst recap markdown/JSON/image folders, `CLAUDE.md`, `WAVE5_CONTINUITY_RECOVERY_FREEZE.md`, `golden/*`, scripts, model service files, additional frontend public API artifacts, and tests.

Risk note: because `mcp_server/tools/snapshot.py` was already modified before AT-R0, any later adapter work must first confirm whether that file is intended baseline or outstanding work.

## 3. Current Market/Workbench Entrypoint Map

### 3.1 MCP Server Public Tool Registry

File: `mcp_server/server.py`

Registered read-only tools:

- Fact layer:
  - `market_context_snapshot` → `mcp_server/tools/market_context.py`
- Judgment layer:
  - `market_workbench_review` → `mcp_server/tools/workbench_review.py`
- Research layer:
  - `market_stock_history` → `mcp_server/tools/research_tools.py`
  - `market_stock_auction` → `mcp_server/tools/research_tools.py`
  - `market_theme_constituents` → `mcp_server/tools/research_tools.py`
  - `market_theme_capital` → `mcp_server/tools/research_tools.py`
  - `market_regime_read` → `mcp_server/tools/research_tools.py`
- Intelligence layer:
  - `review_market_snapshot` → `mcp_server/tools/snapshot.py`
  - `list_active_alerts` → `mcp_server/tools/alerts.py`
- Legacy:
  - `query_theme_status`
  - `subscribe_agent_channel`
  - `explain_decision`

The file explicitly marks the tools as read-only and states no `execute_order` / `modify_strategy` support.

### 3.2 Market Snapshot Entrypoints

Primary candidates:

1. `mcp_server/tools/market_context.py::market_context_snapshot(trade_date)`
   - Schema: `market-context.v1`
   - Intended use: dynamic market facts with runtime DB/exporter injection.
   - Dependency: configured `MarketContextExporter` instance.
   - Good adapter candidate for `market.snapshot` fact payload, but status vocabulary must be normalized.

2. `mcp_server/tools/snapshot.py::review_market_snapshot(date)`
   - Schema: `analyst-workbench.intelligence.v1`
   - Intended use: analyst-approved market overview for Julia consumption.
   - Flow: workbench approved snapshot → validator → `AnalystIntelligenceExporter`.
   - Current fallback includes draft and `not_ready`; exception loss must be fixed before provider contract freeze.

3. `stock_processing_service/api_app.py::GET /api/v1/analyst-workspace/{trade_date}`
   - Returns full workspace state for UI.
   - Reads approved snapshot or latest draft or empty not-started document.
   - Persists assembled `review_document.json`; therefore not ideal as v1 read-only adapter source.

4. Workbench services:
   - `stock_processing_service/application/services/analyst_workbench/market_context_exporter.py`
   - `stock_processing_service/application/services/analyst_workbench/intelligence_exporter.py`
   - `stock_processing_service/application/services/analyst_workbench/snapshot_validator.py`
   - `stock_processing_service/application/services/analyst_workbench/snapshot.py`

Recommended v1 source split:

- `market.snapshot` facts: wrap `MarketContextExporter` directly or via `market_context_snapshot`, preserving `missing_sources` as source failures.
- `market.workbench.review` / approved opinion: wrap `ApprovedSnapshotValidator + AnalystIntelligenceExporter`, not the existing `review_market_snapshot` fallback behavior as-is.

### 3.3 Alerts Entrypoint

Primary current entrypoint:

- `mcp_server/tools/alerts.py::list_active_alerts(level="L3")`

Current flow:

1. Resolve current CST trade date.
2. `_alerts_from_workbench(trade_date, level)`.
3. Read `tmp/analyst_workbench/{trade_date}/session.json` and `snapshot.json`.
4. Build `ReviewSnapshot`.
5. Validate via `ApprovedSnapshotValidator`.
6. Export via `AnalystIntelligenceExporter`.
7. Filter `claims` by `attention_level` rank.
8. Return filtered list or `[]`.

Adapter risk: this endpoint collapses multiple states into `[]`:

- no approved snapshot,
- invalid snapshot/session,
- exporter/JSON exception,
- legitimate no matching high-attention claims.

Therefore `list_active_alerts` should not be used directly for adapter v1 without a new status-preserving wrapper.

### 3.4 Theme Information Entrypoints

Primary current entrypoints:

1. `mcp_server/tools/research_tools.py::market_theme_constituents(subject_key, as_of)`
   - Uses historical guard: only `SUPPORTED_AS_OF = "2026-07-14"`.
   - Reads hard-coded local baseline path: `/Users/admin/Desktop/ai_theme_app/golden/2026-07-14/outcomes/baseline_universe.json`.
   - Fetches constituent stock history via `STOCK_DB_DSN` and `stock_daily_snapshot`.
   - Produces peer relative strength, breadth, emerging leaders, and stock metrics.

2. `mcp_server/tools/research_tools.py::market_theme_capital(subject_key, as_of)`
   - Currently returns `status="unavailable"`, `data_status="pending_ingestion"`.

3. `MarketContextExporter` / `DerivedContextReader`
   - Theme facts from DB tables:
     - `theme_cycle_judgement_v2`
     - `money_flow_enhanced`
     - `strong_stock_watch_history`
     - `vw_subject_theme_binding`
     - `stock_abnormal_signal`
   - Produces theme rows, money flows, strong stocks, market state, missing sources.

4. Broader API routes in `stock_processing_service/api_app.py` provide theme lookup and semantic-name resolution, but they are UI/API paths, not a clean adapter boundary.

### 3.5 Symbol Information Entrypoints

Primary current entrypoints:

1. `mcp_server/tools/research_tools.py::market_stock_history(stock_code, as_of, lookback_sessions=5)`
   - Guarded to `2026-07-14` only.
   - Requires `STOCK_DB_DSN`.
   - Reads `stock_daily_snapshot` via `asyncpg`.
   - Produces OHLCV bars, returns, drawdown, volume trend, key-level status, provenance.

2. `mcp_server/tools/research_tools.py::market_stock_auction(stock_code, as_of)`
   - Currently returns unavailable: `auction archive not available for historical dates`.

3. `DerivedContextReader._fetch_strong_stocks(...)`
   - Reads `strong_stock_watch_history` for stock-level watch facts in workbench context.

## 4. Dependency / Call Graph

### 4.1 Workbench Approved Intelligence Path

```text
review_market_snapshot / market_workbench_review / list_active_alerts
  -> tmp/analyst_workbench/{trade_date}/session.json
  -> tmp/analyst_workbench/{trade_date}/snapshot.json
  -> ReviewSnapshot.from_dict
  -> ApprovedSnapshotValidator.validate
  -> AnalystIntelligenceExporter.export
  -> analyst-workbench.intelligence.v1 or analyst-workbench.review.v1 payload
```

Source dependencies:

- Local filesystem workbench store: `tmp/analyst_workbench/{date}/`.
- Session state machine: `WorkbenchStatus` values in `session.py`.
- Snapshot hash/approval metadata via `ReviewSnapshot`.

### 4.2 Workbench Draft / Workspace Path

```text
GET /api/v1/analyst-workspace/{trade_date}
  -> tmp/analyst_workbench/{date}/snapshot.json if present
  -> else tmp/analyst_workbench/{date}/drafts/*.json
  -> _assemble_workspace_review_document
  -> _inject_capital_producer_outputs_async
  -> _apply_recap_completeness_guard for draft
  -> _persist_workspace_review_document
  -> response with review_document / metadata / diagnostics
```

Important: this endpoint persists assembled review documents, so it is not pure read-only.

### 4.3 Market Context / Facts Path

```text
market_context_snapshot
  -> configured MarketContextExporter.export(td)
     -> DerivedContextReader.read(date) if reader exists
        -> DB pool.acquire()
        -> theme_cycle_judgement_v2
        -> post_market_recap_snapshot
        -> money_flow_enhanced
        -> strong_stock_watch_history
        -> vw_subject_theme_binding
        -> stock_abnormal_signal
     -> if no derived themes, fallback to frontend/public/api/analyst-charts/{date}.json
        + frontend/public/api/emotion-{date}.json
     -> market-context.v1 payload
```

### 4.4 Research Tool Path

```text
market_stock_history
  -> as_of guard == 2026-07-14
  -> STOCK_DB_DSN env
  -> asyncpg.connect
  -> stock_daily_snapshot

market_theme_constituents
  -> as_of guard == 2026-07-14
  -> /Users/admin/Desktop/ai_theme_app/golden/2026-07-14/outcomes/baseline_universe.json
  -> _fetch_stock_bars for constituents
  -> STOCK_DB_DSN / stock_daily_snapshot
```

### 4.5 Redis / Streams / Runtime Health

Observed broader runtime dependencies in `stock_processing_service/api_app.py`:

- `REDIS_URL` defaults to localhost.
- Redis readiness/health endpoints:
  - `GET /api/v1/kline-alerts/readiness`
  - `GET /api/v1/w2s-alerts/readiness`
  - `GET /api/v1/runtime/redis-health`
- Streams include kline, W2S, news, events, decision, dead letter.

Current snapshot/alerts/workbench paths do not directly require Redis, but deployment readiness for an HTTP adapter must distinguish process health from DB/Redis/provider readiness.

### 4.6 Model / External API Dependencies

- Draft generation path uses `AnalystWorkbenchGenerateService` and a draft CLI. It may involve generated draft artifacts and model service outside the read adapter.
- `api_app.py` includes DeepSeek/LLM initialization for other routes; this is not part of the read-only adapter candidate.
- External data tokens appear in broader routes, e.g. `TUSHARE_TOKEN`; not required for approved snapshot read but relevant to generation/producer paths.

## 5. Failure and Degradation Behavior

### 5.1 Good Existing Patterns

- `market_context_snapshot` returns explicit `status="unavailable"` when exporter is not configured.
- `market_context_snapshot` catches exporter failure and returns `reason="export_failed"` with diagnostics.
- `ApprovedSnapshotValidator` explicitly rejects unapproved, unpublished, missing, corrupted, or hash-invalid snapshots.
- `market_workbench_review` distinguishes:
  - `opinion_mode="analyst_approved"`
  - `opinion_mode="ai_draft"`
  - `opinion_mode="rejected"`
  - `opinion_mode="not_ready"`
- `DerivedContextReader` preserves partial DB-source absence through `missing_sources` for key tables.

### 5.2 Critical Lossy Patterns

#### P0 — Alerts collapse failure into empty list

`list_active_alerts` catches all exceptions and returns `[]`.

`_alerts_from_workbench` also returns `[]` for missing session/snapshot, invalid validation, or no claims. This makes these cases indistinguishable:

- legitimate empty alerts,
- no approved data,
- DB/file/JSON exception,
- snapshot validation failure.

Adapter invariant violation if used as-is:

```text
dependency/provider exception MUST NOT become success + empty
```

#### P0 — Snapshot fallback can hide approved-path failure

`review_market_snapshot` does:

```text
try _export_from_workbench
except Exception: pass
then draft fallback
then not_ready
```

An approved snapshot read/parse/export failure can become draft or not-ready, losing the required provider failure semantics.

#### P1 — File fallback exceptions are swallowed

`MarketContextExporter._try_chart_emotion` catches all exceptions and returns `None`, so corrupted chart/emotion files can appear as `no_data_source_available` rather than a source failure.

#### P1 — Some diagnostic strings may expose raw exception text

Examples:

- `market_context_snapshot` returns `str(exc)` in diagnostics.
- `MarketContextExporter._error` returns exception string.
- `research_tools` include `DB query failed: {type}: {e}`.

If DSNs, filesystem paths, tokens, or raw driver errors appear in exception text, adapter v1 must redact.

#### P1 — Status vocabulary is inconsistent

Observed statuses/modes include:

- `live`
- `partial`
- `unavailable`
- `draft`
- `not_ready`
- `rejected`
- `analyst_approved`
- `ai_draft`

Adapter v1 must map these into provider-native status/data_state without pretending these are Julia canonical objects.

#### P1 — Generation path can mark degraded as success

`AnalystWorkbenchGenerateService.generate(..., force=True)` can continue after derived-data failure and mark the derived step as success with diagnostics `degraded=True`. This is acceptable for draft generation UX but must not be reused as adapter execution status without preserving original degradation.

### 5.3 Empty / Stale / Partial Handling

- Legitimate empty result is not consistently separated from failure today.
- Stale data is not a first-class status in current MCP outputs.
- Partial exists in several places (`market-context.v1`, research tools), but partial source details are not normalized as source records.
- `DerivedContextReader.missing_sources` is the best current hook for source-level partial degradation.

## 6. Boundary Risks

### 6.1 Natural-Language / Intent Routing

No natural-language operation dispatch was observed in the current MCP tool registry. MCP dispatch is exact tool-name based.

Broader `api_app.py` contains LLM/semantic matching routes and theme-name resolution for other product flows. These should not be included in adapter v1.

Adapter rule for AT-R1+: public API should accept deterministic `operation` IDs, not arbitrary user text.

### 6.2 Hard-Coded Paths

Observed:

- `mcp_server/tools/research_tools.py` hard-codes:
  - `/Users/admin/Desktop/ai_theme_app/golden/2026-07-14`
- Several workbench paths derive project root from `__file__`, then read/write under:
  - `tmp/analyst_workbench/{date}`
  - `frontend/public/api/analyst-charts/{date}.json`
  - `frontend/public/api/emotion-{date}.json`

Adapter v1 must remove hard-coded developer home paths from public execution paths.

### 6.3 Cross-Repo / sys.path Risk

- Current inspected MCP/server/workbench adapter candidates do not import Julia Core.
- Existing tests such as `tests/workbench/test_intelligence_export_e2e.py` insert project root into `sys.path`; this is acceptable for local tests but should not become adapter runtime behavior.
- No sibling `Julia_core` import should be introduced.

### 6.4 Secret Leakage Risk

- Runtime uses env values such as `STOCK_DB_DSN`, `DATABASE_URL`, `REDIS_URL`, `PG_PASSWORD`, `TUSHARE_TOKEN`, `DEEPSEEK_API_KEY` in broader app routes.
- Redis health masks Redis URL only weakly; fallback error endpoint can return raw `REDIS_URL`.
- Adapter diagnostics must redact DSN/token/password-like values and avoid returning raw exception text to Julia.

### 6.5 Write / Trading Side Effects

- MCP tools are declared read-only and no trade execution tool was observed in the MCP registry.
- Workbench generation/approval/publish/workspace endpoints write files or mutate session state:
  - `/api/v1/analyst-workbench/{date}/generate`
  - `/save-review`
  - `/approve`
  - `/publish`
  - workspace response persists assembled `review_document.json`
- Broader API includes write endpoints for backtest runs, direction tables, observation sessions, Redis streams, etc.

Adapter v1 must not call generation, approval, publish, save, backtest write, direction write, or trading/write-like APIs.

## 7. Existing Test Inventory

Relevant current tests observed:

- MCP/shared contract:
  - `tests/mcp/test_schema.py`
- Workbench intelligence/export:
  - `tests/workbench/test_intelligence_export_e2e.py`
  - `stock_processing_service/tests/unit/test_workbench_intelligence_binding.py`
  - `stock_processing_service/tests/unit/test_workbench_approve_api.py`
  - `stock_processing_service/tests/unit/test_workbench_approval_gate.py`
  - `stock_processing_service/tests/unit/test_workbench_phase454.py`
  - `stock_processing_service/tests/unit/test_workbench_phase455_generate.py`
  - `stock_processing_service/tests/unit/test_workbench_phase455_review_merger.py`
  - `stock_processing_service/tests/unit/test_workbench_phase455_responsibility_contract.py`
  - `stock_processing_service/tests/unit/test_workbench_phase455_compose_gate.py`
  - `stock_processing_service/tests/unit/test_workbench_review_document_only_contract.py`
  - `stock_processing_service/tests/unit/test_workbench_review_override_api.py`
  - `stock_processing_service/tests/unit/test_workbench_session.py`
- Market/domain facts:
  - `stock_processing_service/tests/unit/test_market_regime_fact_context_builder.py`
  - `stock_processing_service/tests/unit/test_market_metrics_emotion_momentum.py`
  - `stock_processing_service/tests/unit/test_market_metrics_active_capital_board_pool.py`
  - `stock_processing_service/tests/unit/test_derived_context_theme_identity_lookup.py`
  - `stock_processing_service/tests/unit/test_post_market_derived_data_generate_use_case.py`
  - `stock_processing_service/tests/unit/test_theme_identity_resolver_contract.py`
  - `stock_processing_service/tests/unit/test_theme_strength.py`
  - `stock_processing_service/tests/unit/test_theme_return.py`
  - `stock_processing_service/tests/unit/test_theme_workspace_graph_api.py`
  - `stock_processing_service/tests/unit/test_theme_kline_evidence_builder.py`
  - `stock_processing_service/tests/unit/test_capital_snapshot_adapter.py`
  - `stock_processing_service/tests/unit/test_seat_money_snapshot_adapter.py`
- Architecture/source ownership contracts:
  - `stock_processing_service/tests/contracts/test_api_contract.py`
  - `stock_processing_service/tests/contracts/test_frontend_single_view.py`
  - `stock_processing_service/tests/contracts/test_source_ownership.py`
  - `stock_processing_service/tests/contracts/test_assembler_purity.py`
  - `stock_processing_service/tests/contracts/test_producer_purity.py`
  - `stock_processing_service/tests/contracts/test_review_document_coverage_guard.py`
  - `stock_processing_service/tests/contracts/test_capital_source_ownership.py`
  - `stock_processing_service/tests/contracts/test_single_interpretation.py`

Gap: no observed standalone provider-native Julia Domain Adapter contract/fault matrix yet. AT-R1/AT-R5 should add tests that run without Julia Core and explicitly assert failure does not become empty success.

## 8. Proposed Adapter Files for AT-R1+

No files below are created in AT-R0. They are proposed only.

Recommended structure:

```text
stock_processing_service/application/services/julia_domain_adapter/
  __init__.py
  contracts.py              # AdapterRequest, AdapterStatus, DataState, SourceRecord, SourceFailure
  facade.py                 # deterministic operation registry
  mappers.py                # source-specific -> adapter-native envelope mapping
  provenance.py             # source_records/freshness/source failure helpers
  redaction.py              # secret/diagnostic redaction
  health.py                 # provider health/readiness model

stock_processing_service/api/julia_domain_adapter.py
  # thin HTTP JSON routes, if api_app split is acceptable

mcp_server/tools/julia_adapter.py
  # optional only if existing MCP runner needs local smoke, not v1 transport canonical

docs/integration/
  JULIA_ADAPTER_IBR_v1.md
  JULIA_ADAPTER_OPERATION_CATALOG_v1.md
  fixtures/
    market_snapshot_success.json
    market_snapshot_partial.json
    market_snapshot_unavailable.json
    market_snapshot_error.json
    market_snapshot_empty.json
    market_snapshot_stale.json
    market_alerts_success.json
    market_alerts_empty.json

tests/julia_domain_adapter/
  test_contract_schema.py
  test_facade_dispatch.py
  test_fault_semantics.py
  test_provenance.py
  test_secret_redaction.py
  test_no_julia_imports.py
  test_no_nlp_dispatch.py
```

Adapter v1 required operations:

- `market.snapshot`
- `market.alerts`

Optional after source stability is proven:

- `market.theme.details`
- `market.symbol.context`

## 9. Recommended Adapter Source Mapping

| Adapter operation | Preferred source | Current blocker |
|---|---|---|
| `market.snapshot` | `MarketContextExporter` + `DerivedContextReader` | Need explicit source_records, stale, status/data_state normalization |
| `market.alerts` | Approved snapshot + `AnalystIntelligenceExporter` claims filter | Current `list_active_alerts` loses failure semantics |
| `market.theme.details` | `DerivedContextReader` / `market_theme_constituents` | Hard-coded golden path and as_of restriction |
| `market.symbol.context` | `market_stock_history` / strong_stock rows | Direct `STOCK_DB_DSN`, as_of restriction, diagnostics redaction |

## 10. Risks

### P0 Risks

1. `list_active_alerts` exception/missing/invalid paths return `[]`, indistinguishable from valid empty alerts.
2. `review_market_snapshot` catches approved-path exceptions and falls back to draft/not-ready, losing true failure status.
3. Existing dirty state includes a modified production MCP file before AT-R0, so baseline cleanliness is not guaranteed.

### P1 Risks

1. No canonical provider-native `status` / `data_state` contract exists yet.
2. Source provenance is present in pieces (`evidence_refs`, `provenance`, `missing_sources`) but not normalized as `source_records`.
3. Hard-coded `/Users/admin/Desktop/ai_theme_app/golden/2026-07-14` blocks portable deployment for research operations.
4. Raw exception strings may leak paths or secrets through diagnostics.
5. Current MCP server is an in-process Python registry, not an independent HTTP provider boundary.
6. Workbench UI endpoints have write/persist side effects and should not be used as adapter v1 read paths.

### P2 Risks

1. Status names like `live`, `draft`, `rejected`, `not_ready`, `partial`, `unavailable` need stable mapping to adapter status/data_state.
2. Stale data is not explicit today.
3. Some helper conversions coerce invalid numbers to `0`/`0.0`; AT-R1 should preserve null/missing when semantically different from zero.

## 11. Next Recommendation

Do not enter AT-R1 until this AT-R0 report receives architecture gate review.

Recommended gate decision:

1. Approve source ownership:
   - ai_theme_app owns market domain observations and source records.
   - Julia Core owns CapabilityRequest/CapabilityCall, authorization, ToolResult, Evidence, Trace, Context OS, and cognition.
2. Require AT-R1 to define provider-native DTOs and JSON fixtures only; no Julia imports and no natural-language routing.
3. Require AT-R1/AT-R3 to fix or wrap lossy functions before live adapter use:
   - do not call `list_active_alerts` directly without preserving missing/invalid/exception states;
   - do not allow `review_market_snapshot` approved-path exceptions to become draft/not-ready success.
4. Prefer HTTP JSON for transport after the contract is stable; do not add MCP in v1.
5. Require secret redaction and portable path configuration before deployment hardening.

AT-R0 conclusion: ai_theme_app already has useful building blocks for a read-only Julia Domain Adapter, especially `MarketContextExporter`, `DerivedContextReader`, `ApprovedSnapshotValidator`, and `AnalystIntelligenceExporter`. The main gap is not data access; it is lossless provider boundary semantics: explicit status, data_state, source_records, failure preservation, and portable transport.
