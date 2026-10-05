# WORKBENCH_RUNTIME_SOURCE_CONVERGENCE_P0

Status: OWNER DESIGN FREEZE CANDIDATE  
Implementation authorized: NO  
Runtime restart authorized: NO  
Database mutation authorized: NO  

Canonical base at freeze time: `e55559bc5c151cc946ebadbe408c5c463da66ea6`

## 1. Purpose

Eliminate runtime source ambiguity before any Workbench durable snapshot repair.

The Market runtime, web_app_service:8000 runtime, and Analyst Workbench runtime must execute from one explicitly authorized canonical worktree and one exact Git commit. No production verification may mix code loaded from historical Desktop worktrees, PRE_A3 worktrees, or a different `PYTHONPATH`.

This card authorizes design freeze only. It does not authorize code changes, service restart, DB writes, historical backfill, E2E, or external model calls.

Architecture note: `frontend_bff:8003` is the retired legacy BFF and is explicitly outside this task. The current gateway is `web_app_service:8000`, which reads SPS on `stock_processing_service:8090`.

## 2. Audited current defect

Three source identities are currently observable:

- canonical source: `/Users/admin/glm-workspace/ai_theme_app`
- live SPS process cwd observed during audit: `/Users/admin/Desktop/ai_theme_app_PRE_A3_20261004`
- live SPS `PYTHONPATH` / `PWD` observed during audit: `/Users/admin/Desktop/ai_theme_app`

In addition, canonical-main startup scripts currently hard-code:

```bash
ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
```

in:

- `scripts/start_new_chain_stack.sh`
- `scripts/start_new_chain_stack_detached.sh`

Therefore canonical Git source and runtime source are not converged.

## 3. Correct existing direction

Current main already contains two runtime launch paths that are architecture-compatible:

- `desktop/src/runtime/serviceManager.ts` uses the supplied `projectRoot` for `cwd` and `PYTHONPATH`.
- `web_app_service/services/realtime_stack_manager.py` uses `self._project_root` for `cwd` and `PYTHONPATH`.

The convergence fix must align shell startup behavior with this project-root-based model. It must not introduce another independent runtime root selector.

## 4. Required invariant

For any authorized runtime launch:

```text
AUTHORIZED_WORKTREE_ROOT
= process cwd
= PYTHONPATH root
= runtime healthz cwd
= source location used by SPS/Web/Workbench
```

The authorized worktree HEAD must equal the exact Owner-approved Git SHA.

A runtime is invalid if any of these identities differ.

## 5. Scope allowed for a future implementation task

Only runtime-source convergence may be changed.

Candidate scope:

- remove hard-coded `/Users/admin/Desktop/ai_theme_app` assumptions from canonical startup scripts;
- derive `ROOT_DIR` from the script/repository location or one explicit caller-supplied canonical project root;
- preserve existing runtime-profile, Python interpreter, port, health, text2vec-path, env-loading, and process-lifecycle behavior;
- make runtime self-report sufficient to prove exact root and exact Git SHA;
- fail closed if a launched process does not match the authorized root/SHA.

## 6. Explicit prohibitions

The implementation MUST NOT:

- modify Workbench business logic;
- add or repair recap snapshot generation;
- write or backfill `post_market_recap_snapshot`;
- run DailyReviewV2 generation;
- modify Julia Core;
- resurrect `julia_domain_adapter` or historical `market_public_boundary` code;
- alter theme/event matching;
- run E2E against production data during this card unless separately authorized;
- call external LLM/model services;
- use fallback to a historical worktree when canonical root is unavailable;
- silently accept cwd/PYTHONPATH mismatch.

## 7. Required runtime identity evidence

A future candidate must provide machine-readable evidence for SPS and web_app_service:8000 containing at minimum:

```text
repo_root
cwd
python executable
PYTHONPATH
runtime_profile
git_sha
service port
```

The runtime must fail readiness when:

```text
cwd != authorized repo_root
or PYTHONPATH root != authorized repo_root
or git_sha != authorized SHA
```

No warning-only downgrade is acceptable for these identity checks.

## 8. Canonical health/readiness contract

SPS `/healthz` already exposes runtime-oriented diagnostics such as cwd, Python, and runtime profile. The future implementation should extend or reuse that mechanism rather than inventing a parallel control plane.

Acceptance requires an exact-SHA proof, not only a path-name match.

web_app_service:8000 readiness must also prove that it is connected to the SPS instance launched from the same authorized root/SHA.

## 9. Workbench storage warning

Current Workbench local state exists under worktree-local paths such as:

```text
tmp/analyst_workbench/<trade_date>/...
```

Runtime convergence MUST NOT copy, overwrite, delete, or silently relocate these historical local assets.

Any later migration of analyst session/draft/approved-snapshot storage is a separate task.

## 10. Golden verification target

After a future convergence implementation, a read-only verification should use 2026-09-24 as the golden reference because its Market durable snapshot is already known to make:

```text
market.state.read    -> READY
market.analysis.read -> READY
```

The convergence task itself must not rebuild or overwrite the 2026-09-24 snapshot.

## 11. Acceptance criteria

A candidate is acceptable only if all are true:

1. Base SHA equals the exact Owner-authorized canonical main SHA.
2. No historical Desktop/PRE_A3 worktree is used as SPS or web_app_service:8000 source.
3. Canonical shell startup no longer hard-codes `/Users/admin/Desktop/ai_theme_app`.
4. SPS starts with `cwd == authorized repo root`.
5. SPS starts with `PYTHONPATH == authorized repo root`.
6. SPS reports the expected runtime profile and Python environment.
7. Runtime reports the exact Git SHA and it equals the authorized SHA.
8. `web_app_service:8000` targets the SPS instance belonging to the same root/SHA.
9. Existing model-path wiring remains project-root-relative.
10. No DB writes, historical backfill, Workbench generation, or external LLM invocation are required to prove convergence.
11. Any mismatch is fail-closed, never warning-only or fallback-to-Desktop.
12. Repository and preserved historical Workbench assets remain unchanged except for the explicitly authorized runtime-source code delta.

## 12. Next gate

Only after Owner accepts runtime-source convergence may `WORKBENCH_DURABLE_MARKET_SNAPSHOT_CLOSURE_P0` implementation begin.

That later task must separately implement deterministic Market recap materialization from existing durable/read-model data, without requiring external LLM output for Julia's ten required analysis modules.
