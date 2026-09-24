# Legacy Identity-Prior Behavior Decomposition v1

## Entrypoint

```text
stock_service/scripts/enforce_v2_identity_prior_gate.py::main_async()
```

The script directly imports `asyncpg`, constructs a connection from `StockServiceConfig`, queries `theme_cycle_judgement_v2` joined to `theme_mainline_identity_registry`, and optionally executes two `UPDATE` statements.

It is dry-run by default. The legacy recap orchestration invoked it with:

```text
--apply
--promote-confirmed-nonfade
```

after building/checking cycle rows and before legacy mainline-state tracking.

## Preview classification

`_count_targets()` classifies rows for the requested trade date.

### `target_rows`

Conditions:

```text
cycle.final_mainline_alive = TRUE
AND (
  identity.is_main_theme = FALSE
  OR identity.identity_status != confirmed
)
```

This identifies an alive Layer B row whose current joined identity is not confirmed.

### `promote_rows`

Conditions:

```text
cycle.final_mainline_alive = FALSE
AND cycle.fade_confirmed = FALSE
AND identity.is_main_theme = TRUE
AND identity.identity_status = confirmed
AND cycle.final_cycle_state IN non-fade active states
```

This identifies a false alive value on a confirmed, non-faded identity. Under the current canonical rule `final_mainline_alive = NOT fade_confirmed`, such a value can only be legacy drift, an older-rule result, or damaged data.

### `alive_rows_before`

Counts rows whose cycle boolean is true before execution. It is diagnostic only.

## Action A — identity-prior demotion

`_apply_gate()` updates:

```text
table
= theme_cycle_judgement_v2

columns
= final_mainline_alive
= state_transition_reason
```

It sets:

```text
final_mainline_alive = FALSE
```

when the joined identity is not a confirmed main theme, and appends `identity_prior_gate` to `state_transition_reason`.

It does not:

- create a new cycle snapshot version;
- supply a new batch/trace identity;
- preserve the prior value as explicit evidence;
- update the identity table;
- write a separate transition object.

## Action B — confirmed-non-fade promotion

`_apply_promote_confirmed_nonfade()` updates the same two columns and sets:

```text
final_mainline_alive = TRUE
```

for confirmed, non-fade identities in selected active cycle states. It appends `identity_confirmed_nonfade_bridge` to the reason.

This is a repair/backfill bridge. It is not a current Layer B generation rule.

## Semantic classification

| Legacy action | Classification |
|---|---|
| Block unconfirmed identities from formal mainline eligibility | BUSINESS INVARIANT, represented canonically by downstream composition |
| Flip cycle `final_mainline_alive=false` from identity status | LEGACY REPAIR / CROSS-LAYER CONVERGENCE MECHANISM |
| Flip confirmed non-fade rows to alive | HISTORICAL DATA REPAIR / OLD RULE BRIDGE |
| Preserve a single `final_mainline_alive` containing both cycle and identity meaning | REDUNDANT DERIVED STATE / SEMANTIC OVERLOAD |
| Reinterpret a historical cycle row using current registry state | HISTORICAL REWRITE RISK |

## Timing comparison

### Legacy orchestration

```text
identity registry
→ ensure/build theme_cycle_judgement_v2
→ enforce identity prior mutation
→ build mainline state tracking
→ strong watch / recap
```

### Canonical orchestration

`BuildPostMarketRecapJob` and `PostMarketPrerequisitesRunner` both execute:

```text
BuildThemeCycleEvidenceDailyJob
→ BuildCycleJudgementJob
→ BuildIdentityJob
→ BuildCycleJudgementJob
→ BuildMainlineStateJob
```

The second `BuildCycleJudgementJob` recreates cycle truth from cycle evidence and the post-identity tracked universe. `BuildMainlineStateJob` then composes identity and cycle without changing either source table.

## Why the promotion is obsolete

Current `CycleJudgementService` defines:

```text
final_mainline_alive
= NOT fade_confirmed
```

Therefore:

```text
fade_confirmed = FALSE
→ final_mainline_alive = TRUE
```

after a canonical cycle rebuild. The legacy promotion is only needed to repair rows generated under drifted or older semantics; it must not become a post-generation identity write-back.

## Historical/as-of risk

The legacy join is effectively by `subject_key`, while filtering the cycle row by `trade_date`. It does not select the identity row as of that cycle trade date.

If current identity later changes, rerunning the gate against an old date can reinterpret and rewrite that old cycle row. It also mutates the row in place and only appends a string reason, without a new immutable snapshot event or transition record.

Accordingly:

```text
HISTORICAL_REWRITE_RISK
= P0_IF_LEGACY_MUTATION_IS_RUN
```

The canonical direction avoids this class of damage by retaining identity and cycle as separate inputs and composing them into `mainline_state_daily`.

## Non-migration consequence

```text
DO_NOT_MIGRATE
= identity-prior UPDATE
= confirmed-non-fade promotion UPDATE
= untracked reason-string mutation
= current-identity reinterpretation of historical cycle rows
```

Any historical data repair must be separately authorized with an explicit as-of contract, immutable evidence, owner approval, and replay acceptance. No such repair is authorized by Issue #423.
