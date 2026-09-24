# STRATEGY_SOURCE_PROVENANCE_CONTRACT_v1

## Authority and scope

- `TASK_ID = POST-RD1-E1-C-STRATEGY-COGNITION-KNOWLEDGE-FREEZE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD = e07030f570b596c2f67200c3274bcc372731f019`
- Governing candidate: `STRATEGY_KNOWLEDGE_CONTRACT_FREEZE_CANDIDATE_v1.md`
- Scope: source-to-knowledge provenance for StrategyKnowledge. This is a contract only; it does not authorize or implement a parser.

## Transformation model

The only authorized conceptual transformation is:

```text
source span
  -> normalized cognition knowledge
  -> evidence requirement / counterevidence / applicability question
```

The following transformation is forbidden:

```text
source document
  -> executable conclusion rule
  -> final answer
```

Normalization may organize what Julia must examine. It may not decide what Julia must conclude.

## 1. Source span identity

A provenance record MUST be able to identify:

- `source_document_ref`;
- `source_page_ref` or equivalent bounded locator, when available;
- span locator within that page/document, when available;
- source document version or immutable content identity, when available;
- extracted span text or its immutable content hash;
- extraction record identity;
- extraction agent/model/process identity, when applicable;
- extraction timestamp, when applicable;
- later revision references.

Unavailable identity components MUST remain explicit `UNKNOWN`. They MUST NOT be inferred from memory, model plausibility, or normalized text.

## 2. Provenance classes

| Class | Meaning | Required use | Forbidden use |
|---|---|---|---|
| `SOURCE_QUOTE` | Verbatim text copied from an identified source span. | Preserving the exact source expression and its span identity. | Paraphrase, cleanup, translation without marking transformation, or inferred content. |
| `NORMALIZED_SUMMARY` | Faithful normalized restatement/structuring of source material. | Organizing source content into cognition fields while retaining source refs. | Claiming verbatim status or erasing the source quote. |
| `MODEL_INFERENCE` | Conclusion, grouping, mapping, or interpretation added by an extraction model rather than directly stated by the source. | Making added interpretation auditable and reviewable. | Presenting inference as source fact or verified truth. |
| `HUMAN_CORRECTION` | Append-only human revision to prior extraction/knowledge. | Recording reviewer, reason, time, changed fields, and authority/source refs. | Silently rewriting historical records or masquerading as original source text. |

These classes are semantic provenance labels, not Market epistemic-origin classes and not evidence truth. They do not override Market `PROVENANCE_INCOMPLETE` or manufacture field-level origin absent from Market output.

## 3. Integrity rules

### MUST

- Every normalized strategy field MUST cite at least one source provenance class and reference.
- `SOURCE_QUOTE` MUST preserve verbatim content, subject only to explicitly recorded bounded transformations such as encoding or locator formatting.
- `NORMALIZED_SUMMARY` MUST retain a route back to its supporting source span.
- `MODEL_INFERENCE` MUST identify the inference record and distinguish it from source-supported content.
- `HUMAN_CORRECTION` MUST preserve the prior value and its provenance.
- A correction that changes strategy meaning, evidence boundary, effective time, dependency, or maturity MUST create a new version.
- Provenance references MUST remain stable and append-only.

### MUST NOT

- Normalized text MUST NOT masquerade as verbatim source text.
- Model inference MUST NOT masquerade as `SOURCE_QUOTE` or `NORMALIZED_SUMMARY`.
- Human correction MUST NOT silently rewrite historical provenance.
- A later summary MUST NOT replace the original quote as historical evidence.
- Missing provenance MUST NOT be filled with plausible reconstruction.
- Provenance presence MUST NOT imply semantic correctness, strategy applicability, or Julia acceptance.

## 4. Append-only correction

Every correction MUST be represented as a `StrategyKnowledgeRevision` containing:

- `revision_id`;
- `strategy_id`;
- `previous_version`;
- `new_version`;
- `changed_fields`;
- `reason`;
- `reviewer`;
- `reviewed_at`;
- `source_refs`.

The revision history MUST preserve the original source span and quote; prior normalized summaries and inferences; the exact fields changed; the correction reason and authority reference; reviewer/time identity or explicit `UNKNOWN`; and effective-time boundaries of the new version.

Deleting or overwriting those records is forbidden. Supersession marks a version as no longer effective going forward; it does not erase or reinterpret its historical state.

## 5. Anti-hindsight and effective-time requirements

### Version binding

Each Julia Review MUST bind:

- `strategy_framework_version`;
- `policy_version`;
- the exact `StrategyKnowledge` versions used.

Historical replay MUST additionally select, or explicitly report as `UNKNOWN`, the versions actually effective at the historical effective/review time.

### MUST

- Replay MUST use the effective-time strategy version, strategy framework version, and policy version.
- Supersession MUST follow the recorded `effective_from` / `effective_to` boundaries.
- Missing effective-time data MUST produce explicit `UNKNOWN` and a reproducibility limitation.
- Correction provenance MUST retain the time at which the correction became available.
- Review outcome MUST retain the exact version identities under which it was formed.

### MUST NOT

- A newer strategy framework MUST NOT reinterpret an old review while claiming reproducibility.
- A later human correction MUST NOT be projected backward as information available at the original time.
- An open effective boundary MUST NOT be closed retroactively without an append-only revision.
- Version absence MUST NOT be silently replaced by the current version.
- Historical replay MUST NOT report deterministic reproducibility when any required effective-time version is `UNKNOWN`.

## 6. Relationship to Market provenance

Strategy source provenance describes how source material became StrategyKnowledge. Market provenance describes how Market produced its evidence payload. The two layers MUST remain separately attributable and MUST NOT be merged into one claim.

Strategy provenance MUST NOT overwrite Market source/evidence/public-object identities; replace Market exact-date or content-hash semantics; manufacture field-level Market epistemic origin; convert `PROVENANCE_INCOMPLETE` into complete provenance; infer durable analyst approval/publication from Market maturity passthrough; or reinterpret Market coverage or bounded quality as correctness or causal support.

When a strategy dependency requires unavailable Market semantics, the StrategyKnowledge item MUST record an explicit dependency, question, and `UNKNOWN`.

## 7. Deferred implementation semantics

The following require separate Owner-authorized contracts and are not implemented by this document:

- physical provenance storage and content hashing;
- document/page locator format;
- parser and extraction pipeline;
- model/extraction-run identity and prompt capture;
- reviewer authentication and authorization;
- correction workflow UI or API;
- effective-time index and replay runtime;
- automated provenance verification;
- production governance/release references.

## 8. Freeze boundary

This contract freezes provenance semantics only. It does not assert that any current StrategyKnowledge source record, parser, reviewer identity, effective-time index, or replay implementation exists. Any future implementation MUST preserve these class, append-only, and effective-time rules or request an Owner-approved contract revision.
