# Canonical Identity LLM Contract Freeze v1 — Owner Decision Packet

## Status

```text
CONTRACT_FREEZE_STATUS
= BLOCKED_OWNER_IDENTITY_LLM_CONTRACT_DECISION_REQUIRED
```

This is not an accepted contract freeze. It is the complete Owner decision packet requested by Issue #425. No option below has been selected as authority, no default is promoted as frozen, and no calibration or implementation is authorized.

## Authority Basis

- Repository main under audit: `bc34e973686d7f78b0e9c3efd67b433f0901f21a`.
- Issue #424 Stage-0 audit head `7a4fe3c7a8f76c13cced1d45358e333847f3ddc3` is evidence only and is not ancestry.
- `docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md` makes the historical Layer A algorithm semantics authoritative while assigning the canonical implementation owners as `IdentityRuleEngine`, `OneDayTourDetector`, `IdentityLLMReviewService`, `IdentityDecider`, and `BuildIdentityJob`.
- The migration and third-stage architecture documents require controlled inputs, structured output, replayability, and non-confirming `review_pending` funnel semantics.
- No available ADR freezes the exact identity-LLM prompt text, response schema, provider/model authority, token budget, or per-class failure terminal representation.

## Non-Negotiable Invariants

Regardless of the Owner selections, the accepted contract must satisfy all of the following:

1. `IdentityLLMReviewService` is the controlled review owner invoked by `BuildIdentityJob`; the legacy script is not rehabilitated.
2. The prompt contains the Layer A evidence needed to preserve logic, market, one-day-tour, continuity, and K-line semantics.
3. Prompt construction is deterministic and versioned; it supports exact provenance and replay.
4. The response is strict JSON with a versioned schema and explicit required-key/type validation.
5. Provider/API/transport/contract failures are individually typed and remain observable.
6. No failure becomes `confirmed`, successful cognition, silent deterministic substitution, or synthetic success.
7. Required-real-LLM mode never silently selects the current deterministic reviewer.
8. The provider exchange is one request per review attempt with no retry or alternate provider.
9. Token budget is selected only by calibration against the exact frozen prompt, model, temperature, and response schema.
10. No identity-to-cycle mutation is introduced.

## Normative Decision Table

| Contract Item | Frozen Decision | Authority/Evidence | Implementation Consequence |
|---|---|---|---|
| Prompt owner | `BLOCKED`: choose Option P1 existing `build_llm_prompt()`, P2 corrected canonical prompt artifact, or P3 another exact authorized artifact. | Issue #424 proves the executable inline prompt, unused builder, and historical prompt are three different authorities. | No production prompt may be edited or calibrated until one artifact is selected. |
| Input fields | `BLOCKED`: choose the input set belonging to P1, P2, or P3; all candidates must cover Layer A semantics. | `BuildIdentityJob` currently supplies only five rule-output values, while the richer builder accepts trade date, subject identity, full rule data, and K-line evidence. | Caller plumbing scope cannot be finalized before prompt selection. |
| Prompt version | `BLOCKED`: select `identity-llm-prompt.v1` for the chosen artifact or another exact Owner version. | No prompt version is currently recorded. | Version must be emitted in review provenance. |
| Prompt hash | `FROZEN_CONDITIONALLY`: SHA-256 over exact UTF-8 prompt bytes after canonical serialization; no newline normalization or locale-dependent formatting. | Deterministic replay requires byte-exact hashing. | Implementation records `prompt_sha256`; a changed prompt requires a new version. |
| Response schema | `BLOCKED`: choose historical six-key dimensional schema or canonical four-key aggregate schema as the base for strict v1. | The two schemas and confidence scales conflict; architecture authority does not select one. | Parser, decider mapping, tests, and calibration acceptance cannot be finalized. |
| Confidence scale | `BLOCKED`: choose decimal `0.0–1.0` or integer `0–100`, together with the selected schema. | Current canonical candidates use `0.0–1.0`; historical Layer A review uses `0–100`. | Conversion boundaries and downstream interpretation remain unauthorized. |
| Provider config | `BLOCKED`: choose `IDENTITY_LLM_*`, `DEEPSEEK_*`, or a new explicitly owned configuration namespace. | Current canonical and historical paths use different namespaces; no ADR resolves authority. | Configuration loader and required-mode checks cannot be implemented. |
| Model rule | `BLOCKED`: choose configuration-bound model with an allowed-value gate, or freeze one exact model identifier. | Current defaults to `deepseek-chat`; historical production diagnostic used `deepseek-v4-pro`. | Calibration and production request construction remain blocked. |
| Temperature | `FROZEN`: `0.1`. | Both existing semantic candidates use `0.1`; no authority proposes another value. | The implementation must send exactly `0.1`. |
| JSON-object mode | `BLOCKED`: choose enabled strict mode or explain an Owner-authorized provider exception. | Historical request enables it; current canonical request omits it. | Strict JSON transport and provider compatibility tests depend on this decision. |
| Timeout | `BLOCKED`: choose one exact bounded request timeout. | Current canonical uses 30 seconds; historical script accepts a configurable timeout; no canonical contract freezes one. | Timeout classification and test fixtures cannot be finalized. |
| Retry | `FROZEN`: maximum one provider HTTP request per review attempt; transport retry is forbidden. | Issue #425 governance forbids retry masking. | All failures terminate that review attempt with their typed class. |
| Missing config | `FROZEN`: required-real-LLM mode fails `CONFIGURATION_MISSING`; deterministic fallback is forbidden. | Required-real mode cannot substitute rule cognition. | Caller receives the selected terminal representation with this exact type. |
| Transport error | `FROZEN` type: `TRANSPORT_FAILURE`; terminal mapping remains `BLOCKED`. | Timeout/network/transport failures must not collapse into a generic exception. | Choose `review_pending + metadata` or hard typed caller failure. |
| HTTP error | `FROZEN` type: `HTTP_FAILURE`; terminal mapping remains `BLOCKED`. | HTTP status is a distinct provider execution failure. | Record sanitized status/class; choose terminal mapping. |
| Truncation | `FROZEN` type: `OUTPUT_TRUNCATED`; terminal mapping remains `BLOCKED`. | `finish_reason=length` must be detected before JSON parsing. | No repair or second request; choose terminal mapping. |
| Invalid JSON | `FROZEN` type: `INVALID_JSON`; terminal mapping remains `BLOCKED`. | Malformed provider content is a distinct transport-contract failure. | No repair; choose terminal mapping. |
| Contract mismatch | `FROZEN` type: `CONTRACT_INVALID`; terminal mapping remains `BLOCKED`. | Missing keys and type/value violations require explicit classification. | Reject the response as unsuccessful cognition; choose terminal mapping. |
| `review_pending` semantics | `FROZEN`: it is a review funnel state, never direct confirmation; per-error use is `BLOCKED`. | Architecture authority defines the funnel but not every provider-failure mapping. | The Owner must select pending versus hard failure for each typed class. |
| Calibration method | `BLOCKED`: choose representative subjects, final tier list, and confirmation count after prompt/schema/model are frozen. | Calibration against an unfrozen contract would create false authority. | No provider call or token selection is authorized. |

## Unresolved Owner Decisions

The Owner must return one exact choice for every item below:

1. Prompt artifact: P1, P2, or P3.
2. Exact prompt input set and serialization.
3. Prompt version label.
4. Response schema family and exact keys/types/list limits.
5. Confidence scale and numeric bounds.
6. Provider configuration namespace.
7. Exact model-selection rule.
8. JSON-object response mode.
9. Exact request timeout.
10. Terminal mapping for every typed class in the error matrix.
11. Representative calibration subjects/sample-selection rule.
12. Final token-tier sequence and confirmation rerun count.

## Stop Result

```text
PROMPT_OWNER_FROZEN
= NO

PROMPT_INPUT_SET_FROZEN
= NO

RESPONSE_SCHEMA_FROZEN
= NO

PROVIDER_MODEL_AUTHORITY_FROZEN
= NO

ERROR_TAXONOMY_FROZEN
= PARTIAL

TERMINAL_REPRESENTATION_FROZEN
= NO

CALIBRATION_PROTOCOL_FROZEN
= NO

UNRESOLVED_OWNER_DECISIONS
= PROMPT_ARTIFACT, PROMPT_INPUT_SET, PROMPT_VERSION, RESPONSE_SCHEMA,
  CONFIDENCE_SCALE, PROVIDER_CONFIG, MODEL_RULE, JSON_OBJECT_MODE, TIMEOUT,
  TERMINAL_MAPPING_BY_ERROR_CLASS, CALIBRATION_SUBJECTS, TOKEN_TIERS_AND_RERUNS
```

