# RD1-M1B — Market/Core Research Composition Report

## Base and responsibility

- Implementation base: `b6b55c5b8a8c5a95a56031bb78bb6f30b8d48eb7`
- M1A contract: `market.event.read`, schema `1.0`
- C1 reviewed consumer: `ac25125045f0997da69693e19581eebf544764cd`
- R1-PRECHECK verdict: `PASS`

M1B is implemented as a dependency-inverted application boundary:

```text
DomainObservationEnvelope(market.event.read)
→ validate admission/failure truth
→ deterministic frozen MarketEventContext projection
→ explicit direction/evidence representation
→ injected MarketEventResearchAdapter.build_request()
→ governed research.event.enrich CapabilityRequest
```

The production module does not import Julia Core and does not bind a provider. The exact C1 adapter is injected at the composition edge.

## Projection contract

`MarketEventResearchComposer` admits only:

- `operation=market.event.read`
- `schema_version=1.0`
- `success|partial` with `data_state=normal`
- exact M1A payload keys `event`, `theme_relations`, and `missing_fields`

The projected event contains exactly the twelve frozen C1 fields. Required values are type-checked before forwarding. Nullable values retain null identity.

Explicit representations are:

- M1A integer `direction` → exact decimal string for C1
- numeric confidence/relation confidence → finite float
- M1A relation `evidence` JSON → canonical sorted JSON string
- M1A relation input → only the nine C1 relation fields in `MarketEventContext`

M1A relation `created_at` and `run_id` remain outside the projected context in the retained Market envelope/source-record provenance.

## Decisions

- Successful complete event: `BUILD_C1_REQUEST`
- Qualified partial event or relation-source failure with a C1-valid event: `BUILD_WITH_PARTIAL_CONTEXT`
- Error/unavailable/empty, malformed shape, unknown field, missing required field, or C1 adapter mismatch: `STOP_BEFORE_C1`

Successful empty relations require `relation_state=empty_not_mapped`. A relation-source failure requires a failed `event_subject_map` source record and is never reinterpreted as successful discovery of no relations.

## Provenance continuity

The result retains the complete original `DomainObservationEnvelope`, including:

- `source_records`
- `failures`
- `correlation_id`
- `provider_request_id`
- `observed_at`
- `diagnostics`
- `payload.missing_fields`
- schema and operation identity

A deterministic SHA-256 projection identity is derived from the projected context and Market envelope truth. It is passed as the C1 `capability_request_id`. A non-empty Market correlation ID is copied directly; if empty, M1B mints a distinct deterministic correlation ID while retaining the original empty Market value.

The result keeps M1A metadata outside `MarketEventContext` and links it through the deterministic projection/request ID and effective correlation ID.

## Boundary compliance

M1B does not:

- invoke Claude or any model provider
- execute WebSearch or WebFetch
- mint `verification_state`
- normalize D1/provider evidence
- implement Julia cognition
- compose Assistant output
- route multiple events
- import Julia Core in production
- add HTTP/MCP transport
- add trading semantics

## Verification

Focused M1B acceptance regressions:

```text
/opt/miniconda3/bin/pytest -q \
  tests/market_research/test_m1b_market_event_composition.py

14 passed
```

Market plus existing wire/adapter regressions:

```text
/opt/miniconda3/bin/pytest -q --import-mode=importlib \
  tests/market_research tests/julia_domain_adapter

92 passed, 1 warning
```

The warning is the existing Starlette `python_multipart` pending-deprecation notice.

Exact local C1 object smoke check:

```text
PYTHONPATH=<ai_theme_app>:<Julia_core> python3.13
→ MarketEventResearchComposer.compose(..., research_adapter=MarketEventResearchAdapter())

BUILD_C1_REQUEST
cap_req_m1b_86bd4c33a8239f5a609d81639d06d428203cea0b86a99aeba73c22a1e41d4e2b
```

The smoke check used the exact reviewed C1 class as an injected test dependency only; it is not a production import or committed repository dependency.

Static checks:

```text
python3.13 -m compileall -q \
  stock_processing_service/application/services/market_research \
  tests/market_research/test_m1b_market_event_composition.py

git diff --check
```

Both passed.

## Not proven

- Runtime `CapabilityCall` creation and D1 dispatch
- Provider execution and observation acquisition
- `ResearchEvidenceNormalizer` execution in this repository
- Final Julia synthesis
- Multi-event orchestration

These remain outside frozen M1B responsibility.

## Verdict

**M1B = PASS**
