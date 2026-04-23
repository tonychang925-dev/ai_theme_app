# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 前端统一产品出口第一版
- Phase Code: `P3.phase0`
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
| 第三阶段命名 | `P3.phase0` | `P3.phaseA` 作为主标识 | 统一阶段编号并保留历史别名 |
| 前端出口边界 | `/api/*` 统一出口 | 前端直连领域服务 | 降低耦合并冻结产品契约 |

## 2. Phase Objective（可量化）

1. 建立 `frontend_bff` 统一产品出口，并覆盖情报页、题材工作台、个股工作台。
2. 前端长期契约全部收口到 `/api/*`。
3. 完成真实 PostgreSQL 集成验证，保障接口可用性。

## 3. Acceptance Targets（门禁条件）

- [ ] 必须存在独立 `frontend_bff` 服务目录与应用入口。
- [ ] 必须提供 `GET /api/intel/feed`、`GET /api/theme-workspace/{subject_key}`、`GET /api/stock-workspace/{stock_id}` 三个接口。
- [ ] 前端长期契约必须统一收口到 `/api/*`。
- [ ] `theme-workspace` 必须聚合题材摘要、历史、子题材、股票池。
- [ ] `stock-workspace` 必须聚合个股基础信息与所属题材列表。
- [ ] 真实 PostgreSQL 集成测试必须通过。

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q frontend_bff/tests`
- `.venv/bin/python -m pytest -q frontend_bff/tests/integration`
- `rg -n "frontend_bff|/api/intel/feed|/api/theme-workspace|/api/stock-workspace" frontend_bff docs/project_control`

## 5. Deliverables

- `frontend_bff` 服务入口与路由聚合层
- `/api/intel/feed`、`/api/theme-workspace/{subject_key}`、`/api/stock-workspace/{stock_id}`
- `tmp/phase_contract_P3.phase0.json`
- `tmp/phase_contract_consistency_P3.phase0.json`

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 前端继续直连领域服务 | High | Medium | 页面绕过 BFF 调用 | FE/BFF | 网关与代码扫描门禁 |
| DTO 漂移 | High | Medium | 下游字段变动 | BFF | DTO 版本冻结 + 回归测试 |

## 7. Rollback Plan

- 代码回滚：BFF 接口异常时回退至上一稳定 tag。
- 数据回滚：本阶段无新增业务真源表，无数据回滚动作。
- 同步补偿回滚：补跑 BFF 集成测试与路由健康检查后再恢复发布。

## 8. Non-Goals

- 不引入 SSE。
- 不引入分钟级异动。
- 不建设实时链路。
