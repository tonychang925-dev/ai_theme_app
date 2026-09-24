# MARKET_ANALYTICAL_EVIDENCE_CONTRACT_FREEZE_CANDIDATE_v1

## Authority binding

- `TASK_ID = POST-RD1-E1-B-MARKET-ANALYTICAL-EVIDENCE-CONTRACT-FREEZE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `BASE_HEAD / E1-A_ACCEPTED_HEAD = ea9032cf45832ea5f4ad801b82c3af023d291abe`
- Authority inputs: current branch source plus the three E1-A artifacts at the exact base head.
- Historical Issue #415 remains noncanonical donor material and contributes no normative rule to this candidate.
- This document is a contract candidate, not production implementation and not an Owner acceptance record.

## Freeze scope

This candidate freezes a bounded **Market Analytical Evidence MVP contract** for `market.analysis.read`. It freezes mechanically supported evidence, exact-date behavior, envelope semantics, preservation guarantees, explicit limitations, and the Julia/Market authority boundary.

It does not declare production provenance completeness, field-level epistemic origin, normalized lifecycle semantics, analyst maturity, or quality correctness guarantees that current code does not provide.

## 1. Capability and result contract

### MUST

- Consumers MUST call `market.analysis.read` with `MarketAnalysisReadRequest` and an exact canonical `YYYY-MM-DD` `trade_date`.
- `MarketResultEnvelope` MUST remain the transport-neutral Julia-facing result contract.
- Consumers MUST treat `operation_status`, `data_state`, `payload`, `failures`, and `provenance` as independent semantic planes.
- Exact-date source absence MUST be interpreted as `SUCCESS` + `EMPTY` + `payload=None`.
- Consumers MUST preserve and propagate `request_id`, `correlation_id`, evidence refs, source refs, and public object refs when making downstream claims.
- Consumers MUST treat every emitted `EvidenceItem` as Market evidence, never as Julia observation, analyst approval, or final investment judgment.
- Consumers MUST honor `module_coverage` and `quality` as coverage/presence metadata within their frozen scope.

Mechanical source:

- Request and envelope: `market_public/contracts.py:MarketAnalysisReadRequest`, `MarketResultEnvelope`, `MarketOperationStatus`, `MarketDataState`, `MarketFailure`.
- Dispatch and mapping: `market_public/provider.py:_MarketPublicProvider.execute`, `_execute_market_analysis`.
- Exact date and projection: `market_public/private/market_analysis.py:MarketAnalysisReader.read`, `_invalid_request_reason`, `_project`.
- Exact source read: `market_public/private/phase1_market_state_repository.py:Phase1MarketStateReadRepository.get_existing_post_market_recap_snapshot`.

### MUST NOT

- Market MUST NOT select another date, latest snapshot, synthetic payload, mock success, or fallback producer when the exact date is absent.
- Market MUST NOT return `FAILURE` + `EMPTY`; that combination is rejected by `MarketResultEnvelope.__post_init__`.
- Market MUST NOT recalculate producer analytics in `market.analysis.read`; projection is through `MarketKnowledgeBundleBuilder` and `MarketEvidenceAdapter`.
- Consumers MUST NOT treat a valid `SUCCESS/EMPTY` result as a Market assertion that no market activity occurred.
- Consumers MUST NOT infer approval, publication, correctness, causal truth, or Julia acceptance from evidence presence.

### MAY

- Julia/Core MAY combine this evidence with other authorized Market capabilities and other authorized evidence sources.
- Julia/Core MAY reject evidence for admissibility, sufficiency, compatibility, temporal, or policy reasons not frozen by Market.
- Market MAY return embedded review maturity when it already exists in the canonical recap layers, subject to the boundaries below.

## 2. Envelope semantics

The frozen mapping is:

| Private result | Operation | Data state | Payload | Failure |
|---|---|---|---|---|
| `READY` | `SUCCESS` | `READY` | projected evidence | none |
| `EMPTY` | `SUCCESS` | `EMPTY` | `None` | none |
| `INVALID_REQUEST` | `FAILURE` | `NOT_APPLICABLE` | `None` | `CONTRACT_MISMATCH` |
| `DEPENDENCY_UNAVAILABLE` | `FAILURE` | `UNAVAILABLE` | `None` | `UNAVAILABLE` |
| other private failure | `FAILURE` | `UNAVAILABLE` | `None` | `INTERNAL_FAILURE` |

`PARTIAL`, `PENDING`, `STALE`, and their related typed failure kinds remain declared transport vocabulary, not guarantees that the current analytical reader emits those states. Consumers MUST NOT invent pending/partial/stale behavior for this capability.

## 3. Evidence and identity preservation

### Frozen payload identity

The payload MUST retain:

- `schema_version = market.analysis.v1`;
- exact `trade_date`;
- projection `as_of`;
- `source.snapshot_ref`, `snapshot_identity`, `snapshot_version`, `source_snapshot_ids`, `batch_id`, `trace_id`, `producer_versions`, and `source_refs`;
- hash-derived `source_bundle_id`, `evidence_snapshot_id`, and `content_hash`.

### Frozen evidence item shape

Every emitted evidence item MUST contain:

- normalized `key`;
- producer `value`;
- `ref.ref_id`;
- `ref.source_module`;
- `ref.source_path`;
- `ref.source_snapshot_id`;
- `observed_at`.

Mechanical source: `stock_processing_service/contracts/market_cognition.py:EvidenceRef`, `EvidenceItem`, `MarketKnowledgeBundle`, `MarketEvidenceSnapshot`; `stock_processing_service/application/services/market_cognition/knowledge_evidence.py:MarketKnowledgeBundleBuilder`, `MarketEvidenceAdapter`, `_item`; serialization in `market_public/private/market_analysis.py:_evidence_item`.

### Frozen extraction boundary

Current evidence keys are limited to:

- engine decision fields: allow trade, trade mode, blocking rule, position limit, next-day strategy;
- market regime labels: broad market regime, short-term sentiment, mainline environment;
- next trade date and setup summary/focus/reason/rationale fields;
- watchlist stock/theme/reason/date/decision/setup fields;
- mainline name, lifecycle, state, and strong-stock count.

Module coverage can list additional modules without exposing their content as analytical evidence. In particular, `daily_recap_essentials`, `theme_reviews`, `limit_up_theme_events`, `new_high_summary`, and `seat_money_summary` are not currently extracted into evidence items by `MarketEvidenceAdapter`.

## 4. Epistemic ownership taxonomy

The v1 interpretation contract freezes this closed taxonomy:

| Class | Meaning |
|---|---|
| `DIRECT_OBSERVED` | A value mechanically observed from a designated direct source, with direct-source semantics frozen by contract |
| `DERIVED_MARKET_EVIDENCE` | Market-owned projection of persisted producer knowledge, without claiming original direct observation |
| `ANALYST_CLAIM` | A factual assertion authored or selected by an analyst |
| `ANALYST_OPINION` | An analyst interpretation, forecast, or judgment |
| `APPROVAL_METADATA` | Review, approval, publication, or maturity metadata |
| `QUALITY_METADATA` | Coverage, presence, availability, failure, or measured quality metadata |
| `PROVENANCE_METADATA` | Source, version, identity, path, hash, trace, or temporal provenance |
| `UNKNOWN` | Origin cannot be mechanically established under the frozen contract |

### MVP binding

- All currently emitted `evidence[].value` fields are classified at the public projection layer as `DERIVED_MARKET_EVIDENCE`.
- Envelope execution fields are `QUALITY_METADATA`.
- Source, identity, path, hash, trace, and temporal fields are `PROVENANCE_METADATA`.
- Coverage and quality fields are `QUALITY_METADATA`.
- Recognized review fields are conditionally `APPROVAL_METADATA`.
- If a downstream consumer needs the original machine/analyst role and that role is not mechanically supplied, its classification MUST be `UNKNOWN`; the consumer MUST NOT guess.

Field-level mechanical `epistemic_status` emission is explicitly deferred. This taxonomy is an interpretation and compatibility contract only; it does not alter payload shape or claim that current code can identify every original producer role.

## 5. Theme and lifecycle passthrough boundary

### FREEZE_NOW

- Mainline name, lifecycle source string, state source string, and strong-stock count MAY be frozen as passthrough evidence when emitted.
- Theme/product identity MAY be read only through the separate current public product capabilities.
- Julia retains interpretation and judgment authority.

### MUST NOT

- Market MUST NOT normalize, rank, translate, score, or reinterpret lifecycle strings in this v1 contract.
- Consumers MUST NOT treat `lifecycle`, `state`, or theme labels as a canonical lifecycle state machine, causal conclusion, confidence score, or investment permission.
- Consumers MUST NOT infer unextracted `theme_reviews` content from module coverage.

Normalized vocabulary, temporal semantics, confidence, and richer theme projection require a separate contract change.

## 6. Provenance contract

### Frozen guarantees

- `MarketProvenance.provenance_status` is derived, never caller asserted.
- With no selected profile, current results are explicitly `PROVENANCE_INCOMPLETE`.
- Source refs, evidence refs, public object refs, capability call ref, correlation ID, and `as_of` data cutoff MUST be preserved mechanically.
- Release identity and governance reference are currently `None`; consumers MUST NOT manufacture them.

Mechanical source: `market_public/provenance.py:MarketProvenance`, `MarketProvenanceProfile`, `MarketReleaseIdentity`, `ProvenancePredicate`; `market_public/provider.py:_provenance`.

### MVP / production boundary

- `PROVENANCE_INCOMPLETE` is admissible for the bounded MVP only when consumers preserve and expose the limitation.
- A capability-specific complete provenance profile, release identity, and governance reference are **REQUIRED_BEFORE_PRODUCTION**.
- They are not silently implied by this MVP freeze.

## 7. Analyst maturity and Workbench boundary

### Frozen principles

- `market.analysis.read` is the canonical aggregate Market analytical evidence base.
- Analyst Workbench review is optional semantic augmentation, not the exclusive Market truth source.
- Analyst output remains analyst claim/opinion or approval metadata; it cannot become Julia observation or final judgment.
- Draft, preview, unapproved, stale, or missing Workbench state MUST NOT be substituted for approved semantics.
- Separate Workbench `SessionStore` and `SnapshotStore` state under `tmp/analyst_workbench` is not canonical Julia-facing Market truth.

### Conditional recap passthrough

`MarketAnalysisReader._review_maturity` MAY expose ten recognized fields only when already embedded in `payload`, `recap_doc`, or `daily_review_v2`:

`review_maturity`, `source_mode`, `approval_mode`, `approved`, `approved_at`, `approved_by`, `published`, `published_at`, `analyst_reviewed`, `review_status`.

When absent, the contract requires `available=false`, `source_mode="unavailable"`, and `source="not_bound"`. Presence is passthrough and does not independently verify the separate Workbench state.

### Durable binding

A canonical durable binding of `analyst_reviewed`, `approved`, and `published` to an exact analytical payload is deferred to ME-2 and is REQUIRED_BEFORE_PRODUCTION whenever a consumer relies on analyst maturity for production admissibility.

## 8. Quality and coverage contract

### Frozen guarantees

- Coverage reports module presence/absence, row count, and declared missing fields.
- Quality reports `ready` or `partial`, module-presence score, missing modules, and issue strings.
- Current score is the ratio of ready canonical modules to total canonical modules.

### MUST NOT

- Consumers MUST NOT interpret the score as correctness, completeness of meaning, statistical reliability, causal support, confidence, model quality, or investment safety.
- Market MUST NOT claim per-field correctness, source reliability, or causal-support semantics in v1.

Richer quality semantics require a separate Owner-authorized contract and implementation task.

## 9. Julia / Market authority boundary

Market MAY guarantee:

- exact request and source-date semantics;
- envelope state and typed failures;
- mechanical projection of listed evidence fields;
- evidence/source/public-object identity preservation;
- coverage and bounded quality metadata;
- conditional passthrough of embedded maturity;
- explicit provenance incompleteness.

Julia/Core MUST retain authority over:

- admissibility thresholds not mechanically frozen by Market;
- interpretation and semantic weighting;
- strategy applicability and trading permission;
- hypothesis generation and causal synthesis;
- `ACCEPTED`, `CHALLENGED`, and `DEFERRED` outcomes;
- final investment judgment.

No Market field in this v1 contract is a Julia final judgment. No Workbench field transfers Julia judgment authority to Market or to an analyst.

## 10. Deferred items

| Deferred item | Required before |
|---|---|
| Mechanical field-level `epistemic_status` producer-role binding | Production use that depends on original role |
| Complete theme review extraction and unified mainline/theme semantic model | ME-2 / production semantic reliance |
| Lifecycle vocabulary, temporal transitions, and confidence semantics | ME-2 / production semantic reliance |
| Capability-specific complete provenance profile | Production |
| Release identity and governance reference | Production |
| Durable canonical analyst-review/approval/publication binding | ME-2, or production use that relies on maturity |
| Correctness/reliability/causal-support quality semantics | ME-2 / production quality reliance |
| Explicit Julia sufficiency threshold profile | Julia/Core contract task |

These deferrals do not permit implementation under this freeze. Each requires explicit Owner authorization and a new contract version where applicable.

## 11. Non-goals

This candidate does not:

- modify `market_public` or production source;
- add a schema field or runtime capability;
- bind Workbench to Market;
- implement epistemic metadata;
- normalize lifecycle;
- create a complete provenance profile;
- restore `market.snapshot`, `market.alerts`, `DomainObservationEnvelope`, `julia_domain_adapter`, or old Market Brain paths;
- make Approved Workbench the sole Julia entry point;
- transfer final judgment authority from Julia;
- authorize merge to main.

## 12. Versioning and change control

- Candidate version: `MARKET_ANALYTICAL_EVIDENCE_CONTRACT_v1`.
- The candidate becomes binding only after Owner acceptance of this exact document version.
- Any change to capability identity, request date semantics, envelope state semantics, evidence identity fields, taxonomy, authority boundary, or deferral classification requires `v2` review.
- Additive optional metadata may be reviewed as a minor revision only if it cannot change existing READY/EMPTY/FAILURE semantics or reinterpret existing fields.
- Implementation changes cannot silently expand this contract; tests passing without a source-grounded contract change are not acceptance authority.
