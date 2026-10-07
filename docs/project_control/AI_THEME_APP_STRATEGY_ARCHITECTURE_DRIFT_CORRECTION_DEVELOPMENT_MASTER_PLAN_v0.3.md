# AI Theme App — Strategy / Architecture Drift Correction Development Master Plan v0.3

> **Document type:** Development master plan / implementation control document  
> **Status:** DRAFT FOR OWNER APPROVAL — IMPLEMENTATION NOT AUTHORIZED  
> **Owner:** Tony  
> **Implementation owner:** Claude  
> **Date:** 2026-10-07  
> **Program type:** CORRECTION / MIGRATION COMPLETION — NOT GREENFIELD REDESIGN  
> **Engineering truth:** `origin/main@ddc9442e88c5bf6f5248bfb141e74472c48eb25a`  
> **Local main at planning time:** `ddc9442e88c5bf6f5248bfb141e74472c48eb25a`  
> **Local working-tree HEAD at planning time:** `/Users/admin/Desktop/ai_theme_app` = `e1f1b9ad1e44af0edaba9543bc4868ae42f2382f` — verified locally but **not** engineering truth; implementation must start from `origin/main` exact SHA.  
> **Strategy baseline:** `AI_THEME_APP_CANONICAL_INVESTMENT_STRATEGY_DEVELOPMENT_MODEL_v0.6.4_APPROVED_WORKING_BASELINE.md`  
> **Strategy baseline SHA256:** `f75dd6624d43870c299607239601c80befa83ad7f963bef69fd24e5dd3591d2b`  
> **Strategy status:** OWNER APPROVED WORKING BASELINE / NOT FROZEN  
> **Maximum parallel implementation tasks:** 3  
> **One task → one branch → one PR → merged-main verification → branch cleanup**

---

## 0. Purpose

This plan converts the completed read-only audit into a controlled implementation program.

The program does **not** replace the current architecture. It corrects two historical classes of drift:

```text
OLD CHAIN
= useful strategy semantics in many places
+ poor engineering boundaries
  (direct SQL / direct DB / scripts / case-tuned rules)

NEW CHAIN
= materially better engineering boundaries
  (Ports / Gateway / Domain / Jobs / Snapshot / Replay)
+ meaningful strategy-semantic drift
+ incomplete migration / duplicate producers
```

The correction objective is:

```text
validated strategy semantics
+ existing new-chain engineering structure
- old-chain implementation debt
- new-chain semantic drift
- duplicate truth producers
= corrected current system
```

The development sequence is governed by dependency, not by file ownership or apparent ease of change.

---

## 1. Audit inputs and immutable planning evidence

This plan is based on the following audited artifacts:

| Artifact | SHA256 / status | Role |
|---|---|---|
| `AI_THEME_APP_ARCHITECTURE_STRATEGY_DRIFT_CORRECTION_AUDIT_R1_DETAILED.md` | `108ea48e71a3e997bc3d36c58cbf1b4835a7768584fb1b8bf5bb3636ca046f64` | master drift audit |
| `AI_THEME_APP_DRIFT_AUDIT_R1_INDEPENDENT_VERIFICATION.md` | `c54d9ab57c45d6c66b0b3900a1e9842f9cfdb4433f50c16ca32cce29776718e1` | independent verification / corrections |
| `EXECUTABLE_RULE_AUTHORITY_INVENTORY.md` | `54ac0a26c9a64d7c073cd18043c8a6ac953462dcdb19bb7c0add3fc71356a137` | 86 executable rule authority inventory |
| `CANONICAL_AND_LEGACY_DECISION_PRODUCER_INVENTORY.md` | `7fb8be093590bc08a2c8dbc90bb22cffad4a8036c01b07b2094c8a0fc6addfae` | producer / consumer / runtime inventory |
| `AI_THEME_APP_PREIMPLEMENTATION_GAP_CLOSURE_P0A2.md` | `31daa43fb1bef519c9fb8112cba6920173e67238a28ebc6e2d62aa74071360e1` | final pre-implementation gap closure |
| v0.6.4 strategy model | `f75dd6624d43870c299607239601c80befa83ad7f963bef69fd24e5dd3591d2b` | strategy authority |
| `DEVELOPMENT_MASTER_PLAN_v0.1_AUDIT.md` | `3ca7c9e0e110f932bc96327d00aff5c4753731e9823ef8ba1569304dff012e46` | independent plan audit driving v0.2 revisions |
| `DEVELOPMENT_MASTER_PLAN_v0.2_AUDIT.md` | `9eed1fde30d12424a88882af83f007fb9e60b3f514706527946db8e206e16189` | independent plan audit driving lifecycle-gap corrections in v0.3 |

If any of these inputs change, the affected task cards must be re-evaluated before implementation.

---

## 2. Program-wide hard constraints

### 2.1 Prohibited

```text
NO GREENFIELD REDESIGN
NO THIRD DECISION CHAIN
NO OLD SQL RESTORATION
NO DIRECT DB ACCESS IN DOMAIN
NO PORT/GATEWAY INTERNAL ATTRIBUTE BYPASS
NO FALLBACK / MOCK / SYNTHETIC SUCCESS
NO MISSING → PASS
NO HISTORICAL REPLAY FUTURE LEAKAGE
NO CASE-SPECIFIC PATCH
NO DEEPSEEK ARCHITECTURE OR STRATEGY AUTHORITY
NO UNAUTHORIZED POLICY FREEZE
NO "TESTS PASSED = SEMANTIC PASS"
NO CONSUMER CUTOVER BEFORE SHADOW / REPLAY EVIDENCE
```

### 2.2 Required

Every implementation task must identify:

```text
TASK_ID
EXACT_BASE_SHA
STRATEGY_AUTHORITY
ARCHITECTURE_AUTHORITY
CURRENT_DRIFT
AUTHORIZED_PATHS
AUTHORIZED_CHANGE
NON_GOALS
TESTS
REPLAY / NEGATIVE CASES
DOWNSTREAM CONSUMERS
ROLLBACK
MERGED-MAIN VERIFICATION
```

### 2.3 Rule authority

Every executable rule touched by a task must be classified as exactly one of:

```text
SOURCE_SUPPORTED
OWNER_APPROVED
EMPIRICAL_CANDIDATE
POLICY_UNFROZEN
LEGACY_ONLY
UNAUTHORIZED_INFERENCE
```

A task must stop rather than silently promote the last four categories into canonical policy.

---

## 3. Corrected dependency model

The implementation order is not simply L1→L12.

The audit shows the true dependency chain is:

```text
DATA TRUTH
    ↓
SEMANTIC EXPRESSIBILITY
    ↓
SEMANTIC CLASSIFICATION
    ↓
TRADING PERMISSION
    ↓
ROLE / SETUP ELIGIBILITY
    ↓
EXPECTATION / CONFIRMATION
    ↓
DECISION / PROJECTION
    ↓
CONSUMER CUTOVER
    ↓
LEGACY RETIREMENT
```

For the EARLY / OTO path specifically:

```text
P-03/P-04 L1 fact integrity
    ↓
B0 Candidate Mainline context visibility
    ↓
B1 Candidate lifecycle visibility
    ↓
B1' real EARLY classification
    ↓
B2 Trading Permission supports candidate+EARLY
    ↓
B3 OTO eligibility correction
```

For W2S:

```text
L1 fact integrity
    ↓
L2 confirmed mainline
    ↓
L3 divergence→repair
    ↓
L5 leader/core
    ↓
canonical D1 producer
    ↓
D2 confirmation
    ↓
intraday alert projection
```

---

## 4. Program phases

| Phase | Name | Goal | Owner gate |
|---|---|---|---|
| P0-A | Authority provisioning, safety & architecture lock | make audit/strategy authorities available from clean main-based branches; stop new boundary/policy drift | **yes: docs authority + P0-A authorization** |
| P0-B | Decision/data-integrity fail-closed corrections | remove fabricated/future/missing-as-positive facts in L1, W2S and lifecycle unknown handling | no |
| P0-C | Candidate expressibility + non-EARLY lifecycle semantic correction | keep candidate facts isolated from permission; align lifecycle vocabulary/transition authority before W2S relies on it | **yes: lifecycle mapping + non-EARLY lifecycle authority** |
| P0-D | EARLY semantic calibration | Owner labels EARLY truth set; replay/research; Owner decides positive EARLY evidence | **yes: labels + EARLY policy** |
| P0-E | Trading permission correction | first fix EARLY-independent permission semantics after lifecycle mapping, then separately enable candidate+EARLY probe | **yes for EARLY/policy gates** |
| P0-F | OneToTwo correction | restore approved discovery/probe window in existing OTO architecture | no after P0-D/E |
| P0-G | StrongStock / W2S convergence | converge D1/D2 and restore W2S semantics; formal W2S authority waits for approved DIVERGENCE→REPAIR lifecycle authority | **yes: lifecycle authority / producer cutover where required** |
| P0-H | Decision / projection convergence | complete missing new-chain projections and retire old decision authority safely | **yes: cutover** |
| P1-A | Display / metric semantics | correct Owner-facing emotion and metric labels/calculation | no |
| P1-B | Remaining architecture boundary cleanup | remove non-core direct DB debt | no semantic change |
| P1-C | Workbench / external reference separation | prevent Haoge labels from impersonating system output | no |
| P1-D | Expectation / outcome / M8 lineage | complete downstream validation loop | possible contract approval |
| P2 | Legacy / dead-code cleanup | remove dead paths after proof | yes for destructive retirement |

---

## 5. WBS summary

| Task ID | Priority | Task | Depends on | Parallel-safe |
|---|---:|---|---|---|
| P0A-00 | GOV | Provision audited strategy/audit/plan authorities into a clean main-based docs-only PR | Owner approval | no; must merge before implementation branches rely on docs |
| P0A-01 | P0 | Boundary guardrail baseline + ratchet | P0A-00 merged | with P0A-02 |
| P0A-02 | P0 | Rule-authority registry + pinning tests + PR checklist | P0A-00 merged | with P0A-01 |
| P0A-03 | P0 | Core live direct-DB remediation — recap job + mainline logic only | P0A-01 | limited |
| P0B-01 | P0 | MarketRegime fabricated-default removal + same-file Port/Gateway remediation | P0-A | no |
| P0B-02 | P0 | Historical-index future-leakage removal + same-file data-source remediation | P0B-01 or same PR if atomic | no |
| P0B-03 | P0 | UNKNOWN / missing L1 fail-closed semantics | P0B-01/02 | no |
| P0B-04 | P0 | W2S unified alert fail-closed safety | P0-A | can parallel after interfaces stable |
| P0B-05 | P0 | W2S D1 missing-data fail-closed safety + candidate-count delta report | P0-A | can parallel with P0B-04 if file sets do not overlap |
| P0B-06 | P0 | Lifecycle UNKNOWN / unmapped-state fail-closed safety | P0-A | can parallel with P0B-04/05 if file sets do not overlap |
| P0C-01 | P0 | Candidate-mainline diagnostic/context propagation with consumer isolation | P0-B | no |
| P0C-02 | P0 | Candidate lifecycle diagnostic propagation with consumer isolation | P0C-01 | no |
| P0C-03A | P0-READ | Build legacy→canonical lifecycle vocabulary mapping dossier + frequencies/examples | P0B-06 | yes, read-only |
| P0C-GATE-MAP | OWNER | Approve lifecycle vocabulary mapping / legacy-only states | P0C-03A | no |
| P0C-03B | P0 | Implement approved canonical lifecycle mapping adapter; preserve raw legacy state | P0C-GATE-MAP | no |
| P0C-04 | P0-RESEARCH | Replay non-EARLY lifecycle transitions, especially DIVERGENCE→REPAIR / FADE / CATCH_UP / ENDED | P0C-03B | research lane |
| P0C-GATE-L3 | OWNER | Approve provisional non-EARLY lifecycle evidence/transition authority | P0C-04 | no |
| P0C-05 | P0 | Enforce approved non-EARLY canonical transition authority / graph | P0C-GATE-L3 | no |
| P0D-00 | OWNER | EARLY replay sample labeling | P0C-02 | no |
| P0D-01 | P0-RESEARCH | EARLY evidence replay study | P0D-00 | research lane |
| P0D-GATE | OWNER | Approve EARLY positive-evidence policy | P0D-01 | no |
| P0D-02 | P0 | Implement approved EARLY classification | P0D-GATE | no |
| P0E-01a | P0 | TradingPermission corrections independent of EARLY | P0B + P0C-03B | no |
| P0E-01b | P0 | Candidate-mainline + EARLY probe permission | P0D-02 + P0E-01a | no |
| P0E-02 | P0 | Remove canonical authority from unfrozen position sizes | P0E-01a; repeat compatibility after P0E-01b | no |
| P0F-01 | P0 | Remove OTO legacy trading_principle existence dependency | P0C-02 | yes |
| P0F-02 | P0 | Correct OTO candidate/confirmed + EARLY eligibility | P0E-01b + P0F-01 | no |
| P0F-03 | P1 | Quarantine unfrozen OTO numeric gates | P0F-02 | no |
| P0G-01 | P0 | Strong-stock role eligibility correction | P0-B + P0E-01a | no |
| P0G-02 | P0 | W2S D1 producer convergence | P0G-01 + P0B-05 | no |
| P0G-03S | P0-SHADOW | Build W2S canonical eligibility in shadow with full lifecycle evidence lineage; no production authority | P0G-02 + P0C-03B + P0E-01a | no |
| P0G-03 | P0 | Activate canonical W2S eligibility using approved DIVERGENCE→REPAIR / FADE lifecycle authority | P0G-03S + P0C-05 | no |
| P0G-04 | P0 | W2S D2 / unified-alert authority convergence | P0G-03 + P0B-04 | no |
| P0H-01 | P0 | Legacy-output-to-new-source mapping | P0F + P0G | read-only mapping may start earlier; final mapping waits |
| P0H-02 | P0 | Complete PDV2 projection from canonical setup outputs | P0H-01 | no |
| P0H-03 | P0 | Shadow comparison and consumer cutover | P0H-02 | no |
| P0H-04 | P0 | Retire legacy decision authority | P0H-03 + Owner approval | no |
| P1A-01 | P1 | Fix emotion metric semantics | P0-B complete | yes |
| P1A-02 | P1 | Correct NarrativeEngine L1 display vocabulary | P1A-01 | yes |
| P1B-01 | P1 | Remaining Application/Domain boundary cleanup | P0-A | yes |
| P1C-01 | P1 | Separate analyst calibration from system output | independent | yes |
| P1D-01 | P1 | Normalize setup expectation contract | P0F/P0G | yes |
| P1D-02 | P1 | Decision→outcome lineage into M8 | P1D-01 + P0H | no |
| P2-01 | P2 | Dead-code retirement | all relevant cutovers | yes |
| P2-02 | P2 | Governance / architecture final verification | whole program | no |

# 6. Detailed task cards — P0-A Safety & Architecture Lock

## P0A-00 — Provision audited authorities into a clean main-based docs-only PR

### Why this is required

The current audited strategy/audit/plan files are stored under the Desktop worktree but are **untracked**. A clean implementation branch created from `origin/main` will not contain them.

Current status at planning time includes untracked:

- `docs/strategy_model/`;
- R1 audit;
- independent verification;
- executable-rule inventory;
- decision-producer inventory;
- P0A2;
- v0.1/v0.2/v0.3 plans and plan audits.

Implementation tasks must not depend on invisible files in another worktree.

### Required action

Create a documentation-only branch from the then-current `origin/main` and add only the approved authority documents required by implementation.

At minimum, after Owner approval, the versioned authority set must include:

1. v0.6.4 strategy working baseline;
2. R1 detailed audit;
3. R1 independent verification;
4. executable rule authority inventory;
5. canonical/legacy producer inventory;
6. P0A2 gap closure;
7. Development Master Plan v0.3;
8. v0.2 plan audit as provenance for v0.3.

Intermediate superseded plans/audits may also be retained for provenance, but the task must clearly mark which documents are canonical for implementation.

### Hard constraints

- docs-only change;
- no source code, tests, DB, configuration or runtime changes;
- do not include unrelated pre-existing modified/untracked files such as `ARCH_REVIEW.md` unless separately authorized;
- exact hashes of copied authority documents must be recorded before commit;
- clean branch base must be exact `origin/main`, not the feature worktree HEAD.

### Acceptance

- the authority files are committed and visible from a fresh branch based on merged main;
- hashes match the Owner-approved copies;
- no code/config/runtime path changed;
- later task cards can cite repository-visible documents rather than another worktree.

---

## P0A-01 — Boundary guardrail baseline + ratchet

### Objective

Prevent any **new** engineering boundary violation while allowing the current repository to stay green long enough to remove existing debt incrementally.

### Current evidence

Known violations already exist in Application and Domain. Therefore a naive “any violation = CI failure” rule would make the repository permanently red on day one.

### Required implementation

Use the repository's existing AST-guard style, especially the pattern already used by:

`stock_processing_service/tests/unit/test_canonical_metrics_migration_guard.py`

Implement a **baseline + ratchet** mechanism:

1. enumerate every currently accepted violation in a machine-readable baseline;
2. each baseline entry must include file path, violation type, audit reference, and status;
3. CI fails only when a **new** violation appears outside the baseline;
4. when a violation is fixed, its baseline entry is deleted;
5. baseline size may only decrease unless Owner explicitly approves a temporary exception;
6. tests must detect not only DB-driver imports but also boundary penetration such as:
   - `._pool`
   - `._db`
   - `._client`
   - `getattr(..., "_pool")`
   - raw SQL execution from Application/Domain.

### Non-goals

- no business-rule change;
- no DB remediation in this task;
- no deletion of existing violations;
- no collection/backtest cleanup.

### Acceptance

- existing repository is green with the audited baseline;
- a seeded new `asyncpg` import fails;
- a seeded new `_pool/_db/_client` penetration fails;
- an existing baseline violation does not fail CI;
- removing a fixed baseline item keeps CI green;
- adding a new baseline item requires explicit review and is not an automatic escape hatch.

### Exit gate

```text
ARCH_BOUNDARY_GUARD = PASS
BASELINE_CAPTURED = YES
NEW_VIOLATION_RATCHET = ENFORCED
BASELINE_ONLY_DECREASES = ENFORCED_BY_REVIEW
FALSE_POSITIVE_REVIEW = COMPLETE
```

---

## P0A-02 — Rule-authority registry + pinning tests + PR checklist

### Objective

Turn the audited executable-rule inventory into a practical governance control without pretending static analysis can discover every future business rule automatically.

### Required output A — registry

Create a machine-readable registry derived from the 86-rule inventory. Each entry must include at least:

```text
rule_id
path
symbol
strategy_layer
current_value_or_behavior
authority_class
source_ref / owner_decision_ref
policy_status
production_authority
```

### Required output B — pinning tests

For every registered P0/P1 executable rule, tests must pin its current location/value/behavior strongly enough that an unreviewed change causes a failure asking the developer to update the registry and authority classification.

The test is **not** required to infer whether arbitrary new source code contains a business rule.

### Required output C — PR checklist

The repository PR template / task completion contract must include mandatory declarations:

```text
Does this PR add or change an executable rule? YES/NO
If YES: rule_id(s)
Authority class
Source / Owner reference
Does this freeze a previously unfrozen policy? YES/NO
```

Human review is the backstop for genuinely new rules that static analysis cannot identify.

### Important

The registry does **not** freeze `POLICY_UNFROZEN` or `EMPIRICAL_CANDIDATE` values.

### Acceptance

- all audited P0/P1 rules are represented;
- changing a registered value without updating authority metadata fails;
- the PR checklist is mandatory for implementation batches;
- no rule is relabeled `OWNER_APPROVED` without explicit evidence.

---

## P0A-03 — Core live direct-DB remediation, tranche 1

### Objective

Restore frozen engineering boundaries in two live strategy paths that can be corrected without mixing in the MarketRegime semantic changes scheduled for P0-B.

### Authorized functional scope

1. `stock_processing_service/application/jobs/build_post_market_recap_job.py`
   - remove live Port/facade internal-connection penetration;
   - preserve query/output behavior exactly.
2. `stock_processing_service/domain/services/mainline_discovery/mainline_logic_chain_builder.py`
   - remove Domain-owned physical DB access;
   - Domain must receive typed facts.

### Explicitly excluded from P0A-03

`stock_processing_service/application/services/market_regime/market_regime_fact_context_builder.py`

Its boundary correction is intentionally moved into P0B-01/P0B-02 because the same file's fabricated defaults and historical live-data fallback must be corrected together. Do not preserve those known-bad semantics merely to achieve temporary parity.

### Plan-level authorized path families

The eventual executable task card must bind an exact path list. At plan level the allowed families are:

- the two SPS paths above;
- `stock_processing_service/ports/` for minimal Port additions;
- `stock_processing_service/infrastructure/gateway_adapters/` for adapters;
- `database_service/gateway.py`;
- the exact corresponding `database_service` manager/client file required by the new Gateway method, identified during task preflight.

Any new DatabaseGateway method must be additive and narrowly scoped; unrelated existing methods must not be rewritten.

### Required design behavior

```text
Application
→ explicit Port
→ Gateway adapter
→ DatabaseGateway / approved manager

Domain
← typed facts only
```

### Strict non-goal

Boundary-only behavior must remain semantically identical for the affected queries. No strategy rule, threshold, default, fallback, or data interpretation may change in this task.

### Acceptance

- exact before/after result parity on controlled fixtures/replay;
- no physical DB object reaches Domain;
- recap job no longer penetrates `_pool/_db/_client` for the corrected calls;
- corresponding baseline-ratchet entries are removed;
- no unrelated Gateway behavior changed.

---

# 7. Detailed task cards — P0-B L1 / Data-Integrity Fail-Closed Corrections

## P0B-01 — Remove fabricated MarketRegime defaults and fix same-file data boundary

### Current drift

When required market facts are absent, `MarketRegimeFactContextBuilder` fabricates a plausible market snapshot and that snapshot enters the real permission chain.

The same file also owns a direct database connection. Both issues concern the same responsibility: **where canonical L1 facts come from**.

### Required behavior

```text
missing required market facts
→ quality = UNKNOWN / BLOCKED_DATA_QUALITY
→ no fabricated market numbers
→ no downstream "normal" inference
```

### Engineering correction in the same task

Replace the file's direct physical DB access with the approved Port/Gateway path while correcting the source contract. Do not split this file into a temporary “boundary-only” change followed by a semantic change.

### Non-goals

- no new broad-market numeric thresholds;
- no NarrativeEngine/display changes;
- no EARLY semantics;
- no OTO/W2S eligibility redesign.

### Required tests

- all facts present;
- one required field missing;
- all market facts missing;
- malformed data;
- explicit numeric zero vs missing;
- Port/Gateway source parity for valid historical facts.

### Exit gate

No production permission path can reach an apparently normal market regime using fabricated values, and the corrected file no longer uses a physical DB connection directly.

---

## P0B-02 — Remove historical future-data fallback and enforce as-of source truth

### Current drift

Historical `trade_date` replay can fall back to current/live Akshare index data when bounded historical data is unavailable.

### Required behavior

```text
historical trade_date
+ bounded historical data missing
→ BLOCKED_DATA_QUALITY / UNKNOWN
→ never substitute current/post-date live data
```

If an external source is used for historical retrieval, it must explicitly support the requested historical date and the returned source timestamp must be bounded by the decision `as_of`.

### Required evidence

```text
max(source_observed_at) <= decision_as_of
```

for every decision fact.

### Acceptance

- anti-lookahead contract test;
- source trace includes source + observed_at/as_of;
- historical replay never consumes later/current data as a fallback;
- same-file DB/source boundary remains through Port/Gateway.

---

## P0B-03 — Fail-closed UNKNOWN semantics in L1/L4 boundary

### Current drifts

- missing short-term sentiment may fall to `normal`;
- unknown/unmatched market combinations may fall to the most permissive mode;
- allow/prohibit fields can conflict.

### Required behavior

Unknown must not become optimistic.

Formal downstream status must distinguish at least:

```text
KNOWN_ALLOWED
KNOWN_WAIT
BLOCKED_DATA_QUALITY
BLOCKED_UNDEFINED
BLOCKED_POLICY_UNFROZEN
```

### Acceptance

- unknown never maps to most aggressive trade mode;
- missing market context cannot authorize new entry;
- conflicting allow/prohibit fields are impossible or rejected;
- behavior is replay-safe.

---

## P0B-04 — W2S unified alert fail-closed safety

### Why this task is early

The service is LIVE by default and pushes every minute. Two known defects can create stale or falsely high-confidence alerts.

### Current P0 defects

1. no candidate for the current effective date → reuses the latest prior candidate date;
2. quote/fund-flow read failure → `unknown`, while `unknown != outflow` can still satisfy `high_confidence`.

### Required behavior

```text
no candidate for current effective date
→ no current-day W2S alert

required quote/fund-flow evidence missing
→ cannot emit high_confidence
→ insufficient-data / blocked diagnostic or no alert
```

### Non-goals

- no intraday scoring redesign;
- no threshold changes;
- no D1 producer convergence;
- no W2S canonical eligibility change.

### Acceptance

- stale candidate cannot produce today's alert;
- missing quote/fund-flow cannot produce `high_confidence`;
- candidate source date and alert date are explicit;
- no hidden exception swallowing can upgrade confidence.

---

## P0B-05 — W2S D1 missing-data fail-closed safety

### Purpose

Correct three LIVE “missing → allowed/default-positive” behaviors immediately, without waiting for OP-06/EARLY work because they are pure data-integrity defects.

### Scope

Only these audited behaviors:

1. weekly data missing → current `passed=True`;
2. previous lifecycle/state missing → current soft-pass path;
3. strong-stock grade missing → current default `"B"`.

### Required behavior

```text
required weekly evidence missing
→ not formally passed

required prior state missing
→ no W2S eligibility upgrade

strong grade missing
→ UNKNOWN / not qualified
```

Exact output shape should preserve compatibility where possible, but formal candidate eligibility must fail closed or remain explicitly unknown.

### Non-goals

- no W2S scoring rewrite;
- no divergence→repair redesign;
- no role-threshold decision;
- no D1 producer convergence;
- no EARLY dependency.

### Acceptance

- all three missing cases are covered by negative tests;
- candidate counts may decrease; that is an expected correction, not a regression;
- replay report must show **daily before/after candidate counts**, every removed candidate, and the exact removal reason;
- no unexplained candidate-count delta is allowed;
- no new substitute/default evidence is introduced;
- source/quality reason is visible.

---

## P0B-06 — Lifecycle UNKNOWN / unmapped-state fail-closed safety

### Purpose

Correct lifecycle-layer cases where unknown or unmapped state can currently fall through to a tradeable/default path. This is a data/semantic-safety fix, not a lifecycle reclassification task.

### Current evidence

In `layer_b_lifecycle_adapter.py`:

- explicit missing Layer B judgement already blocks trading correctly;
- however an unrecognized mapped state falls through `_playability(...)` to:
  - `can_watch=True`;
  - `can_trade_if_market_safe=True`;
  - `preferred_setup="standard"`.

In `mainline_environment_engine.py`, unrecognized lifecycle values can also collapse into misleading environment labels because only known state strings are classified.

### Required behavior

```text
unknown / unmapped lifecycle state
→ can_watch = true only if safe for diagnostics
→ can_trade_if_market_safe = false
→ no formal setup eligibility
→ lifecycle_quality = UNKNOWN / UNMAPPED
→ must not be relabeled as "no confirmed mainline"
```

### Non-goals

- no state-name mapping decision;
- no score-threshold change;
- no EARLY definition;
- no DIVERGENCE→REPAIR authority change.

### Acceptance

- explicit missing judgement remains fail-closed;
- unmapped raw state is fail-closed;
- unknown state cannot enter a tradeable bucket;
- raw state value is preserved for diagnostics;
- regression test covers a synthetic unknown state and a known state.

---

# 8. Detailed task cards — P0-C Candidate Mainline & Lifecycle Expressibility

## P0C-01 — Candidate Mainline diagnostic/context propagation with consumer isolation

### Current blocker

Machine candidate mainlines are produced by Mainline Discovery, but downstream setup context effectively only consumes confirmed mainlines.

### Required correction

Make candidate identity representable downstream without changing current production authorization:

```text
identity_status = CANDIDATE
identity_status = CONFIRMED
```

### Hard isolation rule

Until P0E-01b is merged:

```text
MainlineEnvironmentEngine
TradingPermissionEngine
OneToTwoRuleEngine
PDV2 / canonical trade consumers
```

must continue to consume **CONFIRMED only** for any behavior that can change trade permission, OTO focus, or formal decision output.

Candidate objects may appear only in:

- new typed diagnostic/context fields with no current decision consumer;
- replay/debug output;
- explicit candidate-only projections.

### Required guarantees

- candidate never becomes confirmed by propagation;
- candidate is never mapped to `is_strong_hotspot` merely to bypass the confirmed gate;
- no write-back to confirmed registry;
- no existing decision consumer changes behavior.

### Regression requirement

For the same replay dates before and after P0C-01:

```text
market_regime_review.allow_trade
market_regime_review.position_limit
OneToTwo outputs
```

must be **day-by-day identical**.

Any difference blocks the task.

---

## P0C-02 — Candidate lifecycle diagnostic propagation with consumer isolation

### Current blocker

Layer B cycle judgement already exists for all themes, but `MainlineLifecycleFactContextBuilder` only constructs lifecycle reviews for confirmed mainlines.

### Required correction

Allow candidate-mainline objects to carry Layer B evidence/state into a candidate-only diagnostic/context channel.

### Hard isolation rule

Before P0E-01b, candidate lifecycle rows must **not** be placed into the collection consumed by `MainlineEnvironmentEngine` / `TradingPermissionEngine` as trade-active mainlines.

Existing consumers must continue to see only confirmed lifecycle reviews for permission purposes.

### Critical semantic restriction

Do **not** reinterpret residual `start` as canonical EARLY.

For candidate diagnostics:

```text
observed_layer_b_state = existing state
canonical_early_status = UNRESOLVED / POLICY_UNFROZEN
decision_authority = NONE
```

### Regression requirement

Using identical replay inputs, P0C-02 must preserve day-by-day:

- MarketRegime permission;
- position-limit output;
- OneToTwo classification/focus status;
- PDV2 permission passthrough.

### Exit gate for P0-C

```text
CANDIDATE_IDENTITY_EXPRESSIBLE = YES
CANDIDATE_LIFECYCLE_EVIDENCE_EXPRESSIBLE = YES
TRADE_CONSUMERS_STILL_CONFIRMED_ONLY = YES
MARKET_REGIME_REPLAY_DIFF = ZERO
OTO_REPLAY_DIFF = ZERO
RESIDUAL_START_NOT_PROMOTED_TO_EARLY = YES
```

---

## P0C-03A — Build lifecycle vocabulary mapping dossier

### Purpose

Resolve the semantic gap between current local lifecycle labels and v0.6.4 canonical lifecycle labels before TradingPermission or W2S treats those labels as canonical truth.

### Current local labels

At minimum:

```text
seed
start
fermentation
acceleration
climax
divergence
repair
fade_watch
fade_confirmed
dead
```

Canonical v0.6.4 lifecycle:

```text
EARLY
FERMENTATION
ACCELERATION
CLIMAX
DIVERGENCE
REPAIR
CATCH_UP
FADE
ENDED
```

### Required read-only dossier

For each local state:

- exact producer/path/symbol;
- historical occurrence count;
- previous/next-state examples;
- representative evidence rows;
- downstream consumers;
- current playability/permission effect;
- proposed canonical mapping options;
- conflicts with v0.6.4 transition graph;
- whether the state should remain legacy-only.

Special questions to surface for Owner decision:

1. whether `fade_watch` maps to DIVERGENCE, FADE, or remains a non-canonical observation substate;
2. whether `fade_confirmed` maps to FADE;
3. whether `dead` maps to ENDED;
4. how CATCH_UP will be represented;
5. whether `seed` remains an identity/discovery diagnostic rather than canonical lifecycle;
6. how residual `start` is treated before EARLY is approved;
7. whether `fade_watch → repair` is invalid and must be removed from canonical transition authority.

### Non-goal

No production state changes.

---

## P0C-GATE-MAP — Owner lifecycle vocabulary decision

Tony reviews P0C-03A and assigns each local state one of:

```text
CANONICAL_MAP_TO_<STATE>
LEGACY_OBSERVATION_ONLY
DEPRECATED
UNRESOLVED
```

Any unresolved mapping blocks only consumers that require that specific semantic distinction.

---

## P0C-03B — Implement approved canonical lifecycle mapping adapter

### Purpose

Introduce an explicit semantic adapter between legacy/raw lifecycle labels and canonical v0.6.4 lifecycle semantics without rewriting historical stored data.

### Required output

Each lifecycle review must be able to expose separately:

```text
raw_lifecycle_state
canonical_lifecycle_state
mapping_authority
mapping_version
lifecycle_quality
```

### Rules

- preserve raw legacy state for replay and diagnostics;
- do not rename historical DB data in place;
- do not invent CATCH_UP/ENDED evidence merely to fill the vocabulary;
- residual `start` remains non-canonical until P0-D;
- unmapped/unknown stays fail-closed per P0B-06.

### Acceptance

- every known raw state has an Owner-approved mapping status;
- downstream code can consume canonical state without losing raw provenance;
- mapping alone does not change trade permission until the consuming task is explicitly authorized.

---

## P0C-04 — Non-EARLY lifecycle transition / evidence replay study

### Purpose

Validate the canonical authority of lifecycle states used by trading, especially the W2S-critical DIVERGENCE→REPAIR path, rather than letting current score thresholds silently define lifecycle truth.

### Current evidence/problem

`SubjectCycleJudgementService` currently uses weighted scores and thresholds such as:

```text
DIVERGENCE >= 60
REPAIR >= 65
ACCELERATION >= 75
FERMENTATION >= 60
```

and currently allows:

```text
repair_transition_allowed
= previous_state in {divergence, fade_watch}
```

The canonical v0.6.4 graph does not authorize `fade_watch → repair` as a canonical edge, and its observables/thresholds remain unfrozen.

### Study scope

Focus on non-EARLY states required by current production decisions:

- DIVERGENCE;
- REPAIR;
- FADE;
- ENDED;
- CATCH_UP where source-supported;
- FERMENTATION / ACCELERATION only as needed to validate transition context.

### Replay requirements

- positive and negative DIVERGENCE cases;
- genuine REPAIR after DIVERGENCE;
- fade cases that should not repair;
- second-divergence cases relevant to CATCH_UP;
- ENDED cases;
- transition ordering across multiple days;
- no future data in state assignment;
- evidence features separated from score thresholds.

### Required output

```text
current score-derived labels vs evidence
transition confusion matrix
false repair / false fade cases
candidate observable rules
threshold sensitivity
unresolved policy items
recommended provisional authority
```

No production changes.

---

## P0C-GATE-L3 — Owner decision on non-EARLY lifecycle authority

Tony decides whether the replay supports a provisional production authority for the lifecycle semantics required by W2S and permission.

Allowed outcomes:

```text
APPROVE_PROVISIONAL_NON_EARLY_POLICY
APPROVE_MAPPING_ONLY_KEEP_STATE_AUTHORITY_UNRESOLVED
REQUEST_MORE_REPLAY
REJECT_AND_REDEFINE
```

### Program rule for W2S

Until this gate approves production authority:

- P0G-01/P0G-02 may proceed;
- P0G-03S may build/shadow the corrected eligibility chain;
- **formal P0G-03 activation may not treat current score-derived DIVERGENCE/REPAIR labels as canonical truth**.

This is the selected governance answer to the v0.2 audit question: continue engineering and shadow work, but do not grant production trade authority to POLICY_UNFROZEN lifecycle labels.

---

## P0C-05 — Implement approved non-EARLY lifecycle transition authority

### Preconditions

- P0C-GATE-MAP approved;
- P0C-GATE-L3 approved a provisional/final policy.

### Required correction

Make canonical lifecycle authority depend on:

```text
previous canonical state
+ positive evidence
+ allowed canonical transition edge
+ data-quality status
```

rather than a flat score→state result alone.

Current weighted scores may remain as diagnostics/research features if useful, but they must not override the approved transition graph.

### Mandatory graph constraints

- no unsupported T06;
- no unsupported T12;
- DIVERGENCE→REPAIR only through approved evidence;
- T13 CATCH_UP only under the approved second-divergence semantics;
- FADE→ENDED preserved;
- no `fade_watch → repair` canonical shortcut unless Owner explicitly authorizes an equivalent mapped semantic after reviewing P0C-03A/P0C-04.

### Acceptance

- transition graph tests;
- multi-day replay;
- raw score diagnostics preserved but not canonical authority;
- W2S can cite exact prior/current canonical states and transition evidence.

---

# 9. Detailed task cards — P0-D EARLY Semantic Calibration

## P0D-00 — Owner-labeled EARLY replay set

### Purpose

Create a strategy-valid replay truth set **before** empirical EARLY research. EARLY ground truth cannot be inferred from later price success or from the current `start` label.

### Implementation-side preparation

Claude may prepare a candidate labeling table containing only information visible as of each proposed historical decision date:

```text
trade_date
theme
identity status at as_of
visible catalyst / event evidence
visible breadth / leader evidence
visible lifecycle evidence
market environment facts
proposed label slot
```

No future outcome may be shown in the labeling view used to make the initial label.

### Owner labeling

Tony labels each candidate:

```text
EARLY_POSITIVE
EARLY_NEGATIVE
UNCERTAIN
```

Optional later outcome data may be attached **after** labels are frozen for analysis, but cannot retroactively define the label.

Pending Haoge/external labels may be reviewed in the same session, but remain external reference until Tony explicitly accepts a label. They cannot become Tony-strategy ground truth automatically.

### Exit gate

```text
OWNER_LABELED_SET = FROZEN
UNCERTAIN_CASES = PRESERVED_AS_UNCERTAIN
NO_LOOKAHEAD_IN_LABEL_VIEW = VERIFIED
```

---

## P0D-01 — EARLY evidence replay study

### Purpose

Resolve OP-06 empirically without allowing Claude to invent a threshold.

### Preconditions

P0D-00 Owner-labeled set is frozen.

### Strategy evidence to use

Use v0.6.4 and the original strategy-source statements describing early-stage positive evidence, including concepts such as:

- initial board emergence / limited board formation;
- sector abnormality / first market response;
- clustered or concentrated catalyst/news;
- early leader/front-row formation;
- absence of already-mature fermentation/acceleration evidence.

Do not convert prose into a hard number without evidence and Owner approval.

### Dataset requirements

Use the Owner-labeled truth set plus additional unlabeled research cases. The validation set must include:

1. Owner-labeled genuine EARLY positives;
2. Owner-labeled false-start / one-day-tour negatives;
3. already-FERMENTATION examples;
4. weak/noise themes currently falling into residual `start`;
5. multiple market environments;
6. candidate-mainline cases where OTO opportunity appeared before human confirmation;
7. uncertain cases retained as uncertain, not forced into binary labels.

### Required output

A report, not production logic:

```text
candidate evidence features
positive/negative discrimination
sample counts
failure modes
candidate rule alternatives
sensitivity to thresholds
lookahead controls
recommended provisional policy
unresolved cases
```

### Prohibited

- tuning solely to named winners;
- using future success as an input feature;
- treating current `start` as truth;
- treating external analyst labels as Tony ground truth;
- writing production state.

---

## P0D-GATE — Owner decision for OP-06

Implementation stops here until Tony explicitly selects or rejects the proposed EARLY policy.

Possible outcomes:

```text
APPROVE_PROVISIONAL_POLICY
REQUEST_MORE_REPLAY
REJECT_AND_REDEFINE
KEEP_UNRESOLVED
```

If unresolved, only EARLY-dependent implementation remains blocked. W2S data-integrity fixes and EARLY-independent permission corrections may continue according to their own dependencies.

---

## P0D-02 — Implement approved EARLY classification

### Preconditions

- explicit Owner decision from P0D-GATE;
- rule source/version recorded;
- positive/negative replay set frozen.

### Required correction

Replace residual-default semantics with positive-evidence EARLY recognition.

EARLY must not be:

- “all other states”;
- a low-score residual bucket;
- an identity status;
- a broad-market state.

### Acceptance

- Owner-positive cases can enter EARLY through approved positive evidence;
- Owner-negative weak/noise cases do not become EARLY by fallthrough;
- transition out of EARLY follows approved/source-supported edges;
- no unsupported T06/T12 transitions reappear;
- replay remains as-of safe.

---

# 10. Detailed task cards — P0-E Trading Permission Correction

## P0E-01a — Correct EARLY-independent permission semantics

### Purpose

Fix permission errors that are already decidable from approved v0.6.4 semantics and do **not** depend on OP-06 / EARLY classification.

### Preconditions

- P0-B data-integrity corrections are complete;
- P0C-03B lifecycle vocabulary mapping is merged, so canonical state names are available without pretending that their score-derived production authority is already frozen.

### Scope

At minimum:

1. missing / unknown facts stay blocked or unknown;
2. ordinary `RISK_OFF` does **not** automatically veto the W2S strategy family;
3. `allow_trade` cannot contradict explicit prohibition semantics;
4. data-quality and policy-unfrozen blocks remain distinct from strategic WAIT;
5. existing confirmed-mainline consumers remain the only trade-authoritative identity path until P0E-01b;
6. the permission contract exposes a canonical lifecycle-veto slot, but **new production FADE/DIVERGENCE/REPAIR authority may not be activated from score-derived labels until P0C-05**.

### Required output semantics

```text
WAIT
ELIGIBLE
BLOCKED_DATA_QUALITY
BLOCKED_UNDEFINED
BLOCKED_POLICY_UNFROZEN
```

No candidate+EARLY probe authorization is introduced here.

### Non-goals

- no candidate-mainline trade permission;
- no EARLY definition;
- no OTO change;
- no W2S numeric threshold changes;
- no position-sizing policy.

### Acceptance

Matrix tests prove:

- ordinary RISK_OFF is not a blanket strategy-family veto;
- unknown does not become permissive;
- allow/prohibit semantics are internally consistent;
- no behavior depends on unapproved EARLY semantics;
- lifecycle-veto test cases using FADE/DIVERGENCE/REPAIR remain shadow/non-authoritative until P0C-05 if their state authority is not yet approved.

---

## P0E-01b — Candidate-mainline + EARLY probe permission

### Purpose

Only after OP-06 is approved and implemented, allow the already-approved candidate-mainline / EARLY discovery semantics to affect formal permission.

### Preconditions

- P0C complete with candidate diagnostics isolated;
- P0D-02 approved EARLY classification merged;
- P0E-01a merged.

### Required input contract

At minimum:

```text
global_market_state
global_market_quality
mainline_identity_status
mainline_lifecycle_state
lifecycle_quality
strategy_family
policy_status
```

### Required approved cases

1. extreme-risk / ice-point itself → no routine new entry;
2. verified recovery may allow EARLY core probe;
3. CANDIDATE_MAINLINE + EARLY may become `PROBE_ELIGIBLE`;
4. candidate identity remains candidate — permission does not confirm it;
5. missing/unknown facts never authorize probe.

### Required transition from P0-C isolation

Only in this task may the candidate-only diagnostic fields created in P0-C be connected to trade-permission logic.

The change must be explicit and reviewed; removing the P0-C consumer isolation is itself part of this task.

### Acceptance

- candidate+EARLY path is reachable only through approved positive EARLY evidence;
- confirmed-mainline existing behavior remains traceable;
- no candidate is mapped to strong-hotspot/confirmed as a shortcut;
- extreme-risk/missing data blocks probe;
- OTO still remains a separate downstream setup decision.

---

## P0E-02 — Remove canonical authority from unfrozen position sizing

### Current drift

Position limits such as `0.15 / 0.2 / 0.3 / 0.5` are hard-coded while OP-16 and related sizing policy remain unfrozen.

### Required correction

Separate:

```text
trade permission
from
position sizing policy
```

The canonical permission path must not treat unfrozen numeric size as Owner strategy truth.

### Scheduling

P0E-02 may begin after P0E-01a. A final compatibility verification must be repeated after P0E-01b because candidate+EARLY probe permission may expose paths that previously carried a numeric position field.

### Compatibility option

Legacy numeric fields may remain only if clearly labeled non-canonical / policy-unfrozen and cannot silently authorize behavior.

### Acceptance

- permission can be correct without frozen numeric sizing;
- policy status is visible;
- no consumer interprets provisional numeric values as Owner-frozen strategy.

---

# 11. Detailed task cards — P0-F OneToTwo Correction

## P0F-01 — Remove legacy trading_principle existence dependency

### Current drift

The new OTO fact builder requires the old-chain `trading_principle` object to exist even though it does not consume its content.

### Required correction

Remove that existence dependency and rely only on canonical/new-chain facts actually used by OTO.

### Why this can happen before full OTO semantic correction

This is an engineering dependency cleanup with no strategy effect.

### Acceptance

- OTO fact build no longer fails solely because legacy `trading_principle` is absent;
- output is identical when all canonical inputs are the same;
- legacy P-11 remains otherwise untouched.

---

## P0F-02 — Correct OTO candidate / confirmed / EARLY eligibility

### Preconditions

- P0C candidate propagation complete with consumer isolation;
- P0D EARLY policy approved and implemented;
- P0E-01a and P0E-01b TradingPermission corrections merged.

### Existing architecture to preserve

```text
FactContext
→ RuleEngine
→ TechnicalGate
→ Scorer
→ SetupPlan
→ premarket/intraday confirmation
```

### Required semantic correction

Approved model:

```text
CANDIDATE_MAINLINE + EARLY + market permits
→ OTO may be PROBE-eligible

CONFIRMED_MAINLINE + appropriate lifecycle
→ OTO normal eligibility

FADE / blocked market / data-quality block
→ no entry authorization
```

OTO must remain distinct from EARLY_PROBE itself.

### Required output distinction

At least conceptually:

```text
PROBE_ELIGIBLE
NORMAL_ELIGIBLE
OBSERVE_ONLY
PENDING_REVIEW
REJECT
```

Exact DTO changes should minimize compatibility impact.

### Acceptance

- confirmed mainline is no longer the only path to meaningful OTO eligibility;
- candidate identity is never upgraded by OTO;
- setup cannot bypass global permission;
- OTO still requires its own next-day confirmation.

---

## P0F-03 — Quarantine unfrozen OTO numeric gates

### Scope

Review all OTO thresholds already identified:

- turnover 3/5/8/15%;
- score 70/80;
- technical 55;
- amount 1bn;
- 120-day position threshold;
- breadth counts;
- other score weights.

### Required action

For each:

```text
SOURCE_SUPPORTED numeric + same semantic role
→ may remain

SOURCE_SUPPORTED numeric but code uses it in a different role
→ correct semantic role or downgrade

POLICY_UNFROZEN
→ cannot be canonical hard gate without Owner decision

LEGACY_ONLY
→ remove/demote after replay
```

### Important

This task must not opportunistically choose between 8% and 15%. OP-10 remains an explicit Owner/empirical gate.

---

# 12. Detailed task cards — P0-G StrongStock / W2S Convergence

## P0G-01 — Correct strong-stock / role eligibility

### Preconditions

- P0-B data-integrity corrections complete;
- P0E-01a EARLY-independent permission contract correction complete;
- this W2S lane does **not** wait for EARLY / P0-D.

### Goal

Preserve Layer C rolling-pool engineering while ensuring role evidence does not become mainline, lifecycle or trade authority by itself.

### Review items

- two-board independent-leader path;
- rank/front-row shortcuts;
- recent-limit-up count grades;
- trend score gates;
- observe/formal transitions;
- role/grade defaults already identified by the rule inventory.

### Required semantic rule

```text
strong-stock fact / role evidence
!= mainline confirmation
!= lifecycle state authority
!= W2S authorization by itself
```

### Acceptance

Role output is explainable, source-traced, and cannot bypass L1/L2/L3 qualification.

---

## P0G-02 — Converge W2S D1 to one canonical producer

### Preconditions

P0B-05 has already removed the three audited missing-data positive defaults. Producer convergence must preserve those fail-closed semantics.

### Current conflict

Two LIVE D1 producers currently disagree on candidate limits and weak/strong definitions.

### Required migration

1. establish one canonical D1 domain contract;
2. make API and PreMarketBrief consume the same canonical producer;
3. preserve separate presentation limits only when they are explicitly projection concerns;
4. remove duplicate semantic authority from the non-canonical producer;
5. keep lifecycle state inputs fully source-traced, even before their canonical authority is approved.

### Acceptance

Same date + same upstream facts → same D1 candidate truth regardless of consumer.

---

## P0G-03S — Build corrected W2S eligibility in SHADOW

### Purpose

Continue engineering progress without allowing current score-derived DIVERGENCE/REPAIR labels to become production truth before lifecycle replay and Owner approval.

### Preconditions

- P0G-02 complete;
- P0C-03B canonical lifecycle mapping available;
- P0E-01a complete;
- P0C-GATE-L3 may still be unresolved.

### Shadow semantic model

```text
non-extreme global market
× CONFIRMED_MAINLINE
× mapped lifecycle evidence indicating DIVERGENCE→REPAIR
× LEADER / CORE
× structure survives
× re-consensus confirmation
```

### Critical authority rule

If the DIVERGENCE/REPAIR classification is still based on POLICY_UNFROZEN score thresholds:

```text
production_authority = false
mode = shadow
```

The task may compare, explain and replay candidates, but may not replace the current production D1 eligibility truth or authorize an alert/trade.

### Required lineage

Every shadow candidate must expose:

```text
raw_prior_state
raw_current_state
canonical_prior_state
canonical_current_state
transition_evidence
score_diagnostics
state_authority_status
mainline_identity
role
market_permission
structure evidence
```

### Acceptance

- no missing-data pass;
- passive-divergence entry remains distinct from W2S;
- fade/unmapped/unknown cases are not silently treated as valid repair;
- shadow outputs are clearly labeled non-authoritative;
- comparison report identifies where current score labels disagree with evidence/transition expectations.

---

## P0G-03 — Activate canonical W2S eligibility

### Preconditions

- P0G-03S complete;
- P0C-05 approved non-EARLY lifecycle transition authority merged.

### Approved semantic model

```text
non-extreme global market
× CONFIRMED_MAINLINE
× canonical DIVERGENCE→REPAIR
× LEADER / CORE
× structure survives
× re-consensus confirmation
```

Ordinary RISK_OFF is not an automatic veto. Canonical FADE invalidates W2S.

### Required corrections

- broad OR strong-background shortcut cannot replace role/mainline qualification;
- missing weekly/prior-state/grade evidence cannot pass;
- lifecycle transition must be canonical and evidence-backed;
- score values may remain diagnostic but may not override canonical state/transition authority;
- any remaining unfrozen numeric rule stays explicitly POLICY_UNFROZEN.

### Acceptance

Every production W2S candidate exposes a complete eligibility lineage across L1/L2/L3/L5/L7 and cites the approved lifecycle transition authority.

---

## P0G-04 — Converge D2 confirmation and unified alert authority

### Preconditions

P0G-03 is production-authoritative and P0B-04 alert fail-closed safety is already merged.

### Current issue

P-16 already produces D2 confirmation. P-20 then combines D2 and intraday scoring into a second outward-facing `high_confidence` classification.

### Required end state

The unified alert layer is a projection/alert consumer, not a second independent W2S truth producer.

### Required behavior

- D2 confirmation source is explicit;
- intraday evidence may refine alert urgency but cannot redefine canonical D2 truth;
- no stale candidate reuse;
- missing quote/fund-flow cannot elevate confidence;
- all alert levels carry source date and data-quality state.

### Acceptance

There is one canonical W2S confirmation truth and one or more alert projections consuming it.

---

# 13. Detailed task cards — P0-H Decision / Projection Convergence

## P0H-01 — Legacy-output to canonical-source mapping

### Why this task exists

P0A2 proved that `PostMarketDecisionEngineV2` is not a decision engine. It is an assembler that:

- projects strong-stock rows;
- passes through MarketRegime permission;
- currently leaves `weak_to_strong_d1_reviews` and `next_day_focus_stocks` empty.

Therefore old-chain P-11 cannot be retired until every still-required output has a canonical new-chain source.

### Required mapping table

For each old P-11 output:

```text
old output field
old producer
actual consumer
business meaning
still required? yes/no
canonical replacement source
projection owner
cutover precondition
```

At minimum cover:

- `market_environment_review`;
- `theme_decision_reviews`;
- `strong_stock_decision_reviews`;
- `watchlist_reviews`;
- `trading_principle`.

### Key principle

Do not create a replacement “decision engine” merely to mimic the old object.

Where the canonical truth already exists as:

- MarketRegime permission;
- Mainline/Lifecycle facts;
- OTO setup plan;
- W2S D1/D2;
- Layer C role facts;

the new output should be a projection/assembler over those truths.

### Acceptance

Every old field is classified:

```text
REPLACED_BY_CANONICAL_SOURCE
PROJECTION_ONLY
NO_LONGER_VALID_SEMANTICS
OWNER_DECISION_REQUIRED
```

No code cutover in this task.

---

## P0H-02 — Complete PDV2 projection without turning PDV2 into a strategy engine

### Goal

Use existing PDV2 as a structured assembler for corrected canonical outputs.

### Required sources

Potential sources include, subject to P0H-01 mapping:

- MarketRegime permission;
- ActiveMainlineUniverse;
- lifecycle reviews;
- Layer C strong-stock rows;
- OTO setup plan;
- canonical W2S D1/D2;
- other already-existing setup projections.

### Required rule

PDV2 may:

- normalize;
- deduplicate;
- annotate;
- project;
- preserve source lineage.

PDV2 may **not**:

- invent strategy eligibility;
- create new weighted scores;
- decide mainline identity;
- decide lifecycle;
- invent candidate fallback.

### Specific correction

Fields currently hard-coded empty must either:

1. receive canonical existing sources, or
2. remain absent/unknown with explicit reason if no canonical source exists.

No fake placeholder success.

### Acceptance

Every PDV2 field has:

```text
source producer
source object
as_of
policy version
data quality
projection transformation
```

---

## P0H-03 — Shadow comparison and consumer cutover

### Preconditions

- P0B–P0G complete;
- P0H-02 produces all required canonical projections;
- old P-11 still intact for comparison.

### Shadow period

Run old and corrected new outputs side by side, but only one is canonical for each consumer during a given stage.

Compare:

- market permission;
- theme/mainline representation;
- role/strong-stock display;
- OTO watchlist;
- W2S candidates/confirmations;
- next-day focus projection;
- DailyReview V2;
- Notion/report output.

### Required diff classification

Every difference must be tagged:

```text
EXPECTED_CORRECTION
LEGACY_BUG
NEW_BUG
POLICY_UNFROZEN
DATA_QUALITY_DIFFERENCE
PROJECTION_ONLY_DIFFERENCE
UNEXPLAINED
```

`UNEXPLAINED` blocks cutover.

### Consumer migration

Cut over one consumer group at a time:

1. internal recap structured payload;
2. DailyReviewV2;
3. front-end recap;
4. Notion/report;
5. any setup dependency.

### Owner gate

Tony must approve the cutover evidence before legacy authority removal.

---

## P0H-04 — Retire legacy decision authority

### Preconditions

- P0H-03 approved;
- all consumers migrated;
- OTO no longer depends on old `trading_principle`;
- no unresolved legacy field consumer.

### Required end state

P-11 may remain temporarily as diagnostic/replay reference but must no longer be:

- display authority;
- trade permission authority;
- setup prerequisite;
- report truth producer.

### Destructive cleanup

Physical code deletion is optional and should be deferred to P2 if keeping it aids replay/reference.

The important P0 result is **authority retirement**, not file deletion.

### Acceptance

Search/call-graph evidence proves no production consumer reads P-11 business outputs as canonical truth.

---

# 14. P1 tasks

## P1A-01 — Correct emotion metric semantics

### Known defects

- `first_board_red_ratio` actually uses yesterday-limit-up → today-continue-limit-up ratio;
- chain ratio denominator is wrong;
- `chain_red` is inferred from another score;
- `chain_loss` is estimated;
- `yest_red` is constant;
- fallback derives all six metrics from breadth;
- weighting model does not match the external reference method.

### Correction policy

Separate three concerns:

```text
measured fact
estimated/research feature
external analyst reference metric
```

Do not relabel one as another.

### Required end state

Owner-facing metric names exactly match their actual numerator/denominator/time window.

If a required metric cannot be measured from available data:

```text
UNKNOWN / unavailable
```

not an estimate under the canonical label.

---

## P1A-02 — Correct NarrativeEngine L1 display semantics

### Current issue

NarrativeEngine uses a single feedback score and labels broad-market phase with theme-lifecycle words such as divergence/repair/fade.

### Required correction

Use L1 environmental language consistent with v0.6.4.

This is a display/research path, not the canonical trade-permission path.

### Important

Do not mechanically reuse P0 MarketRegime thresholds unless they are semantically appropriate and authorized.

---

## P1B-01 — Remaining Application / Domain boundary cleanup

### Scope

After P0 core-path remediation, clean remaining live P1/P2 violations:

- `market_metrics/service.py`;
- `event_driver_tracer.py`;
- `event_driven_opportunity_builder.py`;
- live collection/operations;
- backtest `gw._client` penetration;
- cognition display direct connections;
- remaining Domain direct DB services.

### Security subtask

Remove hard-coded database username/password from `event_driven_opportunity_builder.py` and migrate to approved configuration / Gateway access.

### Rule

Engineering cleanup must preserve business outputs unless a separate semantic task authorizes change.

---

## P1C-01 — Separate external analyst calibration from system output

### Current risk

Workbench “apply calibration” can overwrite system draft fields with Haoge labels, then later compare the resulting draft back against Haoge, inflating agreement.

### Required correction

Preserve separate namespaces:

```text
SYSTEM_OUTPUT
ANALYST_REFERENCE
CALIBRATION_SUGGESTION
OWNER_ACCEPTED_OVERRIDE (if ever approved)
```

External reference must not masquerade as original system output.

### Acceptance

Turing/alignment metrics are computed against immutable pre-calibration system output.

---

## P1D-01 — Normalize setup expectation contract

### Existing capabilities

- OTO next-day expectation;
- W2S auction expectation;
- M8 expected observations / falsifiers.

### Goal

Create a minimal shared contract without creating a new strategy engine.

Required semantic fields:

```text
setup_id
strategy_family
as_of
expected_observations
falsifiers
confirmation_window
source_evidence_refs
policy_version
quality_status
```

OTO/W2S remain the producers of their strategy-specific expectations.

---

## P1D-02 — Connect decision → outcome lineage into M8

### Preconditions

- canonical decision path converged;
- setup expectation contract available;
- M8 remains downstream-only.

### Goal

Enable:

```text
Expectation
→ Confirmation
→ Decision
→ Outcome
→ Validation
→ Replay
```

without allowing M8 validation results to rewrite business truth.

---

# 15. P2 cleanup

## P2-01 — Dead-code retirement

Candidates include:

- `application/services/market_cognition/emotion_engine.py`;
- unused `engines/` directory wrappers;
- dead `build_jyhf_stock_daily_bar_job.py`;
- obsolete diagnostic paths after migration;
- legacy P-11 code if no longer useful for replay.

### Rule

No deletion until:

- reference search complete;
- production call graph complete;
- historical replay dependency checked;
- Owner approves destructive cleanup where material.

---

## P2-02 — Final governance and architecture verification

Perform a final independent audit against:

- v0.6.4 or its later approved successor;
- current architecture/ADRs;
- merged main;
- final producer inventory;
- final rule-authority inventory.

Required output:

```text
remaining POLICY_UNFROZEN rules
remaining direct-DB violations
remaining duplicate producers
remaining legacy-live consumers
remaining data-quality fallbacks
remaining strategy-model open questions
```

Program closes only when these are explicitly accepted or tracked.



---

# 16. Validation matrix

| Task | Unit | Contract | Replay | Negative | Shadow | Merged-main verification |
|---|---|---|---|---|---|---|
| P0A-00 | n/a | docs-hash/provenance | n/a | unrelated-file exclusion | n/a | **primary** |
| P0A-01 | yes | **baseline+ratchet primary** | n/a | seeded violations | n/a | yes |
| P0A-02 | yes | registry pinning | n/a | metadata mismatch | n/a | yes |
| P0A-03 | yes | boundary | parity replay | yes | optional | yes |
| P0B-01 | yes | fact + boundary | yes | **required** | yes | yes |
| P0B-02 | yes | anti-lookahead | **required** | required | yes | yes |
| P0B-03 | yes | L1 quality | yes | **required** | yes | yes |
| P0B-04 | yes | alert contract | date replay | **required** | yes | yes |
| P0B-05 | yes | D1 quality contract | **before/after daily counts** | **required** | yes | yes |
| P0B-06 | yes | lifecycle quality | yes | unknown/unmapped | yes | yes |
| P0C-01 | yes | identity isolation | **parity required** | yes | yes | yes |
| P0C-02 | yes | lifecycle isolation | **parity required** | yes | yes | yes |
| P0C-03A | research | mapping dossier | historical frequencies/examples | conflicts | n/a | report only |
| P0C-GATE-MAP | Owner | mapping decision | n/a | unresolved preserved | n/a | frozen artifact |
| P0C-03B | yes | mapping adapter | mapping replay | unmapped | yes | yes |
| P0C-04 | research | transition study | **primary** | **primary** | n/a | report only |
| P0C-GATE-L3 | Owner | lifecycle authority | n/a | unresolved preserved | n/a | frozen artifact |
| P0C-05 | yes | transition graph | **multi-day required** | **required** | yes | yes |
| P0D-00 | Owner labels | labeling protocol | n/a | yes/no/uncertain | n/a | frozen artifact |
| P0D-01 | research | n/a | **primary** | **primary** | n/a | report only |
| P0D-02 | yes | EARLY transition | **required** | required | yes | yes |
| P0E-01a | yes | permission matrix | **required** | **required** | yes | yes |
| P0E-01b | yes | candidate+EARLY permission | **required** | **required** | yes | yes |
| P0E-02 | yes | policy-status contract | yes | yes | yes | yes |
| P0F-01 | yes | dependency contract | parity | yes | optional | yes |
| P0F-02 | yes | OTO eligibility | **required** | **required** | yes | yes |
| P0F-03 | yes | authority contract | yes | yes | yes | yes |
| P0G-01 | yes | role contract | yes | required | yes | yes |
| P0G-02 | yes | producer parity | **required** | required | **required** | yes |
| P0G-03S | yes | shadow W2S eligibility | **required** | **required** | **primary** | yes |
| P0G-03 | yes | canonical W2S eligibility | **required** | **required** | yes | yes |
| P0G-04 | yes | D2/alert contract | **required** | **required** | yes | yes |
| P0H-01 | n/a | mapping | evidence review | n/a | n/a | report only |
| P0H-02 | yes | projection contract | yes | yes | yes | yes |
| P0H-03 | n/a | consumer contract | **required** | required | **primary** | yes |
| P0H-04 | yes | no-consumer-left | yes | yes | yes | yes |
| P1A-01 | yes | metric contract | historical calc | required | n/a | yes |
| P1A-02 | yes | display semantic | yes | yes | n/a | yes |
| P1B-01 | yes | boundary | parity where needed | yes | optional | yes |
| P1C-01 | yes | provenance | yes | yes | n/a | yes |
| P1D-01 | yes | expectation schema | yes | yes | yes | yes |
| P1D-02 | yes | lineage | yes | yes | yes | yes |
| P2-01 | yes | reference scan | n/a | n/a | n/a | yes |
| P2-02 | audit | audit | representative | representative | audit | **primary** |

# 17. Mandatory replay composition

No strategy-semantic task may be accepted using only known successful stocks.

Each semantic task must include:

### 17.1 Positive cases

Cases expected to satisfy the strategy.

### 17.2 Negative cases

Superficially similar cases that should fail.

### 17.3 Boundary cases

Examples near a policy/semantic boundary.

### 17.4 Missing-data cases

At least:

```text
missing market facts
missing prior lifecycle
missing role evidence
missing auction quote
missing support evidence
```

Expected behavior must be fail-closed or explicitly unknown.

### 17.5 Conflicting-evidence cases

Example:

```text
good theme evidence
but extreme market risk

strong stock
but lifecycle invalid

good auction
but candidate eligibility absent
```

### 17.6 Cross-day transition cases

Especially for lifecycle and W2S:

```text
DIVERGENCE(t)
→ REPAIR(t+1)
```

with evidence timestamps bounded to each day.

### 17.7 Anti-lookahead

For every replay:

```text
max(source_observed_at) <= decision_as_of
```

unless the source is explicitly post-decision outcome data used only for validation.

---

# 18. Phase exit gates

## P0-A EXIT

```text
[ ] P0A-00 authority documents are committed on clean main-based history and visible from fresh branches
[ ] document hashes match Owner-approved copies
[ ] baseline+ratchet guard detects direct driver use
[ ] baseline+ratchet guard detects _pool/_db/_client penetration
[ ] current known violations are baselined, not silently ignored
[ ] baseline has not grown without explicit Owner-approved exception
[ ] executable P0/P1 rules have authority registry entries
[ ] pinning tests catch unreviewed changes to registered rules
[ ] PR checklist declares any new/changed executable rule
[ ] P0A-03 boundary corrections pass parity tests
```

## P0-B EXIT

```text
[ ] no fabricated market snapshot in canonical permission path
[ ] MarketRegime fact builder uses approved Port/Gateway path
[ ] no historical live-data fallback / future leakage
[ ] missing sentiment != normal
[ ] unknown market != aggressive/default-active
[ ] allow/prohibit semantics are non-contradictory
[ ] current-day W2S alert cannot use stale candidate date
[ ] missing quote/fund-flow cannot create high-confidence alert
[ ] W2S weekly-data missing cannot formally pass
[ ] W2S prior-state missing cannot soft-pass
[ ] W2S strong-grade missing cannot default to B
[ ] daily before/after W2S candidate-count deltas are reported and every removal is explained
[ ] lifecycle unknown/unmapped state cannot become tradeable/default-standard
[ ] unknown lifecycle is not mislabeled as "no confirmed mainline"
```

## P0-C EXIT

```text
[ ] CANDIDATE identity is representable downstream as CANDIDATE
[ ] candidate lifecycle evidence is representable diagnostically
[ ] existing trade consumers still consume CONFIRMED only until explicitly authorized
[ ] candidate is not remapped to strong_hotspot/confirmed as a shortcut
[ ] residual start is NOT promoted to EARLY
[ ] market_regime_review day-by-day replay diff = ZERO for P0C-01/02 isolation work
[ ] OneToTwo day-by-day replay diff = ZERO for P0C-01/02 isolation work
[ ] lifecycle vocabulary dossier completed with occurrence frequencies and examples
[ ] Owner-approved mapping exists for every production-relevant raw lifecycle state or remains explicitly unresolved
[ ] raw_lifecycle_state and canonical_lifecycle_state are separately traceable
[ ] non-EARLY transition replay completed
[ ] Owner decides provisional non-EARLY lifecycle authority
[ ] approved canonical graph rejects unsupported transitions
[ ] score-derived lifecycle values are diagnostics unless explicitly authorized
```

## P0-D EXIT

```text
[ ] Owner-labeled EARLY set frozen before research
[ ] labels are positive / negative / uncertain
[ ] initial label view contains no future outcome
[ ] EARLY study includes positive/negative/boundary/uncertain cases
[ ] no lookahead
[ ] Owner approves provisional/final EARLY semantics
[ ] implementation uses positive evidence, not residual default
[ ] weak/noise theme does not become EARLY by fallthrough
```

## P0-E EXIT

```text
[ ] EARLY-independent permission corrections do not depend on unapproved EARLY
[ ] ordinary RISK_OFF does not mechanically veto the W2S strategy family
[ ] allow/prohibit output is internally consistent
[ ] UNKNOWN / undefined / policy-unfrozen remain distinct
[ ] lifecycle vetoes are production-authoritative only after approved lifecycle authority exists
[ ] after P0E-01b: no-mainline != candidate-EARLY
[ ] after P0E-01b: candidate-EARLY can be PROBE_ELIGIBLE only through approved EARLY evidence
[ ] numeric position sizing is not canonical unless frozen
```

## P0-F EXIT

```text
[ ] OTO no longer depends on legacy trading_principle existence
[ ] OTO preserves candidate vs confirmed identity
[ ] candidate+EARLY path can reach PROBE_ELIGIBLE
[ ] OTO does not itself confirm mainline
[ ] OTO does not bypass L1 permission
[ ] OTO normal lifecycle eligibility consumes approved canonical lifecycle semantics
[ ] unfrozen numeric rules remain visibly unfrozen
```

## P0-G EXIT

```text
[ ] one canonical W2S D1 truth producer
[ ] API and premarket consume same D1 truth
[ ] shadow W2S eligibility exists before production activation
[ ] current score-derived DIVERGENCE/REPAIR cannot gain production authority before P0C-GATE-L3 / P0C-05
[ ] production W2S requires confirmed mainline + canonical divergence→repair + leader/core
[ ] canonical FADE invalidates W2S
[ ] lifecycle evidence/transition lineage is auditable
[ ] missing weekly/prior-state/strong-grade evidence cannot silently pass
[ ] D2 is one canonical confirmation truth
[ ] unified alert cannot create a second independent truth
```

## P0-H EXIT

```text
[ ] every legacy P-11 output mapped or explicitly retired
[ ] PDV2 is assembler, not a new strategy engine
[ ] corrected new outputs shadow-compared
[ ] no unexplained diff
[ ] Owner approves consumer cutover
[ ] no production consumer depends on legacy decision authority
```

---

# 19. Parallel execution policy

Maximum parallel tasks remains 3, but parallelism is allowed only when task outputs do not define each other's semantics.

## 19.1 Authority provisioning and first wave

```text
P0A-00 docs-only authority provisioning
        ↓ merged main
Lane A: P0A-01 Boundary baseline + ratchet
Lane B: P0A-02 Rule authority registry / pinning / PR checklist
```

P0A-03 begins after P0A-01 is stable.

## 19.2 P0-B parallelism

```text
Lane A: P0B-01 → P0B-02 → P0B-03   (L1 fact chain, serial)
Lane B: P0B-04                       (W2S unified-alert fail-closed)
Lane C: P0B-05 or P0B-06            (D1 or lifecycle missing-data fail-closed)
```

Because max parallelism is 3, P0B-05 and P0B-06 may run sequentially in Lane C unless one of the other lanes is idle.

## 19.3 Candidate / EARLY lane

```text
P0C-01
→ P0C-02
→ P0D-00 Owner labels
→ P0D-01
→ P0D-GATE
→ P0D-02
→ P0E-01b
→ P0F-02
```

P0E-01a is deliberately outside this chain.

## 19.4 Non-EARLY lifecycle authority lane

After P0B-06:

```text
P0C-03A
→ P0C-GATE-MAP
→ P0C-03B
→ P0C-04
→ P0C-GATE-L3
→ P0C-05
```

This lane can overlap EARLY research where file sets and review responsibilities do not conflict.

## 19.5 W2S lane

After P0-B and P0E-01a:

```text
P0G-01
→ P0G-02
→ P0G-03S   (shadow only)
               ↓ waits for P0C-05
            P0G-03
→ P0G-04
```

This explicitly answers the v0.2 audit question:

> W2S engineering and shadow comparison may proceed using mapped/raw lifecycle evidence with full lineage, but **production W2S authority must wait for lifecycle replay + Owner-approved DIVERGENCE→REPAIR / FADE semantics**.

## 19.6 Later safe parallelism

After P0 core semantics stabilize:

```text
P1A metric/display
P1B boundary cleanup
P1C workbench calibration separation
```

may run in parallel when file sets do not overlap.

---

# 20. Git / branch governance

For each Claude implementation task:

1. fetch and verify current remote main;
2. record exact base SHA;
3. create exactly one task branch;
4. only touch authorized paths;
5. commit all task work;
6. push branch;
7. open/update exactly one PR;
8. attach raw tests/replay evidence;
9. independent review against exact PR HEAD by a reviewer that is **not the same Claude conversation/session that implemented the task**; another Claude session/model may review, but must independently inspect the exact PR HEAD;
10. merge only after Owner/QA gate where required;
11. verify merged main behavior;
12. delete local and remote task branch.

Prohibited branch patterns:

```text
fix-v2
retry
final
final-final
clean-copy
temporary-alt
```

If a task must be reworked, continue within the same task branch unless Owner authorizes a replacement.

---

# 21. Claude completion-report contract

Every completion report must include:

```text
TASK_ID
BASE_SHA
HEAD_SHA
PARENT_SHA
CHANGED_PATHS
AUTHORITY_REFS
SEMANTIC_BEFORE
SEMANTIC_AFTER
ARCHITECTURE_BEFORE
ARCHITECTURE_AFTER
RAW_TEST_OUTPUT
REPLAY_OUTPUT
NEGATIVE_CASE_OUTPUT
DATA_QUALITY_BEHAVIOR
DOWNSTREAM_CONSUMERS
LEGACY_IMPACT
POLICY_UNFROZEN_ITEMS
KNOWN_REMAINING_BLOCKERS
GIT_DIFF_CHECK
REMOTE_PUSH_VERIFIED
```

A completion report must not use `PASS` if any mandatory exit condition is unverified.

---

# 22. Owner decision gates

## Gate O-00 — Authority-document provisioning

Current strategy/audit/plan authorities are untracked in the Desktop feature worktree and are absent from a clean `origin/main` branch.

Before implementation tasks depend on them, Tony must authorize P0A-00 to create a docs-only PR from current `origin/main`.

The docs-only PR must not include unrelated worktree changes.

## Gate O-01 — Development Master Plan v0.3 approval + P0-A authorization

This document itself does not authorize implementation.

Recommended Owner authorization:

```text
Approve Development Master Plan v0.3.

Authorize P0-A only:
P0A-00 → P0A-01 / P0A-02 → P0A-03.

Do not authorize P0-B yet.
```

### Temporary W2S alert operation

Record separately:

```text
SPS_ENABLE_W2S_ALERT_LOOP
= DISABLE_UNTIL_P0B04_VERIFIED
or
= KEEP_ENABLED_WITH_KNOWN_RISK
```

Recommendation remains `DISABLE_UNTIL_P0B04_VERIFIED` because the LIVE loop is known to reuse stale candidates and may emit `high_confidence` when fund-flow evidence is missing.

This is an operational decision, not implementation authorization. Claude must not change it without explicit Owner instruction.

## Gate O-02 — Lifecycle vocabulary mapping

Occurs at `P0C-GATE-MAP`.

Tony decides how current raw states map to v0.6.4 canonical lifecycle semantics, including:

- `fade_watch`;
- `fade_confirmed`;
- `dead`;
- `seed`;
- representation of CATCH_UP;
- treatment of residual `start` before EARLY approval;
- whether any current transition semantics remain legacy-only.

No implementation agent may decide these mappings unilaterally.

## Gate O-03 — Non-EARLY lifecycle authority

Occurs at `P0C-GATE-L3` after replay of DIVERGENCE / REPAIR / FADE / CATCH_UP / ENDED transitions.

Tony decides whether current/revised observables are sufficient for provisional production authority.

Until approved, W2S corrected eligibility may run only in shadow where it depends on those lifecycle labels.

## Gate O-04 — EARLY truth-set labeling

Occurs at `P0D-00`.

Claude prepares as-of-safe candidate samples. Tony assigns:

```text
EARLY_POSITIVE
EARLY_NEGATIVE
UNCERTAIN
```

No model/analyst may substitute for Owner labeling.

## Gate O-05 — EARLY policy

Occurs after `P0D-01` replay study.

Tony may approve a provisional policy, request more replay, reject/redefine, or keep unresolved.

## Gate O-06 — Any unresolved numeric policy

Examples:

- OTO turnover conflict;
- position limits;
- candidate caps if business-semantic rather than projection-only;
- W2S numeric grading;
- auction grading.

If task correctness depends on the value, stop and ask Owner.

## Gate O-07 — Decision cutover

Required before P0H-03/P0H-04 changes canonical consumers or legacy authority.

## Gate O-08 — Destructive retirement

Required before deleting major legacy modules still valuable for replay/reference.

---

# 23. Explicit non-goals of this program

This program does not:

- freeze the entire v0.6.4 strategy model;
- select all unresolved numeric thresholds;
- redesign Theme ontology;
- redesign M8;
- redesign Event→Theme matching;
- create an automated trading execution system;
- tune for maximum backtest return;
- treat Haoge external analysis as Tony strategy authority;
- rewrite the front end unless required by corrected contracts;
- clean every historical code smell before restoring semantic correctness.

---

# 24. Program success criteria

The program is successful only when all of the following are true.

## 24.1 Strategy fidelity

- L1 global market and L3 mainline lifecycle are separate;
- L2 identity and L3 lifecycle are separate;
- EARLY is positively evidenced, not a residual bucket;
- candidate-mainline discovery window is reachable;
- OTO can participate in the approved EARLY window;
- W2S uses approved mainline/lifecycle/role semantics;
- passive-divergence entry remains distinct from W2S;
- missing/estimated data cannot create formal eligibility;
- 35/30/20/15 is never used as an additive trading score.

## 24.2 Engineering architecture

- canonical Application/Domain paths respect Port/Gateway boundaries;
- no direct physical DB handle reaches pure Domain logic;
- canonical decision capabilities have one truth producer;
- projections do not invent strategy truth;
- replay is as-of safe and reproducible;
- new and old decision chains no longer coexist as equal production authorities.

## 24.3 Governance

- every executable P0/P1 rule has authority metadata;
- every unfrozen policy is visible;
- every cutover has shadow/replay evidence;
- no implementation batch exceeds its authorized scope;
- merged main, not PR narrative, is final engineering truth.

---

# 25. Recommended immediate next step

After Owner approves this v0.3 plan, do **not** authorize the entire program at once.

Authorize only P0-A.

The first action is:

```text
P0A-00
= docs-only authority provisioning from clean origin/main
```

After P0A-00 is merged and a fresh main-based branch can read all authority documents:

```text
P0A-01
P0A-02
```

may run in parallel.

Then:

```text
P0A-03
```

runs against their merged-main result.

Only after the P0-A exit gate passes should P0-B be authorized.

This preserves the central correction discipline:

> **First make the system unable to silently grow new drift; then correct the live decision facts; then restore strategy semantics in dependency order.**

