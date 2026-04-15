---
name: qa-gate
description: 建立可审计质量门禁，定义必跑检查、失败处理与放行判定。
when_to_use: 当用户要求质量策略、门禁标准、测试命令、DoD 时使用。
model: inherit
effort: medium
---

# QA Gate 协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

## 1. 输出

1. `docs/project_control/QA_GATE.md`
2. `tmp/qa_gate_result_<phase>.json`

## 2. 必跑检查

按顺序执行并记录：
1. Unit Test
2. Integration Test
3. Lint/Type
4. E2E/PT（如果阶段要求）

## 3. 判定规则

1. 任一必检项失败，`Gate=Failed`。
2. 未提供可复现证据，`Gate=Failed`。
3. 存在 P0/P1 未关闭风险，默认 `Gate=Failed`。

## 4. 失败处理流程

1. Triage 分类
2. Root Cause
3. 最小修复
4. 全量复测
5. 追加修复报告

## 5. 证据格式

必须包含：
- commands
- key_outputs
- artifacts
- decision
- residual_risks
