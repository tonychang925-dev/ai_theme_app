# Identity LLM Calibration Reentry After Reasons Correction v1

## Reentry Contract

```text
NEXT_PROMPT_VERSION
= identity-llm-prompt.v2

NEXT_RESPONSE_SCHEMA_VERSION
= identity-llm-response.v1

MODEL
= deepseek-v4-pro

TEMPERATURE
= 0.1

JSON_OBJECT_MODE
= {"type":"json_object"}

TIMEOUT_SECONDS
= 120

RETRY
= 0
```

## C1 Artifact

The next calibration must reconstruct the same real evidence through the canonical read-only boundary:

```text
trade_date
= 2026-04-07

subject_key
= 9062832

prompt_version
= identity-llm-prompt.v2

prompt_utf8_bytes
= 4871

prompt_sha256
= 3ed6334fe3ddc9849c1f5e7db940a575202d4dc982849bab117ff4a55c67ec3c
```

The process-launch binding from Issue #428 must be materialized before startup, and the fresh calibration process must independently recheck all three canonical variables.

## Restart Rule

Because the exact prompt artifact changes from v1 to v2, the token sequence restarts at:

```text
1000
```

The complete authorized sequence remains:

```text
[1000, 2000, 4000, 8000, 16000]
```

Only `max_tokens` may vary. The first tier where every selected cohort sample passes receives exactly one confirmation observation per sample.

## Historical Evidence Disposition

The #427 v1 observations at 1000 and 2000 tokens are historical failure evidence only. They cannot establish `SELECTED_MAX_TOKENS` for prompt v2.

## Cohort Reresolution

The next calibration must again resolve the real cohort under the accepted rule:

- fixed C1;
- C2 only if canonical evidence confirms required-review eligibility;
- C3/C4/C5 only if real qualifying evidence exists.

No synthetic subject or business value may be introduced to enlarge the cohort.

## Not Executed in This Task

```text
FULL_CALIBRATION_RUN
= NO

PRODUCTION_SOURCE_CHANGED
= NO

DB_MUTATION
= NO

P2_REAL_COMPOSITE
= HOLD
```

