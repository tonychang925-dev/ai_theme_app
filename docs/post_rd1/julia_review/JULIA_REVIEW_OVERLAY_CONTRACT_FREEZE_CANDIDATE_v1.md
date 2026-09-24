# JULIA_REVIEW_OVERLAY_CONTRACT_FREEZE_CANDIDATE_v1

## Authority binding

- `TASK_ID = POST-RD1-E1-D-JULIA-FINANCIAL-REVIEW-IR-FREEZE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD / STRATEGY_KNOWLEDGE_V1_FROZEN_HEAD = 4669942734dffb292fa3fc75acddbad79d95476f`
- Architecture authority: POST-RD1 Julia Financial Analyst Detailed Architecture v0.5.
- Market authority: `MARKET_ANALYTICAL_EVIDENCE_CONTRACT_v1`, adopted from Issue #417 comment `5807764213`.
- Strategy authority: `StrategyKnowledge.v1`, adopted from Issue #419 comment `5809205274`.
- Current source truth: no `JuliaReviewOverlay`, Julia review persistence, DailyResearchCycle implementation, or Julia judgment runtime exists in this repository at the start head. Historical M8 cognition material is noncanonical donor context and supplies no normative rule.
- This document is a contract candidate, not a schema implementation, runtime design, persistence design, LLM invocation protocol, or Owner acceptance record.

## Contract identity

`JuliaReviewOverlay.v1` is the Julia-owned semantic review result. It records Julia's interpretation and disposition of upstream evidence and claims, unresolved inputs, causal reasoning, and final Julia judgment binding.

```text
Market / Workbench / StrategyKnowledge / External Research
= upstream evidence, claims, provenance, or cognition scaffold

JuliaReviewOverlay
= Julia-owned interpretation + disposition + judgment

DailyResearchCycle
= lifecycle / continuity / persistence / idempotency

Runtime
≠ semantic judgment authority
```

## 1. Field contract

These are contract-level semantics, not storage fields or implementation guarantees. `FREEZE_NOW` freezes meaning and required binding; it does not authorize source implementation.

| Field | Disposition | Contract semantics | Required boundary |
|---|---|---|---|
| `review_id` | `FREEZE_NOW` | Stable identity of this immutable semantic review result. | MUST NOT be reused by a later or revised review. |
| `workbench_ref` | `FREEZE_NOW` as optional semantic reference | Identity of Workbench material considered by Julia, when present. | MUST remain analyst-owned and MUST NOT imply that ApprovedWorkbenchEnvelope is always present. |
| `snapshot_id` | `FREEZE_NOW` | Identity of the exact composed input snapshot consumed by the review. | MUST bind the actual Market, Workbench, external, and StrategyKnowledge identities considered; it MUST NOT become a second Market truth identity. |
| `information_cutoff` | `FREEZE_NOW` | Julia's effective knowledge boundary for this review. | MUST be explicit or `UNKNOWN`; evidence outside the boundary MUST NOT be silently treated as considered. |
| `strategy_framework_version` | `FREEZE_NOW` | Exact strategy framework version used by Julia. | MUST be explicit or `UNKNOWN`; a newer framework MUST NOT be substituted during historical replay. |
| `policy_version` | `FREEZE_NOW` | Exact review/admissibility policy version used by Julia. | MUST be explicit or `UNKNOWN`; policy absence MUST NOT be hidden. |
| `accepted` | `FREEZE_NOW` | Item-level collection of upstream inputs Julia accepts as current research premises. | MUST preserve original ownership and MUST NOT mean fact verification. |
| `challenged` | `FREEZE_NOW` | Item-level collection of inputs Julia challenges for stated evidence, contradiction, strategy, causal, or source reasons. | MUST preserve the challenged input and its provenance. |
| `deferred` | `FREEZE_NOW` | Item-level collection where current information is insufficient to reasonably accept or challenge and later evidence is required. | MUST NOT represent a completed review-object-level directional result. |
| `inconclusive` | `FREEZE_NOW` | Explicit review-object-level disposition used when review execution completes but Julia cannot form a sufficiently grounded directional disposition. | MUST NOT be an item-level evidence bucket and MUST NOT silently replace `deferred`. |
| `external_evidence_refs` | `FREEZE_NOW` | References to externally owned research/evidence consumed. | MUST preserve external provenance and MUST NOT recast external content as Julia or Market truth. |
| `strategy_refs` | `FREEZE_NOW` | References and exact versions of StrategyKnowledge items consumed. | MUST preserve source-grounded scaffold ownership; applicability remains Julia cognition. |
| `missing_evidence` | `FREEZE_NOW` | Explicit semantic evidence gaps relevant to the review. | MUST NOT convert exact-date contractual absence into a claim that no market activity occurred. |
| `contradictions` | `FREEZE_NOW` | Explicit conflicting inputs/evidence retained for Julia review. | MUST preserve all sides and their ownership; no side may be silently overwritten. |
| `causal_interpretation` | `FREEZE_NOW` | Julia's reasoned interpretation of causal or explanatory relationships. | MUST be distinguishable from observation, analyst claim, strategy source, and external fact. |
| `open_questions` | `FREEZE_NOW` | Questions Julia could not resolve within the information cutoff. | MUST NOT be converted into automatic failure, approval, or action. |
| `watch_items` | `FREEZE_NOW` | Inputs or questions Julia marks for later attention. | MUST NOT schedule execution or imply that later evidence automatically resolves the item. |
| `confidence` | `FREEZE_NOW` for semantic presence only | Confidence value, including explicit `null`/`UNKNOWN`. | No numeric threshold, weighting, calibration, admissibility, or trading implication is frozen. |
| `Julia_judgment` | `FREEZE_NOW` | Julia-owned final semantic judgment binding for this review. | MUST remain distinct from upstream evidence and MUST NOT be pre-populated by Market, Workbench, StrategyKnowledge, or Runtime. |

The explicit `inconclusive` concern is resolved as a **review-object-level disposition field**, not another item collection. Item-level insufficiency belongs in `deferred`; completed review-level inability to form a grounded directional disposition belongs in `inconclusive`.

Every `accepted`, `challenged`, or `deferred` entry MUST preserve, or explicitly mark `UNKNOWN`, the upstream item reference, original owner/provenance, Julia disposition reason, supporting/conflicting evidence references, and version/cutoff inheritance from the review. An `inconclusive` review-object record MUST likewise preserve the reason Julia could not form a sufficiently grounded directional disposition and MUST NOT hide accepted, challenged, deferred, missing, or contradictory inputs.

## 2. Ownership preservation

### MUST

- Market evidence MUST remain Market-owned evidence with its original refs, identities, provenance, coverage, quality, and maturity semantics.
- Workbench analyst material MUST remain analyst-owned claims, opinions, or approval metadata.
- External research MUST remain externally owned evidence with its own provenance.
- StrategyKnowledge MUST remain a source-grounded cognition scaffold and MUST NOT become an executable decision engine.
- JuliaReviewOverlay MUST identify Julia's interpretation/disposition separately from every upstream owner.
- Julia MAY cite, accept, challenge, defer, interpret, synthesize, or judgment-bind upstream material while preserving its original provenance.

### MUST NOT

- Julia MUST NOT mutate upstream provenance or source content.
- Julia MUST NOT represent an upstream claim as originating from Julia.
- `ACCEPTED` MUST NOT change a source class to `SOURCE_VERIFIED`, transfer ownership, or reverify a fact.
- Runtime MUST not become semantic author by minting dispositions or judgment on Julia's behalf.
- DailyResearchCycle lifecycle state MUST NOT imply semantic acceptance.

## 3. Evidence and version binding

A review MUST retain, or explicitly mark `UNKNOWN`, bindings for:

1. exact Market result/evidence identities consumed, including request/correlation, evidence/source/public-object refs, and available snapshot/content identities;
2. `external_evidence_refs`;
3. `strategy_refs` with exact StrategyKnowledge versions;
4. `information_cutoff`;
5. `strategy_framework_version`;
6. `policy_version`;
7. `missing_evidence`;
8. `contradictions`;
9. `open_questions`;
10. `watch_items`.

Market references MUST preserve the frozen Market envelope semantics. They MUST not reinterpret exact-date absence, bounded coverage/quality, incomplete provenance, unbound maturity, or unavailable field-level epistemic origin.

Where physical reference representation, storage, indexing, or replay lookup is not yet defined, this contract freezes the semantic requirement and leaves realization `DEFERRED`.

## 4. Information cutoff

`information_cutoff` defines the effective knowledge horizon Julia used. It is not automatically the Market `trade_date`, `as_of`, Workbench approval time, commit time, or current wall-clock time.

- It MUST be explicitly recorded or marked `UNKNOWN`.
- Evidence produced or discovered after the cutoff MUST NOT be silently treated as part of the original review.
- A later review may use a later cutoff, but it MUST create a new review identity and preserve the earlier result.
- Historical replay MUST use the cutoff and versions actually effective at review time or explicitly report `UNKNOWN`; it MUST NOT claim reproducibility after substituting later knowledge.

## 5. Causal interpretation boundary

`causal_interpretation` MAY capture Julia's reasoned explanation, causal synthesis, relationships among evidence, conflict resolution, and limitations.

It MUST:

- remain visibly Julia-owned interpretation;
- cite supporting and conflicting evidence refs where available;
- preserve missing-evidence and contradiction visibility;
- distinguish correlation, mechanism, hypothesis, and judgment where those distinctions are material.

It MUST NOT:

- be represented as mechanically verified truth merely because it is stored in the overlay;
- overwrite Market observation, analyst claim, strategy source knowledge, or external source fact;
- erase counterevidence;
- become a deterministic strategy engine;
- issue runtime buy/sell/hold behavior.

## 6. Julia_judgment boundary

`Julia_judgment` is Julia-owned semantic output for the completed review object. At contract level it MUST retain:

- judgment identity within the immutable review, where that identity MUST NOT be reused by another judgment;
- relation to `accepted`, `challenged`, `deferred`, and review-level `inconclusive`;
- supporting/conflicting/external/strategy evidence references;
- `information_cutoff`;
- `strategy_framework_version` and `policy_version`;
- `confidence` or explicit `null`/`UNKNOWN`;
- unresolved contradiction and missing-evidence visibility.

The judgment is a synthesis, not a vote count over items. It MAY coexist with accepted premises, challenged premises, deferred items, and unresolved questions. It MUST NOT be inferred automatically from presence, count, maturity, or coverage.

`Julia_judgment` MUST NOT be pre-populated by Market, Workbench, StrategyKnowledge, or Runtime. This contract does not define buy/sell/hold runtime behavior, order semantics, execution permission, or an investment-action command. Any production action contract requires separate Owner authorization.

## 7. Confidence boundary

`confidence` is frozen as semantic presence only. It MAY be `null` or `UNKNOWN`.

If a numeric value is eventually represented, it remains uncalibrated Julia-reported confidence unless a separate confidence policy is frozen. This contract does not define:

- numeric range or normalization;
- thresholds;
- weights;
- calibration;
- admissibility;
- trading implications.

`confidence` MUST NOT override evidence refs, contradictions, missing evidence, or judgment semantics.

## 8. DailyResearchCycle authority split

JuliaReviewOverlay owns semantic review result and judgment meaning. DailyResearchCycle owns lifecycle, continuity, persistence, and idempotency mechanics.

### MUST

- Runtime MAY persist or bind a disposition after Julia cognition, while preserving Julia authorship and input identity.
- DailyResearchCycle MUST preserve review identity, versions, information cutoff, and upstream ownership.
- Lifecycle completion MUST remain distinct from semantic acceptance or judgment quality.

### MUST NOT

- DailyResearchCycle MUST NOT imply semantic acceptance.
- Runtime MUST NOT mint `ACCEPTED`, `CHALLENGED`, `DEFERRED`, or `INCONCLUSIVE` without Julia cognition.
- Lifecycle retry or idempotency logic MUST NOT synthesize a new semantic result.
- Continuity state MUST NOT rewrite an immutable overlay.

## 9. Composition boundary

Julia Research Product MAY compose:

1. frozen `MarketResultEnvelope` evidence;
2. optional approved analyst semantic augmentation where canonically available;
3. External Research Evidence;
4. StrategyKnowledge;
5. JuliaReviewOverlay.

ApprovedWorkbenchEnvelope is optional and MUST NOT be assumed always present. Optional Workbench augmentation remains analyst-owned and cannot become Julia truth, exclusive entry, or a second Market truth path.

Composition MUST preserve each participant's ownership, version, provenance, and optionality. It MUST NOT manufacture missing Market semantics, promote unbound analyst maturity, or pre-populate Julia judgment.

## 10. Deferred items

The following remain deferred and are not implemented by this freeze:

- physical overlay schema, storage, migration, and persistence;
- DailyResearchCycle implementation;
- LLM invocation and cognition protocol;
- Workbench wiring;
- UI or publication path;
- deterministic reference encoding and replay index;
- confidence policy;
- buy/sell/hold or order-action contract;
- review revision/supersession storage;
- automated provenance verification;
- production governance and release identity.

## 11. Non-goals

This candidate does not implement runtime, persistence, LLM invocation, DailyResearchCycle, Workbench wiring, Market capability, StrategyKnowledge parser/engine, UI, or production source; does not modify upstream contracts; does not define trading-action runtime behavior; and does not authorize merge to main or production use.

## 12. Supersession and change control

- Candidate version: `JuliaReviewOverlay.v1`.
- The candidate becomes binding only after Owner acceptance of this exact document version.
- Only an Owner-approved later contract version may supersede it.
- Changes to ownership, disposition semantics, item/review-level boundaries, evidence/version binding, causal interpretation, Julia judgment authority, confidence boundary, or DailyResearchCycle authority require a new contract review.
- Additive metadata may be reviewed only if it cannot transfer judgment authority, erase unresolved evidence, or reinterpret existing dispositions.
