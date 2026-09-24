# HISTORICAL_COGNITION_ACCEPTANCE_GATE_v1

## Authority

- `TASK_ID = POST-RD1-E1-E-HISTORICAL-COGNITION-ACCEPTANCE-P0`
- `CANONICAL_MAIN = bc34e973686d7f78b0e9c3efd67b433f0901f21a`
- `WORK_BRANCH = post-rd1/market-financial-analyst-integration`
- `START_HEAD = 97a8eb4257cdbde75ee632884c5bd1cbb6bc442c`
- Contract: `HISTORICAL_COGNITION_ACCEPTANCE_CONTRACT_v1.md`
- Historical matrix: `HISTORICAL_COGNITION_FIXTURE_MATRIX_v1.md`
- Failure matrix: `HISTORICAL_COGNITION_FAILURE_FIXTURES_v1.md`

## Quantitative gates

| Gate | Required result |
|---|---|
| Historical cognition fixtures complete | `12/12` |
| Failure fixtures fail/degrade as designed | `8/8` |
| Schema-valid JuliaReviewOverlay outputs | `100%` |
| Claim/source ownership preserved | `100%` |
| Required evidence-ref integrity for evidence-dependent ACCEPTED/CHALLENGED items | `100%` |
| DEFERRED items expose known missing-evidence/open-question need | `100%` |
| Information-cutoff compliance | `100%` |
| Silent fallback | `0` |
| Schema guessing | `0` |
| Ownership mutation | `0` |
| Market/provider claim -> Julia observation truth promotion | `0` |
| Runtime/workflow-minted semantic disposition or judgment | `0` |
| Hindsight leakage | `0` |
| Cognition dispositions/judgment bound to generation identity or explicit deferred `UNKNOWN` | `100%` |

Every count is over executed, ready fixtures. `SOURCE_MISSING / NOT_READY` rows are blockers and count as incomplete for the `12/12` gate; they MUST NOT be excluded from the denominator.

## PASS / HOLD / FAIL

Current corpus status: `HOLD / NOT_READY` because all 12 historical rows remain `SOURCE_MISSING / NOT_READY`. This does not prevent Owner freeze of the acceptance contract and fixture plan, but it prevents acceptance execution and E2 entry.

### PASS

The gate passes only when every quantitative gate is met, every historical row is `READY`, every failure behaves exactly as designed, and the evidence report proves all authority, ownership, binding, freshness, and cutoff checks.

### HOLD

The gate is `HOLD / NOT_READY` when the contract is defined but one or more rows remain `SOURCE_MISSING / NOT_READY`, required version/cutoff inputs are `UNKNOWN` in a way that prevents auditable replay, or an implementation prerequisite is absent. HOLD does not authorize synthetic evidence or E2 implementation.

### FAIL

The gate fails on any violation, including one silent fallback, schema guess, ownership mutation, authority promotion, Runtime-minted semantic result, hindsight leak, invalid overlay, missing required evidence ref, unintended failure recovery, or outcome-only pass logic.

## Required evidence report

The acceptance report MUST provide:

1. exact corpus and branch/commit identity;
2. each fixture ID, readiness, trade date, cutoff, and source inventory;
3. exact Market envelope/evidence/source identities consumed;
4. external research availability/failure state and refs;
5. StrategyKnowledge versions, maturity dimensions, framework/policy versions;
6. JuliaReviewOverlay schema-validation result;
7. item disposition counts and review-level `INCONCLUSIVE` count;
8. ownership preservation matrix;
9. evidence-ref integrity results;
10. missing-evidence/open-question visibility;
11. contradiction retention results;
12. cutoff exclusion/rejection audit;
13. cognition generation identity or explicit deferred `UNKNOWN`;
14. deterministic identity comparisons where frozen;
15. failure-fixture observed/expected behavior and STOP result;
16. all policy violations with file/fixture/ref detail;
17. final gate arithmetic and PASS/HOLD/FAIL result.

Natural-language Julia output need not be byte-identical. Deterministic projection/contract layers MUST be identical where deterministic identity is frozen.

## E2 prohibition

E2 Daily Product implementation is forbidden until:

1. this E1-E acceptance contract is Owner-frozen;
2. all 12 historical fixtures are materialized and pass;
3. all 8 failure fixtures fail/degrade exactly as designed;
4. every quantitative gate passes;
5. the acceptance evidence report is complete and auditable;
6. the Owner explicitly accepts and freezes E1-E completion.

A source-missing corpus, HOLD result, failed gate, or implementation shortcut cannot be used to start E2.
