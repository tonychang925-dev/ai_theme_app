# Identity LLM Provider Binding Audit v1

## Scope

```text
TASK_ID
= RD1-P2-I7B-CANONICAL-IDENTITY-LLM-PROVIDER-BINDING-MATERIALIZATION-P0

TASK_BASE
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

PROVIDER_REQUEST_COUNT
= 0
```

This audit inspected only variable presence and non-secret identity metadata. No secret value, authorization header, API key, or raw provider payload was printed or committed.

## Environment Findings

| Variable | Present | Non-Secret Metadata |
|---|---:|---|
| `DEEPSEEK_API_KEY` | YES | Secret value intentionally not read into output. |
| `DEEPSEEK_API_BASE` | NO | No legacy base value was present. |
| `DEEPSEEK_MODEL` | YES | `deepseek-v4-pro`. |
| `IDENTITY_LLM_API_URL` | NO | Not used by the compiled engineering contract. |
| `IDENTITY_LLM_API_KEY` | NO before materialization | Explicit process-launch mapping supplied it. |
| `IDENTITY_LLM_MODEL` | NO before materialization | Explicit process-launch mapping supplied it. |
| `IDENTITY_LLM_API_BASE` | NO before materialization | Explicit process-launch mapping supplied it. |

## Repository Binding Evidence

Repository code establishes the non-secret DeepSeek provider origin as:

```text
https://api.deepseek.com
```

That value composes exactly once with the engineering-contract suffix:

```text
https://api.deepseek.com/chat/completions
```

The environment also supplies an exact model binding:

```text
deepseek-v4-pro
```

No competing non-blank `IDENTITY_LLM_MODEL` binding was present. The repository's historical `deepseek-chat` defaults were not selected because the secure environment provides an explicit model.

## Selection

The available secure source binding is sufficient:

```text
SECURE_PROVIDER_KEY_AVAILABLE
= YES

SECURE_API_BASE_AVAILABLE
= YES

SECURE_MODEL_BINDING_AVAILABLE
= YES
```

The base is a non-secret provider origin, while the key and model come from the authorized process environment.

## Prohibitions Preserved

- No provider request was made.
- No production or test source was modified.
- No repository configuration or deployment artifact was modified.
- No secret was committed.
- No runtime fallback was added to `IdentityLLMReviewService`.
- No legacy provider path became the canonical architecture.
- No prompt, schema, timeout, or calibration protocol changed.
