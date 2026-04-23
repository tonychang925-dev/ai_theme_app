# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 实时化与高级增强
- Phase Code: `P3.phase3`
- Parent Milestone: `P3`
- Risk Level: `P1`
- Source Documents:
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/prd_p3.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 实时出口 | REST + SSE 双轨 | 仅 SSE | 保障断线回补 |
| 实时边界 | 轻量增强 | Tick 级平台 | 保持可交付范围 |

## 2. Phase Objective（可量化）

1. 建立 `/intel` SSE 实时出口与 REST 回补。
2. 建立分钟级异动增强与联动展示。
3. 保证实时链故障不影响日频主链。

## 3. Acceptance Targets（门禁条件）

- [ ] 必须提供 `/api/intel/stream` 或等价 `SSE` 实时出口。
- [ ] 必须保留既有 `REST` 接口作为断线回补兜底。
- [ ] 必须增加分钟级异动增强对象。
- [ ] 必须实现情报流与股票异动联动展示。
- [ ] 必须提供轻量产业链视图。
- [ ] 实时链故障不得影响盘前/盘后快照主链。
- [ ] 不得把本阶段膨胀为 Tick 级全市场实时平台。

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q intel_service/tests`
- `.venv/bin/python -m pytest -q frontend_bff/tests`
- `rg -n "SSE|/intel/stream|minute_abnormal_event|industry_chain" frontend_bff intel_service recap_service`

## 5. Deliverables

- `/intel` SSE 与 REST 双轨
- 分钟级异动对象
- 情报/异动联动
- 轻量产业链视图
- `tmp/phase_contract_P3.phase3.json`
- `tmp/phase_contract_consistency_P3.phase3.json`

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| SSE 不稳定 | High | Medium | 断连频繁 | Realtime | REST 回补 |
| 实时链污染主链 | High | Medium | 日频任务失败 | Platform | 主链隔离 |

## 7. Rollback Plan

- 代码回滚：关闭 SSE 与分钟级增强，保留 REST。
- 数据回滚：回滚分钟级对象批次。
- 同步补偿回滚：按游标重放并补拉缺失。

## 8. Non-Goals

- 不建设 Tick 级实时平台。
- 不建设高频策略引擎。
