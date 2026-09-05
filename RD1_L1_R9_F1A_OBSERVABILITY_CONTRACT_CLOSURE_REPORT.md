# RD1-L1-R9-F1A Market Failure Observability Contract Closure

```text
AGENT = GLM-D
CROSS_REVIEW = GLM-A
TASK = RD1-L1-R9-F1A MARKET FAILURE OBSERVABILITY CONTRACT CLOSURE
AUTHORIZATION = EXPLICIT_TONY_GO_R9_F1A_OBSERVABILITY_CONTRACT_CLOSURE
DATE = 2026-09-05
```

## Lineage and Scope

```text
REPOSITORY = tonychang925-dev/ai_theme_app
R9_F1_PARENT_SHA = 459cf5fa38d3372e259cf24d256bff5f37746308
R9_F1A_BASE_SHA = 459cf5fa38d3372e259cf24d256bff5f37746308
SOURCE_CLOSURE_HEAD_SHA = 0bb026889f5c51e72aff9561b5eb542db7adf088
REMOTE_BRANCH = glm-d/rd1-l1-r9-f1a-market-observability-closure
```

Before editing:

```text
branch head = 459cf5fa38d3372e259cf24d256bff5f37746308
parent lineage contains R9-F1 head = YES
merge-base = 459cf5fa38d3372e259cf24d256bff5f37746308
working tree clean = YES
event_resolve.py matched R9-F1 head = YES
```

The source closure commit parent is exactly the reviewed R9-F1 Market head. Prior history was not rewritten and no force push was used.

Changed source files:

```text
stock_processing_service/application/services/julia_domain_adapter/operations/event_resolve.py
tests/julia_domain_adapter/test_i2a_market_event_resolve.py
```

No other Market production file and no Core file changed.

## Concern A Closure

The underlying resolver exception's persisted `SourceFailure.message` now uses:

```text
raw exception class and text
→ existing redaction policy
→ deterministic whitespace normalization
→ explicit 2048-character bound
→ SourceFailure.message
```

The message retains the human-readable form:

```text
<ExceptionClass>: <sanitized bounded exception text>
```

The fixture proves:

```text
FakeDatabaseError retained
password marker redacted
R9_F1_FAKE_SECRET_DO_NOT_MATCH absent
len(SourceFailure.message) <= 2048
```

No DTO family or `contracts.py` change was required.

## Concern B Closure

`precollapse_provider_status` is no longer populated from Market `classify_exception()` or any collapsed status.

The only lookup is an explicit, bounded inspection of genuine underlying exception attributes:

```text
provider_status
upstream_status
status
```

If none exists, the retained value is `None`.

Fixture proof:

```text
outer result.status = unavailable
precollapse_provider_status = None
```

A narrow genuine-status fixture also proves:

```text
provider_status = connection_lost
precollapse_provider_status = connection_lost
```

No exception `__dict__`, environment, traceback object, database object, or broad reflection is serialized.

## Diff Summary

```text
stock_processing_service/application/services/julia_domain_adapter/operations/event_resolve.py
  + persisted SourceFailure.message bounded through existing helper
  + removed classify_exception-derived pre-collapse status
  + explicit genuine exception status lookup only

tests/julia_domain_adapter/test_i2a_market_event_resolve.py
  + persisted-message redaction/bounding assertions
  + no-synthesized-status assertion
  + genuine provider_status fixture
  + one-resolver-call fail-closed assertion
```

```text
2 files changed
33 insertions
5 deletions
```

## Verification

Exact commands and results:

```text
/opt/miniconda3/bin/pytest -q \
  tests/julia_domain_adapter/test_i2a_market_event_resolve.py

RESULT:
10 passed in 0.21s
```

```text
PYTHONPATH=/Users/admin/glm-workspace/ai_theme_app_i2a \
/opt/miniconda3/bin/pytest -q \
  tests/julia_domain_adapter/test_i2a_market_event_resolve.py \
  tests/julia_domain_adapter/test_at_r3_degradation_provenance.py \
  tests/market_research/test_m1b_market_event_composition.py

RESULT:
36 passed in 0.28s
```

```text
PYTHONPATH=/Users/admin/glm-workspace/ai_theme_app_i2a \
/opt/miniconda3/bin/pytest -q \
  tests/julia_domain_adapter/test_at_r5_contract_fault_matrix.py \
  -k 'not alerts_normal_success_covered_by_facade_fixture and not no_write_side_effects'

RESULT:
20 passed, 2 deselected, 1 warning in 0.60s
```

Core compatibility, without changing Core:

```text
cd /Users/admin/glm-workspace/Julia_core
/opt/miniconda3/bin/pytest -q \
  tests/runtime/test_r9_f1_capability_failure_event_retention.py

RESULT:
2 passed in 0.16s
```

Static checks:

```text
/opt/miniconda3/bin/python -m compileall -q \
  stock_processing_service/application/services/julia_domain_adapter/operations/event_resolve.py \
  tests/julia_domain_adapter/test_i2a_market_event_resolve.py

RESULT:
PASS

git diff --check
RESULT:
PASS
```

## Pre-existing Failures

The full AT-R5 file retains two unrelated package-import failures:

```text
test_tc_at_r5_002_alerts_normal_success_covered_by_facade_fixture
test_tc_at_r5_017_no_write_side_effects
```

Both import `tests.julia_domain_adapter.test_at_r2_domain_adapter_facade`, but `tests.julia_domain_adapter` does not resolve in this workspace. They were explicitly deselected and are not counted as R9-F1A failures.

The suite also reports the pre-existing Starlette `python_multipart` deprecation warning.

## Contract Gates

```text
SOURCEFAILURE_MESSAGE_BOUNDED = YES
PRECOLLAPSE_EXCEPTION_MESSAGE_BOUNDED = YES
NO_SYNTHESIZED_PRECOLLAPSE_PROVIDER_STATUS = YES
GENUINE_PROVIDER_STATUS_ONLY = YES
SECRET_REDACTION_PASS = YES
BOUNDS_PASS = YES
TRACEBACK_RETENTION = NO

EXTERNAL_STATUS_UNCHANGED = YES
ERROR_CODE_UNCHANGED = YES
RETRYABLE_UNCHANGED = YES
RESOLVER_MATCHING_UNCHANGED = YES
CANDIDATE_SELECTION_UNCHANGED = YES
EVENT_ID_OWNERSHIP_UNCHANGED = YES
RETRY_FALLBACK_UNCHANGED = YES
FAIL_CLOSED_SEMANTICS_UNCHANGED = YES

TRUTH_AUTHORITY_UNCHANGED = YES
CORE_PRODUCTION_CHANGE = NO
RAW_UNAPPROVED_PROVIDER_FIELDS_EXCLUDED = YES
ARCHITECTURE_DEVIATIONS = NONE
```

Fixture fail-closed proof:

```text
resolver call count = 1
market.event.read executions = 0
research.event.enrich executions = 0
D1 executions = 0
retry = 0
fallback = 0
```

## Execution Boundaries

```text
USER_TURNS = 0
MARKET_EVENT_RESOLVE_LIVE_EXECUTIONS = 0
MARKET_EVENT_READ_LIVE_EXECUTIONS = 0
D1_EXECUTIONS = 0
D1_RETRY = 0
D1_FALLBACK = 0
DB_WRITES = 0
```

No Brain, Client, Assistant, D1, Voice, HTTP substitute, live database, or controlled R10 execution was used.

## Readiness

```text
R10_AUTHORIZED = NO
R10_READY = YES
VERDICT = PASS
```
