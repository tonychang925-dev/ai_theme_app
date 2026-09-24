# Identity LLM Calibration Preparation v1

## Status

```text
CALIBRATION_PREPARED
= YES

CALIBRATION_EXECUTED
= NO

PROVIDER_REQUEST_COUNT
= 0
```

This document defines the exact later calibration. It does not select a token budget and does not use synthetic business evidence.

## Fixed Calibration Mechanics

| Item | Value |
|---|---|
| Prompt | `identity-llm-prompt.v1` |
| Schema | `identity-llm-response.v1` |
| Provider | OpenAI-compatible `/chat/completions` endpoint configured by `IDENTITY_LLM_API_BASE` |
| Model | Exact non-blank `IDENTITY_LLM_MODEL`; no substitution |
| Temperature | `0.1` |
| JSON mode | `{"type":"json_object"}` |
| Timeout | `120` seconds |
| Requests per sample/tier | `1` |
| Retry | `0` |
| Variable by tier | `max_tokens` only |

## Real Cohort Selection Rule

The cohort contains at most five real subjects. No synthetic business values are permitted.

### Fixed C1 — Layer A regression rule-pass sample

```text
trade_date
= 2026-04-07

subject_key
= 9062832
```

Authority: frozen Layer A regression truth in `PHASE_CONTRACT_LAYER_ABCD.md`.

### Deterministic C2 — Current target borderline sample

```text
trade_date
= 2026-09-23

subject_key
= 9064103
```

This subject is retained only if read-only canonical evidence reconstructs a required-review prompt input. It covers the current target-date borderline/risk surface.

### Deterministic C3 — Current one-day-tour/risk sample

From the target-date required-review set:

1. filter subjects with `one_day_tour_flag=true` or `one_day_tour_risk_score>=70`;
2. order by `one_day_tour_risk_score DESC`, then `subject_key ASC`;
3. select the first subject other than C1/C2.

### Deterministic C4 — Current non-rule borderline sample

From the target-date required-review set:

1. exclude confirmed/inherited/bootstrap subjects;
2. require `rule_is_main_theme=false`;
3. require `logic_ok=true` or `composite_score>=55`;
4. order by `abs(composite_score-60) ASC`, then `subject_key ASC`;
5. select the first subject other than C1/C2/C3.

### Deterministic C5 — Explicit missing/insufficient-evidence sample

From the target-date explicit evidence reconstruction:

1. include only subjects with at least one `MISSING` or `UNAVAILABLE` evidence field;
2. order by count of such fields `DESC`, then `subject_key ASC`;
3. select the first subject other than C1/C2/C3/C4.

If real data does not support a class, the manifest records that class as unavailable. The class is not replaced with synthetic evidence.

## Required-Review Eligibility

For non-inherited, non-bootstrap subjects, calibration reconstructs the same eligibility predicate as `BuildIdentityJob`:

```text
rule_is_main_theme
OR logic_ok
OR composite_score >= 55
```

Cohort resolution is read-only and must not run production writes, recap jobs, or composite flow.

## Cohort Manifest

For every selected subject, record:

```text
cohort_slot
trade_date
subject_key
selection_rule
required_review
prompt_version
prompt_utf8_bytes
prompt_sha256
schema_version
model
evidence_state_counts
```

The manifest hash is SHA-256 over the UTF-8 JSON serialization using:

```python
json.dumps(
    manifest,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
)
```

## Token Tiers

Exact ascending sequence:

```text
1000
2000
4000
8000
16000
```

Historical `4000` is diagnostic evidence only and receives no preferential selection.

## Confirmation Count

When a tier first passes every cohort sample:

```text
confirmation reruns per sample
= 1
```

Thus a stable first-pass tier requires two successful provider observations per sample: one initial and one confirmation. If a confirmation fails with `OUTPUT_TRUNCATED`, calibration advances to the next tier. No same-tier retry is permitted.

Maximum requests with five samples and all tiers exhausting:

```text
initial
= 25

confirmation
= 5

maximum
= 30
```

Calibration stops earlier when a lower tier is stable.

## Tier Success Criteria

Every sample must return:

- HTTP `200`;
- `finish_reason` not indicating output length;
- non-empty content;
- one valid JSON object;
- exact six-key schema;
- valid types, bounds, list limits, and aggregate consistency;
- typed error code `NONE`;
- exactly one provider request.

The smallest tier with all initial and confirmation observations passing becomes:

```text
SELECTED_MAX_TOKENS
```

No larger tier may be selected for comfort.

## Evidence Record Per Request

```text
cohort_slot
trade_date
subject_key
prompt_version
prompt_sha256
schema_version
model
temperature
max_tokens
json_object_mode
timeout_seconds
http_status
finish_reason
prompt_tokens
completion_tokens
total_tokens
content_present
content_utf8_bytes
content_sha256
response_json_valid
response_contract_valid
typed_error_code
provider_request_count
attempt_kind
```

`attempt_kind` is exactly `INITIAL` or `CONFIRMATION`.

## Stop Conditions

Calibration is blocked or stopped without source correction if:

1. required provider configuration is missing;
2. no real C1 evidence can be reconstructed;
3. the exact model binding is absent;
4. any tier returns a non-provider success but invalid contract;
5. all tiers exhaust without stable success;
6. preserving the exact prompt would exceed the highest tier;
7. any implementation attempts to simplify the prompt, swap the model, retry, repair JSON, or substitute a provider.

No raw response content or credential-bearing header may be persisted in task evidence.

