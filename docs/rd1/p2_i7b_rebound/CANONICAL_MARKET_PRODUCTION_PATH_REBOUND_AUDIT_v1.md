# RD1 P2/I7B Canonical Market Production Path Rebound Audit v1

## Audit identity

- Task: `RD1-P2-I7B-CANONICAL-MARKET-PRODUCTION-PATH-REBOUND-P0`
- Repository: `tonychang925-dev/ai_theme_app`
- Audited base: `bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- Rejected candidate: `12a69132cfda80825dca43a4757e05520656eb9a`
- Audit mode: repository read-only plus docs-only deliverables
- Production execution: none
- DB mutation: none
- E2E/composite execution: none

## Executive finding

The failed P2/I7B recovery violated the established Market production architecture by selecting the historical direct-DB orchestration entrypoint:

```text
scripts/build_post_market_recap.py
→ subprocess
→ stock_service/scripts/build_mainline_identity_registry.py
→ asyncpg
→ raw SQL / DDL / schema ownership
→ PostgreSQL
```

The canonical direction is already present in the repository:

```text
Collection / Runner
→ SPS Application Jobs
→ declared Ports
→ Gateway Adapters
→ database_service Gateway
→ PostgresDatabaseManager
→ Market data products
→ market_public
→ Julia
```

The `InvalidColumnReferenceError` on `ON CONFLICT (subject_key)` is not the root defect. It is the observable consequence of duplicated schema ownership:

- Legacy assumption: `stock_service/scripts/build_mainline_identity_registry.py:1904` creates the table with `subject_key PRIMARY KEY`.
- Legacy writer: `stock_service/scripts/build_mainline_identity_registry.py:1934` uses `ON CONFLICT (subject_key)`.
- Canonical writer: `database_service/managers/postgres_manager.py:7363` uses `ON CONFLICT (subject_key, source_trade_date)`.

Repairing the legacy SQL would deepen the architecture violation. The rejected candidate modified only the legacy transport and added a test which imported that legacy script, so its passing tests did not certify the canonical production path.

## Architecture authority

`docs/adrs/ADR_LIST.md:741` requires old scripts to become CLI wrappers at most, with production business flow in application services or Jobs. `docs/adrs/ADR_LIST.md:753` forbids direct SQL in `stock_processing_service` and requires Port plus `database_service` Gateway access.

`docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md:79` names `IdentityRuleEngine`, `IdentityLLMReviewService`, `IdentityDecider`, and `BuildIdentityJob` as the Layer A authority and states that `database_service` owns SQL/schema access.

The canonical composition is wired in `stock_processing_service/application/orchestrators/bootstrap.py:77` through `DBThemeDataGateway`, `DBStockObjectGateway`, event/idempotency adapters, and the required Jobs. Architecture authority is not ambiguous.

## Failed recovery entrypoints

Retained recovery evidence establishes these generation entrypoints:

1. `scripts/build_post_market_recap.py --trade-date 2026-09-23 --identity-mode incremental`
2. `stock_service/scripts/build_mainline_identity_registry.py --trade-date 2026-09-23 --mode incremental`

The first directly imports `asyncpg`, opens private connections, and invokes legacy subprocesses. The second owns connection, DDL, reads, writes, lifecycle updates, and LLM transport.

`market.state.read` and `market.analysis.read` were public readiness probes, not generation paths. The `/private/tmp` DeepSeek experiment was diagnostic only; its `4000` result is not canonical production evidence.

## Canonical entrypoint finding

The canonical collection path exists:

- Planner: `stock_processing_service/application/services/collection_orchestrator.py:262`
- Prerequisites runner: `stock_processing_service/application/services/collection_task_runners.py:275`
- Recap runner: `stock_processing_service/application/services/collection_task_runners.py:1327`
- Worker: `stock_processing_service/workers/run_collection_runner.py:27`
- Container: `stock_processing_service/application/orchestrators/bootstrap.py:77`

With `task_key="recap_snapshot"` and `force_rebuild_truth_source=true`, the planner emits:

```text
stock.kline_judgements
recap.prerequisites.isolated
recap.market_environment_daily
recap.theme_capital_flow_daily
money_flow_enhanced
abnormal.signal
recap.snapshot.isolated
```

`PostMarketPrerequisitesRunner` executes evidence, cycle, identity, cycle refresh, and mainline-state Jobs. `PostMarketRecapRunner` directly invokes `BuildPostMarketRecapJob.execute()` and does not invoke the legacy recap script.

A newer API path also exists at `stock_processing_service/api_app.py:2963`, calling the same Job at `:3075`. It is architecturally closer to the target but its readiness/status wrappers extract a Gateway private client/pool and cannot serve as the P2 rebound authority without correction.

## Mapping summary

| Required legacy area | Canonical replacement | Architecture replacement | Semantic status |
|---|---|---|---|
| `scripts/build_post_market_recap.py` | force-truth `recap_snapshot` collection plan | YES | PARTIAL |
| `build_mainline_identity_registry.py` | `BuildIdentityJob` | YES | PARTIAL |
| `enforce_v2_identity_prior_gate.py` | no exact explicit Job/Gateway operation found | NO | MISSING |
| legacy theme-cycle build | evidence + cycle Jobs | YES | PARTIAL |
| `build_mainline_state_tracking.py` | `BuildMainlineStateJob` | YES | PARTIAL |
| direct recap snapshot write | recap Job → Port → Gateway → manager | YES | PARTIAL |
| legacy strong-watch pipeline | `BuildStrongStockTrackingUseCase` / recap integration | YES | PARTIAL |

No mapping is marked equivalent from class or test names alone. Exact contracts are recorded in `LEGACY_TO_CANONICAL_ENTRYPOINT_MAP_v1.md`.

## Canonical Identity LLM finding

Correct ownership is:

```text
BuildIdentityJob
→ IdentityLLMReviewService
→ strict provider transport
```

The Job already uses Ports for DB access, but current LLM semantics do not satisfy the required gate:

- missing provider configuration selects deterministic review;
- provider/transport/JSON failures become `review_pending`;
- request budget is fixed at `512`;
- JSON-object response format is absent;
- `finish_reason=length` is not classified;
- missing content defaults to `"{}"`;
- the request prompt is not the exact documented canonical prompt.

Therefore provider/transport failure must not be represented as `review_pending`. Full details are in `CANONICAL_IDENTITY_LLM_GAP_AUDIT_v1.md`.

## Required-path Gateway escape finding

`BuildPostMarketRecapJob` contains seven private pool/client resolution sites, several with direct raw SQL or raw-SQL application services. The selected collection worker also imports `_ReplayDatabaseStockFacade` from a test replay module and extracts `gateway._client`. The selected canonical collection path therefore has eight mechanically proven escape/contamination points. Details are in `RECAP_GATEWAY_ESCAPE_INVENTORY_v1.md`.

## Julia-facing boundary

The Julia-facing read boundary remains directionally correct:

```text
Julia/Core
→ market.analysis.read
→ MarketPublicFactory
→ _MarketPublicProvider
→ MarketAnalysisReader
→ Market-owned private repository
→ MarketResultEnvelope
```

Evidence is present at `market_public/factory.py:10`, `market_public/provider.py:222`, and `market_public/private/market_analysis.py:44`. No deviation was found. The violation is internal Market generation, not Julia access to Market internals.

## Resume decision

```text
CAN_P2_RESUME_WITHOUT_PRODUCTION_SOURCE_EDITS
= NO
```

Minimum blockers:

1. Canonical strict identity LLM transport and typed fail-closed behavior.
2. Required recap-path Gateway escape closure.
3. Production-entrypoint architecture guard.
4. Explicit canonical replacement or owner decision for identity-prior enforcement.
5. Canonical readiness and semantic regression evidence.

Bounded follow-ups are defined in `P2_I7B_CORRECTION_TASK_DECOMPOSITION_v1.md`.

## Final disposition

```text
12a69132cfda80825dca43a4757e05520656eb9a
= REJECT_AS_P2_CLOSURE_CANDIDATE

LEGACY_SCHEMA_FIX
= FORBIDDEN

P2_REAL_COMPOSITE
= HOLD
```

## Audit provenance

```text
BASE
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

ORIGIN_MAIN_VERIFIED
= YES

PRODUCTION_SOURCE_EDIT
= FORBIDDEN
```
