# HISTORICAL_COGNITION_FIXTURE_MATRIX_v1

## Authority and readiness

- `TASK_ID = POST-RD1-E1-E-HISTORICAL-COGNITION-ACCEPTANCE-P0`
- `START_HEAD = 97a8eb4257cdbde75ee632884c5bd1cbb6bc442c`
- Governing contract: `HISTORICAL_COGNITION_ACCEPTANCE_CONTRACT_v1.md`

The dates `2026-04-01` through `2026-04-16` are selection anchors already present in `reports/mainline_discovery_backtest_20260401_20260430.json`. `2026-07-02` is a selection anchor present in `datasets/market_thesis_validation/2026/07/20260703_a0b9bf5e94ed642c1679c8a2.json`.

Those artifacts do not establish that the POST-RD1 Market analytical snapshot, External Research evidence, StrategyKnowledge item, or Julia cognition input for a row is complete. Scenario labels below are **target allocation classes**, not source claims. Consequently every row is `SOURCE_MISSING / NOT_READY`; no historical evidence has been invented to force corpus completion.

`CUTOFF_TBD` means the exact auditable historical cutoff must be materialized from source-available times before execution. It is not permission to use current time or later verification data.

## Matrix

| ID | Trade date | Target scenario | Market expectation | External expectation | Strategy version/maturity | Competing/counterevidence | Cutoff | Allowed disposition properties | Fresh judgment | Prohibited shortcuts | Required refs | Readiness |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HC-001 | 2026-04-01 | Mainline start / fermentation | Exact-date envelope and refs; no substitution | External provenance or explicit unavailable state | Exact strategy version; `STRUCTURED_KNOWLEDGE` or `UNKNOWN` | Preserve at least one competing interpretation if materialized | `CUTOFF_TBD` | Item `ACCEPTED`/`CHALLENGED`/`DEFERRED`; review-level `INCONCLUSIVE` allowed | New generation bound to exact input/version/cutoff | No outcome label, no current framework | Market request/envelope/evidence/source IDs; strategy refs; external state | `SOURCE_MISSING / NOT_READY` |
| HC-002 | 2026-04-02 | Mainline start / fermentation | Same exact-date and ownership checks | Source-available time and partial state explicit | Strategy questions/counterevidence visible | Preserve formation versus noise conflict | `CUTOFF_TBD` | Reasoned item set; no forced directional answer | Julia-only semantic authorship | No evidence presence -> applicability | All consumed Market/external/strategy refs | `SOURCE_MISSING / NOT_READY` |
| HC-003 | 2026-04-03 | Climax / divergence | Preserve contradictory Market evidence | External claim remains external | Invalidation and failure-mode questions visible | Retain climax versus extension conflict | `CUTOFF_TBD` | `CHALLENGED` allowed; `DEFERRED` for missing causal support | Fresh causal interpretation citing both sides | No vote-count judgment | Supporting/conflicting refs required | `SOURCE_MISSING / NOT_READY` |
| HC-004 | 2026-04-07 | Climax / divergence | Exact-date envelope despite adjacent-day history | Explicit external availability | Applicability question, not applicability result | Preserve divergence counterevidence | `CUTOFF_TBD` | `ACCEPTED` premise + `CHALLENGED` conflict allowed | Judgment remains non-action semantic output | No buy/sell/hold inference | Exact Market identities + conflict refs | `SOURCE_MISSING / NOT_READY` |
| HC-005 | 2026-04-08 | Repair / weak-to-strong candidate | Preserve repair evidence and limitations | External source provenance | Required/positive/negative evidence visible | Preserve weak versus strengthening interpretations | `CUTOFF_TBD` | `DEFERRED` allowed when support is insufficient | Must expose unresolved causal gap | No detector invented | Market/external/strategy refs | `SOURCE_MISSING / NOT_READY` |
| HC-006 | 2026-04-09 | Repair / weak-to-strong candidate | Preserve exact-date quality/coverage limits | Partial failure remains explicit | `DETERMINISTIC_DETECTOR=UNKNOWN` allowed | Preserve candidate failure modes | `CUTOFF_TBD` | `INCONCLUSIVE` allowed at review level | No judgment from absent detector | No fabricated detector output | Missing-evidence/open-question refs | `SOURCE_MISSING / NOT_READY` |
| HC-007 | 2026-04-10 | Ebb / retreat | Exact-date evidence only | Unavailable research remains explicit | Retreat/invalidation questions visible | Preserve ebb versus pause interpretations | `CUTOFF_TBD` | `CHALLENGED`/`DEFERRED`/`INCONCLUSIVE` allowed | Fresh cutoff-bound reasoning | No later reversal leakage | Market + strategy + external-state refs | `SOURCE_MISSING / NOT_READY` |
| HC-008 | 2026-04-13 | Ebb / retreat | No adjacent-date substitution | External provenance preserved | Strategy version and maturity explicit | Preserve negative evidence | `CUTOFF_TBD` | Negative evidence does not force sell/reject | Julia interpretation remains separate | No Runtime disposition | Contradiction/ownership refs | `SOURCE_MISSING / NOT_READY` |
| HC-009 | 2026-04-14 | Analyst/Workbench claim challenged by Julia | Market evidence remains canonical base | External evidence optional and owned externally | Strategy framework version explicit | Analyst claim and conflicting evidence preserved | `CUTOFF_TBD` | `CHALLENGED` with reason and refs; no source rewrite | Judgment may not adopt analyst authority | No unapproved maturity promotion | Analyst ref if present; Market conflict refs | `SOURCE_MISSING / NOT_READY` |
| HC-010 | 2026-04-15 | Analyst/Workbench claim challenged by Julia | Exact-date Market envelope preserved | External partial state explicit | Strategy applicability questions visible | Analyst ownership preserved after challenge | `CUTOFF_TBD` | `CHALLENGED` or `DEFERRED`; `INCONCLUSIVE` allowed | Fresh Julia synthesis | No Workbench-exclusive intake | Immutable analyst content identity when present | `SOURCE_MISSING / NOT_READY` |
| HC-011 | 2026-04-16 | Evidence insufficient -> item DEFERRED | Exact-date absence or partial evidence explicit | Unavailable/partial external research explicit | `REVIEW_POLICY=UNKNOWN` allowed | Preserve why support is insufficient | `CUTOFF_TBD` | Required item-level `DEFERRED`; review may complete or be `INCONCLUSIVE` | No directional judgment from absence | No missing evidence -> truth | Missing-evidence/open-question refs | `SOURCE_MISSING / NOT_READY` |
| HC-012 | 2026-07-02 | Evidence insufficient -> item DEFERRED | Exact-date Market evidence and refs | External state explicit | Exact StrategyKnowledge version; detector absence explicit | Preserve incomplete evidence and counterevidence | `2026-07-02T15:30:00+08:00` candidate; audit before use | Item `DEFERRED` with later-evidence need; `INCONCLUSIVE` only at review level | Bound fresh generation to historical cutoff | No 2026-07-03 verification leakage | Existing thesis-source refs plus all consumed POST-RD1 refs | `SOURCE_MISSING / NOT_READY` |

## Coverage accounting

- Mainline start / fermentation: HC-001, HC-002.
- Climax / divergence: HC-003, HC-004.
- Repair / weak-to-strong candidate: HC-005, HC-006.
- Ebb / retreat: HC-007, HC-008.
- Analyst/Workbench claim challenged by Julia: HC-009, HC-010.
- Evidence insufficient -> item-level `DEFERRED`: HC-011, HC-012.
- Historical rows defined: 12.
- Rows currently ready: 0.
- Rows currently `SOURCE_MISSING / NOT_READY`: 12.

The corpus MUST cover at least one `STRUCTURED_KNOWLEDGE` case, one explicit `REVIEW_POLICY` bound-or-`UNKNOWN` case, and one explicit `DETERMINISTIC_DETECTOR` bound-or-`UNKNOWN` case when materialized. Current detector absence MUST be represented explicitly and MUST NOT be converted into detector output.
