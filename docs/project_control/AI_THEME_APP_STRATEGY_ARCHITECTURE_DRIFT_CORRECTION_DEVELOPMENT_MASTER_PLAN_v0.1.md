# AI Theme App — Strategy / Architecture Drift Correction Development Master Plan v0.1

> **Document type:** Development master plan / implementation control document  
> **Status:** DRAFT FOR OWNER APPROVAL — IMPLEMENTATION NOT AUTHORIZED  
> **Owner:** Tony  
> **Implementation owner:** Claude  
> **Date:** 2026-10-07  
> **Program type:** CORRECTION / MIGRATION COMPLETION — NOT GREENFIELD REDESIGN  
> **Engineering truth:** `origin/main@ddc9442e88c5bf6f5248bfb141e74472c48eb25a`  
> **Local main at planning time:** `ddc9442e88c5bf6f5248bfb141e74472c48eb25a`  
> **Local working-tree HEAD at planning time:** `e1f1b9ad1e44af0edaba9543bc4868ae42f2382f` — not engineering truth  
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
| P0-A | Safety & architecture lock | stop new boundary/policy drift | no |
| P0-B | L1 decision fact integrity | remove fabricated/future/missing-as-normal market facts | no |
| P0-C | Candidate mainline & lifecycle expressibility | let approved candidate semantics flow without pretending they are confirmed | no |
| P0-D | EARLY semantic calibration | define positive EARLY evidence through replay, then Owner decision | **yes: OP-06** |
| P0-E | Trading permission correction | distinguish no-mainline / candidate-EARLY / confirmed lifecycle / unknown | yes if unresolved policy appears |
| P0-F | OneToTwo correction | restore approved discovery/probe window in existing OTO architecture | no after P0-D/E |
| P0-G | StrongStock / W2S convergence | restore W2S eligibility and one D1 truth producer | possible producer-cutover approval |
| P0-H | Decision / projection convergence | complete missing new-chain outputs and retire old decision authority safely | **yes: cutover** |
| P1-A | Display / metric semantics | correct Owner-facing emotion and metric labels/calculation | no |
| P1-B | Remaining architecture boundary cleanup | remove non-core direct DB debt | no semantic change |
| P1-C | Workbench / external reference separation | prevent Haoge labels from impersonating system output | no |
| P1-D | Expectation / outcome / M8 lineage | complete downstream validation loop | possible contract approval |
| P2 | Legacy / dead-code cleanup | remove dead paths after proof | yes for destructive retirement |

---

## 5. WBS summary

| Task ID | Priority | Task | Depends on | Parallel-safe |
|---|---:|---|---|---|
| P0A-01 | P0 | Boundary guardrails and authority tests | plan approval | with P0A-02 |
| P0A-02 | P0 | Rule-authority manifest / diagnostics contract | plan approval | with P0A-01 |
| P0A-03 | P0 | Core live direct-DB boundary remediation | P0A-01 | limited |
| P0B-01 | P0 | MarketRegime fabricated-default removal | P0A | no |
| P0B-02 | P0 | Historical-index future-leakage removal | P0B-01 or same batch if atomic | no |
| P0B-03 | P0 | UNKNOWN / missing L1 fail-closed semantics | P0B-01/02 | no |
| P0B-04 | P0 | W2S unified alert fail-closed safety | P0A | can parallel after interfaces stable |
| P0C-01 | P0 | Candidate-mainline downstream context propagation | P0B | no |
| P0C-02 | P0 | Candidate lifecycle review propagation | P0C-01 | no |
| P0D-01 | P0 | EARLY replay dataset & evidence study | P0C | yes, research lane |
| P0D-GATE | OWNER | OP-06 EARLY decision | P0D-01 | no |
| P0D-02 | P0 | Implement approved EARLY classification | P0D-GATE | no |
| P0E-01 | P0 | TradingPermission semantic correction | P0D-02 | no |
| P0E-02 | P0 | Remove canonical authority from unfrozen position sizes | P0E-01 | no |
| P0F-01 | P0 | Remove OTO legacy trading_principle existence dependency | P0C | yes |
| P0F-02 | P0 | Correct OTO candidate/confirmed + EARLY eligibility | P0E + P0F-01 | no |
| P0F-03 | P1 | Quarantine unfrozen OTO numeric gates | P0F-02 | no |
| P0G-01 | P0 | Strong-stock role eligibility correction | P0E | no |
| P0G-02 | P0 | W2S D1 producer convergence | P0G-01 | no |
| P0G-03 | P0 | W2S canonical eligibility / missing-data correction | P0G-02 | no |
| P0G-04 | P0 | W2S D2 / unified-alert authority convergence | P0G-03 | no |
| P0H-01 | P0 | Legacy-output-to-new-source mapping | P0F + P0G | yes, read-only/design mapping |
| P0H-02 | P0 | Complete PDV2 projection from canonical setup outputs | P0H-01 | no |
| P0H-03 | P0 | Shadow comparison and consumer cutover | P0H-02 | no |
| P0H-04 | P0 | Retire legacy decision authority | P0H-03 + Owner approval | no |
| P1A-01 | P1 | Fix emotion metric semantics | P0B complete | yes |
| P1A-02 | P1 | Correct NarrativeEngine L1 display vocabulary | P1A-01 | yes |
| P1B-01 | P1 | Remaining Application/Domain boundary cleanup | P0A | yes |
| P1C-01 | P1 | Separate analyst calibration from system output | independent | yes |
| P1D-01 | P1 | Normalize setup expectation contract | P0F/P0G | yes |
| P1D-02 | P1 | Decision→outcome lineage into M8 | P1D-01 + P0H | no |
| P2-01 | P2 | Dead-code retirement | all relevant cutovers | yes |
| P2-02 | P2 | Governance / architecture final verification | whole program | no |



---

# 6. Detailed task cards — P0-A Safety & Architecture Lock

## P0A-01 — Boundary guardrails and architecture contract tests

### Objective

Prevent any new code from deepening the exact engineering mistake that motivated the new chain: bypassing Ports/Gateway from Application or Domain.

### Current evidence

Known P0 violations include:

- `application/jobs/build_post_market_recap_job.py` — multiple `getattr(..., "_pool")` / `_db` penetrations and raw SQL.
- `application/services/market_regime/market_regime_fact_context_builder.py` — hard-coded DSN and direct `asyncpg.connect`.
- `domain/services/mainline_discovery/mainline_logic_chain_builder.py` — Domain receives/uses pool and raw queries.
- `domain/services/kline_break_detector.py` — live Domain direct DB.
- `domain/services/w2s_unified_alert_service.py` — live Domain direct DB.

### Authorized change

Add architecture contract tests / static checks that fail when production Application or Domain code:

- imports DB drivers directly where forbidden;
- contains raw SQL execution;
- accesses `_pool` / `_db` / `_client` of Port/Gateway implementations;
- reaches through a facade to physical DB objects.

Tests must allow explicitly whitelisted infrastructure/adapters and must not treat false positives as violations.

### Non-goals

- no business-rule change;
- no port implementation rewrite in this task;
- no dead-code deletion;
- no collection/backtest cleanup yet.

### Acceptance

- test demonstrably fails against a seeded forbidden example;
- existing legitimate adapter code is not falsely blocked;
- all currently known P0 boundary violations are detected;
- test result is reported separately from business tests.

### Exit gate

```text
ARCH_BOUNDARY_GUARD = PASS
KNOWN_P0_VIOLATIONS_DETECTED = YES
FALSE_POSITIVE_REVIEW = COMPLETE
```

---

## P0A-02 — Executable rule authority manifest and semantic-change guard

### Objective

Convert the 86-rule audit inventory into an enforceable development artifact so future PRs cannot silently add or promote policy.

### Required output

A machine-readable or code-review-friendly registry that maps touched executable rules to:

```text
rule_id
path
symbol
strategy_layer
authority_class
source_ref / owner_decision_ref
policy_status
production_authority
```

### Rule

A new or changed executable rule with no authority mapping must fail review/contract validation.

### Important

The registry does **not** freeze POLICY_UNFROZEN or EMPIRICAL_CANDIDATE values. It exposes them as unresolved.

### Acceptance

- all currently P0/P1 decision rules in the two inventories have an entry;
- no numeric value is relabeled OWNER_APPROVED unless supported by v0.6.4 or an explicit later Owner decision;
- changes to authority class are review-visible.

---

## P0A-03 — Core live direct-DB remediation

### Objective

Restore the already-frozen engineering boundary in live strategy paths before semantic correction.

### Scope, first tranche only

1. `build_post_market_recap_job.py` P0 Port penetration.
2. `market_regime_fact_context_builder.py` hard-coded direct connection.
3. `mainline_logic_chain_builder.py` Domain direct query.
4. Other live P0 boundary paths only if the same Port/Gateway addition can safely serve them.

### Required design behavior

```text
Application
→ explicit Port method
→ Gateway / Adapter
→ DatabaseService
```

Domain receives typed facts, not physical connections.

### Strict non-goal

The values returned by the new Port must be semantically identical to the existing physical query before any business correction is layered on top. Boundary change and semantic change should not be mixed in one commit unless inseparable and explicitly justified.

### Acceptance

- exact before/after query result parity on fixtures/replay;
- no direct DB object available to Domain;
- no new raw SQL in Application;
- existing downstream DTO shape preserved unless contract change is separately approved.

---

# 7. Detailed task cards — P0-B L1 Decision Fact Integrity

## P0B-01 — Remove fabricated MarketRegime defaults

### Current drift

When market facts are absent, `MarketRegimeFactContextBuilder` fabricates a plausible-looking market:

```text
up ≈ 2000
down ≈ 3000
limit_up ≈ 30
limit_down ≈ 10
relay = normal
break = normal
```

This fabricated snapshot feeds the actual trade-permission chain.

### Required behavior

```text
missing required market facts
→ quality state = UNKNOWN / BLOCKED_DATA_QUALITY
→ no fabricated numeric market facts
→ no downstream "normal" inference
```

### Non-goals

- do not decide new broad-market thresholds;
- do not rename all L1 states yet;
- do not touch NarrativeEngine display path.

### Required tests

- all facts present;
- one required field missing;
- all market facts missing;
- malformed data;
- explicit zero market value vs missing value distinction.

### Exit gate

No production permission path can reach an apparently normal market regime using fabricated values.

---

## P0B-02 — Remove historical future-data fallback

### Current drift

Historical `trade_date` replay can fall back to current/live Akshare index data when historical DB data is unavailable.

### Required behavior

```text
historical trade_date
+ historical index data missing
→ BLOCKED_DATA_QUALITY / UNKNOWN
→ never fetch post-date live data as substitute
```

Current-day runtime and historical replay must have different data-availability semantics if needed, but both must preserve as-of truth.

### Required evidence

Replay must prove that no source timestamp exceeds requested `trade_date / as_of`.

### Acceptance

- anti-lookahead contract test;
- source trace includes as-of timestamp/source;
- no live source is consumed for a past replay date unless the source itself supports historical bounded retrieval.

---

## P0B-03 — Fail-closed UNKNOWN semantics in L1/L4 boundary

### Current drifts

- missing sentiment may fall to `normal`;
- unknown/unmatched market combinations may fall to the most permissive `mainline_active` path;
- `allow_trade` and prohibition lists can conflict.

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

Exact public DTO naming may preserve compatibility, but the semantics above must be representable and auditable.

### Acceptance

- unknown never maps to highest position/most aggressive trade mode;
- conflicting allow/prohibit fields are impossible or fail validation;
- missing market context cannot authorize new position entry.

---

## P0B-04 — W2S unified alert fail-closed safety

### Why this task is early

The service is LIVE by default and pushes external alerts every minute. Its current errors can create stale or falsely high-confidence alerts.

### Current P0 defects

1. today's candidate pool missing → uses latest prior available candidate date;
2. quote/fund-flow read failure → `unknown`, while `unknown != outflow` allows `high_confidence`.

### Required behavior

```text
no candidate for current effective date
→ no current-day W2S alert

required quote/fund-flow evidence missing
→ cannot emit high_confidence
→ emit blocked/insufficient-data diagnostic or no alert
```

### Non-goals

- no rewrite of intraday scoring;
- no new thresholds;
- no W2S strategy-semantic change in this task;
- no D1 producer convergence yet.

### Acceptance

- stale candidate cannot produce today's alert;
- missing quote evidence cannot produce `high_confidence`;
- alert source date and candidate source date are explicit;
- Domain direct-DB remediation may be included only if isolated and behavior-preserving.



---

# 8. Detailed task cards — P0-C Candidate Mainline & Lifecycle Expressibility

## P0C-01 — Candidate Mainline downstream context propagation

### Current blocker

Machine candidate mainlines are produced by Mainline Discovery, but downstream setup context effectively only consumes human-confirmed mainlines.

Known blocker B0:

- `application/services/post_market_setup_fact_context_builder.py` filters to confirmed source/context.

### Required correction

Allow downstream fact/context construction to represent both:

```text
identity_status = CANDIDATE
identity_status = CONFIRMED
```

without conflating them.

### Required guarantees

- CANDIDATE never becomes CONFIRMED by propagation;
- no candidate write-back into confirmed registry;
- every consumer can distinguish candidate from confirmed;
- no trade authorization is created by this task alone.

### Acceptance

A replay fixture with a valid machine candidate but no human confirmation must produce a typed downstream context carrying candidate identity, while all confirmed-only behaviors remain unchanged.

---

## P0C-02 — Candidate lifecycle review propagation

### Current blocker

Layer B cycle judgement exists for all themes, but `MainlineLifecycleFactContextBuilder` only constructs lifecycle reviews for confirmed mainlines.

Known blocker B1.

### Required correction

Permit candidate-mainline objects to carry their existing Layer B lifecycle evidence/review downstream, while preserving identity distinction.

### Critical restriction

Do **not** reinterpret current residual `start` as canonical EARLY in this task.

For candidate objects:

```text
layer_b_state = existing observed state
canonical_early_status = UNRESOLVED / POLICY_UNFROZEN
```

until P0-D is completed.

### Acceptance

- candidate lifecycle evidence reaches MarketRegime/setup context;
- candidate/confirmed identity remains visible;
- no new state threshold is introduced;
- no default state is promoted to canonical EARLY.

---

# 9. Detailed task cards — P0-D EARLY Semantic Calibration

## P0D-01 — EARLY evidence replay study

### Purpose

Resolve OP-06 empirically without allowing Claude to invent a threshold.

### Strategy evidence to use

Use v0.6.4 and the original strategy-source statements describing early-stage positive evidence, including concepts such as:

- initial board emergence / limited number of limit-ups;
- sector abnormality / first market response;
- clustered or concentrated catalyst/news;
- early leader/front-row formation;
- absence of already-mature fermentation/acceleration evidence.

Do not convert any prose item into a hard number without replay evidence and Owner approval.

### Dataset requirements

Build a replay study containing:

1. known genuine EARLY → later mainline positive cases;
2. false-start / one-day-tour negative cases;
3. themes that were already FERMENTATION when first detected;
4. weak/noise themes incorrectly falling into current residual `start`;
5. multiple market environments;
6. at least one candidate-mainline case where OTO opportunity emerged before human confirmation.

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
```

### Prohibited

- tuning solely to 神剑/联德/维科;
- using future mainline success as an input feature;
- treating current `start` label as ground truth;
- writing production state.

---

## P0D-GATE — Owner decision for OP-06

Implementation stops here until Tony explicitly selects or rejects the proposed EARLY policy.

Possible Owner outcomes:

```text
APPROVE_PROVISIONAL_POLICY
REQUEST_MORE_REPLAY
REJECT_AND_REDEFINE
KEEP_UNRESOLVED
```

If unresolved, P0E/P0F paths depending on machine EARLY classification remain blocked.

---

## P0D-02 — Implement approved EARLY classification

### Preconditions

- explicit Owner decision from P0D-GATE;
- rule source and version recorded;
- positive/negative replay set frozen for validation.

### Required correction

Replace residual-default semantics with positive-evidence EARLY recognition.

### Required relation to lifecycle graph

EARLY is a canonical lifecycle state. It must not be:

- “all other states”;
- a low score bucket;
- an identity status;
- a broad-market state.

### Acceptance

- true EARLY cases enter EARLY through positive evidence;
- weak/noise cases do not become EARLY merely because other thresholds miss;
- transition out of EARLY follows only approved/source-supported lifecycle edges;
- no unsupported T06/T12 transitions reappear;
- replay has explicit as-of protection.

---

# 10. Detailed task cards — P0-E Trading Permission Correction

## P0E-01 — Correct Market × Lifecycle permission semantics

### Purpose

Restore L4 as a permission/resonance layer using existing MarketRegime/MainlineEnvironment/TradingPermission architecture.

### Current defects

- no confirmed mainline → all trade disabled;
- candidate+EARLY cannot be expressed;
- unknown can fall into permissive mode;
- ordinary RISK_OFF can over-block W2S;
- allow/prohibit outputs can conflict.

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

### Required semantic outcomes

The system must distinguish:

```text
WAIT
PROBE_ELIGIBLE
ELIGIBLE
BLOCKED_DATA_QUALITY
BLOCKED_UNDEFINED
BLOCKED_POLICY_UNFROZEN
```

### Key approved cases

1. extreme-risk / ice-point itself → no routine new entry;
2. verified recovery may allow EARLY core probe;
3. candidate mainline + EARLY may be probe-eligible;
4. confirmed mainline lifecycle governs normal setup eligibility;
5. ordinary RISK_OFF does not automatically kill all W2S;
6. theme FADE invalidates W2S;
7. missing/unknown facts do not authorize entry.

### Non-goals

- no numeric position sizing;
- no new strategy-family rules beyond approved v0.6.4 semantics;
- no OTO scoring change;
- no W2S scoring change.

### Acceptance

A matrix test covers approved Market×Lifecycle cases plus undefined/policy-unfrozen cells. Undefined cells must remain blocked/unknown, not filled for completeness.

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

The canonical permission path must not treat unfrozen numeric size as strategy truth.

### Compatibility options

Implementation may preserve legacy numeric fields for backward compatibility only if they are explicitly labeled non-canonical / policy-unfrozen and cannot silently authorize behavior.

### Acceptance

- permission can be correct without a frozen numeric position;
- policy-unfrozen status is visible in output/diagnostics;
- no downstream consumer interprets a provisional number as Owner-frozen strategy.

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

- P0C candidate propagation complete;
- P0D EARLY policy approved and implemented;
- P0E TradingPermission corrected.

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

### Goal

Preserve Layer C rolling pool architecture while ensuring role evidence does not become trade permission by itself.

### Review items

- two-board independent-leader path;
- rank≤3 front-row shortcut;
- recent-limit-up count grades;
- trend score gates;
- observe/formal transitions;
- missing strong-grade defaults.

### Required semantic rule

```text
strong-stock fact / role evidence
!= mainline confirmation
!= lifecycle permission
!= W2S authorization by itself
```

### Acceptance

Role output is explainable, source-traced, and does not bypass L1/L2/L3.

---

## P0G-02 — Converge W2S D1 to one canonical producer

### Current conflict

Two LIVE D1 producers:

- P-14 API path: max 10, different weak/strong definitions;
- P-15 premarket path: max 20, different weak/strong definitions.

### Architecture intent

Existing architecture assigns new-chain D1 domain responsibility to `domain/services/w2s_candidate_service`.

### Required migration

1. establish one canonical D1 domain contract;
2. make API use case and PreMarketBrief consume the same canonical producer;
3. preserve separate presentation limits only if they are explicitly projection concerns, not candidate-truth differences;
4. mark/remove duplicate rule authority from the non-canonical producer.

### Acceptance

Same date + same facts → same D1 candidate truth regardless of consumer.

---

## P0G-03 — Restore canonical W2S eligibility and fail-closed behavior

### Approved semantic model

```text
non-extreme global market
× CONFIRMED_MAINLINE
× DIVERGENCE→REPAIR
× LEADER / CORE
× structure survives
× re-consensus confirmation
```

Ordinary RISK_OFF is not an automatic veto; theme FADE is.

### Remove / correct

- broad OR strong-background shortcut;
- weekly-data-missing → pass;
- unknown prior lifecycle → soft pass;
- default strong grade;
- fade-watch ranking above divergence if it effectively authorizes W2S.

### Distinguish

```text
PASSIVE_DIVERGENCE_ENTRY
!= W2S
```

### Acceptance

Every W2S candidate exposes a complete eligibility lineage across L1/L2/L3/L5/L7.

---

## P0G-04 — Converge D2 confirmation and unified alert authority

### Current issue

P-16 already produces D2 confirmation. P-20 then combines D2 and intraday scoring into a second outward-facing `high_confidence` classification.

### Required end state

The unified alert layer should be a projection/alert consumer, not a second independent semantic truth producer.

### Required behavior

- D2 confirmation source is explicit;
- intraday evidence may refine alert urgency but cannot silently redefine canonical D2 truth;
- no stale candidate reuse;
- missing quote/fund-flow cannot elevate confidence;
- all alert levels carry source date and evidence quality.

### Acceptance

There is one canonical W2S confirmation truth and one or more projections/alerts consuming it.



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
| P0A-01 | yes | **primary** | n/a | yes | n/a | yes |
| P0A-02 | yes | **primary** | n/a | yes | n/a | yes |
| P0A-03 | yes | yes | parity replay | yes | optional | yes |
| P0B-01 | yes | yes | yes | **required** | yes | yes |
| P0B-02 | yes | anti-lookahead | **required** | required | yes | yes |
| P0B-03 | yes | **required** | yes | **required** | yes | yes |
| P0B-04 | yes | alert contract | date replay | **required** | yes | yes |
| P0C-01 | yes | identity contract | yes | yes | yes | yes |
| P0C-02 | yes | lifecycle context | yes | yes | yes | yes |
| P0D-01 | research | n/a | **primary** | **primary** | n/a | report only |
| P0D-02 | yes | lifecycle transition | **required** | required | yes | yes |
| P0E-01 | yes | permission matrix | **required** | **required** | yes | yes |
| P0E-02 | yes | policy-status contract | yes | yes | yes | yes |
| P0F-01 | yes | dependency contract | parity | yes | optional | yes |
| P0F-02 | yes | OTO eligibility | **required** | **required** | yes | yes |
| P0F-03 | yes | authority contract | yes | yes | yes | yes |
| P0G-01 | yes | role contract | yes | required | yes | yes |
| P0G-02 | yes | producer parity | **required** | required | **required** | yes |
| P0G-03 | yes | W2S eligibility | **required** | **required** | yes | yes |
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

---

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
[ ] architecture boundary guard detects direct driver use
[ ] architecture boundary guard detects _pool/_db/_client penetration
[ ] executable decision rules have authority classification
[ ] no new unresolved rule can enter production silently
[ ] core Port/Gateway boundary corrections pass parity tests
```

## P0-B EXIT

```text
[ ] no fabricated market snapshot in canonical permission path
[ ] no historical live-data fallback / future leakage
[ ] missing sentiment != normal
[ ] unknown market != aggressive/default-active
[ ] allow/prohibit semantics are non-contradictory
[ ] current-day W2S alert cannot use stale candidate date
[ ] missing quote/fund-flow cannot create high-confidence alert
```

## P0-C EXIT

```text
[ ] CANDIDATE mainline can flow downstream as CANDIDATE
[ ] CONFIRMED remains distinct
[ ] candidate lifecycle evidence reaches context
[ ] current residual start is NOT promoted to EARLY
[ ] no new trade permission created yet
```

## P0-D EXIT

```text
[ ] EARLY study includes positive/negative/boundary cases
[ ] no lookahead
[ ] Owner approves provisional/final OP-06 semantics
[ ] implementation uses positive evidence, not residual default
[ ] weak/noise theme does not become EARLY by fallthrough
```

## P0-E EXIT

```text
[ ] no-mainline != candidate-EARLY
[ ] candidate-EARLY can be represented as probe-eligible when approved
[ ] UNKNOWN / undefined / policy-unfrozen remain distinct
[ ] ordinary RISK_OFF does not mechanically veto all W2S
[ ] FADE invalidates W2S
[ ] numeric position sizing is not canonical unless frozen
```

## P0-F EXIT

```text
[ ] OTO no longer depends on legacy trading_principle existence
[ ] OTO preserves candidate vs confirmed identity
[ ] candidate+EARLY path can reach PROBE_ELIGIBLE
[ ] OTO does not itself confirm mainline
[ ] OTO does not bypass L1 permission
[ ] unfrozen numeric rules remain visibly unfrozen
```

## P0-G EXIT

```text
[ ] one canonical W2S D1 truth producer
[ ] API and premarket consume same D1 truth
[ ] W2S requires confirmed mainline + divergence→repair + leader/core
[ ] missing weekly/prior-state evidence cannot silently pass
[ ] D2 is one canonical confirmation truth
[ ] unified alert cannot create second independent truth
```

## P0-H EXIT

```text
[ ] every legacy P-11 output mapped or explicitly retired
[ ] PDV2 is assembler, not new strategy engine
[ ] corrected new outputs shadow-compared
[ ] no unexplained diff
[ ] Owner approves consumer cutover
[ ] no production consumer depends on legacy decision authority
```

---

# 19. Parallel execution policy

Maximum parallel tasks remains 3, but parallelism is allowed only when task outputs do not define each other's semantics.

## 19.1 Safe early parallelism

After plan approval:

```text
Lane A: P0A-01 Boundary guardrails
Lane B: P0A-02 Rule authority manifest
```

P0A-03 begins after P0A-01 is stable.

During P0-B:

```text
Lane A: P0B-01/02/03 L1 fact chain — serial, one owner
Lane B: P0B-04 W2S alert fail-closed — may run separately if shared interfaces are untouched
```

## 19.2 Required serialization

The following chain must remain serial:

```text
P0C-01
→ P0C-02
→ P0D-01
→ Owner Gate
→ P0D-02
→ P0E-01
→ P0F-02
```

Do not parallelize these merely to increase throughput.

## 19.3 Later safe parallelism

After P0 core semantics stabilize:

```text
P1A metric/display
P1B boundary cleanup
P1C workbench calibration separation
```

can run in parallel if their file sets do not overlap.

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
9. independent review against exact PR HEAD;
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

## Gate O-01 — Plan approval

This document itself does not authorize implementation.

Required Owner statement:

```text
Approve Development Master Plan v0.1
and authorize P0-A implementation.
```

Only P0-A starts from that authorization.

## Gate O-02 — OP-06 EARLY policy

Occurs after P0D-01 replay study.

No Claude implementation may invent this decision.

## Gate O-03 — Any unresolved numeric policy

Examples:

- OTO turnover conflict;
- position limits;
- candidate caps if business-semantic rather than presentation;
- W2S numeric grading;
- auction grading.

If task correctness depends on the value, stop and ask Owner.

## Gate O-04 — Decision cutover

Required before P0H-03/P0H-04 changes canonical consumers/legacy authority.

## Gate O-05 — Destructive retirement

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

After Owner approves this v0.1 plan, do **not** authorize the entire program at once.

Authorize only:

```text
P0-A
= Safety & Architecture Lock
```

First implementation wave:

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

