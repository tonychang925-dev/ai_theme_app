# STRATEGY_KNOWLEDGE_CONTRACT_FREEZE_CANDIDATE_v1

## Authority binding

- `TASK_ID = POST-RD1-E1-C-STRATEGY-COGNITION-KNOWLEDGE-FREEZE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD / MARKET_ANALYTICAL_EVIDENCE_MVP_CONTRACT_FROZEN_HEAD = e07030f570b596c2f67200c3274bcc372731f019`
- Architecture authority: POST-RD1 Julia Financial Analyst Detailed Architecture v0.5, constrained by the Owner freeze in Issue #417 comment `5807764213`.
- Market authority: `MARKET_ANALYTICAL_EVIDENCE_CONTRACT_v1` as frozen at the exact head above.
- Current repository source-truth: no `StrategyKnowledge`, `StrategyKnowledgeRevision`, strategy parser, strategy detector, or strategy engine implementation exists in this repository at the start head.
- This document is a conceptual contract candidate and implementation inventory. It is not a storage schema, parser specification, production implementation, or Owner acceptance record.

## Contract identity

`StrategyKnowledge.v1` is a **cognition knowledge scaffold**. It organizes source-grounded strategy questions, evidence expectations, dependencies, invalidation prompts, revisions, and maturity evidence for Julia.

The governing identity is:

```text
StrategyKnowledge
= cognition knowledge scaffold
≠ executable decision engine
```

It is therefore invalid to interpret satisfaction of any field or combination of fields as Julia's acceptance of a strategy, a market-stage conclusion, or an investment action.

## 1. StrategyKnowledgeItem field contract

All fields below are contract-level semantics, not implementation-ready guarantees unless explicitly marked `FREEZE_NOW`. A `FREEZE_NOW` classification freezes meaning and required provenance; it does not authorize a parser, runtime, storage change, or production source edit.

| Field | Freeze classification | Contract semantics | Required boundary |
|---|---|---|---|
| `strategy_id` | `FREEZE_NOW` | Stable identity for one strategy concept across versions and revisions. | MUST NOT encode a conclusion, action, or applicability result. |
| `strategy_version` | `FREEZE_NOW` | Immutable version identity within the append-only lineage. | MUST NOT be reused after supersession or silently rewritten. |
| `name` | `FREEZE_NOW` | Human-readable display label. | MUST NOT be treated as a definition, classification result, or truth claim. |
| `definition` | `FREEZE_NOW` | Source-grounded normalized definition of the strategy concept, preserving extraction provenance. | MUST distinguish verbatim source text from normalized summary and model inference. |
| `required_evidence` | `FREEZE_NOW` | Evidence requirements whose absence Julia may treat as an admissibility question. | MUST NOT define a universal `strategy_applicable=false` rule or final insufficiency verdict. |
| `positive_evidence` | `FREEZE_NOW` | Evidence that supports continuing the strategy hypothesis and its supporting questions. | MUST NOT imply truth, approval, causal proof, or a buy action. |
| `negative_evidence` | `FREEZE_NOW` | Evidence that challenges the hypothesis and should be surfaced to Julia. | MUST NOT trigger an automatic sell, reject, or challenge outcome. |
| `invalidating_conditions` | `FREEZE_NOW` | Conditions that frame when the hypothesis or its evidence interpretation may be invalid. | MUST remain a question/prompt set, not a runtime evaluator, unless separately frozen as a detector. |
| `applicable_market_regime` | `FREEZE_NOW` | Applicability questions and semantic regime dependencies derived from source material. | MUST NOT directly decide final market stage or emit `strategy_applicable=true/false`. |
| `observation_window` | `FREEZE_NOW` | Source-derived temporal questions and observation boundaries for evidence formation. | MUST NOT become a production scheduling or execution-window engine. |
| `data_dependencies` | `FREEZE_NOW` | Semantic dependency declarations, including Market capability/field semantics and explicit `UNKNOWN` for unavailable semantics. | MUST NOT duplicate Market facts as canonical strategy truth or override Market provenance limitations. |
| `confidence_policy` | `DEFER` | Intended future binding to a separately governed Julia confidence/admissibility policy. | MUST NOT freeze numeric confidence, weighting, thresholds, or a decision function in v1. |
| `human_review_required` | `FREEZE_NOW` | Governance declaration that a human review lane is required before designated reliance. | MUST NOT imply that review has occurred, approval is present, or Market maturity is canonically bound. |
| `implementation_refs` | `DEFER` | Reserved references to separately authorized parser/detector/engine contracts. | MUST remain empty/unbound in v1; historical strategy implementations are not canonical authority. |
| `source_document_refs` | `FREEZE_NOW` | Immutable references to source documents used to form the item. | MUST NOT be replaced by normalized knowledge without retaining document identity. |
| `source_page_refs` | `FREEZE_NOW` | Page-level or equivalent locator references, with explicit `UNKNOWN` when source layout cannot provide them. | MUST NOT manufacture page certainty. |
| `extraction_provenance_refs` | `FREEZE_NOW` | References to source spans and append-only provenance records defined by `STRATEGY_SOURCE_PROVENANCE_CONTRACT_v1`. | MUST preserve `SOURCE_QUOTE`, `NORMALIZED_SUMMARY`, `MODEL_INFERENCE`, and `HUMAN_CORRECTION` distinctions. |
| `maturity` | `FREEZE_NOW` | Independent per-dimension maturity evidence defined in section 5. | MUST NOT collapse maturity to one `PASS/FAIL` flag or convert maturity into judgment authority. |
| `effective_from` | `FREEZE_NOW` | Inclusive effective-time boundary for the strategy version. | MUST be authoritative for historical replay selection once known; absence remains explicit `UNKNOWN`. |
| `effective_to` | `FREEZE_NOW` | Exclusive, possibly-open end boundary for the strategy version. | MUST NOT be inferred from later supersession without an append-only revision record. |
| `supersedes` | `FREEZE_NOW` | Previous strategy version identity, if any. | MUST NOT overwrite, reinterpret, or erase the prior version or its provenance. |

### Required shape rule

Every non-empty `StrategyKnowledgeItem` MUST have:

1. `strategy_id` and `strategy_version`;
2. `definition` with extraction provenance;
3. at least one `source_document_ref`;
4. `extraction_provenance_refs` sufficient to classify normalized material under the source provenance contract;
5. explicit effective-time values or `UNKNOWN`;
6. independent maturity values or `UNKNOWN` for every frozen maturity dimension.

An item MAY have empty evidence structures only while its `SOURCE_PRESENT` or `PARSED_TEXT_ONLY` maturity records that limitation. It MUST NOT pretend to be `STRUCTURED_KNOWLEDGE` when required structures are absent.

## 2. EvidenceRequirement semantic boundary

An `EvidenceRequirement` MAY describe:

- semantic evidence target;
- Market capability or public-contract field dependency;
- required, positive, negative, or counterevidence role;
- observation-window question;
- producer/provenance/coverage prerequisites;
- unresolved admissibility questions;
- explicit `UNKNOWN` where Market semantics are unavailable.

An `EvidenceRequirement` MUST NOT:

- redefine Market evidence truth or projection semantics;
- convert evidence presence into strategy applicability;
- convert absence into a universal failure decision;
- infer analyst approval from unbound Market maturity;
- erase `PROVENANCE_INCOMPLETE`;
- invent field-level epistemic origin;
- assign final confidence, truth, causal strength, or investment safety;
- select `ACCEPTED`, `CHALLENGED`, or `DEFERRED`.

Market evidence remains evidence. Evidence saying X does not mean Julia believes X or that X is true.

## 3. Condition semantic boundary

Activation, required, positive, negative, counterevidence, invalidating, and failure-mode conditions are cognition prompts. They organize what Julia must ask and which evidence must be joined.

StrategyKnowledge MAY also structure source-grounded **historical formation**: how the strategy concept was described, when its evidence pattern was observed, which earlier versions contributed to it, and which source spans explain its origin. Historical formation is context for Julia cognition. It is not proof that the formation process was complete, causal, reproducible, or investment-safe, and it cannot become a backtest verdict.

### MUST

- Conditions MUST reference the evidence requirements and source provenance they organize.
- Invalidating conditions MUST be retained even when positive evidence is abundant.
- Failure modes and counterevidence MUST be inspectable by Julia.
- Applicability conditions MUST remain questions unless a narrow deterministic detector is separately frozen.
- Unavailable dependencies MUST be represented as explicit questions or `UNKNOWN`.

### MUST NOT

- Conditions MUST NOT directly output `strategy_applicable=true`, `strategy_applicable=false`, final market stage, buy, sell, hold, final thesis, or Julia judgment.
- Conditions MUST NOT bypass Julia admissibility, interpretation, causal synthesis, or policy authority.
- Conditions MUST NOT silently promote producer text, analyst text, or model inference into verified truth.

## 4. Deterministic detector exception

A separately frozen narrow detector contract MAY evaluate an explicitly bounded deterministic expression and emit an authorized derived result.

Any such result MUST be labeled as derived evidence or a derived signal. It MUST NOT be labeled Julia judgment, final strategy applicability, final market stage, or an investment action. The detector MUST cite its exact contract/version and input identities. It MUST fail closed outside its frozen scope.

No detector is created, implied, or authorized by this StrategyKnowledge.v1 candidate.

## 5. Independent maturity model

Maturity MUST be recorded independently on these dimensions:

| Dimension | Frozen meaning | Not a claim of |
|---|---|---|
| `SOURCE_PRESENT` | Source document/span identity is available and auditable. | Parsing quality, semantic correctness, or production readiness. |
| `PARSED_TEXT_ONLY` | Source text can be inspected as text. | Structured evidence requirements or normalized knowledge correctness. |
| `STRUCTURED_KNOWLEDGE` | Strategy fields and provenance satisfy this contract. | Applicability, truth, or investment safety. |
| `REVIEW_POLICY` | A separately versioned review policy and human-review requirements are bound. | Approval of a market conclusion or final judgment. |
| `DETERMINISTIC_DETECTOR` | A separately frozen detector contract/version is bound. | Julia judgment or final applicability. |
| `PRODUCTION_CONTRACT` | Separate production storage/runtime/governance contracts are complete. | Immunity from failure modes or counterevidence. |

Each dimension MUST use `UNKNOWN` or its separately defined state; dimensions MUST NOT be summed, averaged, or collapsed into one flag. High maturity in one dimension MUST NOT compensate for low maturity in another.

## 6. Human revision and version lineage

`StrategyKnowledgeRevision` is append-only and MUST retain:

- `revision_id`;
- `strategy_id`;
- `previous_version`;
- `new_version`;
- `changed_fields`;
- `reason`;
- `reviewer`;
- `reviewed_at`;
- `source_refs`.

### MUST

- A new version MUST supersede rather than mutate the historical version in place.
- `changed_fields` MUST identify semantic fields and provenance records, not merely textual diffs.
- Human correction MUST add `HUMAN_CORRECTION` provenance and cite its authority/source.
- The correction MUST preserve the original `SOURCE_QUOTE`, prior `NORMALIZED_SUMMARY`, and prior `MODEL_INFERENCE` when those records exist.
- `reviewer` and `reviewed_at` MUST remain explicit identity/time references or `UNKNOWN`; they MUST NOT be inferred.
- Revisions affecting meaning, evidence boundaries, effective time, provenance, or maturity MUST create a new strategy version.
- Every Julia Review MUST bind the exact `strategy_framework_version` and `policy_version` used.
- Historical replay MUST select the strategy framework, policy, and strategy versions actually effective at the review/effective time, or explicitly mark the binding `UNKNOWN`.

### MUST NOT

- Human correction MUST NOT silently rewrite historical provenance.
- A later correction MUST NOT be projected backward as though it was available at the original effective time.
- A newer framework MUST NOT reinterpret an old review while claiming reproducibility.
- Missing version binding MUST NOT be backfilled as canonical historical fact.

## 7. Market evidence relationship

StrategyKnowledge references Market evidence semantically; Market remains the evidence authority and Julia/Core remain the cognition and judgment authority.

### MUST

- `data_dependencies` MUST reference Market public capabilities and frozen contract fields by semantic identity.
- Strategy requirements MUST preserve Market `EvidenceRef`, source refs, public-object refs, provenance, coverage, bounded quality, and exact-date semantics when consumed.
- Requirements needing unavailable Market semantics MUST record `UNKNOWN` and an explicit question.
- Strategy maturity MUST remain independent from Market module coverage and quality-presence semantics.

### MUST NOT

- StrategyKnowledge MUST NOT duplicate Market facts as canonical truth.
- It MUST NOT redefine exact-date, envelope, provenance, coverage, quality, maturity-passthrough, or epistemic-origin semantics.
- It MUST NOT treat evidence presence as applicability, approval as truth, or bounded quality as correctness.
- It MUST NOT manufacture field-level epistemic origin, durable analyst approval, release identity, governance binding, or complete provenance not supplied by Market.

## 8. Julia authority boundary

Julia/Core retain authority over evidence admissibility and sufficiency; semantic interpretation and weighting; strategy applicability; market-stage synthesis; causal hypothesis formation; counterevidence resolution; `ACCEPTED`, `CHALLENGED`, and `DEFERRED`; final thesis and investment judgment; and buy, sell, hold, or no-action decisions.

StrategyKnowledge has no authority to answer those questions. Its role is to make the relevant source material, evidence requirements, dependencies, revisions, and failure modes inspectable.

## 9. Deferred items

The following remain explicitly deferred and do not authorize implementation under this freeze:

- physical storage schema and persistence migration;
- source parser, extraction pipeline, and detector implementation;
- confidence policy, thresholds, weights, and numeric scores;
- Strategy-to-System mapping;
- JuliaReviewOverlay implementation;
- deterministic condition evaluation;
- production ingestion, review workflow, and publication workflow;
- reviewer identity verification and access control;
- durable approval/publication binding;
- historical corpus ingestion and effective-time index;
- automated provenance verification;
- production release identity and governance binding.

`implementation_refs` remains unbound until each referenced contract is separately Owner-authorized.

## 10. Non-goals

This candidate does not implement a parser, detector, strategy engine, runtime, or storage system; edit Market, Julia, Core, Assistant, frontend, database, test, tool, or workflow source; start Strategy-to-System mapping; freeze a strategy applicability evaluator; define buy/sell/hold logic or final thesis generation; make historical strategy implementations canonical; bind Workbench state to StrategyKnowledge; override the frozen Market Analytical Evidence MVP contract; or authorize merge to main or production use.

## 11. Supersession and change control

- Candidate version: `StrategyKnowledge.v1`.
- The candidate becomes binding only after Owner acceptance of this exact document version.
- Only an Owner-approved later contract version may supersede it.
- Changes to authority boundary, non-decision semantics, field identity, provenance classes, revision/effective-time semantics, maturity dimensions, or Market dependency semantics require a new major contract review.
- Additive optional metadata may be considered only if it cannot reinterpret existing fields, manufacture missing provenance, transfer Julia authority, or turn StrategyKnowledge into a decision engine.
- Implementation work cannot silently expand this contract; passing an implementation test is not acceptance authority.
