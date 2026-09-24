# Canonical Identity LLM Error Terminal Matrix v1 — Owner Selection Required

## Status

```text
ERROR_TAXONOMY_STATUS
= FROZEN

TERMINAL_REPRESENTATION_STATUS
= BLOCKED_OWNER_IDENTITY_LLM_CONTRACT_DECISION_REQUIRED
```

The typed classes below are mandatory. For each class, the Owner must select exactly one terminal representation:

```text
REVIEW_PENDING_WITH_TYPED_ERROR
or
HARD_TYPED_FAILURE_RETURNED_TO_CALLER
```

No generic catch-all, silent fallback, retry, or synthetic result is permitted.

## Mandatory Taxonomy

| Class | Exact Trigger | Mandatory Metadata | Never |
|---|---|---|---|
| `CONFIGURATION_MISSING` | Required provider URL/key/model configuration is absent or blank | missing variable names, sanitized values are never exposed | Deterministic review substitution in required-real mode. |
| `TRANSPORT_FAILURE` | Connection failure, DNS failure, or request timeout before a valid HTTP response | safe exception class and phase | Retry, alternate provider, generic failure. |
| `HTTP_FAILURE` | Provider returns a non-success HTTP status | HTTP status, provider request ID if safely available | Raw credential/header/body leakage. |
| `RESPONSE_ENVELOPE_INVALID` | Body is invalid JSON, not an object, `choices` missing/empty, or required envelope shape is invalid | parser/error class and failed envelope check | Treating absent content as `{}`. |
| `CONTENT_MISSING` | Choice/message/content is absent, null, or blank on non-truncated completion | choice index and missing field | Empty-object success. |
| `OUTPUT_TRUNCATED` | `finish_reason` indicates length/output limit before content parsing | finish reason and completion usage when available | JSON repair or second request. |
| `INVALID_JSON` | Content exists but is not one valid JSON object | safe parser position/class only | Raw content leakage or brace/fence repair. |
| `CONTRACT_INVALID` | JSON object violates selected required keys, types, bounds, list limits, or consistency rules | schema version and exact violated rule | Defaulting missing fields. |

## Terminal Decision Matrix

| Class | Terminal Representation | Owner Choice Required | Invariants |
|---|---|---|---|
| `CONFIGURATION_MISSING` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; never deterministic substitution. |
| `TRANSPORT_FAILURE` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; no retry in this attempt. |
| `HTTP_FAILURE` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; status remains visible. |
| `RESPONSE_ENVELOPE_INVALID` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; no empty-object default. |
| `CONTENT_MISSING` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; no synthetic response. |
| `OUTPUT_TRUNCATED` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; no repair. |
| `INVALID_JSON` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; no parser guessing. |
| `CONTRACT_INVALID` | `REVIEW_PENDING_WITH_TYPED_ERROR` or `HARD_TYPED_FAILURE_RETURNED_TO_CALLER` | YES | Never confirmed; no field defaulting. |

## Requirements for Either Terminal Form

### If `REVIEW_PENDING_WITH_TYPED_ERROR`

- Business verdict is exactly `review_pending`.
- Typed error code is mandatory and unambiguous.
- Error metadata survives the service boundary.
- Reason chain identifies provider failure, not successful cognition.
- Downstream cannot promote the item to `confirmed` without a later successful review or authorized override.

### If `HARD_TYPED_FAILURE_RETURNED_TO_CALLER`

- The service returns a typed failure result or raises the project's exact authorized typed exception.
- No partial business verdict is synthesized.
- `BuildIdentityJob` preserves the typed cause and applies its frozen execution policy.
- The failure remains distinguishable from ordinary `review_pending`.

## Sanitization

Error records may expose class names, safe parser class/position, HTTP status, and provider request identifiers only when they are non-secret. They must never expose API keys, authorization headers, full raw responses, credentials, or connection strings.
