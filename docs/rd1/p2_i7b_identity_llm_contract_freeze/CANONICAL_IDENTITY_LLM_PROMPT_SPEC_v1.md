# Canonical Identity LLM Prompt Spec v1 — Owner Selection Required

## Status

```text
PROMPT_SPEC_STATUS
= BLOCKED_OWNER_IDENTITY_LLM_CONTRACT_DECISION_REQUIRED
```

No prompt artifact below is selected. The eventual accepted prompt must be an exact versioned artifact, not an implementation-side convention.

## Common Ownership

- Owner component: `IdentityLLMReviewService`.
- Caller: `BuildIdentityJob`.
- Legacy script role: semantic evidence only.
- Construction: deterministic pure function; no clock, network, DB, random, locale, or ambient environment input.
- Version: emitted with every review result.
- Hash: SHA-256 of the exact UTF-8 prompt bytes produced by canonical serialization.

## Candidate P1 — Existing `build_llm_prompt()`

### Inputs

The current method accepts:

- `trade_date`;
- `subject_key`;
- `subject_name`;
- `rule_input`;
- `rule_output`;
- `one_day_tour_flag`;
- `kline_result` (optional).

### Consequences

- It is richer than the current executable API prompt and aligns more closely with controlled-review ownership.
- Its comment claims production 1:1 behavior, but it is not called by `review_with_rule()`.
- It does not serialize the full historical evidence set or K-line technical fields.
- Optional K-line evidence is not currently a required contract input.

### Owner choice required

Selecting P1 requires the Owner to approve its exact text, make every input required or explicitly excluded, define canonical serialization, and assign `identity-llm-prompt.v1` or another exact version.

## Candidate P2 — Corrected Canonical Prompt Artifact

This option creates a new exact prompt specification that replaces both current candidates. It must explicitly cover:

1. trade date and stable subject identity;
2. logic-dimension evidence and thresholds;
3. market-dimension evidence and thresholds;
4. one-day-tour hard gate and risk evidence;
5. continuity and K-line shape evidence;
6. rule version and complete rule output;
7. evidence provenance identifiers;
8. non-confirmation instructions for insufficient evidence;
9. the exact response JSON schema;
10. list-length and confidence constraints.

### Consequences

- This is the semantically strongest option for replay and Layer A parity.
- It requires exact Owner-approved text and input serialization before implementation.
- It may require `BuildIdentityJob` plumbing additions, which must be separately minimized after the freeze.

### Owner choice required

The Owner must provide or approve the exact artifact. This document must not invent the production wording.

## Candidate P3 — Another Exact Authorized Artifact

The Owner may select an existing exact artifact only if it is already authorized by a design document or ADR. The citation must identify:

- repository path or durable artifact identifier;
- authority document/ADR;
- exact version;
- full input contract;
- response schema dependency.

## Required Field Decision Matrix

| Field | Required by Current Authority | Owner Decision Required |
|---|---|---|
| `trade_date` | YES for stable historical replay | Include or exclude from final prompt. |
| `subject_key` | YES for exact subject provenance | Include or exclude from final prompt. |
| `subject_name` | Useful for human-readable review | Include or exclude from final prompt. |
| Full identity rule input | YES to preserve Layer A input semantics | Select exact field subset and serialization. |
| Full identity rule output | YES to expose rule thresholds and prechecks | Select exact field subset and serialization. |
| `one_day_tour_flag` | YES; hard-gate semantics | Include; no option to omit. |
| K-line result/evidence | YES for historical K-line shape semantics | Select exact required fields or define why unavailable inputs are omitted without default truth. |
| Scores/threshold context | YES for auditability | Select exact score and threshold fields. |
| Rule version | YES for replay | Include; representation to be chosen. |
| Provenance identifiers | YES for evidence traceability | Select exact identifiers and representation. |

## Prompt Hash Procedure

1. Construct the prompt through the selected pure owner function.
2. Serialize using the frozen canonical field order and exact separators.
3. Encode as UTF-8 without newline normalization.
4. Compute SHA-256 over those exact bytes.
5. Emit `prompt_version` and `prompt_sha256` with the review record.
6. Any byte-changing edit increments the prompt version before production use.

## Not Authorized

- Selecting the currently executable short prompt merely because it runs.
- Copying the legacy script prompt without Owner approval.
- Simplifying evidence to reduce token pressure.
- Deriving prompt content from provider output.
- Calibration before this spec is frozen.

