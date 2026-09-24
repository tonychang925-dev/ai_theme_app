# Canonical Identity LLM Contract Audit v1

## Task

`RD1-P2-I7B-CANONICAL-IDENTITY-LLM-JSON-TRANSPORT-ERROR-TYPING-P0`

## Scope and Evidence Basis

- Audit base: `bc34e973686d7f78b0e9c3efd67b433f0901f21a`.
- Audit target: `BuildIdentityJob → IdentityLLMReviewService → provider`.
- The old `stock_service/scripts/build_mainline_identity_registry.py` path was inspected only as historical Layer A evidence and was not modified.
- Issue #422 and Issue #423 evidence are authority references, not ancestry.
- No provider request, DB access, production job execution, recap execution, or composite execution was performed for this audit.

## Executive Disposition

```text
DISPOSITION
= BLOCKED_CANONICAL_IDENTITY_LLM_CONTRACT_NOT_FROZEN
```

The canonical prompt, response schema, model/provider configuration authority, and typed provider-failure terminal representation are not frozen as one coherent production contract. Consequently, Stage 1 calibration and Stage 2 source correction are not authorized in this task.

## Canonical Code Findings

### Actual API path

`stock_processing_service/domain/services/identity_llm_review_service.py`:

- `review_with_rule()` selects the API only when both `IDENTITY_LLM_API_URL` and `IDENTITY_LLM_API_KEY` are present.
- Missing either value silently selects `_deterministic_review()`.
- The active API prompt is the inline prompt in `_api_review()`.
- Its request uses:
  - model from `IDENTITY_LLM_MODEL`, defaulting to `deepseek-chat`;
  - temperature `0.1`;
  - `max_tokens=512`;
  - one `urlopen` request with a 30-second timeout;
  - no `response_format`.
- Missing response content defaults to `"{}"`.
- Transport, envelope, indexing, and JSON parsing failures collapse into one catch and return `verdict="review_pending"` with `reason="llm_api_failed:<exception>"`.
- HTTP status, `finish_reason`, missing required keys, type mismatches, truncation, and other provider/contract failures are not separately typed.
- The parsed result is consumed without a required-key/type schema validation contract.

### Unused alternate prompt

The same service defines `build_llm_prompt()`, described as a production 1:1 reproduction and intended for future API use, but `review_with_rule()` does not call it. That method accepts:

- `trade_date`;
- `subject_key`;
- `subject_name`;
- full `rule_input`;
- full `rule_output`;
- `one_day_tour_flag`;
- optional `kline_result`.

These are materially richer inputs than those passed to the active API prompt. Therefore the current service contains two prompt authorities, and only the shorter inline prompt is executable.

### Caller input mismatch

`BuildIdentityJob` invokes `review_with_rule()` with only:

- `composite_score`;
- `one_day_tour_flag`;
- `logic_ok`;
- `market_ok`;
- `rule_is_main_theme`.

It does not supply the full canonical `build_llm_prompt()` field set or the historical Layer A evidence set. Thus there is no mechanical call-path proof that the active short prompt is equivalent to the service's declared production prompt builder.

## Contract Authority Findings

### Frozen Layer A architecture authority

`docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md` establishes:

- The old-chain identity script is the unique Layer A algorithm authority for scoring, input semantics, K-line shape analysis, and one-day-tour behavior.
- The canonical owners are `IdentityRuleEngine`, `OneDayTourDetector`, `IdentityLLMReviewService`, `IdentityDecider`, and `BuildIdentityJob`.
- Every business judgment must trace to a design document, old-chain equivalent function, or ADR.
- Missing evidence must fail closed or omit the proposition judgment; it must not create default business truth.
- `review_pending` is a review funnel state and never directly confirms identity.

This authority identifies ownership and broad fail-closed semantics, but does not freeze:

- the exact canonical prompt text;
- the exact response JSON schema;
- model or environment-variable authority;
- JSON-object mode;
- completion token budget;
- the terminal representation for each typed provider/transport failure;
- whether all such failures may remain represented as `review_pending`.

### Migration plan and architecture authority

`docs/project_control/P3-M1-LayerA-identity-migration-plan.md` requires a controlled input plus structured output interface and a traceable `review_pending` reason chain. `docs/architecture/个人投资助理-项目架构设计-第三阶段.md` assigns controlled review to `IdentityLLMReviewService`, defines the funnel semantics, and forbids direct confirmation from `review_pending`.

Neither document freezes the exact transport contract or prompt/response schema required for Stage 1 calibration.

### Architecture review conflict

`docs/project_control/ARCH_REVIEW.md` states that LLM failure allows the rule chain to continue and exposes `llm_review_status`. This may support a non-confirmed pending representation, but it does not define the exact typed taxonomy or prove that every provider/transport/JSON failure must map to `review_pending`. It also predates the stricter current requirement for a typed, observable failure classification.

### ADR authority

The available ADR list contains no ADR freezing the canonical identity-LLM prompt, provider contract, response schema, token budget, or provider-failure terminal representation.

## Historical Response-Shape Conflict

The historical legacy response schema is:

```text
logic_dimension_ok_llm: boolean
market_dimension_ok_llm: boolean
is_main_theme_core_llm: boolean
confidence: 0-100
reasons: list, maximum 3
risk_flags: list, maximum 3
```

The executable canonical API prompt and unused `build_llm_prompt()` both request:

```text
is_main_theme: boolean
confidence: 0.0-1.0
reasons: list
risk_flags: list
```

These are incompatible response contracts. The canonical confidence scale also differs from the historical scale. Neither canonical prompt includes the full historical evidence set, and the active API prompt is substantially less complete than the unused canonical builder.

The historical request used DeepSeek environment authority, system plus user messages, temperature `0.1`, `max_tokens=1000`, and `response_format={"type":"json_object"}`. The executable canonical request uses separate `IDENTITY_LLM_*` authority, one user message, `max_tokens=512`, and no response-format declaration.

## Required Frozen Semantics

The following semantics are already established and must be preserved by any later correction:

```text
provider/API failure
→ exact typed classification
→ NOT confirmed
→ NOT observed as successful cognition
→ NOT deterministic fallback in required-real-LLM mode
→ NOT synthetic success
```

Whether a typed provider/transport/contract failure remains internally represented as `review_pending` requires an explicit contract or ADR decision. It cannot be inferred merely from current catch-all behavior, general funnel language, or the legacy script.

## Stage Decisions

| Stage | Result | Reason |
|---|---|---|
| Stage 0 contract proof | BLOCKED | No single coherent frozen prompt/response/provider/failure contract exists. |
| Stage 1 provider calibration | NOT_REACHED | Calibrating a selected prompt by convenience would fabricate authority. |
| Stage 2 production correction | NOT_REACHED | Source correction is unauthorized until Stages 0 and 1 pass. |

## Required Owner Decision Before Reentry

An authorized contract decision must freeze all of the following before implementation:

1. one canonical prompt authority and exact input set;
2. exact response keys, types, confidence scale, and list limits;
3. provider and model configuration authority;
4. JSON-object response mode;
5. required-real-LLM mode and missing-config behavior;
6. exact typed classifications for HTTP, timeout/network, envelope, missing choice/content, truncation, invalid JSON, and schema failures;
7. the authorized terminal business representation for each typed failure;
8. one-request/no-retry semantics;
9. the calibration method and token tiers for the selected exact canonical prompt.

Until those decisions are recorded, selecting the historical 4000-token result as the canonical production budget would be invalid. That value remains diagnostic evidence only.

## Audit Result

```text
CANONICAL_MAIN_VERIFIED
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

TASK_BASE
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

CANONICAL_PROMPT_AUTHORITY
= BLOCKED

CANONICAL_RESPONSE_SCHEMA_AUTHORITY
= BLOCKED

CANONICAL_PROVIDER_MODEL_AUTHORITY
= BLOCKED

SELECTED_MAX_TOKENS
= BLOCKED

CALIBRATION_STABLE
= BLOCKED

PRODUCTION_SOURCE_CHANGED
= NO

LEGACY_SCRIPT_CHANGED
= NO

LEGACY_IDENTITY_PRIOR_MUTATION_ADDED
= NO

REAL_PROVIDER_CANONICAL_RUN
= NOT_RUN

RECAP_RUN
= NO

P2_REAL_COMPOSITE
= HOLD
```
