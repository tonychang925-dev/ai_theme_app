# P2/I7B Correction Task Decomposition v1

## Governance

Every follow-up must:

- verify exact canonical `origin/main` at issuance;
- declare exact allowed and forbidden paths;
- add focused tests;
- preserve typed failures;
- prohibit hidden fallback;
- commit and push its authorized branch;
- stop at the first new concrete defect;
- avoid merge without Owner authorization.

## Task A — Canonical identity LLM strict transport

### Objective

Make `IdentityLLMReviewService` the sole production transport and enforce:

```text
provider / transport failure
!= review_pending
```

### Base

Verified canonical `origin/main` containing this audit.

### Expected allowed paths

```text
stock_processing_service/domain/services/identity_llm_review_service.py
stock_processing_service/application/jobs/build_identity_job.py
stock_processing_service/domain/services/** only for a narrow typed result contract
stock_processing_service/tests/unit/**
docs/rd1/p2_i7b_rebound/**
```

The implementation issue must narrow this list.

### Forbidden paths

```text
stock_service/scripts/build_mainline_identity_registry.py
scripts/build_post_market_recap.py
legacy branch as base
DB schema/migrations
date fallback
```

### Calibration before source edit

1. Owner freezes canonical prompt and response schema.
2. Reconstruct canonical inputs for representative required-review subjects.
3. Calibrate finite authorized token tiers.
4. Require stable valid JSON and non-`length` completion.
5. Record prompt hash, model, semantics, tiers, and stability without secrets.

Historical `4000` remains only a hypothesis.

### Implementation requirements

- required mode fails on missing provider configuration;
- exactly one provider request;
- owner-approved model and temperature;
- calibrated finite completion budget;
- JSON-object response format;
- envelope and HTTP validation;
- inspect `finish_reason` before parsing;
- typed failures for truncation, missing content, invalid JSON, and contract mismatch;
- no deterministic fallback, retry, JSON repair, alternate provider, or rule-only fallback;
- no raw provider content or credentials in errors.

### Acceptance tests

- request semantics and budget;
- exact canonical prompt identity;
- valid JSON succeeds;
- `length` fails typed;
- missing content fails typed;
- invalid JSON fails typed;
- missing keys fails typed;
- timeout/network/HTTP failures fail typed;
- one request only;
- no fallback in required mode;
- `BuildIdentityJob` supplies all canonical inputs.

### STOP

- prompt ownership ambiguous;
- no authorized tier is stable;
- correction requires legacy script changes;
- credentials unavailable;
- hidden fallback is needed to pass.

## Task B — Required recap-path Gateway escape closure

### Objective

Close the audited required-path escapes while preserving business semantics.

### Base

Verified canonical `origin/main` containing Task A.

### Expected allowed paths

```text
stock_processing_service/workers/run_collection_runner.py
stock_processing_service/application/jobs/build_post_market_recap_job.py
stock_processing_service/application/services/post_market_readiness_service.py
stock_processing_service/application/services/post_market_job_status_service.py
stock_processing_service/application/services/limit_up_theme_matrix_builder.py
stock_processing_service/ports/read_ports.py
stock_processing_service/ports/write_ports.py
stock_processing_service/infrastructure/gateway_adapters/**
database_service/gateway.py
database_service/managers/postgres_manager.py
stock_processing_service/tests/**
database_service/tests/** only where existing suite location requires
```

### Forbidden paths

```text
stock_service/scripts/**
scripts/build_post_market_recap.py
market_public/**
frontend/**
migrations/**
```

### Required scope

1. Replace `_ReplayDatabaseStockFacade` in the production worker.
2. Close E1-E7.
3. Add missing canonical chains for limit-up matrix inputs, abnormal signals, daily-basic turnover, job status, subject names, and readiness.
4. Delete the dead strong-review SQL branch.
5. Remove silent required-read exception swallowing.
6. Preserve existing canonical write Ports.

### Acceptance tests

- no private `_pool/_db/_client/.pool` extraction in required files;
- no direct raw SQL for audited operations in the recap Job;
- no `asyncpg` import in the recap Job;
- existing abnormal/strong-review Port paths exercised;
- new Gateway methods contract-tested;
- readiness and status failures remain typed;
- recap Job integration tests pass;
- moved-query equivalence proven.

### STOP

- SQL cannot move without schema change;
- output changes outside a typed boundary correction;
- another undocumented escape is required;
- scope expands into unrelated modules.

## Task C — Production-entrypoint architecture guard

### Objective

Prevent P2 from re-entering the rejected legacy path.

### Base

Verified canonical `origin/main` containing Tasks A and B.

### Expected allowed paths

```text
stock_processing_service/tests/** architecture guard
docs/rd1/p2_i7b_rebound/** exception register
existing test configuration only if required for discovery
```

No production behavior change is expected.

### Hard prohibitions

P2 production path definitions must not reference:

```text
stock_service/scripts/
scripts/build_post_market_recap.py
```

For corrected required files, ban:

- `import asyncpg`;
- `from asyncpg`;
- `getattr(..., "_client")`;
- `getattr(..., "_db")`;
- `getattr(..., "_pool")`;
- `.pool.acquire()`;
- raw SQL execution.

### Required files

- `run_collection_runner.py`
- `build_post_market_recap_job.py`
- `build_identity_job.py`
- `build_theme_cycle_evidence_daily_job.py`
- `build_cycle_judgement_job.py`
- `build_mainline_state_job.py`

### Exceptions

Must be named, justified, owned, and explicit. No broad whitelist.

### Acceptance tests

Guard rejects legacy path strings, injected `asyncpg`, private extraction, and direct SQL markers; it allows explicit Port calls and passes on the corrected required path.

### STOP

Guard requires broad ignore, required path still needs an escape, or production behavior changes.

## Task D — Canonical Market readiness and composite resume

### Objective

Resume real generation and P2/I7B only after A-C pass.

### Base

Verified canonical `origin/main` containing Tasks A-C.

### Source changes

Forbidden unless a new task is issued.

### Required execution path

```text
canonical collection/API entrypoint
→ recap prerequisites
→ identity strict LLM
→ cycle/evidence/state
→ BuildPostMarketRecapJob
→ market.state.read exact date
→ market.analysis.read exact date
→ Julia composite flow
```

### Forbidden

```text
stock_service/scripts/**
scripts/build_post_market_recap.py
manual SQL writes
date fallback
synthetic data
provider fallback
unrelated Research preflight
replacement E2E runs
```

### Market acceptance

- target date remains exact;
- restored upstream counts stable;
- downstream real counts recorded;
- both public capabilities return `SUCCESS / READY`;
- real provenance;
- no date fallback.

### Composite acceptance

- Julia independently selects Market and Research;
- both evidence domains retain distinct provenance;
- both enter C03;
- post-composite cognition occurs;
- final judgment is fresh;
- typed failures remain visible;
- fallback/synthetic success remains zero.

### Expected evidence

- selected entrypoint and SHA;
- per-Job records;
- LLM typed-error counts;
- downstream counts;
- capability envelopes;
- ToolResult states;
- C03 and cognition evidence;
- 4/4 clean composite classification.

### STOP

Any required Job fails, guard fails, Market remains `EMPTY`, first composite fails, or repeatability is not 4/4 clean.

## Order

```text
A → B → C → D
```

C may be prepared against the audited end state in parallel, but must not merge before B closes the required escapes.

No later task may start while an earlier task is blocked. Task D remains unavailable until Tasks A-C pass their acceptance gates.
