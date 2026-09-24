# Identity LLM Engineering Contract v1

## Authority and Status

```text
OWNER_SEMANTIC_AUTHORITY
= Issue #425 comment 5813922812

ENGINEERING_CONTRACT_STATUS
= COMPILED

OWNER_SEMANTICS_REOPENED
= NO

PRODUCTION_SOURCE_EDIT
= NOT_PERFORMED

PROVIDER_REQUEST_COUNT
= 0
```

This contract compiles the Owner-frozen Q1–Q5 semantics into deterministic implementation mechanics. It does not execute a provider, mutate a database, alter production source, or authorize P2 composite execution.

## Component Boundaries

| Component | Exact Responsibility | Forbidden Responsibility |
|---|---|---|
| `IdentityLLMReviewService` | Build the canonical prompt, make at most one provider request, validate strict JSON, classify transport/provider/content/schema failures, return a typed review result or hard configuration failure. | Final identity status, rule scoring, hard-gate override, identity-to-cycle mutation, DB access. |
| `IdentityRuleEngine` | Produce rule scores and rule outputs from explicit canonical inputs. | Provider access or LLM review. |
| `BuildIdentityJob` | Supply all prompt fields with explicit evidence states, translate completed review evidence to the final-decision interface, preserve typed subject failures, aggregate provider-degraded execution, and fail hard on missing configuration. | Construct provider HTTP semantics, reinterpret provider failure as successful cognition, or hide aggregate degradation. |
| `IdentityDecider` | Own the final business identity decision after rule, one-day-tour, continuity/K-line, and review evidence are available under canonical business semantics. | Provider transport or JSON parsing. |
| Database gateway | Persist the compiled typed review fields and aggregate-compatible subject records through existing ports. | Business review interpretation or direct provider access. |

## Exact Provider Binding

### Configuration namespace

The required-real-LLM path uses exactly:

```text
IDENTITY_LLM_API_BASE
IDENTITY_LLM_API_KEY
IDENTITY_LLM_MODEL
```

Rules:

1. All three values must be present and non-blank before the first review attempt.
2. Missing or blank values produce exactly `CONFIGURATION_MISSING`.
3. `IDENTITY_LLM_API_BASE` is a base URL without `/chat/completions`.
4. The endpoint is exactly `<IDENTITY_LLM_API_BASE>/chat/completions` after trimming trailing `/` characters from the base.
5. `IDENTITY_LLM_MODEL` is deployment-bound and has no implicit fallback default. Its exact non-blank value is recorded in prompt/review provenance.
6. The API key is never logged, hashed into prompt provenance, or included in persisted metadata.

### Request shape

```json
{
  "model": "<IDENTITY_LLM_MODEL>",
  "messages": [
    {"role": "system", "content": "You are the canonical identity LLM reviewer. Return only one strict JSON object."},
    {"role": "user", "content": "<identity-llm-prompt.v1 artifact>"}
  ],
  "temperature": 0.1,
  "max_tokens": "<selected calibrated integer>",
  "response_format": {"type": "json_object"}
}
```

The system message is fixed. The user message is exactly the prompt artifact defined in `IDENTITY_LLM_CANONICAL_PROMPT_ARTIFACT_v1.md`.

### Transport mechanics

- Request timeout: `120` seconds, implemented as a finite whole-request timeout.
- HTTP success contract: only status `200` is success.
- Provider request count per subject review attempt: exactly `1`.
- Retry count: `0`.
- Alternate provider count: `0`.
- JSON repair count: `0`.
- Reasoning/thinking parameter: absent; provider default remains unchanged.

## Compiled Version and Hash Literals

| Item | Literal/Mechanic |
|---|---|
| Prompt version | `identity-llm-prompt.v1` |
| Prompt encoding | UTF-8 |
| Prompt hash | SHA-256 over exact prompt artifact bytes |
| Response schema version | `identity-llm-response.v1` |
| Rule identity version | `identity_rule_engine.v1` |
| Confidence domain | Decimal ratio `[0.0000, 1.0000]` |
| Persistence representation | signed integer basis points `[0, 10000]` |
| Provider JSON mode | `response_format={"type":"json_object"}` |
| Temperature | `0.1` |
| Timeout | `120` seconds |

## Exact Result Carrier

The service boundary uses one typed result carrier with three mutually exclusive kinds:

```text
IDENTITY_LLM_REVIEW_SUCCESS
IDENTITY_LLM_PROVIDER_FAILURE
IDENTITY_LLM_CONFIGURATION_FAILURE
```

### Success

```text
kind
= SUCCESS
schema_version
= identity-llm-response.v1
prompt_version
= identity-llm-prompt.v1
prompt_sha256
= <64 lowercase hex characters>
model
= <exact configured model>
logic_dimension_ok
= boolean
market_dimension_ok
= boolean
is_main_theme
= boolean
confidence
= Decimal ratio, four decimal places
confidence_basis_points
= integer 0..10000
reasons
= one to three non-empty strings
risk_flags
= zero to three non-empty strings
```

The service returns dimensional review evidence only. It does not return `identity_status=confirmed`.

### Subject provider failure

```text
kind
= PROVIDER_FAILURE
error_code
= one of the compiled typed classes
prompt_version
= identity-llm-prompt.v1
prompt_sha256
= <64 lowercase hex characters>
model
= <exact configured model>
subject_review_status
= review_pending
sanitized_metadata
= exact class-specific fields
```

### Configuration failure

```text
kind
= CONFIGURATION_FAILURE
error_code
= CONFIGURATION_MISSING
missing_configuration_names
= non-empty sorted list
```

This is a hard typed failure. `BuildIdentityJob` must fail before provider requests or subject writes when configuration is invalid.

## Review-to-Decider Boundary

A completed provider response may enforce only transport-level consistency:

```text
is_main_theme
== logic_dimension_ok AND market_dimension_ok
```

That equality means only that the provider's aggregate review flag agrees with its two review dimensions. It is not the final identity algorithm and does not bypass:

- one-day-tour evidence;
- continuity/K-line hard gates;
- rule conditions;
- inherited/bootstrap/override semantics;
- `IdentityDecider`;
- lifecycle ownership.

For minimal compatibility with the current decider interface, `BuildIdentityJob` translates completed review evidence as follows:

| Provider dimensional review | Temporary decider input candidate |
|---|---|
| `is_main_theme=true` | `llm_verdict="confirmed"` candidate; `IdentityDecider` still applies all hard gates. |
| `is_main_theme=false` and confidence `>= 0.6000` | `llm_verdict="review_pending"` candidate. |
| `is_main_theme=false` and confidence `< 0.6000` | `llm_verdict="observed"` candidate. |

Confidence only controls whether a negative dimensional review remains queued for review. It is never a composite score, rule score, final identity probability, or confirmation override.

## Job Aggregate Contract

`BuildResult.metrics` must include:

```text
required_llm_review_attempt_count
successful_llm_review_count
provider_failure_count
provider_failure_types
pending_due_to_provider_failure_count
llm_execution_status
```

`provider_failure_types` is a map from exact typed code to occurrence count. Exact status vocabulary:

| Condition | `llm_execution_status` | `BuildResult.status` | Clean semantic success |
|---|---|---|---|
| Required reviews exist and all succeed | `CLEAN` | `ok` | YES |
| No subject requires LLM review | `NOT_REQUIRED` | `ok_no_required_llm_review` | YES for LLM execution |
| Some required reviews succeed and some fail | `PROVIDER_DEGRADED_MIXED` | `provider_degraded_mixed` | NO |
| All required attempts fail | `PROVIDER_DEGRADED_ALL_REQUIRED` | `provider_degraded_all_required` | NO |
| Configuration missing | `CONFIGURATION_FAILURE` | `failed_configuration` | NO |

Subject-level provider failures may preserve non-confirming `review_pending` records, but the event payload and job result must not represent the execution as clean semantic success.

## Implementation Consequences

1. `BuildIdentityJob` must retain raw evidence presence before lossy rule-input normalization and pass explicit evidence states to the prompt owner.
2. The prompt owner must never convert `MISSING`, `UNAVAILABLE`, or `NOT_APPLICABLE` into `0`, `false`, `true`, or another business value.
3. The current `int(Decimal("0.85")) → 0` cast is forbidden.
4. Provider-degraded records must carry exact typed metadata in allowed sanitized form.
5. Configuration is preflighted once before subject processing.
6. No implementation may add retry, fallback provider, deterministic substitution in required mode, JSON repair, or identity-to-cycle mutation.

## Deliverable Map

| Deliverable | Contract |
|---|---|
| `IDENTITY_LLM_CANONICAL_PROMPT_ARTIFACT_v1.md` | Exact deterministic prompt and hash fixture. |
| `IDENTITY_LLM_COMPILED_RESPONSE_SCHEMA_v1.md` | Exact strict response keys, types, bounds, and validation order. |
| `IDENTITY_LLM_FAILURE_RESULT_AND_JOB_AGGREGATE_CONTRACT_v1.md` | Exact typed error metadata and aggregate visibility. |
| `IDENTITY_LLM_CONFIDENCE_COMPATIBILITY_AUDIT_v1.md` | End-to-end confidence representation and lossless conversion. |
| `IDENTITY_LLM_CALIBRATION_PREPARATION_v1.md` | Real cohort rule, token tiers, and confirmation count. |
