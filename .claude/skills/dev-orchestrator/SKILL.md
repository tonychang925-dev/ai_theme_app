---
name: dev-orchestrator
description: 阶段驱动执行器，负责计划、实施、验证、报告与验收决策；支持 autopilot 无人值守执行。
when_to_use: 当用户要求按阶段推进并形成可审计交付闭环时使用。
model: inherit
effort: high
---

# Development Orchestrator（Phase 2 Autopilot）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`
- `docs/project_control/TASK_BACKEND_CONTRACT.md`

## 1. 执行状态机

1. STEP 1: Preflight
2. STEP 2: Plan/Design
3. STEP 3: Implement
4. STEP 4: Validate
5. STEP 5: Report
6. STEP 6: Gate + Wait Decision

运行产物：
- `tmp/runs/<run_id>/state.json`
- `tmp/runs/<run_id>/events.log`
- `tmp/runs/<run_id>/checkpoints/`

## 2. 强制门禁

1. 未完成 `Phase Contract` 不得进入 STEP 3。
2. 未完成测试证据不得推进到 `In review/done`。
3. 必须执行 `UT -> IT -> E2E/PT` 顺序。
4. 阶段收尾必须产出报告与 gate 判定。

## 3. backend 调用规则

仅允许使用抽象动作：
- `fetch_tasks`
- `update_task_status`
- `append_test_evidence`
- `update_milestone_progress`
- `create_phase_report`
- `record_acceptance_decision`

默认 backend：`local`

## 4. 失败策略

1. 非阻断错误写入 `pending_sync.json` 并继续。
2. 阻断错误更新 `state=blocked` 并停止在当前步骤。
3. 所有错误必须记入 `events.log`。

## 5. 输出物

1. `docs/project_control/reports/phase-<phase>.md`
2. `tmp/runs/<run_id>/validation_summary.json`
3. `tmp/runs/<run_id>/gate_decision.json`

## 6. 自动执行命令（新增）

### 6.1 从合同生成执行计划

```bash
python3 .claude/automation/plan_from_contract.py \
  --phase P1.phase0 \
  --contract docs/project_control/PHASE_CONTRACT_P1.phase0.md \
  --output tmp/runs/P1.phase0/execution_plan.json
```

### 6.2 启动 autopilot

```bash
python3 .claude/automation/autopilot_runner.py \
  --phase P1.phase0 \
  --contract docs/project_control/PHASE_CONTRACT_P1.phase0.md \
  --plan tmp/runs/P1.phase0/execution_plan.json \
  --run-id P1_phase0_$(date +%Y%m%d_%H%M%S) \
  --mode autopilot \
  --max-retries 5 \
  --retry-backoff 1,2,4,8,16 \
  --reports-dir docs/project_control/reports
```

## 7. 本地 backend 动作（新增）

通过以下脚本执行抽象动作（默认 local）：

```bash
python3 .claude/automation/task_backend_local.py \
  --run-dir tmp/runs/<run_id> \
  --action fetch_tasks \
  --payload-json '{}'
```

支持动作：
- `fetch_tasks`
- `update_task_status`
- `append_test_evidence`
- `update_milestone_progress`
- `create_phase_report`
- `record_acceptance_decision`
