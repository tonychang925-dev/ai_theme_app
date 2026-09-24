# JULIA_REVIEW_DISPOSITION_SEMANTICS_v1

## Authority

- `TASK_ID = POST-RD1-E1-D-JULIA-FINANCIAL-REVIEW-IR-FREEZE-P0`
- `START_HEAD = 4669942734dffb292fa3fc75acddbad79d95476f`
- Governing candidate: `JULIA_REVIEW_OVERLAY_CONTRACT_FREEZE_CANDIDATE_v1.md`

These are non-destructive semantic dispositions. They describe Julia's relation to an input or review object at an exact information cutoff and under exact versions. They do not mutate source content or transfer ownership.

## 1. ACCEPTED

`ACCEPTED` is an **item-level** disposition.

Julia accepts an input claim or judgment as one current research input and reasoning premise for this review.

### MUST

- The accepted item MUST retain its original evidence/source references and owner.
- The disposition MUST retain the exact review, information cutoff, strategy framework, and policy versions.
- Julia MAY use the premise in interpretation or judgment while preserving its original epistemic/provenance status.

### MUST NOT

- `ACCEPTED` MUST NOT mean Julia reverified the fact.
- It MUST NOT change a source to `SOURCE_VERIFIED`.
- It MUST NOT transfer source ownership to Julia.
- It MUST not modify source content or upstream provenance.
- It MUST NOT imply buy, sell, hold, final thesis, or investment safety.

## 2. CHALLENGED

`CHALLENGED` is an **item-level** disposition.

Julia identifies one or more of:

- evidence insufficiency;
- contradiction;
- strategy condition mismatch;
- causal gap;
- source weakness.

### MUST

- The challenged input and its source ownership MUST be preserved.
- The stated challenge reason and supporting/conflicting references MUST remain inspectable.
- Contradicting sides MUST remain separately attributable.

### MUST NOT

- `CHALLENGED` MUST NOT delete, rewrite, or mask the challenged input.
- It MUST NOT automatically reject a strategy, issue an action, or become a final review result.
- It MUST NOT convert Julia disagreement into proof that the upstream source is false.

## 3. DEFERRED

`DEFERRED` is an **item-level** disposition.

Current information is insufficient to reasonably `ACCEPT` or `CHALLENGE` the item; later Market, announcement, or external evidence is required.

### MUST

- The deferred item MUST preserve upstream ownership and references.
- The kind of later evidence or observation needed SHOULD be represented through `missing_evidence`, `open_questions`, or `watch_items` when known.
- The disposition MUST remain bound to the original information cutoff and versions.

### MUST NOT

- `DEFERRED` MUST NOT mean the review failed to execute.
- It MUST NOT be used as the review-object-level result when Julia completes the review but cannot form a grounded directional disposition.
- It MUST NOT imply that missing evidence proves absence, falsity, or risk.

## 4. INCONCLUSIVE

`INCONCLUSIVE` is a **review-object-level** disposition.

Review execution completes, but Julia cannot form a sufficiently grounded directional disposition for the review object.

### MUST

- The review MUST remain complete as a semantic record with its inputs, versions, cutoff, missing evidence, contradictions, open questions, and Julia interpretation where available.
- `INCONCLUSIVE` MUST preserve why a directional disposition is not sufficiently grounded.
- It MUST remain distinguishable from execution failure, Runtime error, and item-level `DEFERRED`.

### MUST NOT

- `INCONCLUSIVE` MUST NOT be silently collapsed into `DEFERRED`.
- It MUST NOT be treated as a fourth item-level evidence bucket.
- It MUST NOT be minted by Runtime because inputs are incomplete.
- It MUST NOT imply a hold action or investment safety.

## 5. Item-level versus review-level boundary

| Question | DEFERRED | INCONCLUSIVE |
|---|---|---|
| Level | One upstream item/claim/evidence requirement. | Whole review object. |
| Execution state | Review may continue or complete. | Review execution is completed. |
| Meaning | More evidence is needed before accept/challenge of that item. | Julia cannot form a sufficiently grounded directional disposition for the object. |
| Result | Item remains pending later evidence. | Review-level directional result is intentionally absent. |
| Error state | No. | No. |
| Action meaning | None. | None. |

An overlay MAY contain deferred items and still produce a Julia judgment. An overlay MAY also contain accepted and challenged premises yet be review-level `INCONCLUSIVE` when those inputs do not sufficiently ground a directional disposition. The levels are related but not interchangeable.

## 6. Ownership preservation

Every disposition MUST retain:

- upstream owner (`Market`, analyst/Workbench, external source, or StrategyKnowledge source lineage);
- exact source/evidence/strategy references;
- original claim/evidence semantics;
- Julia disposition and reason;
- information cutoff and version bindings.

A disposition changes Julia's research relation to the input. It does not change the input's origin, truth status, approval state, provenance, or ownership.

## 7. Transition and immutability semantics

Within one `JuliaReviewOverlay`, dispositions are recorded results, not mutable workflow states. This contract defines no destructive transition.

- A later review MAY supersede an earlier review only through a separately defined immutable revision/supersession record.
- A later disposition MUST NOT overwrite the historical item, review identity, provenance, cutoff, or versions.
- A deferred item is not automatically accepted or challenged when new evidence appears; Julia must review the new evidence in an appropriately bound result.
- An inconclusive review is not automatically resolved by passage of time; Julia must review later evidence and produce a new bound result.
- DailyResearchCycle lifecycle transitions MUST NOT reinterpret or mint these semantic dispositions.

## 8. Non-normative examples

These examples are illustrative only.

- An external claim has one supportive but weak source, so Julia marks the claim `DEFERRED` and records the announcement needed later.
- Market evidence and an analyst claim conflict. Julia marks the analyst item `CHALLENGED`, preserves both sides, and records the contradiction.
- Several premises are accepted for reasoning, but causal direction remains unsupported, so the completed review object is `INCONCLUSIVE`.
- A Market module is contractually absent for the exact date. Julia records `missing_evidence`; absence alone is not accepted proof that no activity occurred.
