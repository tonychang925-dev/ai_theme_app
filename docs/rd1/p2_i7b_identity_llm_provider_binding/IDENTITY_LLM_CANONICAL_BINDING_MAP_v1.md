# Identity LLM Canonical Binding Map v1

## Materialization Class

```text
MECHANISM
= PROCESS_LAUNCH_ENVIRONMENT_BINDING
```

This is an explicit calibration-process materialization. It is not production-code fallback and does not create a second provider path.

## Exact Mapping

```text
IDENTITY_LLM_API_BASE
← https://api.deepseek.com

IDENTITY_LLM_API_KEY
← authorized secure DEEPSEEK_API_KEY process binding

IDENTITY_LLM_MODEL
← authorized secure DEEPSEEK_MODEL process binding
```

The exact selected non-secret model is:

```text
deepseek-v4-pro
```

The API key value is referenced only inside the launched process environment and is never copied into repository docs, logs, source, tests, or configuration.

## Endpoint Composition

```text
IDENTITY_LLM_API_BASE
= https://api.deepseek.com

COMPOSED_ENDPOINT
= https://api.deepseek.com/chat/completions

/chat/completions_OCCURRENCES
= 1
```

The selected base has no path suffix. Therefore the engineering-contract suffix is appended exactly once and does not produce:

```text
/chat/completions/chat/completions
```

or an incompatible pre-suffixed base.

## Launch Shape

A calibration launcher must establish the canonical environment before executing the calibration process:

```text
IDENTITY_LLM_API_BASE=https://api.deepseek.com
IDENTITY_LLM_API_KEY=<secure-reference-to-authorized-DEEPSEEK_API_KEY>
IDENTITY_LLM_MODEL=<secure-reference-to-authorized-DEEPSEEK_MODEL>
```

The angle-bracket expressions denote secure process-environment references, not literal values to commit.

## Boundary

This map authorizes only canonical namespace materialization for calibration reentry. It does not:

- alter `IdentityLLMReviewService`;
- add `DEEPSEEK_API_KEY` as a production fallback;
- add `IDENTITY_LLM_API_KEY` fallback logic;
- change provider ownership;
- change model after calibration begins;
- authorize a provider call in Issue #428.
