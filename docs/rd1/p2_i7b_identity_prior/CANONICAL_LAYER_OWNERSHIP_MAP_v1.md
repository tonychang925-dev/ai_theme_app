# Canonical Layer Ownership Map v1

## Ownership principle

```text
Layer A identity truth
≠ Layer B cycle truth
≠ downstream mainline composition
```

Each source retains its own owner and write path. Cross-layer eligibility is derived when `BuildMainlineStateJob` and canonical read consumers combine the truths.

## Ownership matrix

| Concern | Owner | Exact chain | Writes |
|---|---|---|---|
| Identity rule inputs | `BuildIdentityJob` | `StockReadPort.get_mainline_identity_rule_inputs` → `DBThemeDataGateway` → `DatabaseGateway` → `PostgresDatabaseManager` | none |
| Identity truth | `BuildIdentityJob` | `AlgorithmStateWritePort.upsert_theme_mainline_identity_registry_rows` → `DBStockObjectGateway` → `DatabaseGateway` → `PostgresDatabaseManager` | `theme_mainline_identity_registry` |
| Identity review queue | `BuildIdentityJob` | `AlgorithmStateWritePort.upsert_mainline_identity_review_queue_rows` → `DBStockObjectGateway` → `DatabaseGateway` → `PostgresDatabaseManager` | `mainline_identity_review_queue` |
| Cycle evidence | `BuildThemeCycleEvidenceDailyJob` | `AlgorithmStateWritePort.upsert_theme_cycle_evidence_daily_rows` → `DBStockObjectGateway` → `DatabaseGateway` → `PostgresDatabaseManager` | `theme_cycle_evidence_daily` |
| Cycle judgement | `BuildCycleJudgementJob` | `AlgorithmStateWritePort.upsert_theme_cycle_judgement_v2_rows` → `DBStockObjectGateway` → `DatabaseGateway` → `PostgresDatabaseManager` | `theme_cycle_judgement_v2` |
| Mainline state composition | `BuildMainlineStateJob` | read identity and cycle through `StockReadPort`/`DBThemeDataGateway`/`DatabaseGateway`; write through `AlgorithmStateWritePort` → `DBStockObjectGateway` → `DatabaseGateway` | `mainline_state_daily`, `mainline_state_transition` |
| Lifecycle downgrade | `BuildIdentityJob` | `AlgorithmStateWritePort.apply_lifecycle_downgrade` → `DBStockObjectGateway` → `DatabaseGateway` → `PostgresDatabaseManager.apply_lifecycle_downgrade` | identity registry |
| Post-market orchestration | `BuildPostMarketRecapJob` / `PostMarketPrerequisitesRunner` | invokes evidence, cycle, identity, cycle, and mainline-state Jobs | each Job owns its target |

## Exact composition owner

`BuildMainlineStateJob` is the intentional composition point.

It reads:

```text
StockReadPort.get_all_confirmed_mainlines
  or get_mainline_identity_by_subject_keys

StockReadPort.get_all_cycle_judgements
  or get_mainline_cycle_by_subject_keys
```

It delegates to:

```text
MainlineStateTransitionService.build_daily_snapshots()
```

The service computes:

```text
identity_confirmed
AND cycle.final_mainline_alive
→ mainline_state_daily.is_mainline
```

It then delegates transition generation and writes only the state/transition outputs. It does not call a cycle mutation method.

## Exact orchestration sequence

The current selected collection prerequisite runner names the stages explicitly:

```text
theme_cycle_evidence
→ cycle_pre_identity
→ identity
→ cycle_post_identity
→ mainline_state
```

`BuildPostMarketRecapJob.execute()` repeats the same order when prerequisites are not skipped.

This sequence explains the canonical replacement for the old gate:

1. Build initial cycle truth.
2. Build/review identity truth.
3. Rebuild cycle truth for the post-identity tracked universe using Layer B evidence.
4. Compose both truths in `BuildMainlineStateJob`.

No step requires identity status to overwrite `final_mainline_alive`.

## Cycle ownership detail

`BuildCycleJudgementJob` builds its row from `CycleEvidenceBuilder` and `CycleJudgementService`, then writes through the declared write Port. The row carries:

- trade date;
- subject and theme identity;
- final cycle state;
- final alive value;
- fade flags and scores;
- decision path;
- reason/evidence fields;
- snapshot version;
- batch and trace IDs;
- rule version.

The current authority fixes `final_mainline_alive` to `NOT fade_confirmed`.

## Cross-layer consistency

Consistency is represented by composition at the following points:

1. `MainlineStateTransitionService` creates `is_mainline` only when both inputs are true.
2. State transitions are generated only for composed mainline rows.
3. Canonical database read methods that need mainline eligibility join identity and cycle conditions rather than assuming the cycle boolean alone means confirmed-mainline.
4. The second cycle build ensures the post-identity universe is represented through Layer B's own evidence and rule.

There is no declared Port or Gateway method equivalent to:

```text
mutate theme_cycle_judgement_v2
FROM identity truth
```

That absence is correct under the resolved semantics; it is not a missing replacement to implement.

## Historical/as-of ownership

The architecture separates immutable snapshots from rebuildable state. A later identity change must not silently alter an earlier Layer B judgement.

Canonical state construction must use inputs appropriate to the target trade date and retain version/batch/trace evidence. Exact-date replay remains an implementation acceptance concern for the corrected production chain, but it cannot justify the legacy current-registry write-back.

## Relationship to known P2 blockers

This map resolves only the identity-prior authority question.

It does not close:

- `IdentityLLMReviewService` JSON transport/error-typing gaps;
- selected recap-path Gateway escapes;
- production-worker replay-facade contamination;
- readiness/status raw SQL;
- Market readiness or composite execution.

Those remain separately owned corrections. The presence of those defects does not turn the legacy identity-prior mutation into canonical authority.
