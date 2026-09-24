# POST_RD1_MARKET_GAP_REPORT_v1

## Audit basis

- `CANONICAL_MAIN_SHA = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- This report records gaps only. It contains no implementation plan and authorizes no production change.

## PRESENT_CANONICAL

| Capability / evidence | Current source truth | Result |
|---|---|---|
| Exact-date Market analytical read | `MarketAnalysisReadRequest`; `MarketAnalysisReader.read/_project` | Present with exact row/payload date checks and no date substitution |
| Market regime labels | `MarketEvidenceAdapter._PATHS` for `market_regime_review` | `broad_market_regime`, `short_term_sentiment`, and `mainline_environment` are projected as evidence |
| Market breadth | `MarketStateBreadth`; `MarketStateReader._project`; `market.state.read` | Separate exact-date public capability exposes up/down counts, ratios, limit counts, and turnover |
| Mainline identity, lifecycle, state, strength | `MarketEvidenceAdapter.build` mainline loop | Present when those producer fields exist |
| Watchlist evidence | `MarketEvidenceAdapter._add_watchlist_evidence` | Stock/theme/reason/date/decision/setup fields are projected when present |
| Next-day setup evidence | `MarketEvidenceAdapter._add_setup_evidence` and `calendar.next_trade_date` | Setup summaries/focus/reasons/rationale and watch date are projected when present |
| Module coverage and quality limitations | `SourceCoverage`; `QualityEnvelope`; `_coverage` | All ten canonical modules have coverage; quality exposes status, ratio, missing modules, and issues |
| Evidence references and content identity | `EvidenceRef`; `EvidenceItem`; `canonical_hash`; `_evidence_item` | Every emitted evidence item has module/path/snapshot/ref identity; bundle/evidence content hashes are present |
| Typed empty/failure separation | `MarketResultEnvelope.__post_init__`; `_execute_market_analysis` | Valid `SUCCESS/EMPTY` is distinct from typed failures; `FAILURE+EMPTY` is forbidden |
| Optional maturity passthrough | `MarketAnalysisReader._review_maturity` | Recognizes ten fields from canonical recap layers, preserves origins, rejects conflicts, and explicitly reports unavailable when absent |

## PARTIAL_CANONICAL

| Area | Current source truth | Gap |
|---|---|---|
| Mainline / theme context | `MarketEvidenceAdapter` mainline loop; `SourceCoverage` for `theme_reviews`; `market.product.read`; `market.product.linkage.read` | Mainline rows are evidence, but `theme_reviews` content is not extracted by the analytical adapter; theme/product capabilities are separate and no unified semantic projection is frozen |
| Lifecycle / stage evidence | mainline `lifecycle` / `lifecycle_state` aliases in `MarketEvidenceAdapter.build` | Stage values are passed through without a canonical lifecycle vocabulary, temporal semantics, or confidence model |
| Quality / coverage limitations | `QualityEnvelope` and `SourceCoverage` | Quality is primarily module-presence coverage and ready ratio; it does not measure per-field correctness, producer-role reliability, causal support, or freshness beyond projection `as_of` |
| Julia provenance requirements | `_provenance`; `MarketProvenance`; `MarketProvenanceProfile` | Source/evidence/public-object refs and hashes are preserved, but `market_release_identity=None`, `governance_ref=None`, no capability profile is selected, and derived status is always `PROVENANCE_INCOMPLETE` |
| Analyst maturity | `_review_maturity`; `WorkbenchStatus`; `ApprovalGate` | Market can expose maturity only if already embedded in the canonical recap payload. Workbench approval/publish metadata can be returned by report composition, but that response is not persisted back to `post_market_recap_snapshot` |
| Field-level epistemic status | payload/evidence contracts | No mechanical `epistemic_status` field exists. The projection cannot reliably distinguish machine-derived from analyst-authored upstream values without additional role metadata |
| Fail-closed maturity binding | `_review_maturity` and Workbench stores | Absent maturity is explicit, but there is no canonical durable Market assertion binding a specific analyst-reviewed/approved/published snapshot version to the exact analytical payload |

## ABSENT

| Missing capability or semantic | Source-grounded reason |
|---|---|
| Canonical `machine` maturity state in `market.analysis.read` | `MarketEvidenceAdapter` and `MarketAnalysisReader` do not emit a state named `machine`; `_review_maturity` only recognizes the ten listed passthrough fields |
| Canonical `analyst_reviewed` state from Workbench into Market evidence | `analyst_reviewed` is only passthrough if embedded; Workbench `IN_REVIEW` lives in tmp `SessionStore`, not the canonical Market read |
| Canonical `approved` binding into Market evidence | Workbench `APPROVED` uses tmp `SessionStore`/`SnapshotStore`; `_review_maturity` does not query those stores |
| Canonical `published` binding into Market evidence | Workbench `PUBLISHED` updates tmp session metadata; `_review_maturity` does not query it, and `WorkbenchStatus.PUBLISHED` alone does not rewrite the Market snapshot |
| Approved Workbench exclusive-entry architecture | Current public boundary has seven capabilities; `market.analysis.read` is the canonical analytical evidence base, not an exclusive Workbench entry point |
| Capability-specific complete provenance profile | `_provenance` deliberately passes `None`; no current runtime profile selects mandatory predicates for `market.analysis.read` |
| Release identity in analytical results | `MarketProvenance.market_release_identity` exists, but `_provenance` supplies `None` |
| Field-level analyst claim/opinion classification | Current projection has refs and values but no producer-role or claim/opinion discriminator |

## HISTORICAL_DONOR_ONLY

Issue #415 is explicitly noncanonical. The following are historical donor concepts, not current architecture:

| Historical concept | Current status |
|---|---|
| `market.snapshot` | Not in current `CAPABILITIES` |
| `market.alerts` | Not in current `CAPABILITIES` |
| `DomainObservationEnvelope` | No current public contract of that name; canonical result is `MarketResultEnvelope` |
| `stock_processing_service/application/services/julia_domain_adapter/**` | Not a current canonical production path |
| Old parallel Market Brain / research composition line | Superseded; must not be restored wholesale |
| “Approved Workbench is the single/only Market entry point for Julia” | Superseded by `market.analysis.read` plus the other current public capabilities |
| Historical event-to-observation mapping assumptions | No current `MarketResultEnvelope` semantic change may be inferred from donor mappings |

Reusable donor ideas remain source-record binding, request/correlation preservation, typed failures, hostile-content fixtures, unknown-reference rejection, no-network fixture discipline, approval metadata preservation, and separation of evidence verification from semantic truth. They are candidates only after a fresh contract freeze and current-source verification, not implementation authority.

## FUTURE_CONTRACT_CANDIDATE

These are contract-review questions only, not implementation plans:

| Candidate | Reason it is not already canonical |
|---|---|
| Capability-specific provenance profile and release identity predicates | Contracts exist, but no runtime profile is selected and `_provenance` emits `market_release_identity=None` |
| Mechanical field-level `epistemic_status` / producer-role metadata | Current evidence refs identify module/path/snapshot but not machine versus analyst epistemic origin |
| Canonical durable review-maturity projection | Current projection is conditional passthrough; separate tmp Workbench lifecycle is not bound to the exact Market payload |
| Unified mainline/theme analytical semantics | Mainline evidence and separate product/theme capabilities exist, but `theme_reviews` content is not in the analytical adapter |
| Lifecycle vocabulary and temporal confidence contract | Lifecycle strings pass through without normalized state semantics |
| Richer quality semantics beyond module coverage | Current score is module presence ratio; no correctness/reliability/causal-support model is frozen |
| Explicit Julia sufficiency profile | Provenance is incomplete and maturity is optional, so admissibility thresholds remain Julia/Core policy rather than current Market semantics |

## Julia-facing sufficiency classification

| Required evidence area | Classification |
|---|---|
| Market regime / breadth context | `PRESENT_CANONICAL` when required producer fields and exact market-state snapshot exist |
| Mainline / theme context | `PARTIAL_CANONICAL` |
| Lifecycle / stage evidence | `PARTIAL_CANONICAL` |
| Watchlist / next-day setup evidence | `PRESENT_CANONICAL` when producer fields exist |
| Quality / coverage limitations | `PRESENT_CANONICAL`, with semantic-depth limitations noted above |
| Provenance required by Julia | `PARTIAL_CANONICAL` |
| Analyst maturity | `PARTIAL_CANONICAL` |

## Freeze readiness

`READY_FOR_CONTRACT_FREEZE_REVIEW = NO`

Primary blockers for freeze review are incomplete provenance completion semantics, optional/non-bound analyst maturity, absent field-level epistemic origin, and partial theme/lifecycle semantic normalization. Exact-date behavior, typed failure behavior, evidence references, quality/coverage, and core regime/watchlist/setup evidence are sufficiently source-grounded for review.
# POST_RD1_MARKET_GAP_REPORT_v1
