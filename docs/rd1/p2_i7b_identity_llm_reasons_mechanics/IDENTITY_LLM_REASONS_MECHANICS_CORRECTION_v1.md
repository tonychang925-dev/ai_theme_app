# Identity LLM Reasons Mechanics Correction v1

## Finding

```text
EXACT_VIOLATION
= VALIDATOR_LABEL
```

The controlled observation produced:

```text
reasons_item_count
= 2

reasons_item_lengths
= [150, 174]
```

Both values satisfy the accepted reasons contract. The same response produced five risk flags, so its actual contract violation is risk-flag item count, not reasons shape. A validator that collapses these cases to `reasons_length` is mechanically ambiguous.

The original #427 raw content was not retained, so its exact historical array shapes are not recoverable. No claim is made that the historical and fresh observations had identical shapes.

## Correction 1 — Explicit Prompt Bounds

The current prompt names the six required keys but does not serialize the numeric array bounds. The corrected prompt adds one fixed object immediately after `response_format` inside `review_instructions`:

```json
{
  "reasons": {
    "min_items": 1,
    "max_items": 3,
    "max_item_unicode_codepoints": 240
  },
  "risk_flags": {
    "min_items": 0,
    "max_items": 3,
    "max_item_unicode_codepoints": 240
  }
}
```

This is prompt mechanics only. It does not change Owner Q1–Q5, remove `reasons`, weaken dimensional review, or alter final-decision ownership.

## Prompt Version

```text
NEW_PROMPT_VERSION
= identity-llm-prompt.v2

SUPERSEDED_PROMPT_VERSION
= identity-llm-prompt.v1

SAME_C1_PROMPT_UTF8_BYTES
= 4871

SAME_C1_PROMPT_SHA256
= 3ed6334fe3ddc9849c1f5e7db940a575202d4dc982849bab117ff4a55c67ec3c
```

The hash is calculated over the exact UTF-8 v2 artifact for the same real C1 evidence and the same calibration batch/trace identifiers.

## Correction 2 — Exact Validator Rules

Replace `CONTRACT_INVALID:reasons_length` with these exact classifications:

| Violation | Exact Classification |
|---|---|
| `reasons` is not an array | `CONTRACT_INVALID:REASONS_NOT_ARRAY` |
| reasons item count outside `1..3` | `CONTRACT_INVALID:REASONS_ITEM_COUNT_OUT_OF_RANGE` |
| one or more reason items exceeds 240 Unicode code points | `CONTRACT_INVALID:REASON_ITEM_LENGTH_OUT_OF_RANGE` |
| a reason item is not a non-empty string | `CONTRACT_INVALID:REASON_ITEM_TYPE_INVALID` |
| `risk_flags` is not an array | `CONTRACT_INVALID:RISK_FLAGS_NOT_ARRAY` |
| risk-flag item count outside `0..3` | `CONTRACT_INVALID:RISK_FLAGS_ITEM_COUNT_OUT_OF_RANGE` |
| one or more risk-flag items exceeds 240 Unicode code points | `CONTRACT_INVALID:RISK_FLAG_ITEM_LENGTH_OUT_OF_RANGE` |
| a risk-flag item is not a non-empty string | `CONTRACT_INVALID:RISK_FLAG_ITEM_TYPE_INVALID` |

The outer typed class remains `CONTRACT_INVALID`; the violated rule must be unambiguous and observable.

## Response Schema Version

```text
NEW_RESPONSE_SCHEMA_VERSION
= unchanged: identity-llm-response.v1
```

The accepted key set, types, dimensions, confidence scale, list limits, and semantic bounds do not change. Only prompt instruction and validator classification mechanics change.

## Prohibited Rescue Mechanisms

The correction explicitly forbids:

- unbounded reasons or risk flags;
- disabled array validation;
- ignoring extra array items;
- truncating strings or arrays after receipt;
- dropping reasons or risk flags;
- JSON repair;
- provider retry;
- model substitution;
- prompt simplification;
- treating the old calibration observations as v2 evidence.
