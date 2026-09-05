# RD1-L1-R9-D2B Market Candidate Data-Conversion + Observability Closure Report

## Executive verdict

PASS. `PostgresDatabaseManager.resolve_market_event_candidates()` now normalizes PostgreSQL JSON array representations to Python lists at the database boundary, while `MarketEventResolveOperation._candidate()` retains its strict list contract. Candidate conversion failures now retain bounded operation, layer, exception, request, query/theme/window, index/count, and field-type diagnostics without retaining raw candidates or tracebacks.

No real resolver, PostgreSQL query, Market read, retry, fallback, D1, or user turn was executed. No Core source was changed.

## Source states

- Market base SHA: `0bb026889f5c51e72aff9561b5eb542db7adf088`
- Market source-closure SHA: `f0aae447654bc50100bc6a26a3e204fbdac6a707`
- Core SHA (unchanged): `fce9be72a85629b4d3dc9b8265ba7b58b46ec832`

Production changes:

- `database_service/managers/postgres_manager.py`
- `stock_processing_service/application/services/julia_domain_adapter/operations/event_resolve.py`

Test changes:

- `tests/julia_domain_adapter/test_r9_d2b_candidate_conversion_observability.py`

## Source representation audit

The canonical resolver projection constructs `matched_subjects` with `json_build_array(json_build_object(...))`. asyncpg can surface PostgreSQL JSON as a JSON string, so the Domain Adapter previously received a string and correctly rejected it with `matched_subjects must be an array`.

The SQL guarantees one JSON array for each returned row. It does not model a missing relation as `NULL`. Therefore `None` is not an allowed semantic substitute for an empty array and fails closed.

`MATCHED_SUBJECTS_NONE_SEMANTICS = NOT_ALLOWED`.

## Boundary conversion

`_decode_json_array(value, field=...)` accepts:

- an existing Python list unchanged;
- a valid JSON-array string and decodes it to a list;
- `"[]"` as an empty list.

It fails closed for:

- malformed JSON;
- a JSON object;
- scalar/native non-list values;
- `None`.

The conversion is local to `PostgresDatabaseManager.resolve_market_event_candidates()`. No asyncpg connection, pool, codec, type registry, SQL matching, ordering, joins, limits, or date predicates changed.

## Candidate observability

Candidate conversion now has a distinct failure layer:

- resolver/query failures: `MarketEventResolveOperation._resolve`
- post-query candidate conversion: `MarketEventResolveOperation._candidate`

The retained pre-collapse diagnostics include operation symbol, failure layer, exception class/message, process PID, observed time, query, normalized theme, time window, correlation ID, idempotency ID/provider request ID, capability request ID where available, candidate index, bounded raw candidate count, and `matched_subjects` Python type.

The path does not retain the raw candidate, event payload, SQL, traceback, credentials, DSN, or environment.

## Digests

Old adapter digest:

`a389f92a0026291bbb2820bfce03fb9ff2545553859022dea3a413b8f1d52ad1`

New adapter digest:

`34f72e3ac3d025c05e18814f76d75999ed385baa865b5263dbfb64eab20805f4`

Old DB runtime digest:

`19a4765e6e323bebb5b975560fce0a5a4111000844d95804a9dede1458935cff`

New DB runtime digest:

`23bc6dcf76650700353150f2eb95773169d14a3708293ac8b7826cde4f6b7454`

The database dependency/import closure was re-audited. No local dependency edge or runtime file was added or removed; the existing deterministic 29-file closure remains complete. Only file content changed.

`DB_RUNTIME_FILESET_CHANGED = NO`

## Test evidence

Focused conversion and observability:

```text
/opt/miniconda3/bin/pytest -q tests/julia_domain_adapter/test_r9_d2b_candidate_conversion_observability.py
```

Result: `9 passed in 0.34s`

Focused resolver regression:

```text
/opt/miniconda3/bin/pytest -q tests/julia_domain_adapter/test_i2a_market_event_resolve.py tests/julia_domain_adapter/test_r9_d2b_candidate_conversion_observability.py
```

Result: `19 passed in 0.37s`

Gateway/adapter focused regression:

```text
/opt/miniconda3/bin/pytest -q database_service/tests/unit/test_gateway_subject_stock_pool.py tests/julia_domain_adapter/test_i2a_market_event_resolve.py tests/julia_domain_adapter/test_r9_d2b_candidate_conversion_observability.py
```

Result: `20 passed in 0.45s`

Broader Market adapter contract suites were run across wire contract, facade, degradation/provenance, transport, fault matrix, deployment hardening, event resolve/read, D2B conversion, and composition:

```text
/opt/miniconda3/bin/pytest -q tests/julia_domain_adapter/test_at_r1_wire_contract.py tests/julia_domain_adapter/test_at_r2_domain_adapter_facade.py tests/julia_domain_adapter/test_at_r3_degradation_provenance.py tests/julia_domain_adapter/test_at_r4_http_transport.py tests/julia_domain_adapter/test_at_r5_contract_fault_matrix.py tests/julia_domain_adapter/test_at_r7_deployment_hardening.py tests/julia_domain_adapter/test_i2a_market_event_resolve.py tests/julia_domain_adapter/test_m1a_market_event_read.py tests/julia_domain_adapter/test_r9_d2b_candidate_conversion_observability.py tests/market_research/test_m1b_market_event_composition.py
```

Result: `108 passed, 3 failed`.

The three failures are pre-existing test-package import errors (`ModuleNotFoundError: No module named 'tests.julia_domain_adapter'`). The same three tests were reproduced unchanged at Market base SHA `0bb026889f5c51e72aff9561b5eb542db7adf088` before removing the temporary audit worktree. They are unrelated to D2B files.

## Static checks

```text
python -m compileall -q database_service/managers/postgres_manager.py stock_processing_service/application/services/julia_domain_adapter/operations/event_resolve.py tests/julia_domain_adapter/test_r9_d2b_candidate_conversion_observability.py
git diff --check
```

Results: PASS / PASS.

## Execution counters

- Real resolver executions: 0
- PostgreSQL/manual resolver queries: 0
- Market event read executions: 0
- User turns: 0
- D1/C1/C2 executions: 0
- Assistant research brief executions: 0
- Database writes: 0
- Market resolver retries: 0
- Market resolver fallbacks: 0

## Gates

- R9-D2B ready to close: YES
- R9-D2C ready: YES
- R9-D2C authorized: NO
- R9-D3 ready: NO
- R10 ready: NO
- R10 authorized: NO

