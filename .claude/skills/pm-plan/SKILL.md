---
name: pm-plan
description: 将目标拆解为里程碑、WBS、依赖、风险与排期；输出可执行项目计划（去 Notion 耦合版）。
when_to_use: 当用户要求项目分阶段计划、任务拆解、依赖关系、排期与风险控制时使用。
model: inherit
effort: high
---

# 项目规划协议（去耦版）

统一约束：
- `docs/project_control/EXECUTION_GUARDRAILS.md`

## 1. 目标

生成可执行、可验收、可追踪的项目计划，不依赖外部 PM 系统。

## 2. 输入优先级

1. `docs/project_control/PRD*.md`
2. `docs/project_control/ACCEPTANCE*.md`
3. `docs/architecture/*`
4. `docs/adrs/*`
5. `docs/project_control/ARCH_REVIEW*.md`

## 3. 输出文件

1. `docs/project_control/PLAN_WBS.md`
2. `docs/project_control/MILESTONE_GATES.md`
3. `tmp/pm_plan_payload.json`

## 4. 强制结构

`PLAN_WBS.md` 必须包含：
- 规划范围与边界
- 里程碑总览（Phase/Objective/Duration/Dependency）
- WBS 任务表（Task ID/Owner/Estimate/Depends On/Validation）
- 关键路径与并行段
- 风险矩阵（P0/P1/P2 + 缓解措施）

`MILESTONE_GATES.md` 必须包含：
- 每个里程碑的 DoD
- 必跑命令与通过阈值
- 失败判定与回滚策略

## 5. 执行规则

1. 只做规划，不改业务代码。
2. 任务必须可验收，禁止“优化一下”类空泛描述。
3. 每个里程碑必须有明确门禁和失败判定。
4. 所有任务必须可追溯到 PRD/架构目标。

## 6. 禁止项

1. 不直接调用 Notion/Jira/飞书 API。
2. 不写入密钥到仓库。
3. 不把“同步外部系统成功”作为唯一交付标准。
