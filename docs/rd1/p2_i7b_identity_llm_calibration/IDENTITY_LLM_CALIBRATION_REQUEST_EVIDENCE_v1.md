# Identity LLM Calibration Request Evidence v1

## Request Log

```text
REQUEST_RECORD_COUNT
= 0
```

No provider request was made because the required canonical configuration preflight failed.

## Required Fields

The following fields remain not applicable for every possible cohort/tier because execution stopped before request construction:

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

## Security

No API key, authorization header, endpoint credential, raw response, or raw prompt was logged or committed.

## Reentry Request Log

Two provider requests were made. No raw response content is recorded.

### Request 1 — C1 / Initial / 1000 Tokens

| Field | Value |
|---|---:|
| `cohort_slot` | C1 |
| `trade_date` | 2026-04-07 |
| `subject_key` | 9062832 |
| `prompt_version` | identity-llm-prompt.v1 |
| `prompt_sha256` | f77e11029cf1a4d776eb2f16ddc9799d8b3f4268edf2a63a144ba54006269a2d |
| `schema_version` | identity-llm-response.v1 |
| `model` | deepseek-v4-pro |
| `temperature` | 0.1 |
| `max_tokens` | 1000 |
| `json_object_mode` | YES |
| `timeout_seconds` | 120 |
| `http_status` | 200 |
| `finish_reason` | length |
| `prompt_tokens` | NOT_AVAILABLE |
| `completion_tokens` | NOT_AVAILABLE |
| `total_tokens` | NOT_AVAILABLE |
| `content_present` | NO |
| `content_utf8_bytes` | 0 |
| `content_sha256` | NOT_APPLICABLE |
| `response_json_valid` | NO |
| `response_contract_valid` | NO |
| `typed_error_code` | OUTPUT_TRUNCATED |
| `provider_request_count` | 1 |
| `attempt_kind` | INITIAL |
| `elapsed_seconds` | 17.640 |

### Request 2 — C1 / Initial / 2000 Tokens

| Field | Value |
|---|---:|
| `cohort_slot` | C1 |
| `trade_date` | 2026-04-07 |
| `subject_key` | 9062832 |
| `prompt_version` | identity-llm-prompt.v1 |
| `prompt_sha256` | f77e11029cf1a4d776eb2f16ddc9799d8b3f4268edf2a63a144ba54006269a2d |
| `schema_version` | identity-llm-response.v1 |
| `model` | deepseek-v4-pro |
| `temperature` | 0.1 |
| `max_tokens` | 2000 |
| `json_object_mode` | YES |
| `timeout_seconds` | 120 |
| `http_status` | 200 |
| `finish_reason` | stop |
| `prompt_tokens` | 1432 |
| `completion_tokens` | 1939 |
| `total_tokens` | 3371 |
| `content_present` | YES |
| `content_utf8_bytes` | 889 |
| `content_sha256` | b90799e646165cb2822a595c1d3e331766484a3b0b09c57f013ea2683c89bda6 |
| `response_json_valid` | YES |
| `response_contract_valid` | NO |
| `typed_error_code` | CONTRACT_INVALID:reasons_length |
| `provider_request_count` | 1 |
| `attempt_kind` | INITIAL |
| `elapsed_seconds` | 25.208 |

## Reentry Security

The request log contains only hashes, usage counts, statuses, finish reasons, and typed classification. No API key, authorization header, endpoint credential, raw response content, or raw prompt was logged or committed.
