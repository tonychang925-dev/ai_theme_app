# Identity LLM Reasons Shape Observation v1

## Controlled Observation

```text
TASK_ID
= RD1-P2-I7B-IDENTITY-LLM-REASONS-SHAPE-MECHANICS-CORRECTION-P0

PROVIDER_REQUEST_COUNT
= 1

TRADE_DATE
= 2026-04-07

SUBJECT_KEY
= 9062832

PROMPT_VERSION
= identity-llm-prompt.v1

PROMPT_SHA256
= f77e11029cf1a4d776eb2f16ddc9799d8b3f4268edf2a63a144ba54006269a2d

C1_PROMPT_HASH_MATCH
= YES

MODEL
= deepseek-v4-pro

TEMPERATURE
= 0.1

MAX_TOKENS
= 2000

JSON_OBJECT_MODE
= YES

TIMEOUT_SECONDS
= 120
```

## Provider Envelope

```text
HTTP_STATUS
= 200

FINISH_REASON
= stop

RESPONSE_JSON_VALID
= YES

CONTENT_UTF8_BYTES
= 636

CONTENT_SHA256
= e0cb23acd9878350852a42f5ca15bdc8eac0a8d553e772885a41182715b52ece
```

## Non-Sensitive Shape Evidence

No raw reason, risk flag, response body, authorization header, or API key is recorded.

```text
RESPONSE_KEY_SET
= [
  confidence,
  is_main_theme,
  logic_dimension_ok,
  market_dimension_ok,
  reasons,
  risk_flags
]

REASONS_ITEM_COUNT
= 2

REASONS_ITEM_LENGTHS
= [150, 174]

MAX_REASON_LENGTH
= 174

RISK_FLAGS_ITEM_COUNT
= 5

RISK_FLAG_LENGTHS
= [26, 16, 16, 24, 21]
```

## Mechanical Classification

The observed `reasons` value satisfies both current bounds:

```text
1 <= reasons_item_count <= 3
max_reason_length <= 240
```

Therefore this observation has neither:

```text
REASONS_ITEM_COUNT_VIOLATION
REASON_ITEM_LENGTH_VIOLATION
```

The observed `risk_flags` value has five items and violates the existing maximum of three. The correct detailed classification for this observation is:

```text
CONTRACT_INVALID
contract_violation
= RISK_FLAGS_ITEM_COUNT_OUT_OF_RANGE
```

Accordingly, describing this observation as `reasons_length` would be a validator-labeling error.

## Historical Boundary

The original #427 response content was intentionally not retained. Its exact raw reasons shape cannot be inferred from its content hash or token usage. The fresh observation also produces a new content hash and demonstrates provider shape variability.

Thus the safe mechanical conclusion is not that the historical response had the same shape as this observation. The reusable correction must make array-bound instructions explicit and replace the ambiguous `reasons_length` label with exact violated-rule classification.
