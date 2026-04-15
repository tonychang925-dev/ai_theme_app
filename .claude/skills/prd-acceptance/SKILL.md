---
name: prd-acceptance
description: 基于 PRD 生成验收目标与验收用例，形成可执行的验收基线。
when_to_use: 当用户要求定义阶段验收标准、边界条件和失败判定时使用。
model: inherit
effort: high
---

# PRD 验收协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

## 1. 输入

1. `docs/project_control/PRD*.md`
2. `docs/project_control/PHASE_CONTRACT_*.md`（如存在）

## 2. 输出

1. `docs/project_control/ACCEPTANCE.md`
2. `tmp/acceptance_traceability.json`
3. `tmp/acceptance_validation_report.json`

## 3. 验收条款规则

1. 每条验收目标必须编号（如 `AC-001`）。
2. 每条验收目标必须可执行验证（`TC-ID` 或命令 + 预期）。
3. 验收目标必须可二元判定（Passed/Failed）。
4. 必须覆盖正向、边界、失败、回滚场景。

## 4. 与 PRD 对齐

1. 每条 `FR-*` 至少映射一条 `AC-*`。
2. 若存在未映射项，必须在报告中标红并阻断“终稿通过”。

## 5. 禁止项

1. 禁止用主观描述替代验收判定。
2. 禁止只给“测试建议”而无可执行验证动作。
