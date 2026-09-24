# Identity LLM Calibration Reentry Proof v1

## Fresh-Process Result

A new process was launched with the explicit canonical binding map. It observed:

```text
IDENTITY_LLM_API_BASE_PRESENT
= YES

IDENTITY_LLM_API_KEY_PRESENT
= YES

IDENTITY_LLM_MODEL_PRESENT
= YES

IDENTITY_LLM_MODEL_IDENTIFIER
= deepseek-v4-pro

IDENTITY_LLM_API_BASE_HOST
= api.deepseek.com

COMPOSED_ENDPOINT_PATH
= /chat/completions

ENDPOINT_CHAT_COMPLETIONS_APPENDED_ONCE
= YES
```

## Execution Boundary

```text
PROVIDER_REQUEST_COUNT
= 0

CALIBRATION_RUN
= NO

SECRET_VALUE_LOGGED
= NO
```

The proof process checked only presence, model identity, provider host, and endpoint path shape. It did not send an HTTP request.

## Reentry Condition

Issue #427 calibration may reenter only when its launcher applies the exact map in `IDENTITY_LLM_CANONICAL_BINDING_MAP_v1.md` before process startup. The calibration process must then recheck presence itself and fail closed if any canonical value disappears.

