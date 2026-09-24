# HISTORICAL_COGNITION_ACCEPTANCE_CONTRACT_v1

## Authority binding

- `TASK_ID = POST-RD1-E1-E-HISTORICAL-COGNITION-ACCEPTANCE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD / JULIA_REVIEW_OVERLAY_V1_FROZEN_HEAD = 97a8eb4257cdbde75ee632884c5bd1cbb6bc442c`
- Architecture authority: POST-RD1 Julia Financial Analyst Detailed Architecture v0.5; v0.4 supplies only historical/failure fixture shape and quantitative-gate material explicitly carried forward by v0.5.
- Market authority: `MARKET_ANALYTICAL_EVIDENCE_CONTRACT_v1` from Issue #417 comment `5807764213`.
- Strategy authority: `StrategyKnowledge.v1` from Issue #419 comment `5809205274`.
- Julia review authority: `JuliaReviewOverlay.v1` from Issue #420 comment `5809547275`.
- Current corpus truth: the required canonical StrategyKnowledge corpus, External Research evidence corpus, Julia cognition-generation identity, replay runtime, fixture runner, and overlay persistence are not implemented or materialized. Therefore this document freezes the acceptance contract and required fixture plan, not a claim that historical acceptance has passed.

## Purpose

Historical cognition acceptance proves that POST-RD1 can perform a fresh, source-bound Julia review under historical input constraints. It is not an ordinary outcome-prediction backtest and MUST NOT be reduced to whether later market rise or fall was guessed correctly.

Acceptance evaluates:

- authority boundary;
- evidence binding;
- fresh cognition;
- counterevidence handling;
- anti-hindsight;
- ownership preservation;
- information-cutoff discipline;
- typed degradation and failure behavior.

## 1. Role split

| Participant | Frozen role | Forbidden promotion |
|---|---|---|
| Market | Exact-date evidence, envelope identity/state, provenance, coverage, bounded quality, optional embedded maturity. | Market evidence becoming Julia truth, approval, applicability, or judgment. |
| External Research | Externally owned evidence with source provenance and explicit availability/failure state. | External claim becoming Market truth, verified fact, or Julia authorship. |
| StrategyKnowledge | Source-grounded questions, evidence requirements, counterevidence, invalidations, dependencies, revisions, and maturity. | Strategy applicability decision, action, final thesis, or Julia judgment. |
| Workbench / analyst | Optional canonical analyst claim/opinion/approval augmentation when available. | Mandatory intake, ownership transfer, silent approval, or semantic judgment authority. |
| JuliaReviewOverlay | Julia-owned interpretation, item disposition, causal synthesis, review-level disposition, and semantic judgment binding. | Rewriting upstream provenance or minting upstream truth. |
| DailyResearchCycle | Lifecycle, continuity, persistence, and idempotency. | Semantic acceptance, disposition, or judgment authorship. |
| Runtime / fixture harness | Input presentation, deterministic checks, persistence binding, and reporting. | Semantic disposition or judgment minting. |

## 2. Market evidence intake checks

Every ready historical fixture MUST verify:

- the exact canonical `YYYY-MM-DD` `trade_date` was requested;
- `MarketResultEnvelope` operation/data/failure/provenance identity is preserved;
- exact-date `SUCCESS/EMPTY` remains distinct from failure;
- no other date, latest snapshot, synthetic payload, or alternate producer is substituted;
- Market refs, source refs, public-object refs, snapshot/content identities, coverage, quality, and explicit limitations remain intact;
- Market evidence remains Market-owned.

Contractual absence is not proof that no market activity occurred. It is explicit missing evidence unless a separately frozen Market semantic states more.

## 3. External Research checks

Every ready fixture using external research MUST preserve:

- external source identity and document/span refs;
- source-available time;
- content identity where frozen;
- partial-success/partial-failure state;
- extraction/provenance limitations.

Unavailable or partially failed external research MUST NOT be converted into fabricated completeness. External evidence MUST NOT be relabeled as Market observation, Julia observation, or verified truth.

## 4. Strategy cognition activation checks

Every ready fixture MUST bind:

- exact `StrategyKnowledge` version(s);
- `strategy_framework_version`;
- relevant maturity dimensions;
- evidence requirements;
- positive/negative/required evidence;
- counterevidence;
- invalidating conditions;
- applicability questions;
- observation-window and data-dependency questions;
- explicit `UNKNOWN` for unavailable semantics.

StrategyKnowledge activation means Julia considers its questions and dependencies. It does not mean StrategyKnowledge decides applicability, market stage, action, thesis, or judgment.

## 5. Competing interpretation and counterevidence checks

Ready fixtures MUST retain:

- all competing interpretations and their owners;
- contradictory evidence refs on both sides;
- challenged input without deletion or rewriting;
- counterevidence and failure modes;
- Julia's reason for accepting, challenging, deferring, or remaining review-level inconclusive.

A vote count, evidence-count threshold, module-presence score, or provider majority cannot by itself mint Julia judgment.

## 6. Regime applicability checks

Regime evidence and StrategyKnowledge applicability questions may inform Julia reasoning. They MUST NOT automatically produce:

- `strategy_applicable=true`;
- `strategy_applicable=false`;
- final market stage;
- buy/sell/hold;
- final thesis;
- Julia judgment.

Julia retains interpretation, applicability synthesis, causal synthesis, and judgment authority.

## 7. Fresh Julia judgment and anti-hindsight

For every ready fixture, JuliaReviewOverlay MUST be generated from the frozen historical input set and information cutoff. The fixture MUST prove:

- accepted/challenged/deferred context and review-level `INCONCLUSIVE`, where applicable, are bound;
- judgment is fresh for the exact input, cutoff, strategy framework, policy, and StrategyKnowledge versions;
- no later market outcome, later correction, later framework, or later policy is injected;
- deterministic projection/contract layers remain identical where identity is frozen;
- natural-language wording need not be byte-identical;
- Runtime and fixture harness do not mint semantic conclusions;
- cognition generation identity is bound, or explicitly `UNKNOWN` only while that identity contract remains deferred.

Historical verification data MAY be present in a sealed evaluation plane, but it MUST NOT enter the cognition input plane before judgment. Post-cutoff information can be used only by a separately bound later review.

## 8. Information-cutoff compliance

A fixture MUST reject or exclude input whose `source_available_at` is later than `information_cutoff`. It MUST NOT:

- project later corrections backward;
- select a current strategy/policy version by default;
- close an open historical effective boundary retroactively;
- treat missing version binding as reproducible;
- claim deterministic replay when a required version is `UNKNOWN`.

## 9. Ownership preservation

Every ready fixture MUST preserve:

- Market ownership and provenance;
- external-source ownership;
- analyst/Workbench ownership where optional canonical augmentation is present;
- StrategyKnowledge source lineage and version;
- Julia authorship of interpretation/disposition/judgment;
- byte-identical canonical approved analyst augmentation before and after review, when present.

A disposition changes Julia's research relation to an input; it never changes the input's origin, truth status, or owner.

## 10. Expected-outcome philosophy

Fixture expectations MUST be expressed as:

- required contract properties;
- allowed disposition ranges;
- required reasons and evidence refs;
- explicit missing evidence and contradictions;
- forbidden authority violations.

Retrospective market outcome MAY be an auxiliary sealed observation only when explicitly source-authorized. It MUST NEVER be the sole PASS criterion and MUST NEVER be exposed to Julia before fresh judgment.

## 11. Readiness rule

No historical row may be promoted to `READY` until all required source identities, exact-date evidence bindings, external evidence states, StrategyKnowledge versions, cutoff inputs, and expected contract properties are materialized and auditable.

If material is absent, the row MUST remain `SOURCE_MISSING / NOT_READY`. Missing rows count as source blockers; they MUST NOT be replaced with synthetic evidence, inferred narrative, or an outcome label.

## 12. Non-goals

This contract does not implement a fixture runner, LLM invocation, replay runtime, Market ingestion, external connector, StrategyKnowledge parser/detector, JuliaReviewOverlay runtime, DailyResearchCycle, persistence, publication path, UI, or production source. It does not restore an ApprovedWorkbench-exclusive intake assumption and does not authorize E2 implementation.
