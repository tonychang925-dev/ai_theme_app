# RD1-I2A Market Event Resolver Implementation Report

## 1. Exact base SHA

- `52893734532cdcab54d382c94037263de3eeb194`
- Julia Core reference, read-only: `ff545b7561641e35d6bb689b686d05c3343165fa`

## 2. Changed files

- `stock_processing_service/application/services/julia_domain_adapter/contracts.py`
- `stock_processing_service/application/services/julia_domain_adapter/adapter.py`
- `stock_processing_service/application/services/julia_domain_adapter/operations/event_resolve.py`
- `database_service/managers/postgres_manager.py`
- `database_service/gateway.py`
- `docs/integration/JULIA_ADAPTER_SCHEMA_v1.json`
- `tests/julia_domain_adapter/test_i2a_market_event_resolve.py`
- Frozen wire-catalog/hash expectations in the three existing adapter contract tests.

## 3. Existing seams reused

- Canonical relation: `public.event_subject_map`.
- Canonical event table: `public.news_event`.
- Canonical ID: `public.news_event.id`.
- Existing event recency expression and ordering semantics: event timestamp DESC, event ID DESC, primary relation first, relation confidence DESC.
- Existing adapter envelope/failure/provenance model.
- Existing `market.event.read` operation and its `DatabaseGateway.get_news_event_for_match` boundary.

## 4. Resolver contract

- Operation: `market.event.resolve`.
- Input: required inert `query`; optional bounded `normalized_theme`; optional `time_window` (`date` or `start_at` + `end_at`); bounded `limit` (1–100, default 20).
- The operation rejects unsupported fields, including caller-supplied `market_event_id`; an ID is read identity, not resolution.
- Query/theme matching is exact, trimmed, case-insensitive theme-name matching. No raw-query interpretation, LLM call, provider call, fuzzy tie-break, or caller-owned canonical identity is introduced.

## 5. Candidate construction

Market owns the SQL lookup:

`normalized_theme || query`
→ exact `event_subject_map.subject_name` relation
→ canonical `news_event.id`
→ bounded candidates

Each candidate contains:

- `market_event_id` (`public.news_event.id`)
- `title` (raw title, summary, event type, or deterministic event label fallback)
- `summary`
- `occurred_at`
- `matched_subjects[]` with canonical relation facts (`subject_key`, `subject_name`, `relation_type`, `confidence`)

## 6. Selection semantics

- `candidate_count == 1` → `RESOLVED` plus exactly one `selected_event_id`.
- The selected value is always a source-returned `public.news_event.id`.

## 7. Ambiguity semantics

- `candidate_count == 0` → successful `UNRESOLVED`, empty candidates.
- `candidate_count > 1` → successful `AMBIGUOUS`, bounded ordered candidates.
- No candidate is silently selected in the ambiguous case.

## 8. Failure semantics

- Gateway absence, database unavailability, relation lookup failure, and invalid resolver payloads produce `unavailable` or `error` envelopes with explicit failures.
- Infrastructure failure never becomes successful `UNRESOLVED`.
- Invalid arguments, including caller-supplied event IDs, return `INVALID_ARGUMENT`.

## 9. Determinism

For identical database state, query/theme hint, time bounds, and limit:

- candidate ordering is deterministic;
- state is deterministic;
- SQL ordering is `occurred_at DESC`, `news_event.id DESC`, primary relation first, relation confidence DESC.

No randomness, model call, provider call, or external service participates.

## 10. market.event.read compatibility

`RESOLVED.selected_event_id` is passed unchanged as `market.event.read.arguments.event_id`, whose existing boundary is `DatabaseGateway.get_news_event_for_match`. That existing M1B read path remains unchanged and remains compatible with `MarketEventResearchAdapter` → `research.event.enrich`.

## 11. Tests

- `tests/julia_domain_adapter/test_i2a_market_event_resolve.py`
  - `I2A-F01` one canonical event → `RESOLVED`
  - `I2A-F02` zero events → `UNRESOLVED`
  - `I2A-F03` multiple events → `AMBIGUOUS`, candidates retained
  - `I2A-F04` DB unavailability → `unavailable`, not `UNRESOLVED`
  - `I2A-F05` relation lookup failure → `error`, not successful empty set
  - `I2A-F06` deterministic repeated request/order
  - `I2A-F07` candidate IDs originate as canonical event IDs
  - `I2A-F08` selected ID feeds existing `market.event.read`
  - `I2A-F09` no LLM/provider dependency
  - `I2A-F10` hostile query remains inert data

Validation:

- `pytest -q tests/julia_domain_adapter/test_i2a_market_event_resolve.py`
- `pytest -q --import-mode=importlib tests/julia_domain_adapter`
- `pytest -q tests/market_research/test_m1b_market_event_composition.py`
- `python -m py_compile` for changed Python files
- `git diff --check`

## 12. Regressions

- Adapter suite: 86 passed.
- Market event research composition regression: 14 passed.
- No Core, Assistant, D1, Electron, Voice, schema migration, vector infrastructure, or LLM changes.

## 13. Architecture deviations

- `NONE`
- The resolver is Market-owned and database-backed; Core/cognition callers may supply a normalized theme but cannot supply canonical event identity as resolution.

## 14. Not proven

- Live PostgreSQL execution against production-like data was not run (`LIVE_NETWORK_CALLS = 0`).
- Chinese natural-language normalization remains outside Market and must be supplied by the authorized caller as `normalized_theme`; exact raw full-question strings may naturally remain `UNRESOLVED`.
- End-to-end Core/I1 runtime invocation was not modified or run; compatibility is source/test proven through the unchanged `market.event.read` boundary.

## 15. Verdict

`I2A = PASS`
