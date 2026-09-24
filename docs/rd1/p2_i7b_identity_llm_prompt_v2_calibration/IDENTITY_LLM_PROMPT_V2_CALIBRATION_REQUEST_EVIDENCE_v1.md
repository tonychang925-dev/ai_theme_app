# Identity LLM Prompt v2 Calibration Request Evidence

All observations use the same real C1 sample and frozen prompt:

```text
cohort_slot = C1
trade_date = 2026-04-07
subject_key = 9062832
prompt_version = identity-llm-prompt.v2
prompt_sha256 = 3ed6334fe3ddc9849c1f5e7db940a575202d4dc982849bab117ff4a55c67ec3c
schema_version = identity-llm-response.v1
model = deepseek-v4-pro
temperature = 0.1
```

No prompt text, response text, reasons text, risk-flag text, API key, or HTTP
header is recorded.

## Request 1 — 1000 INITIAL

```text
max_tokens = 1000
http_status = 200
finish_reason = length
prompt_tokens = NOT_AVAILABLE
completion_tokens = NOT_AVAILABLE
total_tokens = NOT_AVAILABLE
content_present = NO
content_utf8_bytes = 0
content_sha256 = NONE
response_json_valid = NO
response_contract_valid = NO
reasons_item_count = NOT_AVAILABLE
reasons_item_lengths = NOT_AVAILABLE
risk_flags_item_count = NOT_AVAILABLE
risk_flag_lengths = NOT_AVAILABLE
typed_error_code = OUTPUT_TRUNCATED
attempt_kind = INITIAL
provider_request_count = 1
```

## Request 2 — 2000 INITIAL

```text
max_tokens = 2000
http_status = 200
finish_reason = length
prompt_tokens = NOT_AVAILABLE
completion_tokens = NOT_AVAILABLE
total_tokens = NOT_AVAILABLE
content_present = NO
content_utf8_bytes = 0
content_sha256 = NONE
response_json_valid = NO
response_contract_valid = NO
reasons_item_count = NOT_AVAILABLE
reasons_item_lengths = NOT_AVAILABLE
risk_flags_item_count = NOT_AVAILABLE
risk_flag_lengths = NOT_AVAILABLE
typed_error_code = OUTPUT_TRUNCATED
attempt_kind = INITIAL
provider_request_count = 1
```

## Request 3 — 4000 INITIAL

```text
max_tokens = 4000
http_status = 200
finish_reason = stop
prompt_tokens = 1488
completion_tokens = 1821
total_tokens = 3309
content_present = YES
content_utf8_bytes = 773
content_sha256 = 301992639bbefdba9773cf33e98712644f56ff7fcf6437ee6aa3451a1c729119
response_json_valid = YES
response_contract_valid = YES
reasons_item_count = 3
reasons_item_lengths = [139, 148, 102]
risk_flags_item_count = 2
risk_flag_lengths = [110, 80]
typed_error_code = NONE
attempt_kind = INITIAL
provider_request_count = 1
```

## Request 4 — 4000 CONFIRMATION

```text
max_tokens = 4000
http_status = 200
finish_reason = stop
prompt_tokens = 1488
completion_tokens = 1744
total_tokens = 3232
content_present = YES
content_utf8_bytes = 585
content_sha256 = 0f361ab8550c6667e27b00fa6359d343d8b607160552c8a4670185fd98868eff
response_json_valid = YES
response_contract_valid = YES
reasons_item_count = 2
reasons_item_lengths = [119, 106]
risk_flags_item_count = 2
risk_flag_lengths = [69, 106]
typed_error_code = NONE
attempt_kind = CONFIRMATION
provider_request_count = 1
```

The provider returned no usage fields for truncated responses; those fields are
recorded as `NOT_AVAILABLE` rather than inferred.
