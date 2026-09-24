# Canonical Identity LLM Calibration Protocol v1 — Owner Selection Required

## Status

```text
CALIBRATION_PROTOCOL_STATUS
= BLOCKED_OWNER_IDENTITY_LLM_CONTRACT_DECISION_REQUIRED
```

The structural protocol below is safe to publish, but it cannot execute until the Owner freezes the exact prompt, schema, provider/model rule, timeout, and terminal semantics. This document does not select a token budget.

## Preconditions

All of the following must be recorded in an accepted contract freeze:

1. exact prompt artifact and version;
2. exact prompt input serialization and `prompt_sha256`;
3. exact response schema version and validation rules;
4. provider family and configuration namespace;
5. exact model-selection rule;
6. temperature `0.1`;
7. JSON-object mode decision;
8. exact timeout;
9. one-request/no-retry policy;
10. terminal representation for every typed error;
11. representative subject selection rule.

## Representative Inputs

The Owner must choose one exact rule. Supported options are:

### R1 — Historical regression subjects

Use the frozen Layer A regression subjects, including the authoritative old-chain samples and one clear non-mainline negative sample. This maximizes semantic coverage but requires the Owner to list exact trade dates and subject keys after read-only verification.

### R2 — Current target-date required-review cohort

Use the first exact required-review subject plus deterministic boundary and negative samples from the current canonical `BuildIdentityJob` eligibility rule. This tests current production input shape but requires a selection order and boundary definitions.

### R3 — Owner-fixed minimal matrix

Use one rule-pass subject, one borderline subject, one one-day-tour hard-gate subject, and one insufficient-evidence subject. This controls token and semantic coverage but requires exact identities and input artifacts.

No synthetic business values may be used. Missing real evidence must be represented as unavailable and cannot be defaulted into a successful calibration input.

## Candidate Token Tiers

The Owner must select an exact ordered list from evidence-supported candidates. Candidate values include:

```text
512
1000
2000
4000
8000
16000
```

Historical `4000` is diagnostic evidence only and is not preselected. The current canonical `512` and historical `1000` are also evidence, not authority.

## Per-Tier Procedure

For each selected tier, in exact ascending order:

1. Construct each representative prompt through the frozen owner function.
2. Record prompt version and SHA-256.
3. Send exactly one provider request per representative input.
4. Freeze model, temperature, JSON-object mode, and all other request parameters; only `max_tokens` changes by tier.
5. Record HTTP status, finish reason, usage, content presence, content byte length and SHA-256, JSON validity, schema validity, and typed error class.
6. A tier passes only when every representative input returns:
   - HTTP success according to the frozen provider contract;
   - non-truncated completion;
   - non-empty content;
   - valid JSON object;
   - valid selected response schema.
7. Stop advancing after the first passing tier.
8. Run exactly one confirmation request per representative input at that tier.
9. The tier is stable only if all confirmation requests also satisfy every success criterion.
10. If confirmation fails because of truncation, advance to the next selected tier only after Owner-approved protocol accounting.
11. Never exceed the highest Owner-selected tier.

## Success Definition

```text
SELECTED_MAX_TOKENS
= smallest selected tier with all representative inputs passing initial
  and confirmation attempts

INITIAL_PROVIDER_REQUEST_COUNT
= number_of_representative_inputs * number_of_executed_tiers

CONFIRMATION_REQUEST_COUNT
= number_of_representative_inputs

TOTAL_PROVIDER_REQUEST_COUNT
= initial + confirmation
```

No larger tier may be selected for comfort. A tier with any typed provider/transport/schema failure is not a valid completion-budget pass.

## Forbidden During Calibration

- Prompt simplification.
- Model substitution.
- Thinking/reasoning-mode change.
- Temperature change.
- Provider substitution.
- Retry of the same input/tier.
- JSON repair.
- Required-key defaulting.
- Deterministic rule-only fallback.
- Synthetic provider success.
- Secret logging.

## Evidence Record

For every request record:

```text
representative_input_id
prompt_version
prompt_sha256
schema_version
model
temperature
max_tokens
json_object_mode
http_status
finish_reason
prompt_tokens
completion_tokens
total_tokens
content_present
content_utf8_bytes
content_sha256
json_valid
contract_valid
typed_error_class
provider_request_count_for_attempt
```

Raw content may be retained temporarily only in a non-repository secured location and must be deleted after hash/error classification unless a separate Owner decision authorizes durable redacted retention.

## Current Blocked Outputs

```text
REPRESENTATIVE_INPUT_RULE
= OWNER_CHOICE_REQUIRED

TOKEN_TIERS
= OWNER_CHOICE_REQUIRED

CONFIRMATION_RERUN_COUNT
= OWNER_CHOICE_REQUIRED

SELECTED_MAX_TOKENS
= BLOCKED_UNTIL_CALIBRATION
```
