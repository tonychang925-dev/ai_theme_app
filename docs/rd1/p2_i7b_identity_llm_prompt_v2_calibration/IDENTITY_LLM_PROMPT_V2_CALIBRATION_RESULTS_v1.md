# Identity LLM Prompt v2 Calibration Results

```text
C1_RECONSTRUCTED
= YES

C1_PROMPT_SHA256
= 3ed6334fe3ddc9849c1f5e7db940a575202d4dc982849bab117ff4a55c67ec3c

C1_PROMPT_UTF8_BYTES
= 4871

COHORT_SELECTED_COUNT
= 1

EXECUTED_TOKEN_TIERS
= [1000, 2000, 4000]

SELECTED_MAX_TOKENS
= 4000

CALIBRATION_STABLE
= YES

INITIAL_PROVIDER_REQUEST_COUNT
= 3

CONFIRMATION_PROVIDER_REQUEST_COUNT
= 1

TOTAL_PROVIDER_REQUEST_COUNT
= 4

RETRY_USED
= NO

FALLBACK_USED
= NO

MODEL_SWAP_USED
= NO

PROMPT_MUTATION_USED
= NO

JSON_REPAIR_USED
= NO

PRODUCTION_SOURCE_CHANGED
= NO

DB_MUTATION
= NO
```

## Tier Outcomes

| Tier | Attempt | HTTP | Finish reason | Content | JSON | Contract | Typed outcome |
|---:|---|---:|---|---|---|---|---|
| 1000 | INITIAL | 200 | `length` | absent | NO | NO | `OUTPUT_TRUNCATED` |
| 2000 | INITIAL | 200 | `length` | absent | NO | NO | `OUTPUT_TRUNCATED` |
| 4000 | INITIAL | 200 | `stop` | present | YES | YES | `NONE` |
| 4000 | CONFIRMATION | 200 | `stop` | present | YES | YES | `NONE` |

Tier 1000 and tier 2000 advanced only because their sole failure was
`OUTPUT_TRUNCATED`. No non-truncation provider, envelope, content, JSON, or
schema failure occurred.

The first stable tier was 4000:

```text
4000 INITIAL
= HTTP 200
= finish_reason stop
= content_present YES
= response_json_valid YES
= response_contract_valid YES
= typed_error_code NONE

4000 CONFIRMATION
= HTTP 200
= finish_reason stop
= content_present YES
= response_json_valid YES
= response_contract_valid YES
= typed_error_code NONE
```

Accordingly, token tiers 8000 and 16000 were not executed.

## Stability Decision

The selected cohort has one real sample. At the first fully passing tier, the
one required confirmation observation also passed. Therefore:

```text
STABLE_PASS_COUNT
= 2/2

SELECTED_MAX_TOKENS
= 4000
```

No v1 result was inherited or used to satisfy this calibration.
