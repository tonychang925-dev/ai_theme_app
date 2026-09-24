# Identity-Prior Decision v1

## Decision

```text
DISPOSITION
= LEGACY_MUTATION_NOT_CANONICAL_INVARIANT
```

## Separated conclusions

### Business decision invariant

```text
unconfirmed identity
→ must not qualify as formal mainline
```

This invariant is current and has an existing canonical owner:

```text
OWNER
= BuildMainlineStateJob

USE CASE
= compose identity truth AND cycle truth into mainline_state_daily

PORT
= StockReadPort for identity/cycle inputs
AlgorithmStateWritePort for state/transition outputs

GATEWAY
= DBThemeDataGateway
DBStockObjectGateway
DatabaseGateway
PostgresDatabaseManager
```

The canonical result is:

```text
is_mainline
= identity_confirmed AND final_mainline_alive
```

### Physical mutation invariant

```text
identity review
→ mutate theme_cycle_judgement_v2.final_mainline_alive
```

This is NOT a current canonical invariant.

## Canonical replacement of the old purpose

| Legacy purpose | Canonical mechanism |
|---|---|
| Prevent unconfirmed identity from entering formal mainline state | `BuildMainlineStateJob` composition |
| Align cycle generation with post-identity universe | second `BuildCycleJudgementJob` execution |
| Define cycle alive truth | `CycleJudgementService`: `NOT fade_confirmed` |
| Repair confirmed non-fade false-alive rows | rebuild Layer B through its owner; no identity write-back |
| Preserve cross-layer explanation | state evidence records `identity_confirmed`, `final_mainline_alive`, and composed `is_mainline` |

## Frozen prohibition

```text
DO_NOT_MIGRATE_LEGACY_IDENTITY_PRIOR_MUTATION
```

Specifically, do not implement:

- `ON CONFLICT` or `UPDATE` variants of the legacy gate;
- a new Job that copies the legacy SQL;
- a Gateway method whose contract is “rewrite cycle from identity”;
- promotion of confirmed non-fade rows as a normal production stage;
- current identity reinterpretation of historical cycle rows.

## Historical rewrite classification

```text
HISTORICAL_REWRITE_RISK
= P0_IF_LEGACY_MUTATION_IS_RUN
```

The legacy script joins current identity by subject and updates an exact-date cycle row in place. A later identity change can therefore alter prior-date meaning. The frozen architecture and Layer contracts reject that direction.

Any historical repair requires a separate owner-approved task with:

- explicit as-of identity selection;
- immutable before/after evidence;
- typed failure behavior;
- no silent reason-string-only mutation;
- replay acceptance;
- no composite execution while repair is unresolved.

## Follow-up effect

Issue #422 Task P/A0 is resolved by this document: no canonical owner is missing for the business invariant, and no source task may be issued to migrate the legacy mutation.

Subsequent P2/I7B work remains blocked by the previously audited canonical LLM transport and recap Gateway corrections. This decision does not authorize production changes, data repair, Market readiness execution, or real composite execution.

## Completion facts

```text
LEGACY_BEHAVIOR_DECOMPOSED
= YES

CURRENT_INVARIANT_PROVEN
= NO

The unqualified term refers specifically to physical identity-prior mutation. The composed eligibility invariant is proven and owned by `BuildMainlineStateJob`.

CANONICAL_OWNER
= BuildMainlineStateJob_FOR_COMPOSED_ELIGIBILITY

PRODUCTION_SOURCE_CHANGED
= NO

TEST_CONFIG_DB_CHANGED
= NO

P2_REAL_COMPOSITE
= HOLD
```
