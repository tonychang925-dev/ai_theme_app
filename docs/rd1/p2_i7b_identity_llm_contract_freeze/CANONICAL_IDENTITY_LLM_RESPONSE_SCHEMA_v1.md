# Canonical Identity LLM Response Schema v1 — Owner Selection Required

## Status

```text
RESPONSE_SCHEMA_STATUS
= BLOCKED_OWNER_IDENTITY_LLM_CONTRACT_DECISION_REQUIRED
```

The architecture authority requires structured output but does not select between the historical dimensional schema and the current canonical aggregate schema. This document defines both options and the mandatory validation envelope; it does not choose one.

## Validation Rules Independent of Schema Choice

- Provider response body must be a valid JSON object envelope.
- `choices` must be present and non-empty.
- Choice message content must be present and non-empty when normal completion is claimed.
- `finish_reason=length` must be classified as `OUTPUT_TRUNCATED` before parsing content.
- Content must parse as one JSON object; arrays, scalars, markdown fences, partial objects, and concatenated objects are invalid.
- Required keys must be present with exact declared types.
- Unknown-field policy must be one exact Owner choice: reject or ignore-and-record.
- Numeric bounds must be inclusive and explicitly validated.
- List elements must be strings; empty lists are allowed only where the chosen schema says so.
- No default value may synthesize a missing required field.

## Option S1 — Historical Dimensional Schema

```text
schema_version: OWNER_CHOICE_REQUIRED
logic_dimension_ok_llm: boolean, required
market_dimension_ok_llm: boolean, required
is_main_theme_core_llm: boolean, required
confidence: integer, required, 0-100 inclusive
reasons: array<string>, required, maximum 3
risk_flags: array<string>, required, maximum 3
```

### Authority and Consequences

- Matches the historical Layer A review decision surface.
- Supports separate logic and market attribution.
- Must define consistency validation: `is_main_theme_core_llm == (logic_dimension_ok_llm AND market_dimension_ok_llm)`.
- Requires a bounded non-empty reason/risk policy and exact unknown-field policy.

## Option S2 — Current Canonical Aggregate Schema

```text
schema_version: OWNER_CHOICE_REQUIRED
is_main_theme: boolean, required
confidence: number, required, 0.0-1.0 inclusive
reasons: array<string>, required, maximum OWNER_CHOICE_REQUIRED
risk_flags: array<string>, required, maximum OWNER_CHOICE_REQUIRED
```

### Authority and Consequences

- Matches both the executable canonical prompt and unused canonical prompt builder.
- Requires a smaller transport surface.
- Loses separate logic/market attribution unless those dimensions remain in reasons or a revised schema adds them.
- Decimal precision and serialization must be defined if selected.

## Option S3 — Corrected Canonical Schema

The Owner may specify a strict v1 that combines dimensional decisions with canonical confidence semantics, for example:

```text
logic_dimension_ok_llm: boolean
market_dimension_ok_llm: boolean
is_main_theme_core_llm: boolean
confidence: exact Owner-selected scale
reasons: bounded array<string>
risk_flags: bounded array<string>
schema_version: exact literal
```

Any additional fields require explicit authority. This document does not select S3 or define its exact version.

## Decision Matrix

| Item | Options | Blocking Consequence |
|---|---|---|
| Schema family | S1 / S2 / S3 | Decider mapping cannot be frozen. |
| Schema version | Exact literal supplied by Owner | Replay records cannot be finalized. |
| Confidence type/scale | integer `0–100` or decimal `0.0–1.0` | Comparison and storage semantics remain unresolved. |
| Reasons limit | exact positive integer | Contract validation remains unresolved. |
| Risk flags limit | exact positive integer | Contract validation remains unresolved. |
| Empty lists | allowed or disallowed per field | Missing-evidence semantics remain unresolved. |
| Unknown fields | reject or ignore-and-record | Parser behavior remains unresolved. |
| Boolean consistency | enforce dimensional conjunction if S1/S3 | Failure classification depends on selection. |

## Failure Classification

| Condition | Typed Result |
|---|---|
| Envelope is not valid JSON or is not an object | `RESPONSE_ENVELOPE_INVALID` |
| Choices absent or empty | `RESPONSE_ENVELOPE_INVALID` |
| Message/content absent or blank | `CONTENT_MISSING` |
| `finish_reason=length` | `OUTPUT_TRUNCATED` |
| Content is not valid JSON object | `INVALID_JSON` |
| Required key absent | `CONTRACT_INVALID` |
| Type/value/list-limit violation | `CONTRACT_INVALID` |
| Dimensional conjunction inconsistency, if selected schema requires it | `CONTRACT_INVALID` |

These classifications are frozen. Their business terminal mapping remains in the separate error matrix and still requires Owner selection.
