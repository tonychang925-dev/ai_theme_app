# Identity-Prior Semantic Authority Audit v1

## Scope

This is a docs-only authority audit for Issue #423.

```text
TASK_BASE
= bc34e973686d7f78b0e9c3efd67b433f0901f21a

AUDIT_AUTHORITY_REF
= Issue #422
= 4815b01343c71f199e0d7b8ddebd7cb40835ca30
= EVIDENCE_ONLY_NOT_ANCESTRY
```

The question is narrow:

```text
Does current canonical authority require identity review
to mutate theme_cycle_judgement_v2.final_mainline_alive?
```

No production source, test, configuration, schema, database row, production job, or composite flow was modified or executed.

## Authority order applied

1. Current frozen architecture and governance baselines.
2. Current Layer A/B/C/D execution contract and equivalence matrix.
3. Current SPS Jobs, Ports, Gateway adapters, and database Gateway methods.
4. Accepted Issue #422 rebound audit, as diagnostic evidence only.
5. Legacy script behavior, only as historical semantic evidence.

## Current authority findings

### 1. Architecture Baseline v4.0 separates audit history from derived state

`docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md` is marked `FROZEN`. Its controlling decisions include:

- Snapshot and State are separate.
- Audit history is immutable.
- Current state is rebuildable.
- Adaptive inputs provide priors but do not modify Evidence history.
- State updates pass through an immutable snapshot/event and a transition function rather than arbitrary in-place mutation.

Relevant sections are the Baseline decisions and `Snapshot` / `State` chapters. This authority favors representing the identity/cycle combination in a downstream state transition rather than rewriting the Layer B judgement truth.

### 2. Current Layer B equivalence matrix forbids redefining `final_mainline_alive`

`docs/architecture/旧链逐项复刻矩阵-2026-05-07.md` states:

```text
final_mainline_alive
= not fade_confirmed

repair action
= 禁止再改成强度硬门
```

That document's Layer B matrix is more specific and later than the 2026-04 draft that named the legacy gate. It directly forbids changing `final_mainline_alive` into an identity or other hard gate.

Therefore the physical value of `theme_cycle_judgement_v2.final_mainline_alive` remains Layer B cycle semantics, not Layer A identity semantics.

### 3. Current post-market design orders a second cycle build, not an identity write-back

`docs/architecture/盘后复盘模块彻底重构设计文档.md` defines the target substeps:

```text
evidence
→ cycle
→ identity
→ cycle
→ mainline
```

The repeated cycle stage is consistent with rebuilding Layer B from its own evidence after identity changes the tracked universe. It is not authority for mutating the already-produced Layer B judgement with identity status.

### 4. Mainline discovery separates confirmation from lifecycle

`docs/architecture/mainline_discovery_architecture_design.md` explicitly separates:

```text
主线确认
= Is it a mainline?

主线生命周期
= Given confirmation, what stage is it in?
```

It also states that lifecycle judgement does not replace mainline confirmation. The current composition direction is therefore:

```text
identity truth
AND cycle truth
→ downstream mainline state / decision eligibility
```

not:

```text
identity truth
→ rewrite cycle truth
```

### 5. Current SPS semantics implement downstream composition

`MainlineStateTransitionService.build_daily_snapshots()` computes:

```text
identity_confirmed
= identity exists
  AND identity.is_main_theme
  AND identity.identity_status == confirmed

final_mainline_alive
= cycle.final_mainline_alive

is_mainline
= identity_confirmed AND final_mainline_alive
```

The evidence object retains both inputs and the composed result. `BuildMainlineStateJob` owns this composition and writes `mainline_state_daily`; it does not call a method that rewrites `theme_cycle_judgement_v2` from identity.

### 6. Current cycle semantics independently define `final_mainline_alive`

`CycleJudgementService.judge_one()` returns:

```text
final_mainline_alive
= NOT (final_cycle_state == fade_confirmed)
```

The cycle row also carries `snapshot_version`, `batch_id`, `trace_id`, `rule_version`, decision path, evidence, and reason codes. This is incompatible with an untracked post-hoc overwrite that appends an identity-prior reason and flips the boolean.

## Historical draft treatment

The root document `项目架构设计-股票服务模块（核心算法&流程）.md` includes:

```text
周期判定V2
→ identity prior gate
→ mainline state snapshot
```

It is historical evidence for the legacy intent: align cycle results with identity before downstream state generation. It is not sufficient current authority to migrate the mutation because:

1. Its header marks it `Draft`.
2. Its last-updated value is 2026-04-19.
3. It predates the 2026-05 Layer B equivalence matrix and the 2026-07 frozen architecture baseline.
4. The later authorities preserve the business gate but represent it through Layer B's own rebuild and downstream composition.

This is not a material unresolved conflict. The invariant is the decision gate; the legacy SQL mutation is only one historical implementation of that gate.

## Direct answers

| Question | Answer |
|---|---|
| Must `theme_cycle_judgement_v2.final_mainline_alive` be physically mutated after identity review? | NO |
| Does canonical mainline truth combine identity and cycle without back-writing cycle rows? | YES |
| Is `BuildMainlineStateJob` the intentional composition point? | YES |
| Does any current ADR/document authorize identity-to-cycle cross-layer mutation? | NO |
| Would migration violate layer ownership and historical/as-of semantics? | YES |
| Is legacy confirmed-non-fade promotion still required? | NO; canonical cycle rebuild defines alive from `NOT fade_confirmed` |
| Is omission of the legacy mutation a proven canonical semantic defect? | NO |

## Disposition

```text
DISPOSITION
= LEGACY_MUTATION_NOT_CANONICAL_INVARIANT

DO_NOT_MIGRATE_LEGACY_IDENTITY_PRIOR_MUTATION
```

The old purpose is replaced by:

1. `BuildCycleJudgementJob` rebuilding Layer B from cycle evidence after identity execution;
2. `BuildMainlineStateJob` composing `identity_confirmed AND final_mainline_alive`;
3. canonical read consumers applying both identity and cycle conditions when mainline eligibility is required.

This decision does not validate the other known recap Gateway escapes or the canonical identity LLM transport gap. Those remain separate P0 corrections from Issue #422.
