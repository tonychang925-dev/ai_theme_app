# Identity LLM Calibration Results v1

## Result

```text
CALIBRATION_STABLE
= BLOCKED

DISPOSITION
= BLOCKED_CALIBRATION_CONFIGURATION_MISSING

SELECTED_MAX_TOKENS
= BLOCKED

EXECUTED_TOKEN_TIERS
= []

INITIAL_PROVIDER_REQUEST_COUNT
= 0

CONFIRMATION_PROVIDER_REQUEST_COUNT
= 0

TOTAL_PROVIDER_REQUEST_COUNT
= 0
```

## Blocking Evidence

All three required canonical configuration bindings were absent from the calibration environment:

```text
IDENTITY_LLM_API_BASE
IDENTITY_LLM_API_KEY
IDENTITY_LLM_MODEL
```

The missing canonical API base is decisive. No endpoint could be constructed without inventing or silently substituting a legacy provider binding, both of which are forbidden.

## Governance Result

```text
RETRY_USED
= NO

FALLBACK_USED
= NO

MODEL_SWAP_USED
= NO

PROMPT_MUTATION_USED
= NO

JSON_REPAIR_USED
= NO

PRODUCTION_SOURCE_CHANGED
= NO

DB_MUTATION
= NO

P2_REAL_COMPOSITE
= HOLD
```

## Reentry Requirement

Before this calibration can rerun, the deployment must provide non-blank canonical values for:

```text
IDENTITY_LLM_API_BASE
IDENTITY_LLM_API_KEY
IDENTITY_LLM_MODEL
```

The exact model identifier may then be recorded, but secrets must remain unlogged.

