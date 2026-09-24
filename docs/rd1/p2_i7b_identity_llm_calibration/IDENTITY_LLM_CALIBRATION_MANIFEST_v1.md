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

## Reentry After Provider Binding

Issue #427 was reopened after Issue #428 established the canonical process-launch binding.

```text
BINDING_AUTHORITY_REF
= Issue #428 head 66baaafbd193f46120ff52f0eaede9a6fb1bf62e

BINDING_AUTHORITY_USED_AS_ANCESTRY
= NO

REENTRY_PARENT
= 79cae03ea53f426904cb5972c85f7fed2bd541dc

BINDING_RECHECK
= PASS
```

Fresh-process checks observed:

```text
IDENTITY_LLM_API_BASE_PRESENT
= YES

IDENTITY_LLM_API_KEY_PRESENT
= YES

IDENTITY_LLM_MODEL_PRESENT
= YES

MODEL_IDENTIFIER
= deepseek-v4-pro
```

## Reentry Cohort

Cohort reconstruction used `DatabaseGateway → DBThemeDataGateway → StockReadPort.get_mainline_identity_rule_inputs` and the canonical `IdentityRuleEngine`. No DB write, legacy script, manual SQL, synthetic row, or identity-job write path was used.

| Slot | Selection Result | Exact Evidence |
|---|---|---|
| C1 | SELECTED | `2026-04-07 / 9062832`; one real rule-input row reconstructed. |
| C2 | UNAVAILABLE | Real row and universe entry exist for `2026-09-23 / 9064103`, but `rule_is_main_theme=false`, `logic_ok=false`, and `composite_score=16.075`; required-review predicate is false. |
| C3 | UNAVAILABLE | No real target-date required-review subject satisfied the one-day-tour/risk rule. |
| C4 | UNAVAILABLE | No real target-date non-rule borderline required-review subject existed. |
| C5 | UNAVAILABLE | No real target-date subject had an explicit missing/unavailable evidence field. |

The target-date canonical universe contained 33 subjects with 33 rule-input rows and zero required-review subjects under the frozen predicate.

### C1 Artifact

```text
trade_date
= 2026-04-07

subject_key
= 9062832

selection_rule
= FIXED_LAYER_A_REGRESSION_SAMPLE

prompt_version
= identity-llm-prompt.v1

prompt_utf8_bytes
= 4695

prompt_sha256
= f77e11029cf1a4d776eb2f16ddc9799d8b3f4268edf2a63a144ba54006269a2d

evidence_state_counts
= AVAILABLE:27, MISSING:0, UNAVAILABLE:0, NOT_APPLICABLE:0
```

## Reentry Disposition

```text
COHORT_SELECTED_COUNT
= 1

EXECUTED_TOKEN_TIERS
= [1000, 2000]

DISPOSITION
= CALIBRATION_PROVIDER_OR_CONTRACT_FAILURE

SELECTED_MAX_TOKENS
= BLOCKED

CALIBRATION_STABLE
= NO
```

The first tier returned `OUTPUT_TRUNCATED`. The second tier returned normal completion and valid JSON but violated the strict response contract at `reasons` list length. Issue #427 requires a stop for a real provider/content/schema failure, so tiers `4000`, `8000`, and `16000` were not executed and no prompt/schema/model change was made.
