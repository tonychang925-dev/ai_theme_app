# Identity LLM Prompt v2 Calibration Manifest

```text
TASK_ID
= RD1-P2-I7B-IDENTITY-LLM-PROMPT-V2-REAL-PROVIDER-CALIBRATION-RESTART-P0

REPO
= tonychang925-dev/ai_theme_app

CANONICAL_MAIN
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

TASK_BASE
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

CALIBRATION_BRANCH
= rd1-v1/p2-i7b-identity-llm-prompt-v2-calibration

AUTHORITY_REFS_USED_AS_ANCESTRY
= NO

OWNER_SEMANTIC_AUTHORITY
= Issue #425 comment 5813922812

ENGINEERING_CONTRACT_AUTHORITY
= Issue #426 accepted engineering contract
= 2815b81598e94f37ceef12420acc2b1d2e8f368d

PROVIDER_BINDING_AUTHORITY
= Issue #428 accepted binding
= 66baaafbd193f46120ff52f0eaede9a6fb1bf62e

PROMPT_V2_MECHANICS_AUTHORITY
= Issue #429 accepted correction
= 47a08249aad6720d3e97d853b4f25e29a20ee37a

PROMPT_VERSION
= identity-llm-prompt.v2

RESPONSE_SCHEMA_VERSION
= identity-llm-response.v1

MODEL
= deepseek-v4-pro

TEMPERATURE
= 0.1

RESPONSE_FORMAT
= {"type":"json_object"}

TIMEOUT_SECONDS
= 120

AUTHORIZED_TOKEN_TIERS
= [1000, 2000, 4000, 8000, 16000]

RETRY
= 0

FALLBACK
= NO

MODEL_SWAP
= NO

PROMPT_MUTATION
= NO

JSON_REPAIR
= NO

PRODUCTION_SOURCE_EDIT
= FORBIDDEN

TEST_SOURCE_EDIT
= FORBIDDEN

CONFIG_EDIT
= FORBIDDEN

DB_MUTATION
= FORBIDDEN

SECRET_LOGGED
= NO

RAW_PROMPT_LOGGED
= NO

RAW_RESPONSE_LOGGED
= NO

P2_REAL_COMPOSITE
= HOLD
```

## Binding Recheck

The calibration ran in a fresh process using the Issue #428 process-launch
binding. Only presence and the model identifier were observed:

```text
IDENTITY_LLM_API_BASE_PRESENT = YES
IDENTITY_LLM_API_KEY_PRESENT  = YES
IDENTITY_LLM_MODEL_PRESENT    = YES
MODEL_IDENTIFIER              = deepseek-v4-pro
```

## Cohort Resolution

The cohort was re-resolved from real canonical evidence through the canonical
database gateway. No synthetic subject was added.

```text
C1
= SELECTED
= trade_date 2026-04-07
= subject_key 9062832
= prompt_utf8_bytes 4871
= prompt_sha256 3ed6334fe3ddc9849c1f5e7db940a575202d4dc982849bab117ff4a55c67ec3c

C1_EVIDENCE_AVAILABLE_COUNT = 27
C1_EVIDENCE_MISSING_COUNT = 0
C1_EVIDENCE_UNAVAILABLE_COUNT = 0
C1_EVIDENCE_NOT_APPLICABLE_COUNT = 0

C2 = UNAVAILABLE_NOT_REQUIRED_REVIEW
C3 = UNAVAILABLE_NO_REAL_QUALIFYING_SUBJECT
C4 = UNAVAILABLE_NO_REAL_QUALIFYING_SUBJECT
C5 = UNAVAILABLE_NO_REAL_MISSING_EVIDENCE_SUBJECT

COHORT_SELECTED_COUNT = 1
```

C1 prompt reconstruction matched the frozen prompt-v2 SHA-256 exactly before
any provider request.

## Authority Boundary

Issues #425, #426, #427, #428, and #429 supplied evidence and authority only.
None is an ancestor of this calibration branch. The branch starts from exact
canonical main `bc34e973686d7f78b0e9c3efd67b433f0901f21a`.
