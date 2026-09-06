---
name: NO_CRITICAL_FALLBACK_REVIEW
description: Apply before editing or reviewing critical Julia production code when fallback, mock, fixture, provider, authority, evidence, or fail-closed behavior can affect correctness.
---

# No Critical Fallback Review

Apply this review whenever a change touches identity, persona, conversation, memory, context, Market, database, provider, D1, WebSearch, WebFetch, C1, C2, evidence, strategy assets, runtime composition, launchers, authentication, or provenance.

Run the repository gate when possible:

```sh
python3 tools/no_critical_fallback_gate.py --repo ai_theme_app --baseline ncf-baseline.json
```

Perform control-flow review even when the scanner is clean. A `P0/P1` finding means:

```text
DECISION = REJECT
COMMIT_ALLOWED = NO
```

Return exactly these fields:

```text
NO_CRITICAL_FALLBACK_REVIEW
CRITICAL_PATH: YES / NO
FALLBACK_INTRODUCED: YES / NO
MOCK_OR_FIXTURE_PRODUCTION_REACHABLE: YES / NO / NOT_PROVEN
LEGACY_AUTHORITY_FALLBACK: YES / NO
SYNTHETIC_SUCCESS: YES / NO
OUTER_SUCCESS_INNER_FAILURE: YES / NO
AMBIENT_RESOLUTION: YES / NO
TEST_MODE_PRODUCTION_REACHABLE: YES / NO
FAIL_CLOSED_PRESERVED: YES / NO
RISK: P0 / P1 / P2 / P3 / NONE
DECISION: APPROVE / REQUEST_CHANGES / REJECT
```

Do not approve outer success when an inner critical result is unavailable or failed. Do not treat a provider exception, missing authority, missing canonical asset, or missing provenance as an acceptable default. Report exact violations; do not silently edit around the gate.
