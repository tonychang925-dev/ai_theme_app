---
name: pm-plan
description: 当用户要求“把目标架构拆成里程碑/任务分解/依赖/风险与排期”时使用。
---

# Project Manager Planning Flow

## Outputs (must)
1) docs/project_control/PLAN_WBS.md
2) 每个 Milestone 的：目标、范围、依赖、风险、DoD（完成定义）

## Steps
1) 读取目标架构与 ADR_LIST
2) 产出 Milestones（Phase0..N）与每阶段目标
3) 对每阶段做 WBS：Task 列表 + 依赖 + 风险 + 估算
4) 明确每阶段“验收门禁”：必须有哪些测试/文档/PR
