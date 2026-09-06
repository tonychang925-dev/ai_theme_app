# RD1-M1A — `market.event.read` Implementation Report

## Audit and implementation base

- M0 canonical source audit base: `08fc1a688c852a9894d6bcb77fb1e9cc14567045`
- M1A implementation base: `5b656b99db2f2e5046bac5b0b2fe94a5bc6a3609`
- Canonical event authority: PostgreSQL `public.news_event`, authoritative ID `news_event.id`
- Canonical theme relation source: PostgreSQL `public.event_subject_map`
- Canonical handoff only: `events:structured`; it is not read as event truth

## Implemented operation

`DomainIntelligenceAdapter` now dispatches the exact operation `market.event.read` to `MarketEventReadOperation`.

The runtime path is:

```text
market.event.read(event_id)
→ DomainIntelligenceAdapter
→ MarketEventReadOperation
→ DatabaseGateway.get_news_event_for_match(event_id)
→ PostgresManager.get_news_event_for_match(event_id)
→ public.news_event LEFT JOIN public.news_raw

MarketEventReadOperation
→ DatabaseGateway.get_event_subject_mappings_by_event_ids([event_id])
→ PostgresManager
→ public.event_subject_map
```

No second database owner, Redis event reader, NLP routing, Julia Core import, M1B composition, or research-provider logic was introduced.

## Source-backed payload

`payload.event` contains only the M0 minimum equivalents:

- `event_id` from `news_event.id`
- `event_type`, `summary`, `direction`, and `confidence`
- nullable `occurred_at`, derived in source order from event time, event creation time, raw-news publication timestamp, then relation creation time
- nullable `title`, source-backed from `news_raw.title` with the M0-approved summary fallback
- `source_category`, preserving the canonical reader's `news` fallback
- nullable `source_name` and `source_url` from `news_raw.source` and `news_raw.url`
- `source_trace_id` and nullable `news_id`

`payload.theme_relations` maps only M0-proven `event_subject_map` fields and provenance. An empty list is represented as `relation_state=empty_not_mapped`.

The event projection in `PostgresManager.get_news_event_for_match` now returns the source-backed timestamp, direction, confidence, trace, and raw-news source/url columns required by that existing boundary. No event rows are modified.

## Explicit exclusions

The following remain excluded from the event payload and are listed in diagnostics as `excluded_not_proven_fields`:

- `related_symbols`
- uniform `entities`, `causal_claim`, `evidence_set`, and `raw_event_json`
- `severity_score` and `source_weight`
- lifecycle, market heat, theme state, and analyst claims

Even when older optional columns happen to be present, this M1A contract does not promote them to uniform Market event fields.

## Failure semantics

- Invalid or missing integer `event_id`: `error / empty / INVALID_ARGUMENT`
- Unknown event: `error / empty / NOT_FOUND`
- Event DB failure or timeout: `unavailable / empty / UPSTREAM_TIMEOUT` or `UPSTREAM_UNAVAILABLE`
- Malformed/non-object event, missing/unstable ID: `error / empty / SCHEMA_MISMATCH`
- Missing source-backed event fields: `partial / normal`, retained event payload plus explicit `missing_fields`
- Relation DB failure: `partial / normal`, retained canonical event plus failed relation `SourceRecord`
- Missing relation capability/table now raises through the existing DatabaseGateway boundary instead of being collapsed into empty success
- Staleness is not inferred; timestamps remain source-backed and caller policy remains deferred

## Provenance

The envelope includes distinct database `SourceRecord` values for:

- `public.news_event:id=<event_id>`, including schema/table/row ID, `source_trace_id`, read boundary, source timestamp-based `as_of`, and read `observed_at`
- `public.event_subject_map:event_id=<event_id>`, including relation run IDs, read boundary, row update `as_of`, and read `observed_at`

Failures retain the failed source record, operation diagnostics, correlation ID, provider request ID, and envelope observation time.

## Verification

Focused regressions:

```text
/opt/miniconda3/bin/pytest -q \
  tests/julia_domain_adapter/test_m1a_market_event_read.py \
  tests/julia_domain_adapter/test_at_r1_wire_contract.py \
  tests/julia_domain_adapter/test_at_r2_domain_adapter_facade.py

27 passed
```

Full current Julia adapter suite:

```text
/opt/miniconda3/bin/pytest -q --import-mode=importlib tests/julia_domain_adapter

77 passed, 1 warning
```

The warning is the existing Starlette `python_multipart` pending-deprecation notice. The default suite import mode has three pre-existing cross-test module import failures; `--import-mode=importlib` is required by the current test layout and avoids changing unrelated test packaging.

Additional checks:

```text
python3.13 -m compileall -q \
  stock_processing_service/application/services/julia_domain_adapter \
  tests/julia_domain_adapter/test_m1a_market_event_read.py

git diff --check
```

Both completed successfully.

## Deferred

- M1B composition
- `related_symbols`
- Intel raw document content/title joins beyond the established minimum
- lifecycle and stale policy
- market heat/theme state composition
- candidate listing by date

## Verdict

**M1A = PASS**
