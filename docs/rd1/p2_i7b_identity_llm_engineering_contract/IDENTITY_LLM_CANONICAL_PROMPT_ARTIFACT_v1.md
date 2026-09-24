# Identity LLM Canonical Prompt Artifact v1

## Artifact Identity

```text
PROMPT_VERSION
= identity-llm-prompt.v1

OWNER
= IdentityLLMReviewService

ENCODING
= UTF-8

HASH
= SHA-256(exact artifact bytes)
```

## Artifact Layout

The artifact is exactly:

```text
identity-llm-prompt.v1\n
<canonical-payload-json>\n
```

The trailing newline is included in the hash. The payload is serialized with:

```python
json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=False,
    separators=(",", ":"),
    allow_nan=False,
)
```

Construction has no clock, network, random, locale, database, environment, or provider dependency. All varying identifiers are explicit payload fields supplied by `BuildIdentityJob`.

## Canonical Payload Field Order

The top-level order is exactly:

1. `prompt_version`;
2. `trade_date`;
3. `subject_identity`;
4. `rule_identity`;
5. `evidence_provenance`;
6. `logic_inputs`;
7. `market_inputs`;
8. `continuity_kline_inputs`;
9. `one_day_tour_evidence`;
10. `rule_outputs`;
11. `missing_evidence_policy`;
12. `review_instructions`.

## Exact Field Sets

### `subject_identity`

```text
subject_key: string
subject_name: evidence value
```

### `rule_identity`

```text
rule_version: identity_rule_engine.v1
owner: IdentityRuleEngine
```

### `evidence_provenance`

```text
read_port_method: StockReadPort.get_mainline_identity_rule_inputs
source_trade_date: ISO-8601 date string
subject_key: string
batch_id: string
trace_id: string
```

### `logic_inputs`

```text
strong_event_count_7d
event_count_3d
event_count_7d
event_recency_days
event_strength_score
event_continuity_score
front_row_strength_score
front_row_alive_ratio
limit_up_count
platform_breakout_flag
platform_breakout_strength
```

### `market_inputs`

```text
heat_latest
avg_heat_5d
hot_days_5d
active_days_10d
active_days_20d
board_stock_count
board_boom_days_5d
net_inflow_sum_5d
net_inflow_days_5d
```

### `continuity_kline_inputs`

```text
above_ma10
above_ma20
theme_support_score
theme_ret_10d
his_pct_chg_latest
his_pct_chg_30d
kline_support_hold
mainline_continuity_score
```

### `one_day_tour_evidence`

```text
one_day_tour_flag
one_day_tour_risk_score
```

### `rule_outputs`

```text
logic_score
market_score
composite_score
logic_ok
market_ok
rule_is_main_theme
rule_reasons
```

### `missing_evidence_policy`

The exact object is:

```json
{"MISSING":"field was absent or null","UNAVAILABLE":"field exists upstream but value could not be retrieved","NOT_APPLICABLE":"upstream contract explicitly marks field as not applicable","prohibition":"never interpret an evidence-state object as false, true, zero, or another business value"}
```

### `review_instructions`

This object is fixed and is serialized after `missing_evidence_policy`. Exact keys:

```text
review_scope
logic_dimension
market_dimension
risk_review
missing_evidence
aggregate_flag
decision_boundary
response_format
required_keys
confidence_meaning
```

Exact values:

```text
review_scope
= Provide an independent Layer A dimensional LLM review only; final business identity is owned elsewhere.

logic_dimension
= Judge whether the logic evidence supports the logic dimension using only AVAILABLE evidence.

market_dimension
= Judge whether the market evidence supports the market dimension using only AVAILABLE evidence.

risk_review
= Consider one-day-tour, continuity, and K-line evidence as structural review evidence.

missing_evidence
= Do not interpret MISSING, UNAVAILABLE, or NOT_APPLICABLE as false, true, zero, or another business value; reduce certainty or return a non-supporting review when evidence is insufficient.

aggregate_flag
= Set is_main_theme=true only when both logic_dimension_ok and market_dimension_ok are true; otherwise set it false.

decision_boundary
= This response is not the final identity decision and must not override rule, one-day-tour, continuity, K-line, or lifecycle gates.

response_format
= Return exactly one strict JSON object with only the six required keys and no markdown or extra text.

required_keys
= ["logic_dimension_ok","market_dimension_ok","is_main_theme","confidence","reasons","risk_flags"]

confidence_meaning
= confidence is only confidence in this LLM review judgment, expressed from 0.0000 through 1.0000
```

## Evidence-State Encoding

Every evidence value except fixed identifiers uses one of:

```json
{"state":"AVAILABLE","value":<normalized-value>}
```

```json
{"state":"MISSING"}
```

```json
{"state":"UNAVAILABLE"}
```

```json
{"state":"NOT_APPLICABLE"}
```

State semantics:

| State | Exact Meaning |
|---|---|
| `AVAILABLE` | A non-null raw or canonical domain value is present. |
| `MISSING` | The field is absent or null at the explicit input boundary. |
| `UNAVAILABLE` | The upstream contract knows the field but its value cannot be retrieved. |
| `NOT_APPLICABLE` | The upstream contract explicitly marks the field as not applicable. |

No state object may be coerced to a business boolean or number.

## Value Normalization

- Dates: `YYYY-MM-DD`.
- Strings: exact JSON strings; no locale formatting.
- Booleans: JSON `true` or `false` only when available.
- Integers: JSON integers.
- Decimals: canonical decimal strings.
- Decimal canonicalization: non-exponent `f` formatting, trailing fractional zeros removed, negative zero normalized to `0`.
- `his_pct_chg_30d`: an array of canonical decimal strings in source order.
- `rule_reasons`: an array of exact strings in rule-engine order.

The provider receives numeric evidence values as strings to avoid floating-point rewriting. This is transport serialization only and does not change domain types.

## Fixed Review Instructions

The prompt payload's evidence coverage and fixed policy instruct the model to:

1. review the logic dimension and market dimension independently;
2. treat one-day-tour, continuity, and K-line evidence as review evidence;
3. preserve missing/unavailable/not-applicable states without inventing facts;
4. return only the six-field response schema;
5. confine `is_main_theme` to agreement with its two dimensional review flags;
6. never claim authority over the final business identity decision.

The exact response contract is compiled separately in `IDENTITY_LLM_COMPILED_RESPONSE_SCHEMA_v1.md`.

## Prompt Hash Fixture

A repository-readable real subject identity is available from the frozen Layer A regression authority:

```text
trade_date
= 2026-04-07

subject_key
= 9062832
```

The following fixture marks every business evidence field `MISSING`. It is a missing-evidence serialization fixture, not a synthetic claim that evidence was present.

```text
ARTIFACT_UTF8_BYTES
= 3706

PROMPT_SHA256
= 312e588723a947cf0358871c4941ce2c410b6af484309c8027f9bc50facf4705
```

The fixture uses:

```text
batch_id
= calibration-fixture-missing-evidence

trace_id
= identity-llm-hash-fixture-v1
```

An implementation test must reconstruct this artifact byte-for-byte and reproduce the hash before any provider call.

## Prompt Construction Prohibitions

- No verbatim copy of the legacy script prompt.
- No use of the current short inline API prompt.
- No field reordering.
- No locale-dependent number formatting.
- No omission of an evidence class to reduce tokens.
- No replacement of an evidence-state object with a default.
- No injection of provider output, clock time, hostname, credentials, or ambient environment data.
- No prompt mutation after calibration begins.
