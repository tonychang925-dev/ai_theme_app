# Identity LLM Calibration Manifest v1

## Task and Authority

```text
TASK_ID
= RD1-P2-I7B-CANONICAL-IDENTITY-LLM-REAL-PROVIDER-CALIBRATION-P0

TASK_BASE
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

OWNER_SEMANTIC_AUTHORITY
= Issue #425 comment 5813922812

ENGINEERING_CONTRACT_AUTHORITY
= Issue #426 head 2815b81598e94f37ceef12420acc2b1d2e8f368d

AUTHORITY_REFS_USED_AS_ANCESTRY
= NO
```

## Intended Calibration Mechanics

```text
prompt_version
= identity-llm-prompt.v1

schema_version
= identity-llm-response.v1

provider_endpoint
= <IDENTITY_LLM_API_BASE>/chat/completions

model_binding
= exact non-blank IDENTITY_LLM_MODEL

temperature
= 0.1

response_format
= {"type":"json_object"}

timeout_seconds
= 120

retry_count
= 0

token_tiers
= [1000, 2000, 4000, 8000, 16000]
```

## Intended Cohort Slots

| Slot | Rule | Disposition |
|---|---|---|
| C1 | Fixed Layer A regression sample `2026-04-07 / 9062832`. | `NOT_REACHED_CONFIGURATION_PREFLIGHT_FAILED` |
| C2 | Target-date borderline candidate `2026-09-23 / 9064103`, only if canonical read-only evidence confirms eligibility. | `NOT_REACHED_CONFIGURATION_PREFLIGHT_FAILED` |
| C3 | Highest real one-day-tour/risk required-review subject. | `NOT_REACHED_CONFIGURATION_PREFLIGHT_FAILED` |
| C4 | Closest real non-rule borderline required-review subject. | `NOT_REACHED_CONFIGURATION_PREFLIGHT_FAILED` |
| C5 | Real subject with the greatest explicit missing/unavailable evidence count. | `NOT_REACHED_CONFIGURATION_PREFLIGHT_FAILED` |

No synthetic subject or business value was introduced.

## Configuration Preflight

The process environment was checked without printing secret values:

```text
IDENTITY_LLM_API_BASE_PRESENT
= NO

IDENTITY_LLM_API_KEY_PRESENT
= NO

IDENTITY_LLM_MODEL_PRESENT
= NO
```

Repository search found no secure deployment binding that materializes all three canonical variables. A legacy replay helper can copy a legacy API key/model into canonical names, but it does not supply the required canonical API base and must not be used as a silent substitution under Issue #427.

## Disposition

```text
DISPOSITION
= BLOCKED_CALIBRATION_CONFIGURATION_MISSING

COHORT_SELECTED_COUNT
= 0

PROVIDER_REQUEST_COUNT
= 0

SELECTED_MAX_TOKENS
= BLOCKED

CALIBRATION_STABLE
= BLOCKED
```

Cohort reconstruction was not attempted after preflight failure because the task requires configuration verification before any provider call and forbids legacy-variable substitution.
