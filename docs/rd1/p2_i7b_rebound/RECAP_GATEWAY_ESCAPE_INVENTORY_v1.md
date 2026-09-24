# Recap Gateway Escape Inventory v1

## Scope

Required selected path:

```text
recap.prerequisites.isolated
recap.snapshot.isolated
→ stock_processing_service/workers/run_collection_runner.py
→ bootstrap.build_container()
→ BuildPostMarketRecapJob.execute()
→ declared Ports where present
```

Patterns searched:

- `asyncpg`
- raw SQL
- `._pool`
- `._db`
- `._client`
- `.pool`
- private gateway/client extraction
- subprocess legacy invocation

## Result

```text
BuildPostMarketRecapJob private extraction sites
= 7

Selected worker test-facade contamination sites
= 1

Required selected collection-path escape/contamination total
= 8
```

## E0 — Production worker imports test replay facade

Locations:

- `stock_processing_service/workers/run_collection_runner.py:44-46`
- `stock_processing_service/tests/replay/_post_market_replay_runner.py:20-33`

The worker imports `_ReplayDatabaseStockFacade`, wraps the production Gateway, and constructs the container through it. The facade extracts `gateway._client` and dynamically delegates to Gateway or private client.

Operation:

```text
construct production SPS container
```

Existing production adapter: none.

Reachability: required selected collection path.

Correction:

```text
NEEDS_OWNER_DECISION
```

Recommended disposition is a production adapter with explicit public delegation and no `_client` extraction.

## E1 — Limit-up theme matrix

Location:

```text
stock_processing_service/application/jobs/build_post_market_recap_job.py:140-164
```

The Job resolves `_pool`, `_db`, `_db._db`, and `.pool`, then passes a connection to `LimitUpThemeMatrixBuilder.build()`.

Operation:

```text
build limit_up_theme_matrix
```

The application builder queries stock history, subject mappings, subject names, stock names, ranked subjects, reason evidence, THS reason rows, and mainline rows.

Existing Port/Gateway method for the complete input bundle: none.

Reachability: required; called at line 960.

Correction:

```text
MOVE_SQL_TO_DATABASE_SERVICE
```

## E2 — Abnormal review injection

Location:

```text
stock_processing_service/application/jobs/build_post_market_recap_job.py:834-857
```

The Job resolves a private pool and directly queries `stock_abnormal_signal`.

Operation:

```text
read abnormal_reviews input
```

Declared Port:

```text
StockReadPort.get_stock_abnormal_signals
```

Adapter method exists in `stock_read_gateway_adapter.py:730`; manager method exists in `database_service/managers/postgres_manager.py:3064`.

Missing canonical chain element:

```text
DatabaseGateway.get_stock_abnormal_signals
```

The bootstrap-selected `DBThemeDataGateway` ultimately requires that public Gateway method.

Reachability: conditional normal path.

Correction:

```text
DELETE_ESCAPE_USE_EXISTING_PORT
```

Implementation must add the missing Gateway delegation.

## E3 — Daily-basic turnover source

Location:

```text
stock_processing_service/application/jobs/build_post_market_recap_job.py:859-890
```

The Job resolves a private pool and directly counts/reads `stock_daily_basic_snapshot`.

Operation:

```text
load positive turnover_rate rows for OneToTwo
```

Manager method exists at `database_service/managers/postgres_manager.py:3049`.

Missing:

```text
StockReadPort.get_stock_daily_basic_snapshot
DatabaseGateway.get_stock_daily_basic_snapshot
DBThemeDataGateway explicit delegation
```

Reachability: required normal path.

Correction:

```text
ADD_PORT_GATEWAY_METHOD
```

## E4 — Job-status writes

Location:

```text
stock_processing_service/application/jobs/build_post_market_recap_job.py:1297-1324
```

The Job resolves a private pool and constructs `PostMarketJobStatusService(pool=pool)`. That service directly upserts/queries `post_market_job_status`.

Operation:

```text
mark post_market_recap_generate running/success/failed
```

Existing Port/Gateway method: no generic typed job-status method.

Reachability: required multiple times per execution.

Correction:

```text
ADD_PORT_GATEWAY_METHOD
```

## E5 — Subject-name resolution

Location:

```text
stock_processing_service/application/jobs/build_post_market_recap_job.py:1514-1567
```

The Job resolves a private pool and directly queries `subject_node_staging` and `event_subject_map`; exceptions are discarded.

Operation:

```text
batch-resolve numeric subject keys to display names
```

Existing exact Port/Gateway method: none.

Reachability: conditional required review display path.

Correction:

```text
ADD_PORT_GATEWAY_METHOD
```

Silent exception swallowing must be removed or explicitly typed in follow-up.

## E6 — Readiness gate

Locations:

```text
stock_processing_service/application/jobs/build_post_market_recap_job.py:1856-1878
stock_processing_service/application/services/post_market_readiness_service.py:52-119
```

The Job resolves `_pool`, `_db`, `.pool`, `_db._db`, and `_client`, then delegates to a pool-based service that directly counts:

- `subject_stock_daily_snapshot`;
- `jyhf_index_quote_snapshot`;
- `theme_cycle_judgement_v2`;
- `money_flow_enhanced`;
- `strong_stock_watch_history`;
- `dragon_tiger_object`;
- `hot_money_trading_activity`;
- `stock_abnormal_signal`.

Operation:

```text
aggregate post-market readiness
```

Existing Port/Gateway method: none.

Reachability: required when prerequisites execute.

Correction:

```text
MOVE_SQL_TO_DATABASE_SERVICE
```

## E7 — Strong-stock review fallback

Location:

```text
stock_processing_service/application/jobs/build_post_market_recap_job.py:2252-2331
```

The method first resolves `_pool`, `_db`, and `_db._db`/`.pool`. Because `rows` starts empty, it then calls the declared `get_strong_stock_watch_view_rows(...)` and returns normalized rows before the later raw SQL block can execute.

Operation:

```text
build structured strong-stock reviews
```

Existing primary chain:

- `StockReadPort.get_strong_stock_watch_view_rows`
- `DBThemeDataGateway.get_strong_stock_watch_view_rows`
- `DatabaseGateway.get_strong_stock_watch_view_rows`
- `PostgresDatabaseManager.get_strong_stock_watch_view_rows`

Reachability:

- private extraction is reachable;
- raw SQL branch is dead as currently written but remains an escape hatch.

Correction:

```text
DELETE_ESCAPE_USE_EXISTING_PORT
```

## API-selected additional escapes

If `/api/v1/post-market/recap/generate` is selected instead of collection orchestration:

- `stock_processing_service/api_app.py:2977-2987`
- `stock_processing_service/api_app.py:3206-3212`

extract `app.state.gateway._client.pool` for readiness/status. Correction:

```text
ADD_PORT_GATEWAY_METHOD
```

That would make the API-selected required path total nine escape/contamination points.

## Methods that should remain authoritative

- `get_post_market_report_context`
- `get_subject_cycle_evidence_daily`
- `get_strong_stock_watch_view_rows`
- `get_prior_strong_watch_pool_rows`
- `get_legacy_strong_watch_candidate_inputs`
- `get_subject_board_stats`
- `get_stock_position_judgement`
- `get_stock_pattern_judgement`
- `get_post_market_setup_plan_rows`
- `get_one_to_two_candidate_feature_rows`
- `get_stock_abnormal_signals`
- `upsert_post_market_recap_snapshot`
- `upsert_theme_cycle_evidence_daily_rows`
- `upsert_theme_cycle_judgement_v2_rows`
- `upsert_mainline_state_daily_rows`
- `upsert_mainline_state_transition_rows`
- `upsert_theme_mainline_identity_registry_rows`
- `upsert_mainline_identity_review_queue_rows`
- `apply_lifecycle_downgrade`

## Guard consequence

The future guard must first close these required-path escapes, then enforce no private extraction in the corrected required files. A global immediate ban would expose many unrelated historical modules; those require a separate explicitly owned cleanup scope.

The API-selected readiness/status path introduces one additional private pool use beyond the selected-worker total of `8`, yielding an API-selected total of `9`.
