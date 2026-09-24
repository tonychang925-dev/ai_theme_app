# Identity LLM Failure Result and Job Aggregate Contract v1

## Boundary Contract

```text
CONFIGURATION_MISSING
= hard typed failure; BuildIdentityJob fails

all runtime/provider/content/schema failures
= subject review_pending
+ exact typed provider failure
+ sanitized metadata
```

No failure may become confirmation, successful provider cognition, silent deterministic substitution, or synthetic success.

## Typed Error Vocabulary

| Code | Exact Trigger | Subject Terminal | Job Effect |
|---|---|---|---|
| `CONFIGURATION_MISSING` | Required provider base, key, or model binding is absent/blank. | No subject result; operation is invalid. | Hard `failed_configuration`; no provider request or subject write from the invalid execution. |
| `TRANSPORT_FAILURE` | Connection, DNS, TLS, or whole-request timeout failure before HTTP status. | `review_pending` | Counts as provider failure. |
| `HTTP_FAILURE` | Status other than `200`. | `review_pending` | Counts as provider failure. |
| `RESPONSE_ENVELOPE_INVALID` | Invalid JSON envelope, non-object envelope, missing/empty choices, or invalid envelope shape. | `review_pending` | Counts as provider failure. |
| `CONTENT_MISSING` | Choice/message/content absent, null, or blank without output-limit classification. | `review_pending` | Counts as provider failure. |
| `OUTPUT_TRUNCATED` | `finish_reason=length` or exact provider output-limit equivalent. | `review_pending` | Counts as provider failure. |
| `INVALID_JSON` | Content is not one valid JSON object. | `review_pending` | Counts as provider failure. |
| `CONTRACT_INVALID` | Exact key set, type, bound, list limit, or response consistency violation. | `review_pending` | Counts as provider failure. |

## Sanitized Metadata Contract

### Common allowed fields

```text
error_code
prompt_version
prompt_sha256
model
provider_attempt_count
```

### Class-specific allowed fields

| Code | Allowed Metadata |
|---|---|
| `CONFIGURATION_MISSING` | Sorted missing configuration variable names. |
| `TRANSPORT_FAILURE` | Safe exception class and phase (`connect`, `send`, `read`, `timeout`). |
| `HTTP_FAILURE` | Integer HTTP status; provider request/correlation ID only if already sanitized. |
| `RESPONSE_ENVELOPE_INVALID` | Envelope validation rule that failed. |
| `CONTENT_MISSING` | Missing content path, such as `choices[0].message.content`. |
| `OUTPUT_TRUNCATED` | Exact finish reason; prompt/completion/total token usage when available. |
| `INVALID_JSON` | Safe parser class and parser position/line-column when available. |
| `CONTRACT_INVALID` | Exact schema rule that failed. |

Forbidden metadata:

- API keys or authorization headers;
- full request headers;
- full raw response body or content;
- database DSNs or credentials;
- unbounded provider payloads;
- stack traces containing local variable values.

## Subject Persistence Semantics

For a provider-degraded subject:

```text
identity_status
= review_pending

is_main_theme
= false

llm_applied
= false

llm_is_main_theme
= false

llm_confidence
= null or persisted unavailable representation

llm_review_error_code
= exact typed code

llm_review_error_metadata
= sanitized JSON object
```

The later implementation must preserve typed error evidence in an existing JSON-compatible field or the narrowest authorized persistence extension. No schema change is authorized by this docs-only task.

## Aggregate Fields

`BuildIdentityJob` must count every required review attempt exactly once:

```text
required_llm_review_attempt_count
```

It must emit:

```text
successful_llm_review_count
provider_failure_count
provider_failure_types
pending_due_to_provider_failure_count
llm_execution_status
```

Invariants:

```text
successful_llm_review_count
<= required_llm_review_attempt_count

provider_failure_count
<= required_llm_review_attempt_count

successful_llm_review_count + provider_failure_count
== required_llm_review_attempt_count

pending_due_to_provider_failure_count
== provider_failure_count
```

`provider_failure_types[code]` counts occurrences by exact code. Codes are sorted deterministically in serialized output.

## Job Status Matrix

| Required Attempts | Successes | Provider Failures | `llm_execution_status` | `BuildResult.status` | Event `success` |
|---:|---:|---:|---|---|---:|
| 0 | 0 | 0 | `NOT_REQUIRED` | `ok_no_required_llm_review` | YES |
| >0 | all | 0 | `CLEAN` | `ok` | YES |
| >0 | some, not all | >0 | `PROVIDER_DEGRADED_MIXED` | `provider_degraded_mixed` | NO |
| >0 | 0 | all | `PROVIDER_DEGRADED_ALL_REQUIRED` | `provider_degraded_all_required` | NO |
| any | 0 | 0 after config preflight failure | `CONFIGURATION_FAILURE` | `failed_configuration` | NO |

The all-required-failed invariant is mechanical:

```text
required_llm_review_attempt_count > 0
AND provider_failure_count == required_llm_review_attempt_count
→ BuildResult.status != ok
→ event success != true
```

## Event and Idempotency Mechanics

- Configuration failure returns/raises before provider requests and before subject writes.
- Provider-degraded execution may preserve non-confirming subject records.
- A provider-degraded job result is durable evidence, not clean success.
- Idempotency completion metadata must include the aggregate fields when a degraded execution is durably recorded.
- Event payload success is false for mixed/all provider failure.
- No automatic retry is spawned by the service or job.

