# STRATEGY_KNOWLEDGE_FREEZE_DECISION_v1

## Decision

`READY_TO_FREEZE = YES`

Scope: `StrategyKnowledge.v1` as a **cognition knowledge scaffold contract**, including its field semantics, evidence/condition boundaries, source provenance requirements, append-only revision lineage, effective-time replay rule, and independent maturity dimensions.

The freeze is ready because the architecture authority and frozen Market contract define a coherent non-decision boundary, while current repository source truth shows that all runtime and storage semantics are absent. The truthful disposition is therefore to freeze conceptual semantics and provenance discipline now, defer implementation contracts, and block every direct-decision interpretation.

This is not production-readiness acceptance and does not authorize implementation.

## Binding

- `TASK_ID = POST-RD1-E1-C-STRATEGY-COGNITION-KNOWLEDGE-FREEZE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD = e07030f570b596c2f67200c3274bcc372731f019`
- Candidate: `STRATEGY_KNOWLEDGE_CONTRACT_FREEZE_CANDIDATE_v1.md`
- Source provenance: `STRATEGY_SOURCE_PROVENANCE_CONTRACT_v1.md`
- Upstream Owner freeze: Issue #417 comment `5807764213`

## Source-truth basis

At `START_HEAD`, repository search finds no `StrategyKnowledge`, `StrategyKnowledgeRevision`, strategy-framework version binding, strategy parser, deterministic strategy detector, or strategy engine. Consequently, no current implementation can establish runtime behavior, persistence, extraction correctness, review identity verification, or production readiness.

The freeze instead relies on:

1. POST-RD1 Julia Financial Analyst Detailed Architecture v0.5 for conceptual semantics;
2. constitutional rules C-00 and C-12;
3. ADR-032's distinction between structuring research questions and pre-answering Julia judgment;
4. the Owner-frozen Market Analytical Evidence MVP contract;
5. explicit `DEFER` or `BLOCK` dispositions for every semantic not supported by current source truth.

## Concern dispositions

| # | Concern | Disposition | Rationale |
|---|---|---|---|
| 1 | StrategyKnowledge as cognition scaffold rather than decision engine | `FREEZE_NOW` | This is the core architecture authority and preserves C-00, C-12, ADR-032, and the Market/Julia authority split. |
| 2 | Stable `strategy_id` / immutable `strategy_version` lineage | `FREEZE_NOW` | Required for append-only revisions, supersession, and effective-time replay; no storage format is implied. |
| 3 | Descriptive `name` and source-grounded `definition` | `FREEZE_NOW` | Labels and definitions can be frozen as cognition metadata when extraction provenance is retained. |
| 4 | `required_evidence`, `positive_evidence`, `negative_evidence` | `FREEZE_NOW` | These organize Julia questions and Market semantic dependencies; they do not evaluate sufficiency or applicability. |
| 5 | Counterevidence and failure modes | `FREEZE_NOW` | Required by ADR-032 to keep challenges inspectable without deciding outcomes. |
| 6 | Source-grounded historical formation | `FREEZE_NOW` | Formation context can be organized with source provenance, but it is not a backtest verdict or causal proof. |
| 7 | `invalidating_conditions` as prompts | `FREEZE_NOW` | Invalidation prompts preserve safety-relevant cognition; runtime evaluation remains forbidden. |
| 8 | `applicable_market_regime` as questions/dependencies | `FREEZE_NOW` | Preserves regime reasoning without deciding final market stage or applicability. |
| 9 | `observation_window` as temporal question/boundary | `FREEZE_NOW` | Source-derived observation semantics are cognition knowledge; scheduling/execution semantics are not frozen. |
| 10 | `data_dependencies` with explicit `UNKNOWN` | `FREEZE_NOW` | Required to align semantic needs with the frozen Market contract without duplicating Market truth. |
| 11 | `confidence_policy` | `DEFER` | No Julia confidence/admissibility policy version exists; inventing weights, scores, or thresholds would violate the authority boundary. |
| 12 | `human_review_required` governance flag | `FREEZE_NOW` | Can truthfully declare that a separately governed review lane is required; it does not assert review occurred. |
| 13 | `implementation_refs` | `DEFER` | No authorized parser, detector, engine, storage, or runtime contract exists. |
| 14 | `source_document_refs` and `source_page_refs` | `FREEZE_NOW` | Required for source identity; unavailable page precision remains explicit `UNKNOWN`. |
| 15 | `extraction_provenance_refs` | `FREEZE_NOW` | Required to distinguish quote, normalized summary, model inference, and human correction. |
| 16 | Independent `maturity` dimensions | `FREEZE_NOW` | Architecture authority requires dimensions; collapsing them would hide partial capability. |
| 17 | Effective-time fields and `supersedes` | `FREEZE_NOW` | Required to prevent hindsight and silent historical rewrite; unknown boundaries remain explicit. |
| 18 | Physical schema and persistence | `DEFER` | No implementation exists and this is a contract-only task. |
| 19 | Source parser/extraction pipeline | `DEFER` | Explicitly forbidden by Issue #419 and unsupported by current source. |
| 20 | Narrow deterministic detector contract | `DEFER` | The exception boundary can be stated, but no detector expression, input contract, output vocabulary, or fail-closed behavior is defined. |
| 21 | Strategy applicability evaluator | `BLOCK` | Direct `strategy_applicable=true/false` output would violate Julia authority. |
| 22 | Final market-stage or action output | `BLOCK` | Buy/sell/hold and final market stage are outside StrategyKnowledge authority. |
| 23 | Final thesis or Julia judgment | `BLOCK` | C-00/C-12 and ADR-032 retain interpretation and judgment with Julia. |
| 24 | Market evidence redefinition | `BLOCK` | Market exact-date, provenance, coverage, quality, maturity, and epistemic limitations remain governed by the frozen Market contract. |
| 25 | Evidence presence becoming applicability | `BLOCK` | Presence is not truth, approval, admissibility, or applicability. |
| 26 | Manufacturing missing Market semantics | `BLOCK` | Unavailable semantics must remain `UNKNOWN`; provenance incompleteness cannot be overridden. |
| 27 | Silent historical provenance rewrite | `BLOCK` | Revisions are append-only; later human correction cannot become original source history. |
| 28 | New-framework replay of old reviews | `BLOCK` | Replay must use effective-time versions or explicitly report unknown version binding; reproducibility cannot be claimed after hindsight substitution. |
| 29 | Strategy-to-System mapping / JuliaReviewOverlay | `DEFER` | Explicitly outside Issue #419 scope. |

## Minimal frozen set

The Owner may freeze only this bounded set:

1. StrategyKnowledge as cognition knowledge scaffold, never an executable decision engine;
2. field-level semantic boundaries and provenance requirements in the candidate;
3. evidence requirements and conditions as questions/dependencies, not evaluators;
4. counterevidence, invalidation, failure-mode, observation-window, and applicability-question preservation;
5. Market semantic references with explicit `UNKNOWN` for unavailable semantics;
6. four-class extraction provenance distinctions;
7. append-only `StrategyKnowledgeRevision`;
8. effective-time supersession and anti-hindsight replay binding;
9. six independent maturity dimensions;
10. Julia/Core authority over applicability, causal synthesis, review outcome, thesis, action, and final judgment;
11. the narrow separately-frozen deterministic-detector exception and its derived-signal boundary.

## Deferred items that do not block this freeze

- storage schema, migrations, indexing, and repository implementation;
- source parser and extraction runtime;
- deterministic detector contract and implementation;
- confidence/admissibility policy and numeric scoring;
- Strategy-to-System mapping;
- JuliaReviewOverlay;
- production review workflow and durable approval/publication binding;
- reviewer identity verification and access control;
- automated source/provenance verification;
- production release identity and governance binding;
- historical corpus materialization and replay infrastructure.

## Production blockers

Before any production reliance, separately authorized work must resolve:

1. durable StrategyKnowledge storage and version lineage;
2. auditable source-span provenance and extraction records;
3. effective-time strategy/policy/framework version selection;
4. human-review authority, reviewer identity, and append-only correction handling;
5. any required narrow deterministic detector contract;
6. dependency-specific Market semantics, without overriding deferred Market limitations;
7. confidence/admissibility policy where it affects production decisions;
8. release identity and governance references.

## Rejected blockers

No parser, detector, engine, runtime, storage, Julia mapping, or production implementation is required to freeze the conceptual non-authority boundary. Freezing that boundary before implementation reduces the risk that future implementation silently converts knowledge organization into decision authority.

## NCF review

This documentation-only candidate introduces no production source, fallback, synthetic success, bypass, test mode, or runtime behavior. It is aligned with accepted Issue #389 schema-v2 NCF authority. No NCF-owned file was modified and no bypass was used.
