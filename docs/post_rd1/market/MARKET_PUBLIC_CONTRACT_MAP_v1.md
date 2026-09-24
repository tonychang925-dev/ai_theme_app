# MARKET_PUBLIC_CONTRACT_MAP_v1

## Audit binding

- `TASK_ID = POST-RD1-E1-A-MARKET-SOURCE-TRUTH-AUDIT-P0`
- `CANONICAL_MAIN_SHA = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `WORK_BRANCH_START_HEAD = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- Audit basis: current branch source only. Issue #415 is historical, noncanonical donor material and is not architecture authority.
- Tests are evidence of execution expectations, not a substitute for source inspection.

## Public boundary

The only Julia-facing Market provider is `_MarketPublicProvider` in `market_public/provider.py`; callers construct it through `MarketPublicFactory.create` in `market_public/factory.py`. `CAPABILITIES`, request dataclasses, `MarketResultEnvelope`, status enums, and typed failures are declared in `market_public/contracts.py`.

### Capability table

| Capability | Request | Implemented by | Result payload source | Exactness / validation |
|---|---|---|---|---|
| `market.event.resolve` | `EventResolveRequest` | `_MarketPublicProvider.execute` | `fetch_intel_feed(...)` through `_LazyPhase1Repository` | `limit` 1–200; optional `feed_date` must parse as `YYYY-MM-DD`; empty feed is `SUCCESS/EMPTY` |
| `market.event.read` | `EventReadRequest` | `_MarketPublicProvider.execute` and `_invalid_event_read_reason` | `fetch_intel_event_by_item_id` or `fetch_intel_event_by_event_id` | exactly one of source-namespaced `item_id` or news-namespace integer `event_id`; exact selector, no alternate-object fallback |
| `market.product.read` | `ProductReadRequest` | `_MarketPublicProvider.execute` | `fetch_theme_detail(subject_key)` | non-blank string `subject_key`; missing product is typed `OBJECT_NOT_FOUND` |
| `market.product.linkage.read` | `ProductLinkageReadRequest` | `_MarketPublicProvider._execute_product_linkage`; `MarketProductLinkageReader.read/_project` | `fetch_stocks_by_theme(...)` | non-blank subject; scope restricted to `pool`, `leader_overlay`, `all`; boolean leader flag; integer limit 1–`MAX_PRODUCT_LINKAGE_LIMIT`; returned row subject must equal request |
| `market.state.read` | `MarketStateReadRequest` | `_MarketPublicProvider._execute_market_state`; `MarketStateReader.read/_project` | exact-date row from `get_existing_post_market_recap_snapshot(trade_date)` | canonical `YYYY-MM-DD`; exact row and payload dates must match request |
| `market.stock.quote.read` | `StockQuoteReadRequest` | `_MarketPublicProvider.execute`; `_invalid_stock_quote_read_reason` | `get_stock_daily_quote(stock_id, trade_date)` | non-blank stock and canonical exact `trade_date`; missing exact quote is `SUCCESS/EMPTY` |
| `market.analysis.read` | `MarketAnalysisReadRequest` | `_MarketPublicProvider._execute_market_analysis`; `MarketAnalysisReader.read/_project` | exact-date `post_market_recap_snapshot`, projected through `MarketKnowledgeBundleBuilder` and `MarketEvidenceAdapter` | canonical `YYYY-MM-DD`; missing snapshot is `SUCCESS/EMPTY`; exact date substitution is forbidden |

All capability metadata is read-only `market.observe`; the tuple is declared by `CAPABILITIES` and `CapabilityMetadata` in `market_public/contracts.py`.

## Request and result contracts

### Envelope

`MarketResultEnvelope` contains:

- identity and protocol: `contract_version`, `capability_id`, `request_id`, `correlation_id`, `boundary_identity_ref`, `produced_at`;
- execution state: `operation_status`, `data_state`, `failures`;
- content: `payload`, `provenance`, `runtime_observation`.

The constructor requires non-empty contract, capability, correlation, boundary, and production values. It deliberately forbids `FAILURE + EMPTY`, making a domain failure distinct from a valid exact-date empty observation.

### Operation status

`MarketOperationStatus`: `SUCCESS`, `PARTIAL`, `FAILURE`.

### Data state

`MarketDataState`: `READY`, `PENDING`, `STALE`, `EMPTY`, `UNAVAILABLE`, `NOT_APPLICABLE`.

### Typed failures

`MarketFailure` carries `kind`, `code`, and `message`. `MarketFailureKind` currently declares:

`UNAVAILABLE`, `NOT_READY`, `CONTRACT_MISMATCH`, `RELEASE_MISMATCH`, `OBJECT_NOT_FOUND`, `EVIDENCE_UNAVAILABLE`, `PROVENANCE_INCOMPLETE`, `ANALYSIS_PENDING`, `ANALYSIS_PARTIAL`, `ANALYSIS_STALE`, `ANALYSIS_FAILED`, `GOVERNANCE_FAILURE`, `AUTHORIZATION_DENIED`, `TIMEOUT`, and `INTERNAL_FAILURE`.

## `market.analysis.read` status / failure matrix

| Private result | Envelope operation | Envelope data | Payload | Failure kind |
|---|---|---|---|---|
| `READY` | `SUCCESS` | `READY` | projected analytical evidence | none |
| `EMPTY` | `SUCCESS` | `EMPTY` | `None` | none |
| `INVALID_REQUEST` | `FAILURE` | `NOT_APPLICABLE` | `None` | `CONTRACT_MISMATCH` |
| `DEPENDENCY_UNAVAILABLE` | `FAILURE` | `UNAVAILABLE` | `None` | `UNAVAILABLE` |
| `INTERNAL_FAILURE` | `FAILURE` | `UNAVAILABLE` | `None` | `INTERNAL_FAILURE` |

`MarketAnalysisReader.read` maps private status values. Its projection converts `DATA_INTEGRITY_FAILURE` from `_project` into a private failure; `_execute_market_analysis` sends every non-READY/EMPTY/INVALID/dependency outcome through the final internal-failure branch as `FAILURE/UNAVAILABLE/INTERNAL_FAILURE`. No synthetic or substitute-date payload is created.

The provider-wide exception boundary in `_MarketPublicProvider.execute` independently maps dependency exceptions to `UNAVAILABLE` and other exceptions to `INTERNAL_FAILURE`, both with `data_state=UNAVAILABLE`.

## Provenance

`_provenance` in `market_public/provider.py` builds every envelope's `MarketProvenance` from payload content. No capability-specific mandatory profile is selected, so `MarketProvenance.__post_init__` derives `PROVENANCE_INCOMPLETE`; callers cannot assert `COMPLETE`.

For `market.analysis.read`, `_provenance` preserves:

- `source_refs`: payload `source.source_refs`;
- `evidence_refs`: every emitted `evidence[].ref.ref_id`;
- `public_object_refs`: `evidence_snapshot_id` and `source_bundle_id`;
- `data_cutoff`: payload `as_of`;
- `capability_call_ref` and `correlation_id`.

`MarketProvenance` also has `market_release_identity` and `governance_ref`, but `_provenance` currently supplies `None` for both. `MarketReleaseIdentity`, `MarketProvenanceProfile`, and `ProvenancePredicate` exist in `market_public/provenance.py`, but no current runtime profile binds them to `market.analysis.read`.

Other capabilities use `_source_refs` and `_public_object_refs`, which only extract source/public identities already present in the payload. This is preservation, not invented provenance.

## Exact-date and fail-closed behavior

- `MarketAnalysisReader._invalid_request_reason` requires a canonical ISO `YYYY-MM-DD` string and rejects noncanonical encodings.
- `Phase1MarketStateReadRepository.get_existing_post_market_recap_snapshot` selects `WHERE trade_date = $1::date` and `LIMIT 1`; it does not search for another date.
- `MarketAnalysisReader._project` requires the row `trade_date` to equal the request and, when the payload contains `trade_date`, requires that value to match too.
- Missing source data is a valid `SUCCESS/EMPTY`; malformed/integrity failures become typed failures rather than substituted data.
- Empty, non-mapping, or empty projected evidence raises `_MarketAnalysisDataIntegrityError`; the public reader maps it to failure.
- `MarketEvidenceAdapter.build` does not calculate new market facts; it projects existing producer-owned knowledge into referenced evidence.
- `MarketResultEnvelope.__post_init__` rejects the contradictory `FAILURE + EMPTY` state.

## Review-maturity boundary

`MarketAnalysisReader._review_maturity` searches only the canonical recap payload, `recap_doc`, and `recap_doc.daily_review_v2` for ten optional maturity fields. If none exists it returns `available=false`, `source_mode="unavailable"`, and `source="not_bound"`. If fields exist, it preserves their values and field origins and rejects conflicting duplicates.

This is not a lookup of Workbench `SessionStore` or `SnapshotStore`. The Analyst Workbench lifecycle exists in `WorkbenchStatus`, `SessionStore`, `ReviewSnapshot`, `SnapshotStore`, and `ApprovalGate`, but those stores are rooted under `tmp/analyst_workbench`; issue #416 explicitly excludes tmp state from canonical Market source truth. `WorkbenchReportComposer.compose` can return approval metadata and approved sections in a DailyReview response, but `compose_daily_review_from_workbench` in `stock_processing_service/api_app.py` does not write that composed response back to `post_market_recap_snapshot`.

Therefore current `market.analysis.read` exposes maturity only when maturity fields were already embedded in the canonical recap payload. It does not bind the separate tmp Workbench session/snapshot lifecycle to Julia-facing analytical evidence.

## Historical donor disposition

Issue #415 is noncanonical. The following are historical-only and must not be inferred into this boundary: `market.snapshot`, `market.alerts`, old `DomainObservationEnvelope`, old `julia_domain_adapter`, the old Market Brain parallel line, and the claim that Approved Workbench is the sole Julia Market entry point.
# MARKET_PUBLIC_CONTRACT_MAP_v1
