# Legacy to Canonical Entrypoint Map v1

## Method

This map starts from legacy entrypoints used by the failed P2/I7B recovery and identifies mechanically present replacements in base `bc34e973686d7f78b0e9c3efd67b433f0901f21a`.

Statuses:

- `EQUIVALENT`: architecture, contracts, writes, and required semantics are proven.
- `PARTIAL`: canonical architecture exists but semantic or boundary gaps remain.
- `MISSING`: no exact canonical replacement is present.
- `BLOCKED`: ownership or semantics require an owner decision.

## 1. Legacy recap orchestration

Legacy entrypoint:

```text
scripts/build_post_market_recap.py::main_async()
```

Evidence:

- imports `asyncpg` at line 14;
- runs subprocesses through `_run_step` at line 110;
- directly connects/queries at lines 122, 155, 199, 266, 718, and 751;
- invokes the legacy identity script at lines 475 and 622.

Canonical replacement:

```text
CollectionCommandPlanner.build_task_plan(
  task_key="recap_snapshot",
  options={"force_rebuild_truth_source": true}
)
→ recap.prerequisites.isolated
→ recap.market_environment_daily
→ recap.theme_capital_flow_daily
→ money_flow_enhanced
→ abnormal.signal
→ recap.snapshot.isolated
```

Exact locations:

- planner: `stock_processing_service/application/services/collection_orchestrator.py:262`
- registry: `stock_processing_service/application/services/collection_task_registry.py:142`
- prerequisites: `stock_processing_service/application/services/collection_task_runners.py:275`
- snapshot: `stock_processing_service/application/services/collection_task_runners.py:1327`
- worker: `stock_processing_service/workers/run_collection_runner.py:27`

Input/output:

- Legacy accepts CLI trade-date and step flags, emits logs, and directly upserts the snapshot.
- Canonical accepts `CollectionTaskContext`, returns `CollectionTaskResult`, and delegates writes to Jobs/Ports.

Gaps:

1. force plan still includes a `script.default` `database_service/scripts/build_money_flow_enhanced.py` step;
2. selected worker wraps production Gateway in a test replay facade;
3. recap Job has seven private pool/client sites;
4. payload parity is not proven by current replay;
5. canonical readiness verification remains pool-based.

Status:

```text
PARTIAL
```

## 2. Legacy mainline identity registry

Legacy entrypoint:

```text
stock_service/scripts/build_mainline_identity_registry.py::main_async()
```

Evidence:

- direct connection at line 290;
- embedded DDL/schema assumptions at line 301;
- legacy LLM transport at line 1682;
- direct upsert at line 1895;
- direct lifecycle update at line 2058.

Canonical replacement:

```text
BuildIdentityJob.execute(
  trade_date,
  snapshot_version,
  batch_id,
  trace_id
)
```

Exact locations:

- class: `stock_processing_service/application/jobs/build_identity_job.py:32`
- execution: `:127`
- rule input read: `:163`
- LLM call: `:326`
- registry/review writes: `:486` and `:491`
- lifecycle delegation: `:495`
- bootstrap wiring: `stock_processing_service/application/orchestrators/bootstrap.py:121`

Input contract:

```text
trade_date: date
snapshot_version: str
batch_id: str
trace_id: str
```

Output contract:

```text
BuildResult
```

Writes:

- `theme_mainline_identity_registry`
- `mainline_identity_review_queue`

Declared write chain:

- `AlgorithmStateWritePort.upsert_theme_mainline_identity_registry_rows`
- `DBStockObjectGateway.upsert_theme_mainline_identity_registry_rows` at `stock_processing_service/infrastructure/gateway_adapters/db_stock_object_gateway.py:79`
- `DatabaseGateway.upsert_theme_mainline_identity_registry_rows` at `database_service/gateway.py:1896`
- `PostgresDatabaseManager.upsert_theme_mainline_identity_registry_rows` at `database_service/managers/postgres_manager.py:7334`

Lifecycle chain:

- `PostgresDatabaseManager.apply_lifecycle_downgrade` at `database_service/managers/postgres_manager.py:7569`
- Gateway method at `database_service/gateway.py:1929`

Gaps:

1. canonical LLM provider/configuration failure becomes deterministic or `review_pending`;
2. request budget is 512 and has no JSON-object response format;
3. `finish_reason=length`, missing content, invalid JSON, and contract mismatch do not fail typed;
4. `BuildIdentityJob` omits canonical prompt inputs;
5. `review_with_rule()` does not use `build_llm_prompt()`;
6. historical/as-of parity requires replay after strict transport correction.

Status:

```text
PARTIAL
```

## 3. Identity prior enforcement

Legacy entrypoint:

```text
stock_service/scripts/enforce_v2_identity_prior_gate.py::main_async()
```

It directly updates `theme_cycle_judgement_v2`:

- sets `final_mainline_alive=false` when identity is not confirmed;
- optionally promotes confirmed non-fade subjects to alive.

Gate and promotion SQL are at lines 81 and 103.

No explicit canonical Job or Gateway method with these semantics was found. `BuildMainlineStateJob` computes `is_mainline = identity_confirmed AND final_mainline_alive`, but does not mutate cycle judgement rows.

Status:

```text
MISSING
```

## 4. Legacy theme-cycle build

Legacy entrypoint:

```text
stock_service/scripts/build_theme_cycle_judgement_v2.py
```

Canonical replacements:

```text
BuildThemeCycleEvidenceDailyJob.execute(
  trade_date,
  snapshot_version,
  batch_id,
  trace_id
)
```

and:

```text
BuildCycleJudgementJob.execute(
  trade_date,
  snapshot_version="cycle_judgement.v2",
  batch_id,
  trace_id
)
```

Evidence Job:

- class: `stock_processing_service/application/jobs/build_theme_cycle_evidence_daily_job.py:46`
- execution: `:71`
- write: `:433`

Judgement Job:

- class: `stock_processing_service/application/jobs/build_cycle_judgement_job.py:27`
- execution: `:47`
- evidence read: `:95`
- write: `:193`

Both return `BuildResult`. Evidence writes `theme_cycle_evidence_daily`; judgement writes `theme_cycle_judgement_v2`.

Write chains use:

- `AlgorithmStateWritePort`
- `DBStockObjectGateway`
- `DatabaseGateway`
- `PostgresDatabaseManager`

Gaps:

1. no exact canonical identity-prior enforcement operation;
2. fixed replay matrix has not been executed in this docs-only audit;
3. cycle-before/after-identity ordering parity must be tested rather than assumed;
4. historical/as-of behavior and typed failures need focused tests.

Status:

```text
PARTIAL
```

## 5. Legacy mainline-state tracking

Legacy entrypoint:

```text
stock_service/scripts/build_mainline_state_tracking.py
```

Canonical replacement:

```text
BuildMainlineStateJob.execute(
  trade_date,
  snapshot_version="mainline_state.v2",
  batch_id,
  trace_id
)
```

Locations:

- class: `stock_processing_service/application/jobs/build_mainline_state_job.py:25`
- execution: `:49`
- identity/cycle reads: `:60-91`
- prior state read: `:103`
- state write: `:147`
- transition write: `:166`

Writes use:

- `upsert_mainline_state_daily_rows`
- `upsert_mainline_state_transition_rows`

Gaps:

1. optional `get_all_*` read exceptions are swallowed;
2. prior-state read exceptions are swallowed;
3. event publication exceptions are swallowed;
4. no `IdempotencyPort` is injected;
5. source failure may become `ok_no_data` or partial success rather than a typed failure.

Status:

```text
PARTIAL
```

## 6. Direct recap snapshot write

Legacy path:

```text
scripts/build_post_market_recap.py
→ asyncpg.connect
→ INSERT INTO post_market_recap_snapshot
```

Exact legacy location: lines 718-747.

Canonical path:

```text
BuildPostMarketRecapJob.execute(...)
→ StockWritePort.upsert_post_market_recap_snapshot
→ DBStockObjectGateway.upsert_post_market_recap_snapshot
→ DatabaseGateway.upsert_post_market_recap_snapshot
→ PostgresDatabaseManager.upsert_post_market_recap_snapshot
```

Locations:

- Job execution: `stock_processing_service/application/jobs/build_post_market_recap_job.py:380`
- snapshot construction: `:969`
- declared write: `:982`
- Port: `stock_processing_service/ports/write_ports.py:28`
- adapter: `stock_processing_service/infrastructure/gateway_adapters/db_stock_object_gateway.py:76`
- Gateway: `database_service/gateway.py:1595`
- manager: `database_service/managers/postgres_manager.py:5951`

Input contract:

```text
trade_date
snapshot_version
batch_id
trace_id
lookback_days
skip_prereqs
skip_layer_c
```

Output contract:

```text
BuildResult
PostMarketRecapSnapshot → post_market_recap_snapshot
```

Gaps:

1. seven required-path private pool/client sites remain;
2. raw SQL remains in the Job or application services it invokes;
3. readiness/job-status services are pool-based;
4. payload parity, Layer C inputs, and D1 candidate semantics need focused tests.

Status:

```text
PARTIAL
```

## 7. Legacy strong-watch pipeline

Legacy entrypoint:

```text
stock_service/scripts/build_strong_stock_watch_pool.py
```

Canonical replacement:

```text
BuildStrongStockTrackingUseCase
→ BuildPostMarketRecapJob integration
```

Wiring exists at `stock_processing_service/application/orchestrators/bootstrap.py:86` and `:154`.

Relevant Ports:

- `get_prior_strong_watch_pool_rows`
- `get_strong_stock_watch_view_rows`
- `get_legacy_strong_watch_candidate_inputs`
- `upsert_strong_watch_pool_rows`
- `upsert_strong_watch_history_rows`
- `promote_strong_watch_candidates`
- `prune_strong_watch_pool`

Gaps:

1. architecture review identifies unresolved Layer C production-input and legacy-program dry-run equivalence risks;
2. legacy table contents are not proof of legacy program output;
3. recap Job contains a raw SQL fallback after the declared view Port path;
4. D1 candidate and OneToTwo persistence semantics require contract tests.

Status:

```text
PARTIAL
```

## Open semantic checks

- identity prior enforcement;
- lifecycle downgrade parity;
- historical/as-of semantics;
- Layer C input authority;
- D1 candidate semantics;
- recap payload completeness;
- idempotency across all Jobs;
- typed failure behavior;
- no fallback under the required provider gate.

## Decision boundary

No replacement marked `PARTIAL` or `MISSING` may be treated as canonical production authority. Promotions require focused implementation, contract tests, and replay evidence in follow-up tasks.
