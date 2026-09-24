# Identity LLM Compiled Response Schema v1

## Schema Identity

```text
SCHEMA_VERSION
= identity-llm-response.v1

JSON_MODE
= response_format({"type":"json_object"})

UNKNOWN_FIELD_POLICY
= REJECT
```

The provider message content must be exactly one JSON object. It must not be wrapped in markdown, text, an array, or a concatenated object stream.

## Exact Object Shape

```json
{
  "logic_dimension_ok": true,
  "market_dimension_ok": true,
  "is_main_theme": true,
  "confidence": 0.8500,
  "reasons": ["string"],
  "risk_flags": ["string"]
}
```

## Field Contract

| Field | Required | Type | Bounds/Constraints |
|---|---|---|---|
| `logic_dimension_ok` | YES | JSON boolean | No integer or string coercion. |
| `market_dimension_ok` | YES | JSON boolean | No integer or string coercion. |
| `is_main_theme` | YES | JSON boolean | Must equal the AND of both dimensional flags. |
| `confidence` | YES | JSON number | Decimal ratio `0.0000..1.0000`; at most four fractional decimal digits; `NaN`, infinity, exponent notation, and strings are invalid. |
| `reasons` | YES | array | One to three items; every item is a non-empty string of at most 240 Unicode code points. |
| `risk_flags` | YES | array | Zero to three items; every item is a non-empty string of at most 240 Unicode code points. |

The content object must contain exactly these six keys. No extra key is ignored.

## Internal Consistency

The only enforced response-level relationship is:

```text
is_main_theme
== logic_dimension_ok AND market_dimension_ok
```

This is a transport consistency check. It is not the final identity business algorithm. Final identity semantics remain with `IdentityDecider` and canonical business ownership.

## Validation Order

1. Receive and decode HTTP body.
2. Require HTTP status `200`.
3. Parse the envelope as JSON with decimal-safe numeric parsing.
4. Require an object envelope with non-empty `choices`.
5. Require choice zero and its `message`.
6. Inspect `finish_reason` before content parsing.
7. If `finish_reason` indicates output length, classify `OUTPUT_TRUNCATED`.
8. Require non-null, non-blank string content.
9. Parse content as JSON with decimal-safe numeric parsing.
10. Require exactly one object.
11. Require exactly the six keys.
12. Validate booleans.
13. Validate confidence syntax, scale, and bounds.
14. Validate arrays, item types, non-emptiness, item length, and list limits.
15. Validate dimensional aggregate consistency.

No later step may repair an earlier validation failure.

## Confidence Parsing

The parser must use a decimal-preserving JSON parser or an equivalent exact numeric token parser. Floating-point conversion is prohibited before validation.

Accepted examples:

```text
0
0.5
0.85
1
```

Rejected examples:

```text
"0.85"
NaN
Infinity
1E-1
0.85001
1.0001
-0.0001
```

The domain representation is `Decimal("0.8500")`; persistence uses `8500` basis points.

## Failure Classification

| Violation | Exact Error Code |
|---|---|
| Envelope is not valid JSON/object or choices is absent/empty | `RESPONSE_ENVELOPE_INVALID` |
| Choice/message/content is absent, null, or blank | `CONTENT_MISSING` |
| `finish_reason=length` or equivalent output-limit signal | `OUTPUT_TRUNCATED` |
| Content is not one valid JSON object | `INVALID_JSON` |
| Missing key, extra key, wrong type, bound/list-limit violation, or aggregate inconsistency | `CONTRACT_INVALID` |

All are subject-level provider failures under Owner Q5. They produce `review_pending`, never `confirmed`, and never synthetic success.
