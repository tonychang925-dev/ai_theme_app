---
name: feature
description: 将阶段目标拆解为可实施的功能设计与任务清单，强调验收可追溯。
when_to_use: 当用户要求功能开发设计、任务拆分、接口与回滚方案时使用。
model: inherit
effort: high
---

# 功能设计协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`
- `docs/project_control/TASK_BACKEND_CONTRACT.md`

## 1. 输入

- `PRD*.md`
- `ACCEPTANCE*.md`
- `PHASE_CONTRACT_<phase>.md`

## 2. 输出

1. `docs/project_control/FEATURE_SPEC_<phase>.md`
2. `tmp/feature_traceability_<phase>.json`

## 3. 必须覆盖的设计项

1. 任务拆解（task_id、依赖、优先级）
2. 接口契约与错误处理
3. 数据模型与兼容性策略
4. 回滚方案
5. 测试映射（task -> TC-ID -> command）

## 4. 质量前置

1. `P0/P1` 任务必须先定义自动化测试策略再进入实现。
2. `UT -> IT -> E2E/PT` 顺序不得跳过。
3. 状态推进前必须有机读证据路径。

## 5. 去耦规则

1. 不绑定任意外部任务系统字段。
2. 只输出抽象动作，不输出平台调用命令。
