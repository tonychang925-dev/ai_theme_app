# AI Theme App — Architecture & Strategy Drift Correction Audit R1

> **Document type:** Detailed audit / correction authority document  
> **Purpose:** Correct accumulated architecture and strategy drift without redesigning the system from scratch  
> **Status:** AUDIT COMPLETE / IMPLEMENTATION NOT STARTED  
> **Implementation owner:** Claude  
> **Owner:** Tony  
> **Date:** 2026-10-06  
> **Engineering truth:** `tonychang925-dev/ai_theme_app@ddc9442e88c5bf6f5248bfb141e74472c48eb25a`  
> **Strategy reference:** `AI_THEME_APP_CANONICAL_INVESTMENT_STRATEGY_DEVELOPMENT_MODEL_v0.6.4_APPROVED_WORKING_BASELINE.md`  
> **Strategy baseline SHA256:** `f75dd6624d43870c299607239601c80befa83ad7f963bef69fd24e5dd3591d2b`  
> **Strategy status:** OWNER APPROVED WORKING BASELINE / NOT FROZEN  
> **Implementation authorization implied by this document:** NO — this document defines what must be corrected and how to preserve intent; Owner starts implementation explicitly.  
> **Implementation agent policy:** Claude is the implementation agent for this correction program. DeepSeek is not authorized to interpret architecture, define strategy semantics, or implement correction code. Codex may be used only for independent read-only verification if the Owner explicitly requests it.

---

## 0. Executive conclusion

The current problem is **not** “old architecture bad, new architecture good”, and it is **not** a reason to design a third architecture.

The project history shows two partially correct systems:

```text
OLD CHAIN
= strategy/business semantics often closer to Tony's actual trading logic
+ heavy direct SQL / DB coupling / scripts / case-tuned thresholds
+ weak engineering boundaries

NEW CHAIN
= materially better engineering architecture
  (Gateway / Ports / Domain Pure / DTO / Snapshot / Job / Replay / Shadow / Human Review)
+ several important strategy-semantic drifts introduced during migration
+ incomplete cutover leaves old and new decision paths alive together
```

Therefore the correction target is:

```text
VALIDATED STRATEGY SEMANTICS
(from original strategy sources + v0.6.4)
        +
NEW-CHAIN ENGINEERING BOUNDARIES
(Gateway / Ports / pure Domain / Snapshot / Replay)
        +
HISTORICALLY PROVEN OLD-CHAIN BUSINESS BEHAVIOR
(only where it is supported by strategy authority)
        -
OLD-CHAIN IMPLEMENTATION DEBT
        -
NEW-CHAIN STRATEGY DRIFT
        -
PARALLEL / LEGACY TRUTH PRODUCERS
        =
CORRECTED CURRENT ARCHITECTURE
```

This is a **drift-correction program**, not a greenfield redesign.

---

## 1. Authority hierarchy for this correction

### 1.1 Strategy authority

Highest authority for trading semantics:

1. Original canonical strategy sources CS-01…CS-12.
2. Tony's approved working interpretation in v0.6.4.
3. Owner decisions explicitly approved after v0.6.4.

The following are **not** strategy authority by themselves:

- old-chain behavior;
- new-chain behavior;
- passing tests;
- historical replay success;
- Claude/Codex reports;
- DeepSeek output;
- hard-coded thresholds in code;
- temporary migration contracts.

If old-chain behavior conflicts with v0.6.4, the old behavior is evidence of historical implementation, not the rule to restore.

### 1.2 Architecture authority

For engineering boundaries and migration intent:

1. `docs/architecture/stock_processing_service-架构设计方案.md`
2. `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
3. `docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md`
4. Accepted ADRs / Architecture Decision Log / Architecture Governance.
5. Capability-specific designs such as Mainline Discovery, OneToTwo, W2S, DailyReview.

Important historical rule already present in the repository:

> 新链不得直接 SQL；Application 只编排；Domain 只做业务算法；所有数据访问经 Port / Gateway。

### 1.3 Engineering truth

Only current GitHub main at exact SHA:

```text
ddc9442e88c5bf6f5248bfb141e74472c48eb25a
```

Local feature branches, uncommitted worktrees, old reports, or historical branches are not current engineering truth.

### 1.4 Historical behavior evidence

Old `stock_service` and old scripts may be used to answer:

- what business behavior previously worked;
- which cases were historically captured;
- what semantics were lost during migration.

They may **not** be copied mechanically when they contain:

- direct SQL / DB coupling;
- case-specific tuning;
- unsupported thresholds;
- fallback/mock/default success;
- rules not traceable to canonical strategy sources.

---

## 2. Critical historical finding: the migration goal was originally correct

The repository itself records the intended migration philosophy.

### 2.1 stock_processing_service design

`docs/architecture/stock_processing_service-架构设计方案.md` states that the project should:

- build `stock_processing_service` as the new production chain;
- retain old `stock_service` only for fallback, reconciliation, experiments, and replay;
- stop extending the old chain with patches;
- require all reads/writes through `DatabaseGateway`;
- forbid Application from SQL/DB client access;
- keep Domain pure.

This means the new chain was created primarily to fix **engineering architecture debt**, not to redefine Tony's investment method.

### 2.2 old-chain replication contract

`docs/architecture/旧链逐项复刻矩阵-2026-05-07.md` explicitly says:

> 新链必须先复刻旧链生产逻辑，再谈工程化增强。

This was directionally correct, but incomplete: at that time old-chain behavior was used as the closest available business truth because the original investment strategy had not yet been normalized into v0.6.4.

The corrected 2026-10 principle is:

> **The new chain must restore old-chain business semantics only where those semantics are validated by canonical strategy sources / v0.6.4, while preserving the new chain's engineering architecture. Old-chain implementation style and unvalidated thresholds must not be replicated.**

### 2.3 Phase Contract exposed the same tension

`docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md` correctly required:

- no invented business rules;
- no fallback/mock/default business judgments;
- new chain must remain decoupled through Ports/Gateway;
- replay and traceability before cutover.

But it also elevated old-chain code behavior to algorithm authority in several places. That was understandable at the time, but v0.6.4 now supersedes that assumption for semantic authority.

---

## 3. Two-axis audit model

Every capability must be evaluated on **two independent axes**.

### Axis A — Strategy semantic correctness

Allowed verdicts:

- `CANONICAL_ALIGNED`
- `PARTIAL`
- `SEMANTIC_DRIFT`
- `UNAUTHORIZED_POLICY_FREEZE`
- `UNAUTHORIZED_INFERENCE`
- `STRATEGY_MODEL_OPEN_QUESTION`

### Axis B — Engineering architecture correctness

Allowed verdicts:

- `BOUNDARY_COMPLIANT`
- `DIRECT_DB_VIOLATION`
- `SCRIPT_COUPLING`
- `MULTI_TRUTH_PRODUCER`
- `INCOMPLETE_CUTOVER`
- `LEGACY_CONFLICT`
- `WRONG_SOURCE_OF_TRUTH`

A module can therefore be:

```text
strategy = good
architecture = bad
```

or:

```text
strategy = drifted
architecture = good
```

This distinction is mandatory for the correction program.

---

## 4. High-level lineage verdict

| Capability | Old-chain semantics | Old-chain engineering | New-chain engineering | New-chain/current semantic state | Correction direction |
|---|---|---|---|---|---|
| Event→Theme | generally sound concept | direct persistence coupling in places | stronger streaming / contracts | mostly reusable | preserve new chain |
| Mainline Identity | closer to “logic + market recognition” but score-heavy | DB/script coupled | registry/review/ports are better | identity/lifecycle coupling remains | keep new structure, correct semantics |
| Mainline Lifecycle | many useful business signals | score/state and SQL-era debt | evidence objects + Layer B are better | still score→state and old state vocabulary | keep evidence architecture, replace semantic authority |
| Global Market Environment | business awareness existed but scattered | no clean owner | componentized | multiple producers + L1/L3 mixed vocabulary | consolidate existing new modules, no greenfield engine |
| Timing Resonance | implicit in trading rules | scattered | partial permission layer | no canonical L1×L3 contract | correct existing permission path |
| Strong Stock / Role | historically useful object pool | coupled scripts and ad hoc gates | formal pool/services | some migration gates invented | restore canonical role eligibility inside new chain |
| W2S | qualitative idea often closer to source | direct SQL + case tuning | Candidate→Expectation→AuctionConfirm boundary is good | eligibility widened; missing data can pass | preserve new structure, restore qualification semantics |
| OTO | strategy source is clear | limited old engineering | Setup plan architecture is good | confirmed-mainline focus gate is late | keep setup engine, correct eligibility timing |
| Decision | often direct/implicit | tightly coupled | snapshots/PDV2 exist | old + new decision producers coexist | complete cutover after semantic parity |
| Replay/Audit | weak | weak | materially stronger | reusable | preserve |
| M8 | n/a | n/a | read-only cognition architecture is good | not primary cause of strategy drift | preserve, do not make business truth owner |



---

## 5. Detailed capability audit

## 5.1 Data access / service boundary

### Historical old-chain behavior

Old strategy modules frequently embedded SQL directly inside screening/strategy logic. A representative example is `docs/architecture/weak_to_strong_strategy_design.md`, where the W2S selector:

- queries `subject_stock_daily_snapshot` directly;
- fetches previous-day rows directly;
- performs support scans with additional SQL;
- mixes data retrieval, rule evaluation, parameter tuning, and result selection.

This made rapid case validation possible, but it created four structural defects:

1. strategy logic depended on physical table layout;
2. tests could not isolate business semantics from DB semantics;
3. replay could silently change when tables or data changed;
4. rule tuning and data extraction were inseparable.

### New-chain correction intent

The frozen `stock_processing_service` architecture correctly introduced:

```text
Application
  -> Port
  -> Gateway Adapter
  -> DatabaseGateway
```

and explicitly prohibited:

- Application SQL;
- Domain SQL;
- direct `_db/_client/pool` access;
- raw DB rows as domain contracts.

### Current main problem

R0 and source inspection show that current main still contains application-layer code reaching through implementation details such as `_pool`, `_db`, or client internals in some paths.

**Verdict**

```text
STRATEGY = N/A
ARCHITECTURE = RESTORE_ARCHITECTURE_BOUNDARY
SEVERITY = P0
```

### Correction rule

Do **not** modernize old-chain scripts one by one.  
Do **not** move SQL into another strategy service.

For any current new-chain runtime path:

```text
Application/Domain direct DB access
→ replace with existing or minimally extended Port/Gateway method
→ preserve business output
→ add contract/replay verification
```

This is engineering correction only; it must not alter trading semantics.

---

## 5.2 Theme / event pipeline

### What is historically correct

The early architecture already had a strong conceptual backbone:

```text
news_raw
→ news_event
→ structured stream
→ ThemeProcessor
→ ThemeMatchEngine
→ decision
→ DecisionExecutor
→ event/theme mapping
```

The second-stage architecture improved this with:

- hybrid recall;
- rerank;
- evidence gate;
- final judge;
- UNKNOWN / HUMAN_REVIEW as first-class outcomes.

These are not part of the current strategy drift problem and should not be redesigned.

### Current correction position

```text
KEEP_AS_DESIGNED
```

Only downstream interpretation must be protected:

```text
Event→Theme match
≠ Mainline confirmation
≠ Lifecycle state
≠ Trade permission
```

A successful event-theme mapping must never automatically imply a mainline or strategy qualification.

---

## 5.3 Mainline Identity — L2

### Correct business intent

Both historical architecture and v0.6.4 agree on the central distinction:

```text
Theme != Mainline

Mainline Identity answers:
“Is this actually a market mainline?”

Core semantic:
logic validity
×
persistent market recognition
```

The Mainline Discovery design correctly states:

> 主线确认 ≠ 主线生命周期

and:

```text
主线 = event logic + market buying/recognition
```

### Old-chain strengths

Old-chain identity logic attempted to model:

- event logic;
- continuity;
- market recognition;
- one-day-tour rejection;
- leader/core evidence.

That was directionally closer to Tony's strategy than a simple popularity score.

### Old-chain debt

However, the old implementation mixed:

- composite scores;
- hard thresholds;
- DB access;
- current-state derived data;
- replay-sensitive data;
- case-tuned gates.

Therefore **old identity formulas are historical evidence, not current strategy authority**.

### New-chain strengths

The new chain improved:

- registry as explicit object;
- machine candidate vs human review;
- fact-context builder;
- durable identity state;
- source diagnostics.

These should be preserved.

### New-chain/current drift

There are three important drifts:

1. Identity confirmation became too dependent on downstream stock/lifecycle evidence.
2. Historical migration contracts treated old score formulas as authoritative.
3. Some consumers use only `confirmed_mainline`, which indirectly turns a governance status into a universal trade gate.

### Corrected semantic rule

```text
CANDIDATE_MAINLINE
= logic is plausible + market recognition is emerging

CONFIRMED_MAINLINE
= logic is valid + persistent recognition has been established

Leader/board evidence
= evidence for market recognition
!= mandatory identity definition by itself
```

Specific numeric thresholds remain policy/empirical unless already Owner-frozen.

**Verdict**

```text
NEW STRUCTURE = KEEP
SEMANTICS = CORRECT_SEMANTIC_DRIFT
OLD SCORE FORMULA = REFERENCE / NOT CANONICAL
SEVERITY = P0
```

---

## 5.4 Mainline Lifecycle — L3

### Historical intent

The original strategy sources and v0.6.4 define lifecycle as a state graph with source-supported paths including:

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

Key principle:

```text
Lifecycle
= state + prior state + transition evidence

NOT:
single weighted score → state
```

### Old-chain strengths

Old-chain lifecycle had useful evidence dimensions:

- leader survival;
- relay ecology;
- breadth;
- event continuity;
- support/breakdown;
- divergence/repair evidence.

It also correctly distinguished “temporary weakness/divergence” from “mainline death” in several iterations.

### Old-chain debt

The old logic eventually codified weighted formulas and thresholds such as 60/65/75 and a fixed priority classifier. That created a score→state shortcut.

### New-chain strengths

New chain preserved useful:

- `theme_cycle_evidence_daily`;
- Layer B fact context;
- lifecycle judgement storage;
- replayable evidence;
- diagnostics.

These should stay.

### New-chain/current drift

`SubjectCycleJudgementService` still computes weighted scores and directly emits states using hard thresholds. Current source at main contains thresholds such as:

```text
FADE_CONFIRMED 60
DIVERGENCE 60
REPAIR 65
ACCELERATION 75
FERMENTATION 60
```

and a priority cascade.

This is a semantic mismatch with v0.6.4.

There is also a historical parallel `MarketEmotionEngine / CycleFSM` vocabulary that uses lifecycle words at the broad-market scope.

### Correction rule

Do not discard evidence builders.

Correct only authority:

```text
Evidence builders
→ KEEP

Weighted lifecycle scores
→ diagnostics / research features only unless Owner later freezes them

Canonical lifecycle transition
→ previous lifecycle state
 + required transition evidence
 + source-supported edge
```

No unsupported transition may be silently inserted.

**Verdict**

```text
EVIDENCE ARCHITECTURE = KEEP
STATE AUTHORITY = CORRECT
SCORE→STATE = REMOVE FROM CANONICAL DECISION AUTHORITY
SEVERITY = P0
```

---

## 5.5 Global Market Environment — L1

### Correct semantic scope

v0.6.4 separates:

```text
L1 Global Market Environment
from
L3 Mainline Lifecycle
```

L1 answers:

> Is the overall market / short-term ecosystem protecting or punishing risk-taking?

It must not reuse theme-lifecycle words as if broad market and theme cycle were the same object.

### New-chain engineering gain

The new chain already has useful decomposition:

- broad market;
- short-term sentiment;
- mainline environment;
- trading permission;
- market regime orchestration.

This decomposition is worth preserving.

### Current drift

Current main still contains multiple L1-like producers and mixed vocabularies. `MarketEmotionEngine` maps a broad-market score into:

```text
CLIMAX
ACCELERATION
FERMENTATION
REPAIR
DIVERGENCE
FADE
ICE_POINT
CHAOS
```

This is exactly the scope collision v0.6.4 was created to remove.

### Data-quality problem

`market_metrics/service.py` currently contains formal calculations where some inputs are estimated:

- `chain_red` inferred from relay feedback;
- `yest_red` fixed at `0.5`;
- breadth-based fallback when relay data is missing;
- active capital calibration factor around `2.04`.

These may be useful for research diagnostics, but they must not silently become formal trade permission facts.

### Correction rule

Do not create a brand-new MarketEnvironment engine.

Instead:

1. identify which existing new-chain component is intended to be the canonical L1 producer;
2. normalize its state vocabulary to L1-only environmental states;
3. demote legacy/mixed producers to diagnostic/shadow;
4. prohibit estimated/missing values from formal permission unless explicitly labeled and Owner-authorized.

**Verdict**

```text
ENGINEERING STRUCTURE = MOSTLY KEEP
TRUTH OWNERSHIP = CONSOLIDATE
VOCABULARY = CORRECT
ESTIMATES IN FORMAL GATE = REMOVE / BLOCK
SEVERITY = P0
```

---

## 5.6 Timing Resonance / Trading Permission — L4

### Strategy requirement

Timing is not a scalar score and not an optional filter.

```text
Timing Resonance
= f(Global Market Environment, Mainline Lifecycle)
```

It determines which strategy families are eligible now.

### Historical architecture

Mainline Discovery design already had:

```text
Lifecycle
→ MarketRegime
→ TradingPrinciple
→ Leader/Core
→ Setup
```

So the concept was already present. The problem is not absence of all prior architecture; it is that the semantics never converged to the canonical Market×Lifecycle contract.

### Current drift

Current permission engines tend to:

- combine counts/flags into modes;
- use hard-coded position limits;
- fail open or use defaults in some paths;
- depend on confirmed-mainline counts in ways that block EARLY discovery;
- fail to distinguish `WAIT`, `BLOCKED_UNDEFINED`, and `BLOCKED_POLICY_UNFROZEN`.

### Correction rule

Do not invent a new “ResonanceEngine” unless existing architecture cannot express the contract.

First try to correct the existing:

```text
MarketRegime
+ MainlineEnvironment
+ TradingPermission
```

path so that it explicitly consumes:

```text
L1 state
L3 state
strategy family
policy status
data-quality status
```

and emits eligibility/permission, not a fabricated confidence score.

**Verdict**

```text
ARCHITECTURAL INTENT = EXISTING
CANONICAL CONTRACT = PARTIAL/MISSING
CORRECTION = RESTORE / COMPLETE EXISTING INTENT
SEVERITY = P0
```



---

## 5.7 Strong Stock / Role — L5

### Correct semantic role

Strong-stock detection is upstream evidence for role assignment and strategy eligibility.

It should answer:

```text
Who is strong?
Who is leader / second leader / core / front-row / catch-up / arbitrage?
```

It must not independently authorize a trade.

### Old-chain strengths

The old chain had useful operational behavior:

- rolling strong-watch pool;
- persistence across multiple days;
- differentiation between formal and observe-only;
- strong-history evidence;
- support / structure evidence;
- explicit removal / weakening behavior.

These concepts are worth preserving.

### Old-chain debt

The old implementation mixed:

- DB reads;
- watch-pool maintenance;
- candidate scoring;
- historical heuristics;
- case-tuned gates.

### New-chain strengths

The new chain introduced:

- explicit Layer C object pool;
- admission / refresh / prune boundaries;
- historical replay;
- standardized DTOs;
- source diagnostics.

### New-chain/current semantic drift

Historical migration added new gates and categories that were not clearly grounded in strategy authority.

The Phase Contract itself lists examples that had to be removed or challenged:

- `B_KEEP`;
- `formal_sa_gate_mode`;
- `admission_soft_reject_observe_only`;
- `hard_reject_any`;
- `weekly_midterm_gate`;
- other override / bypass semantics.

Current W2S code still contains at least one concrete fail-open behavior:

```text
weekly_data_sufficient = false
→ weekly_data_insufficient_bypass
→ passed = true
```

That is not acceptable for formal strategy qualification.

### Special issue: “independent two-board leader” path

Historical third-stage design allowed two consecutive limit-ups to enter Layer C without Layer A/B mainline confirmation.

This must now be split semantically:

```text
two-board fact
= valid strong-stock / role evidence

two-board fact
≠ automatic mainline confirmation
≠ automatic strategy permission
≠ automatic bypass of L1/L2/L3 for trading
```

It may remain an observation/watch-pool path if useful, but it may not become a trading authorization shortcut unless v0.6.4 / Owner policy explicitly permits it.

**Verdict**

```text
POOL ARCHITECTURE = KEEP
ROLLING/HISTORY SEMANTICS = KEEP
UNSUPPORTED GATES = REMOVE OR DEMOTE
INDEPENDENT-LEADER TRADE BYPASS = LEGACY_SEMANTIC_CONFLICT
SEVERITY = P1/P0 depending downstream use
```

---

## 5.8 Weak-to-Strong — L7/L8/L9

### Correct strategy semantics

Canonical W2S requires approximately:

```text
market not in extreme/systemic retreat
× confirmed mainline
× lifecycle DIVERGENCE → REPAIR
× LEADER / CORE
× structure survives
× re-consensus confirmation
```

The exact numeric thresholds remain policy/empirical unless Owner-frozen.

### Old-chain strengths

Old W2S captured several important qualitative ideas:

- prior strength matters;
- “one-day wonder” should not count as real strength;
- current weakness must be real;
- support / structure matters;
- candidate count should stay selective;
- Stage1 candidate and Stage2 auction confirmation are distinct.

These are useful historical semantics.

### Old-chain debt

The old W2S design mixed code and strategy validation directly:

- direct SQL;
- fixed `pct_chg` thresholds;
- fixed support strengths;
- manual gap scans;
- threshold changes driven by individual case success.

For example, the design documents parameter changes specifically to make target historical cases pass. Those numeric values are **not** automatically canonical.

### New-chain strengths

The following structure is worth keeping:

```text
D1 Candidate
→ stored candidate/evidence
→ expected auction/open behavior
→ D2 Auction Confirmation
→ result / rejection reason
```

This is a clear improvement over the old implementation style.

### New-chain/current drift

Current candidate logic allows a “strong background” through broad OR conditions such as:

- leader;
- limit-up;
- recent limit-up count;
- top rank.

This is wider than canonical W2S eligibility.

Additional drift:

- unknown prior lifecycle can soft-pass;
- insufficient weekly data can pass;
- several hard-coded weak/strong scoring thresholds are production rules;
- auction confirmation has fixed grades/thresholds not fully Owner-frozen.

### Correction rule

Preserve the two-stage structure. Correct eligibility before tuning scores.

Required logical ordering:

```text
1. L2/L3 qualification
2. L5 role qualification
3. structure/support validity
4. D1 W2S setup qualification
5. explicit expectation
6. D2 auction/open confirmation
7. decision
```

Missing/unknown evidence must not be converted to `passed=true`.

Numeric rules not frozen by Owner must be tagged as:

```text
EMPIRICAL_CANDIDATE
or
POLICY_UNFROZEN
```

and must not silently serve as canonical hard gates.

**Verdict**

```text
ARCHITECTURE = KEEP
ELIGIBILITY = CORRECT
FAIL-OPEN = REMOVE
UNFROZEN NUMERIC AUTHORITY = QUARANTINE
SEVERITY = P0
```

---

## 5.9 One-to-Two — L7/L8/L9

### What the new architecture got right

The OneToTwo design is one of the cleaner new-chain modules.

It correctly states:

- OTO is not a buy signal;
- post-market output is a next-day observation plan;
- it must not read Layer C/D1 as its primary candidate source;
- it has separate fact, candidate, gate, score, plan, and execution-confirmation stages;
- empty output is valid;
- no fallback/mock/default candidate generation.

These boundaries should be preserved.

### Main semantic drift

The design already corrected an earlier mistake:

```text
wrong:
from confirmed_mainline select stocks

better:
build from first-board facts related to mainline/strong-hotspot context
```

But it still says formal `focus` requires `confirmed_mainline`.

That is inconsistent with v0.6.4 because OTO is allowed to participate in the **mainline discovery window**:

```text
MAINLINE_CANDIDATE
+ EARLY
+ market permits
+ authentic/core first-board candidate
+ next-day confirmation
→ OTO_PROBE
```

### Correct correction

Do not rewrite OneToTwo.

Preserve:

- `PostMarketSetupFactContextBuilder`;
- `OneToTwoRuleEngine`;
- `OneToTwoTechnicalGate`;
- `OneToTwoScorer`;
- `OneToTwoSetupPlanEngine`;
- pre-market/intraday confirmation boundary.

Correct only the mainline/lifecycle permission semantics.

Expected separation:

```text
EARLY_PROBE
= upper-level entry policy

OTO
= specific first-board → next-day second-board setup

EARLY_PROBE != OTO
but
OTO can be eligible inside EARLY
```

Also note that thresholds such as final score 80, technical 55, or turnover gates are not automatically canonical because policy is not frozen.

**Verdict**

```text
ARCHITECTURE = KEEP
MAINLINE GATING = CORRECT
NUMERIC GATES = POLICY_UNFROZEN unless sourced/frozen
SEVERITY = P0/P1
```

---

## 5.10 Expectation — L8

### Historical state

Expectation exists in fragments:

- OTO next-day plan;
- W2S auction expectations;
- M8 Hypothesis / expected observations / falsifiers.

Therefore “L8 completely missing” is too strong.

### Actual problem

There is no single canonical contract connecting:

```text
Setup
→ what should happen next if thesis is correct
→ what would falsify it
→ Confirmation
→ Decision
→ Outcome
```

The current fragments are setup-specific and do not share a stable decision lineage.

### Correction rule

Do not add a large new prediction subsystem.

First define the minimum common expectation contract from existing capabilities:

```text
setup_id
strategy_family
as_of
expected_observations
falsifiers
confirmation_window
source_evidence_refs
policy_version
```

Then adapt existing OTO/W2S expectation producers into it.

M8 may consume this contract for validation, but M8 must not become the business-rule truth owner.

**Verdict**

```text
CAPABILITY = PARTIAL
CANONICAL CONTRACT = MISSING
CORRECTION = NORMALIZE EXISTING CAPABILITIES
SEVERITY = P1
```

---

## 5.11 Confirmation — L9

### Correct semantic role

Auction/open/intraday evidence is confirmation, not an independent strategy scorer that creates candidates from scratch.

### Current strengths

The project already has:

- auction snapshot data;
- auction confirmation services;
- W2S confirmation result objects;
- OTO future confirmation boundary.

These are reusable.

### Drift

Historical/new-chain implementations sometimes assign independent score grades to auction evidence and permit proxy data or fixed grade thresholds to carry too much authority.

Correction rules:

1. Candidate must exist before confirmation.
2. Confirmation may validate or invalidate a candidate.
3. Missing auction evidence cannot be translated into synthetic confirmation.
4. Proxy/estimated data must be explicitly non-canonical unless Owner authorizes.
5. Confirmation thresholds that are not frozen remain policy/empirical.

**Verdict**

```text
STRUCTURE = KEEP
AUTHORITY = TIGHTEN
SEVERITY = P1
```

---

## 5.12 Decision / Position / Risk — L10/L11

### Current problem

The repository still has multiple decision producers:

- new lifecycle/regime/PDV2 path;
- old `PostMarketDecisionEngine` path;
- local theme/leader/watchlist/trading-principle decisions;
- setup-specific decisions.

This produces parallel semantics.

### Major legacy semantic error

The old `ThemeDecisionEngine` treats:

```text
35% mainline
30% market
20% leader
15% setup
```

as a weighted scoring formula.

v0.6.4 explicitly treats these as priority/hierarchy semantics, not a flat additive score.

Therefore this old decision logic must not remain canonical.

### Position policy problem

Current code includes hard-coded position limits and suggested position values.

Because multiple position/risk OP items remain unfrozen, these values must be classified as:

```text
UNAUTHORIZED_POLICY_FREEZE
```

unless each value can be traced to source-explicit or Owner-frozen policy.

### Correction rule

Do not create a new decision universe while old and new paths coexist.

First:

1. identify one intended new-chain decision path;
2. make it consume corrected L1-L9 semantics;
3. shadow it against current outputs;
4. cut consumers over;
5. only then retire old decision producers.

Canonical action vocabulary should remain strategy-level:

```text
WAIT
PROBE
ENTER
ADD
HOLD
REDUCE
EXIT
```

with separate non-trading system statuses:

```text
BLOCKED_UNDEFINED
BLOCKED_POLICY_UNFROZEN
BLOCKED_DATA_QUALITY
```

**Verdict**

```text
CURRENT = INCOMPLETE_CUTOVER + LEGACY_CONFLICT
POSITION NUMBERS = POLICY_UNFROZEN
SEVERITY = P0
```

---

## 5.13 Review / Learning / M8 — L12

### What should be preserved

M8 architecture correctly states:

```text
M8 does not rewrite Layer A/B/C/D
M8 does not own business truth
M8 is read-only cognition orchestration
```

This is a good boundary.

The Overall Architecture also correctly requires:

- immutable evidence/snapshots;
- replayability;
- evidence refs;
- hypothesis source freeze;
- reviewer verdict;
- validation data;
- delayed learning until ground truth exists.

### Actual current gap

The system has strong infrastructure for replay/validation, but the full trade lineage is incomplete:

```text
Decision
→ execution intent
→ fill/tradability
→ outcome
→ expectation delta
→ reason attribution
→ strategy learning
```

### Correction rule

Do not use M8 to repair lower-layer strategy semantics.

First fix L1-L11 truth. Then M8 consumes corrected outputs.

M8 itself should remain mostly untouched unless an adapter or source contract needs correction.

**Verdict**

```text
M8 CORE = KEEP
END-TO-END TRADE LEARNING LOOP = PARTIAL
SEVERITY = P1/P2
```

---

## 6. Current-main runtime conflict

At `main@ddc9442`, `BuildPostMarketRecapJob` still orchestrates both newer and older semantic paths.

Observed structure includes:

```text
Mainline Discovery
→ Mainline Lifecycle
→ MarketRegime
→ ActiveMainlineUniverse
→ PostMarketDecisionV2

AND ALSO

legacy PostMarketDecisionEngine
→ MarketEnvironmentEngine
→ ThemeDecisionEngine
→ LeaderCoreEngine
→ NextDayWatchlistEngine
→ TradingPrincipleEngine
```

Both sets of results can enter recap/report structures.

This is the central runtime architecture drift.

**Classification**

```text
INCOMPLETE_CUTOVER
LEGACY_CONFLICT
MULTI_TRUTH_PRODUCER
P0
```

### Important correction principle

Do **not** retire the old path first.

The old path still contains historically useful semantics.

Correct sequence:

```text
1. recover valid semantics
2. implement them inside the new-chain boundary
3. replay/shadow
4. prove parity against strategy authority
5. cut consumers over
6. retire old path
```

Retiring old code before semantic recovery risks deleting the only working implementation of some business behavior.

---

## 7. What must explicitly NOT be copied from the old chain

The correction program must not confuse “recover old semantic intent” with “restore old implementation”.

The following are **not** to be copied as canonical behavior:

1. direct SQL in strategy/domain code;
2. database table names as domain contracts;
3. environment-dependent local file truth;
4. one-off scripts as production orchestration;
5. fixed thresholds tuned to individual historical examples;
6. silent fallback to another table/source;
7. `missing → 0`;
8. `missing → passed=True`;
9. hard-coded candidate limits treated as strategy semantics;
10. old score formulas treated as source truth;
11. old behavior that contradicts v0.6.4;
12. replay that writes back into current production truth.

---

## 8. What must explicitly NOT be discarded from the new chain

The following should be treated as valuable engineering assets:

1. `stock_processing_service` layer separation;
2. Ports and Gateway adapters;
3. DTO / contracts;
4. immutable/read-model snapshots;
5. source_trace / diagnostics;
6. idempotent Jobs;
7. human-review boundary for mainline confirmation;
8. MainlineDiscovery fact-context architecture;
9. lifecycle evidence objects;
10. rolling strong-watch object model;
11. W2S Candidate → Confirmation separation;
12. OTO Setup Plan ≠ Buy Signal separation;
13. deterministic recap materializer;
14. replay / shadow / validation infrastructure;
15. M8 read-only cognition and ground-truth validation;
16. DailyReview structured contracts.

The goal is to correct what these components mean, not to throw them away.



---

## 9. Correction doctrine

The implementation program must follow these rules.

### C-01 No redesign

Do not create a new architecture to replace both chains.

The target is:

```text
correct existing design intent
+ finish incomplete migration
+ restore strategy semantics
```

### C-02 Strategy beats implementation history

If:

```text
old-chain behavior
!=
v0.6.4 strategy semantics
```

then the old behavior is not restored as canonical.

### C-03 Engineering boundary beats convenience

If a correction can only be made by reintroducing direct SQL or DB-client access into Application/Domain, the correction is invalid.

### C-04 No hidden policy creation

Any threshold, weight, position size, lookback, rank cutoff, candidate cap, score band, or fallback not source-explicit / Owner-frozen must be labeled:

```text
POLICY_UNFROZEN
or
EMPIRICAL_CANDIDATE
```

It must not silently become a production hard gate.

### C-05 Missing data is not negative evidence and not positive evidence

Prohibited:

```text
missing → 0
missing → false business conclusion
missing → true business conclusion
missing → passed
missing → estimated and then formal trade permission
```

Allowed:

```text
UNKNOWN
BLOCKED_DATA_QUALITY
diagnostic estimate not used for formal decision
```

### C-06 Correct semantic owner, not duplicate owner

Do not add a new Engine simply because current semantics are wrong.

First correct the existing intended owner. A new top-level owner requires proof that the existing architecture cannot express the required capability.

### C-07 Shadow before cutover

Any replacement of an existing production decision path must:

1. run in shadow;
2. replay known cases;
3. compare decision lineage;
4. prove no uncontrolled semantic drift;
5. receive Owner approval before consumer cutover.

### C-08 Old chain is a behavioral oracle only when validated

Use old chain for regression comparison, but classify every recovered behavior:

```text
SOURCE_SUPPORTED
OWNER_APPROVED
EMPIRICAL_ONLY
LEGACY_ONLY
CONFLICTS_WITH_v0.6.4
```

Only the first two may become canonical production semantics.

### C-09 M8 remains downstream

M8 may consume corrected domain outputs and validate predictions. M8 must not become the place where L1-L7 business rules are redefined.

### C-10 GitHub main is engineering truth

Every implementation task must pin:

```text
repo
exact base SHA
authorized files
semantic source
expected replay
rollback
```

---

## 10. Correction program — implementation sequence for Claude

This section is an implementation plan, not a redesign proposal.

## Phase A — Authority and safety lock

### Goal

Prevent further semantic drift while preserving runtime behavior.

### Tasks

1. Add/strengthen architecture contract tests that reject:
   - Domain/Application direct SQL;
   - direct `_db/_client/pool` access where forbidden;
   - unsupported fallback/mock/default business judgments.
2. Create a rule-authority mapping for current executable gates:
   - source-supported;
   - Owner-frozen;
   - empirical;
   - unfrozen;
   - legacy-only.
3. Mark current formal decisions that depend on estimated/missing data.
4. Do not yet remove old decision paths.

### Acceptance

- no new business rule without source/Owner authority;
- missing data cannot silently produce formal PASS;
- no new direct-DB violations;
- existing behavior is captured before semantic correction begins.

---

## Phase B — L1 / L2 / L3 semantic recovery inside existing new-chain structure

### B1 Global Market Environment

Correct existing L1 producers; do not create another top-level engine.

Required outcomes:

- one canonical L1 vocabulary;
- broad market states no longer use theme-lifecycle names;
- estimated inputs are diagnostic unless explicitly authorized;
- ICE_POINT source semantics map to global risk/permission without colliding with theme-cycle state.

### B2 Mainline Identity

Preserve:

- discovery fact builder;
- machine candidate;
- human review;
- registry.

Correct:

- confirmation semantics;
- downstream overuse of `confirmed_mainline`;
- any lifecycle evidence that is treated as identity definition.

### B3 Mainline Lifecycle

Preserve:

- evidence builders;
- historical storage;
- diagnostics.

Correct:

- score→state canonical authority;
- unsupported state transitions;
- broad-market vocabulary in theme state;
- lifecycle/identity coupling.

### Acceptance

For each L1-L3 output, Claude must provide:

```text
input facts
data-quality status
semantic authority
previous state (where applicable)
transition evidence
output
source trace
```

No current-main consumer cutover yet unless explicitly authorized.

---

## Phase C — Restore L4/L5 strategy eligibility without redesign

### C1 Timing permission

Use existing MarketRegime/MainlineEnvironment/TradingPermission structures where possible.

Output must distinguish:

```text
ELIGIBLE
WAIT
BLOCKED_UNDEFINED
BLOCKED_POLICY_UNFROZEN
BLOCKED_DATA_QUALITY
```

### C2 Strong stock / role

Preserve rolling pool and role evidence.

Correct:

- unsupported admission gates;
- bypasses that convert strong-stock evidence into trade authority;
- missing-data pass behavior.

Two-board/independent-leader evidence may remain observable, but it must not bypass strategy eligibility unless separately authorized.

### Acceptance

No Layer C object alone may confirm mainline, lifecycle, or trade permission.

---

## Phase D — Correct OTO and W2S in place

### D1 OTO

Do not rewrite the setup engine.

Correct:

- confirmed-mainline-only focus gate;
- lifecycle eligibility window;
- distinction between EARLY_PROBE and OTO;
- numeric rules whose authority is unfrozen.

Required scenarios:

```text
CANDIDATE_MAINLINE + EARLY + market permits
→ OTO can be PROBE-eligible

CONFIRMED_MAINLINE + FERMENTATION
→ normal OTO participation may be eligible

FADE / blocked market
→ no OTO entry
```

Actual trigger still requires setup/confirmation.

### D2 W2S

Do not rewrite Candidate→Auction Confirmation architecture.

Correct:

- candidate eligibility;
- leader/core requirement;
- divergence→repair requirement;
- fail-open missing evidence;
- broad OR strong-background shortcuts;
- unsupported numeric authority.

Required distinction:

```text
PASSIVE_DIVERGENCE_ENTRY
!=
W2S
```

### Acceptance

Each candidate must expose an auditable path:

```text
L1 permission
L2 identity
L3 lifecycle/transition
L5 role
L7 setup
L8 expectation
L9 confirmation
```

No missing evidence may be replaced by a positive business conclusion.

---

## Phase E — Decision-path convergence

Only after Phases B-D pass shadow/replay.

### Goal

Complete the migration that current main started but never finished.

### Actions

1. identify which outputs of legacy `PostMarketDecisionEngine` remain genuinely required;
2. map each required output to corrected new-chain source;
3. run dual output comparison;
4. migrate consumers;
5. retire old semantic producers one at a time.

### Explicitly do not do

Do not delete the old path before recovering valid semantics.

Do not leave both old and new outputs as long-term equal authorities.

### Acceptance

For every displayed/actionable decision:

```text
one canonical producer
one source lineage
one policy version
one data-quality status
```

No report should contain conflicting old/new decisions without explicit diagnostic labeling.

---

## Phase F — Expectation / outcome lineage and M8 consumption

After canonical decision path is stable:

1. normalize existing OTO/W2S expectation objects;
2. connect expectation → confirmation → decision → outcome;
3. expose corrected decision/evidence lineage to M8;
4. use M8 validation/replay without letting M8 overwrite business truth.

This phase is not permitted to redefine trading strategy.

---

## 11. Priority defect register

| ID | Severity | Type | Current area | Required correction |
|---|---|---|---|---|
| DR-001 | P0 | INCOMPLETE_CUTOVER | BuildPostMarketRecapJob | converge old/new decision paths after parity |
| DR-002 | P0 | WRONG_SCOPE | MarketEmotion/Cycle vocabulary | separate L1 from L3 |
| DR-003 | P0 | SEMANTIC_DRIFT | SubjectCycleJudgementService | remove score→state canonical authority |
| DR-004 | P0 | UNAUTHORIZED_INFERENCE | Market metrics / W2S | missing/estimated data must not formally pass |
| DR-005 | P0 | SEMANTIC_DRIFT | OTO | remove confirmed-mainline-only discovery blockage |
| DR-006 | P0 | SEMANTIC_DRIFT | W2S | restore mainline×lifecycle×role eligibility |
| DR-007 | P0 | LEGACY_CONFLICT | ThemeDecisionEngine | 35/30/20/15 must not be additive score authority |
| DR-008 | P0 | DIRECT_DB_VIOLATION | SPS application paths | restore Port/Gateway boundary |
| DR-009 | P1 | UNAUTHORIZED_POLICY_FREEZE | position/score thresholds | quarantine unfrozen policy |
| DR-010 | P1 | MULTI_TRUTH_PRODUCER | market/decision producers | establish one canonical owner per capability |
| DR-011 | P1 | PARTIAL | L8 expectation | normalize existing setup expectations |
| DR-012 | P1 | PARTIAL | L12 learning | close decision→outcome lineage after lower layers stabilize |
| DR-013 | P1 | LEGACY_SEMANTIC_CONFLICT | independent two-board bypass | observation evidence only unless Owner authorizes trade bypass |
| DR-014 | P2 | TRACEABILITY | rules/thresholds | attach source/policy IDs to executable decisions |

---

## 12. Concrete source-code evidence to re-check during implementation

All paths below are against:

```text
main@ddc9442e88c5bf6f5248bfb141e74472c48eb25a
```

### Market / lifecycle

- `stock_processing_service/application/services/market_cognition/emotion_engine.py`
  - broad-market score emits lifecycle-like labels.
- `config/market_cognition/cycle_fsm_v1.yaml`
  - historical mixed market/theme state vocabulary.
- `stock_processing_service/domain/services/subject_cycle_judgement_service.py`
  - weighted lifecycle scores and hard state thresholds.
- `stock_processing_service/application/services/mainline_lifecycle/mainline_lifecycle_fact_context_builder.py`
  - confirmed-mainline input scope.
- `stock_processing_service/domain/services/mainline_lifecycle/layer_b_lifecycle_adapter.py`
  - conservative missing judgement handling; reusable.

### Market facts

- `stock_processing_service/application/services/market_metrics/service.py`
  - estimated `chain_red`;
  - fixed/estimated `yest_red`;
  - breadth fallback;
  - calibrated active-capital multiplier.

### Permission / decision

- `stock_processing_service/domain/services/market_regime/*`
- `stock_processing_service/domain/services/post_market_decision/*`
- `stock_processing_service/domain/services/post_market_decision_v2/post_market_decision_engine_v2.py`
- `stock_processing_service/application/jobs/build_post_market_recap_job.py`

### OTO

- `stock_processing_service/application/services/post_market_setup_fact_context_builder.py`
- `stock_processing_service/domain/services/one_to_two_rule_engine.py`
- `stock_processing_service/domain/services/one_to_two_rule_config.py`
- `stock_processing_service/domain/services/one_to_two_scorer.py`
- `stock_processing_service/application/services/one_to_two_setup_plan_engine.py`

### W2S

- `stock_processing_service/domain/services/w2s_candidate_service.py`
- `stock_processing_service/domain/services/w2s_auction_scorer.py`
- `stock_processing_service/domain/services/w2s_confirm_service.py`
- `stock_processing_service/domain/services/auction_confirmation_service.py`
- `stock_processing_service/application/use_cases/build_weak_to_strong_candidate.py`

### Architecture boundary

Search all `stock_processing_service/application` and `domain` for:

```text
SELECT
INSERT
UPDATE
DELETE
asyncpg
._db
._client
._pool
execute_query
```

Classify each occurrence; do not blindly replace diagnostics/test code.



---

## 13. Architecture documents Claude must read before implementation

Mandatory:

1. `docs/strategy_model/AI_THEME_APP_CANONICAL_INVESTMENT_STRATEGY_DEVELOPMENT_MODEL_v0.6.4_APPROVED_WORKING_BASELINE.md`
2. `docs/architecture/stock_processing_service-架构设计方案.md`
3. `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
4. `docs/architecture/旧链逐项复刻矩阵-2026-05-07.md`
5. `docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md`
6. `docs/architecture/mainline_discovery_architecture_design.md`
7. `docs/architecture/one_to_two_daily_review_architecture.md`
8. `docs/architecture/weak_to_strong_strategy_design.md`
9. `docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md`
10. `docs/architecture/M8_Market_Cognition_Engine_架构设计文档.md`
11. `docs/architecture/Architecture_Decision_Log.md`
12. `docs/architecture/Architecture_Governance_v1.0.md`
13. `docs/architecture/新链服务化切换审计与任务清单.md`
14. `docs/architecture/盘后复盘模块彻底重构设计文档.md`
15. `docs/architecture/采集复盘模块拆分设计文档.md`

Historical strategy implementations may be inspected only as behavior evidence.

---

## 14. Claude implementation contract

### 14.1 Role

```text
IMPLEMENTATION_OWNER = CLAUDE
```

Claude must act as a correction engineer, not a strategy inventor and not a greenfield architect.

### 14.2 Mandatory task preamble for every implementation batch

Each batch must state:

```text
TASK_ID
REPO
EXACT_BASE_SHA
STRATEGY_BASELINE
ARCHITECTURE_DOCS
AUTHORIZED_PATHS
SEMANTIC_CHANGE
NON_GOALS
REPLAY_CASES
TESTS
ROLLBACK
```

### 14.3 Hard prohibitions

Claude must not:

- redesign the entire architecture;
- create a third parallel decision chain;
- change strategy semantics to fit current code;
- copy old-chain SQL into new-chain modules;
- use old-chain thresholds as authority without classification;
- introduce fallback/mock/synthetic success;
- convert missing evidence into pass/fail business claims;
- modify v0.6.4 without Owner instruction;
- use DeepSeek to decide architecture or implementation semantics;
- merge implementation based only on tests passing.

### 14.4 Required behavior on ambiguity

If any correction requires a strategy decision not defined by v0.6.4:

```text
STOP
→ classify STRATEGY_MODEL_OPEN_QUESTION or POLICY_UNFROZEN
→ report to Tony
→ do not invent rule
```

If architecture documents conflict:

```text
STOP
→ identify exact documents / dates / decision IDs
→ determine supersession from ADR/Decision Log
→ if still ambiguous, ask Owner
```

### 14.5 Evidence required in every completion report

For each changed semantic behavior:

```text
before path + symbol
after path + symbol
strategy authority
architecture authority
test evidence
replay evidence
consumer impact
legacy impact
exact HEAD SHA
```

---

## 15. Replay and validation policy

Historical cases remain useful, but the purpose changes.

Previously, too much development followed this pattern:

```text
make 神剑 / 联德 pass
→ tune rule
```

The corrected policy is:

```text
strategy rule established independently
→ replay 神剑 / 联德 / 维科 + negative cases
→ observe whether behavior is consistent
→ never tune solely to one named case
```

Required test composition:

1. positive examples;
2. negative examples;
3. boundary examples;
4. missing-data examples;
5. conflicting-evidence examples;
6. cross-day state-transition examples.

A rule is not accepted merely because named historical winners pass.

---

## 16. Cutover policy

Old-chain retirement is the last step for each capability.

For capability X:

```text
recover semantic intent
→ implement in new-chain boundary
→ unit contract
→ replay
→ shadow
→ compare current consumers
→ Owner/QA acceptance
→ cut consumer
→ retire old producer
```

No big-bang cutover.

No “delete old code then discover what was lost.”

---

## 17. What “done” means

This correction program is not complete when tests are green.

It is complete when all three dimensions below are true.

### 17.1 Strategy

- L1 and L3 are unambiguously separate;
- L2 identity and L3 lifecycle are unambiguously separate;
- OTO can participate in the approved EARLY discovery window;
- W2S requires the approved mainline/lifecycle/role structure;
- missing/estimated data cannot manufacture formal eligibility;
- unfrozen policies are visibly unfrozen;
- 35/30/20/15 is never treated as a flat additive trading score.

### 17.2 Architecture

- new-chain Application/Domain boundaries are restored;
- no canonical domain producer directly depends on DB implementation details;
- one canonical producer exists per decision capability;
- old and new decision paths no longer both act as equal authorities;
- replay and snapshots remain reproducible;
- M8 remains downstream cognition, not business truth.

### 17.3 Governance

- every executable policy is traceable;
- each semantic correction points to v0.6.4 or Owner decision;
- each engineering correction points to an existing architecture boundary/ADR;
- no new architecture is introduced without proof of an actual gap;
- every cutover has shadow/replay evidence.

---

## 18. Recommended first implementation batch for Claude

Do **not** start with a broad rewrite.

The safest first batch is a narrow **Authority & Safety Lock**.

Suggested task identity:

```text
TASK_ID
= AI_THEME_APP_DRIFT_CORRECTION_P0A_AUTHORITY_AND_FAIL_CLOSED_LOCK

PURPOSE
= Stop further semantic drift before correcting business behavior

BASE
= current GitHub main exact SHA at task start

SCOPE
= contract/tests + minimal fail-closed corrections only

NO
= strategy redesign
= lifecycle rewrite
= OTO/W2S behavior rewrite
= consumer cutover
= old-chain removal
```

Expected deliverables:

1. inventory of executable thresholds/gates with authority classification;
2. contract tests preventing new direct-DB access in SPS Application/Domain;
3. contract tests preventing `missing → pass` business logic;
4. explicit diagnostics for estimated facts entering formal gates;
5. exact list of old/new parallel decision producers;
6. zero production semantic cutover.

Only after P0A is reviewed should Claude receive P0B/P1 semantic-correction tasks.

---

## 19. Final Owner-facing conclusion

The project does **not** need a rewrite.

The historical evidence supports this diagnosis:

```text
Old chain:
business logic often useful
engineering boundaries weak

New chain:
engineering boundaries substantially better
business semantics partially drifted

Current main:
migration incomplete
old + new truths coexist
```

Therefore the correct path is:

```text
recover
→ classify
→ correct in place
→ replay
→ shadow
→ cut over
→ retire legacy
```

not:

```text
redesign
→ rebuild
→ replace everything
```

The primary correction objective is:

> **Move validated investment semantics into the already-better new-chain engineering structure, while eliminating both old implementation debt and new semantic drift.**

---

## Appendix A — Historical evidence index

- `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`  
  Early event→theme architecture and database_service as shared data access concept.

- `docs/architecture/个人投资助理-项目架构设计-第二阶段（题材匹配重构版）.md`  
  High-precision ThemeMatchEngine migration; preserves streaming/orchestration while replacing matching core.

- `docs/architecture/weak_to_strong_strategy_design.md`  
  Shows useful W2S business reasoning together with direct-SQL/case-tuning debt.

- `docs/architecture/stock_processing_service-架构设计方案.md`  
  Explicitly freezes Gateway/Port/Domain boundaries and positions old stock_service as legacy/reference.

- `docs/architecture/旧链逐项复刻矩阵-2026-05-07.md`  
  Explicit proof that new-chain strategy behavior had already diverged and production temporarily returned to old-chain semantics.

- `docs/project_control/PHASE_CONTRACT_LAYER_ABCD.md`  
  Strong no-fallback/no-invention contract, but historically over-relies on old-chain behavior as algorithm authority.

- `docs/architecture/mainline_discovery_architecture_design.md`  
  Correct separation of mainline, lifecycle, market environment, leader, and setup at conceptual level; also contains some later confirmation-gate assumptions needing correction.

- `docs/architecture/one_to_two_daily_review_architecture.md`  
  Strong setup architecture; remaining confirmed-mainline focus restriction conflicts with approved v0.6.4 discovery semantics.

- `docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md`  
  Frozen architectural governance, Evidence/Context/Cognition/Hypothesis/Thesis, replay, incremental evolution, no unnecessary engine proliferation.

- `docs/architecture/M8_Market_Cognition_Engine_架构设计文档.md`  
  Explicitly says M8 is not a rewrite and does not own Layer A/B/C/D business truth.

- `docs/architecture/Architecture_Decision_Log.md` and `Architecture_Governance_v1.0.md`  
  Preserve Source of Truth, replay, Adapter-first, Shadow-first, ADR-only structural change.

---

## Appendix B — Audit provenance note

A previously referenced path:

`docs/project_control/ARCHITECTURE_CODE_SEMANTIC_AUDIT_R0_DETAILED.md`

was not found at the expected Mac project path during this R1 audit, so it was not used as an authority source.

This R1 report was independently reconstructed from:

- exact GitHub main source;
- actual architecture documents;
- v0.6.4 working strategy baseline;
- direct code inspection;
- earlier Claude/Codex findings only where independently confirmed.

