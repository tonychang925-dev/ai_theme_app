# Canonical Identity LLM Gap Audit v1

## Scope

Audited canonical owner:

```text
stock_processing_service/domain/services/identity_llm_review_service.py
```

Canonical caller:

```text
stock_processing_service/application/jobs/build_identity_job.py
```

The rejected legacy script and `/private/tmp` calibration are historical comparisons only. Neither is production authority.

## Ownership

The required path is:

```text
BuildIdentityJob
→ IdentityLLMReviewService.review_with_rule()
→ strict JSON provider transport
→ typed verdict or typed provider/API error classification
```

`BuildIdentityJob` injects the service at lines 39-48 and invokes it at line 326. `docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md:89` names this service as the Layer A review authority.

## Current facts

`review_with_rule()` reads `IDENTITY_LLM_API_URL` and `IDENTITY_LLM_API_KEY`. If either is absent, it silently calls deterministic review.

The API request currently uses:

- model `IDENTITY_LLM_MODEL`, default `deepseek-chat`;
- temperature `0.1`;
- `max_tokens=512`;
- 30-second timeout;
- no `response_format`;
- one `urlopen` request.

The response path:

1. parses the HTTP body;
2. reads `choices[0].message.content`, defaulting missing content to `"{}"`;
3. parses string content;
4. maps provider, API, transport, envelope, and JSON failures to `review_pending`.

No `finish_reason` is inspected.

## Gap matrix

| Required property | Current state | Severity |
|---|---|---|
| Real provider invocation | Configuration absence selects deterministic review | P0 |
| Exact canonical prompt identity | Short API prompt differs from documented production prompt builder | P0 |
| Use documented prompt builder | `build_llm_prompt()` exists but is not called | P0 |
| JSON-object request contract | Missing | P0 |
| Terminal finish handling | Missing | P0 |
| `finish_reason=length` fail-closed | Missing | P0 |
| Missing content fail-closed | Defaults to `{}` | P0 |
| Invalid JSON fail-closed from confirmation | Becomes `review_pending`; error class is lost | P0 |
| HTTP status typing | Not separately classified | P0 |
| Transport/provider failure typing | Indistinguishable pending state; not confirmed and not synthetic success | P0 |
| No fallback in required mode | Violated | P0 |
| One request only | Present and must be preserved | P0 requirement |
| Calibrated configurable budget | Fixed 512 | P0 |
| Required response-key validation | Missing | P0 |
| Usage metadata capture | Missing | P1 |
| Safe typed error without raw content | Not established | P1 |

## Required error classification

Current code collapses configuration, network, envelope, content, and JSON failures into `review_pending`. The current semantics are therefore:

```text
provider/API failure
→ review_pending
→ NOT confirmed
→ NOT synthetic success
```

This is `FAIL-CLOSED PENDING SEMANTICS` plus a provider contract/error-typing gap and strict JSON transport gap. The transport must distinguish these classes:

```text
IDENTITY_LLM_CONFIGURATION_MISSING
IDENTITY_LLM_TRANSPORT_FAILURE
IDENTITY_LLM_HTTP_<status>
IDENTITY_LLM_RESPONSE_ENVELOPE_INVALID
IDENTITY_LLM_CONTENT_MISSING
IDENTITY_LLM_OUTPUT_TRUNCATED
IDENTITY_LLM_INVALID_JSON
IDENTITY_LLM_CONTRACT_INVALID
```

None may become `confirmed`, `observed`, deterministic review, or synthetic success. Whether a class remains representable as `review_pending` must first be proven from contract/ADR authority; this audit does not presume that the correction must throw an exception.

## Prompt mismatch

`build_llm_prompt()` at line 221 is documented as a one-to-one production reproduction and accepts:

- `trade_date`;
- `subject_key`;
- `subject_name`;
- `rule_input`;
- `rule_output`;
- `one_day_tour_flag`;
- optional `kline_result`.

`BuildIdentityJob.review_with_rule()` supplies only:

- composite score;
- one-day-tour flag;
- `logic_ok`;
- `market_ok`;
- `rule_is_main_theme`.

Therefore the current API request cannot be the exact documented canonical prompt. The API prompt also asks for `is_main_theme`, while the historical production contract asks for logic, market, and core-main-theme booleans. The owner must freeze the canonical contract before implementation.

## Why 4000 is only a hypothesis

The historical tier was measured on a different prompt, response contract, model default, transport, and fallback policy. The canonical path currently uses 512 tokens and no JSON-object mode.

```text
4000_TOKEN_RESULT
= HISTORICAL_DIAGNOSTIC_EVIDENCE_ONLY
NOT_CANONICAL_PRODUCTION_FACT
```

It may only narrow a future canonical calibration; it cannot be copied as production truth.

## Strict transport requirements

1. Require provider configuration in required-LLM mode.
2. Freeze canonical prompt and response schema.
3. Make exactly one provider request per review.
4. Preserve owner-approved model and temperature semantics.
5. Include JSON-object response format.
6. Use an explicit, finite, independently calibrated completion budget.
7. Validate HTTP status and envelope.
8. Inspect `finish_reason` before parsing content.
9. Fail closed on `finish_reason=length`.
10. Fail closed on missing/empty content.
11. Fail closed on invalid JSON.
12. Validate required keys and types.
13. Return typed provider/API/transport/contract failure classification.
14. Preserve fail-closed pending semantics unless contract/ADR authority proves a different terminal representation.
15. Never use deterministic review in required mode.
16. Never retry or repair JSON.
17. Never expose raw provider content or credentials.

## Disposition

This is a P0 canonical semantic gap. No source change is authorized by the audit task; correction is follow-up A in `P2_I7B_CORRECTION_TASK_DECOMPOSITION_v1.md`.

```text
PROVIDER/API_FAILURE_CURRENT_RESULT
= review_pending
≠ confirmed
≠ synthetic success

PENDING_REPRESENTATION_AUTHORITY
= CONTRACT_ADR_DECISION_REQUIRED

4000_TOKEN_RESULT
= HISTORICAL_DIAGNOSTIC_EVIDENCE_ONLY
```
