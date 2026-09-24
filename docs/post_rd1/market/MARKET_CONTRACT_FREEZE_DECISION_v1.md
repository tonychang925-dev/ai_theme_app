# MARKET_CONTRACT_FREEZE_DECISION_v1

## Decision

`READY_TO_FREEZE = YES`

Scope: bounded Market Analytical Evidence **MVP contract** at `market.analysis.read`.

Rationale: the exact-date behavior, envelope semantics, typed empty/failure separation, evidence references, source identities, content hashes, coverage envelope, bounded quality semantics, and Julia/Market authority split are mechanically grounded. Remaining gaps can be truthfully frozen as explicit limitations or deferred future contract work without pretending they already exist.

This is not production-readiness acceptance. Complete production provenance and any production reliance on analyst maturity require the deferred work listed below.

## Binding

- `TASK_ID = POST-RD1-E1-B-MARKET-ANALYTICAL-EVIDENCE-CONTRACT-FREEZE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD / E1-A_ACCEPTED_HEAD = ea9032cf45832ea5f4ad801b82c3af023d291abe`
- Candidate: `MARKET_ANALYTICAL_EVIDENCE_CONTRACT_FREEZE_CANDIDATE_v1.md`

## Gap dispositions

| # | E1-A unresolved gap | Disposition | Rationale and current source evidence |
|---|---|---|---|
| 1 | `market.analysis.read` as canonical aggregate evidence capability | `FREEZE_NOW` | `CAPABILITIES` and `MarketAnalysisReadRequest` declare it; `_MarketPublicProvider._execute_market_analysis` is the sole dispatch path; `MarketAnalysisReader._project` is the aggregate projection |
| 2 | Exact-date and no-substitution semantics | `FREEZE_NOW` | `_invalid_request_reason` requires canonical `YYYY-MM-DD`; repository query is exact `trade_date`; `_project` rejects row/payload date mismatch; no latest-date fallback exists |
| 3 | `SUCCESS/EMPTY` for contractual missing data | `FREEZE_NOW` | `_execute_market_analysis` maps private `EMPTY` to `SUCCESS/EMPTY/None`; missing snapshot does not create synthetic evidence |
| 4 | Typed failure / empty separation | `FREEZE_NOW` | `MarketResultEnvelope.__post_init__` forbids `FAILURE+EMPTY`; `_execute_market_analysis` preserves typed public failures |
| 5 | Transport-neutral envelope authority | `FREEZE_NOW` | `MarketResultEnvelope`, status enums, and failures are declared in `market_public/contracts.py`; provider emits that contract |
| 6 | Evidence refs and source refs | `FREEZE_NOW` | `EvidenceRef` and `EvidenceItem` require ref fields; `_evidence_item` serializes them; `_provenance` copies ref IDs and source refs |
| 7 | Content and snapshot identity | `FREEZE_NOW` | `MarketKnowledgeBundleBuilder` and `MarketEvidenceAdapter` derive bundle/evidence IDs and canonical hashes; `_project` exposes them |
| 8 | Field-level epistemic origin | `DEFER` | Current items identify module/path/snapshot but do not emit original machine/analyst role. Freeze the eight-class taxonomy and require `UNKNOWN` rather than guessing; mechanical field binding is deferred |
| 9 | Theme semantic normalization | `DEFER` | Mainline name/state evidence exists, but `MarketEvidenceAdapter` does not extract `theme_reviews`; separate product capabilities do not establish one unified semantic model |
| 10 | Lifecycle normalization | `DEFER` | Mainline lifecycle strings pass through, but no normalized vocabulary, temporal transition model, or confidence semantics exists |
| 11 | Complete provenance profile | `DEFER` for MVP; `REQUIRED_BEFORE_PRODUCTION` | `_provenance` passes profile `None`; `MarketProvenance` therefore derives `PROVENANCE_INCOMPLETE`. Preserve this explicit state for MVP; select and enforce predicates before production |
| 12 | Release identity | `DEFER` for MVP; `REQUIRED_BEFORE_PRODUCTION` | `MarketReleaseIdentity` exists, but `_provenance` supplies `market_release_identity=None` |
| 13 | `governance_ref` | `DEFER` for MVP; `REQUIRED_BEFORE_PRODUCTION` | Field exists on `MarketProvenance`, but `_provenance` does not supply a value |
| 14 | Durable `analyst_reviewed` binding | `DEFER` to ME-2; production-required when relied on | `_review_maturity` exposes the field only if embedded; Workbench `IN_REVIEW` is tmp session state and is not queried by Market |
| 15 | Durable `approved` binding | `DEFER` to ME-2; production-required when relied on | Workbench approval is tmp `SessionStore`/`SnapshotStore`; composed report metadata is not written back to canonical recap snapshot |
| 16 | Durable `published` binding | `DEFER` to ME-2; production-required when relied on | Workbench `PUBLISHED` updates tmp session state; `_review_maturity` does not bind it to the exact Market payload |
| 17 | Workbench exclusive-entry assumption | `BLOCK` as proposed architecture | Contradicts current multi-capability boundary and the canonical aggregate evidence rule. It is rejected and must not be introduced |
| 18 | Analyst output becoming Julia observation/judgment | `BLOCK` | Authority split forbids it; analyst content remains claim/opinion or approval metadata |
| 19 | Draft/unapproved maturity fallback | `BLOCK` | No draft or preview state may be represented as approved/published; absent canonical maturity remains explicitly not bound |
| 20 | Quality as module coverage/presence ratio | `FREEZE_NOW` with boundary | `SourceCoverage` and `QualityEnvelope` mechanically define presence/count/score semantics |
| 21 | Correctness/reliability/causal-support quality semantics | `DEFER` | Current score does not measure field correctness, source reliability, causal support, confidence, or investment safety |
| 22 | Julia admissibility thresholds | `DEFER` to Julia/Core | Market exposes limitations; it does not freeze consumer admissibility policy |
| 23 | Julia interpretation and final judgment authority | `FREEZE_NOW` | Market evidence and Workbench augmentation cannot synthesize causal conclusions or final investment judgment |
| 24 | Historical donor paths (`market.snapshot`, `market.alerts`, old adapter/envelope) | `BLOCK` | Not current `CAPABILITIES` or current `MarketResultEnvelope`; Issue #415 is noncanonical |

## Minimal MVP freeze set

The Owner may freeze only this bounded set:

1. exact-date `MarketAnalysisReadRequest`;
2. `MarketResultEnvelope` state/failure semantics;
3. valid exact-date `SUCCESS/EMPTY`;
4. no fallback, substitution, or synthetic evidence;
5. listed evidence extraction and `EvidenceRef` preservation;
6. source/public-object refs and hash-derived identities;
7. module coverage and presence-ratio quality;
8. conditional embedded maturity passthrough with explicit not-bound state;
9. eight-class epistemic interpretation taxonomy with `UNKNOWN` for unverifiable origin;
10. passthrough theme/lifecycle strings without semantic normalization;
11. explicit `PROVENANCE_INCOMPLETE`;
12. Julia/Core final interpretation and judgment authority.

## Deferred items that do not block MVP

- Mechanical field-level epistemic origin binding.
- Complete `theme_reviews` extraction and unified theme/mainline model.
- Normalized lifecycle vocabulary, transitions, and confidence.
- Capability-specific complete provenance profile.
- Release identity and governance reference.
- Durable canonical analyst-review/approval/publication binding.
- Correctness/reliability/causal-support quality semantics.
- Explicit Julia/Core sufficiency threshold profile.

## Production blockers

These do not block the bounded MVP freeze but MUST be resolved before production reliance:

1. capability-specific complete provenance profile;
2. release identity and governance reference;
3. durable maturity binding, whenever analyst-review/approval/publication semantics affect production admissibility;
4. field-level epistemic origin, whenever original producer role affects production admissibility;
5. richer quality semantics, whenever correctness/reliability/causal-support claims affect production decisions.

## Rejected blockers

No additional implementation work is required merely to freeze the MVP interpretation of current partial semantics. A truthful contract can preserve passthrough values, explicit provenance incompleteness, and explicit maturity unavailability without inventing metadata.

## NCF review

This documentation-only candidate does not introduce fallback, synthetic success, bypass, production-source change, or critical-fallback behavior. Review is aligned with the accepted Issue #389 schema-v2 NCF authority. No NCF authority file was modified and no bypass was used.
