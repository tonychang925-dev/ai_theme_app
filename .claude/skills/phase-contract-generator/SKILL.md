---
name: phase-contract-generator
description: 从现有文档提炼阶段执行合同，输出机器可读合同，供编排器执行。
when_to_use: 当用户要求按阶段落地执行、明确验收与命令门禁时使用。
model: inherit
effort: high
---

# Phase Contract 生成协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`
- `docs/project_control/TASK_BACKEND_CONTRACT.md`

## 1. 输出

1. `docs/project_control/PHASE_CONTRACT_<phase>.md`
2. `tmp/phase_contract_<phase>.json`

## 2. 真源优先级

1. `PRD*.md`
2. `ACCEPTANCE*.md`
3. `PLAN_WBS*.md`
4. `ARCH_REVIEW*.md`
5. `docs/adrs/*.md`

冲突必须记录“采用来源 + 放弃来源 + 理由”。

## 3. 合同必填章节

1. Phase Identity
2. Objective（可量化）
3. Acceptance Targets（二元可判断）
4. Required Commands（可复制执行）
5. Deliverables（路径可验证）
6. Risk Matrix
7. Rollback Plan
8. Non-Goals

## 4. 一致性门禁

1. 从 `ACCEPTANCE*.md` 提取本 phase 验收条款。
2. 与合同 `Acceptance Targets` 逐条比对。
3. 输出 `tmp/phase_contract_consistency_<phase>.json`。
4. 若 `missing_in_contract` 非空则禁止输出终稿。

## 5. 去耦规则

1. 合同中不得出现外部系统专有字段名。
2. 合同动作必须使用抽象语义（见 task-backend contract）。
