# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 前端统一产品出口第一版
- Phase Code: `P3.phase0`
- Historical Alias: `P3.phaseA`
- Parent Milestone: `P3`（第三阶段）
- Risk Level: `P1`
- Source Documents:
  - `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
  - `docs/architecture/个人投资助理项目-前端技术设计（第四阶段前置版）.md`
  - `docs/project_control/FEATURE_SPEC_P3.phaseA.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/prd_p2.md`

---

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 前端接口出口 | `FEATURE_SPEC_P3.phaseA.md` 中 `frontend_bff / /api/*` 方案 | 直接长期暴露 `theme_service` | 第三阶段必须建立稳定产品出口层 |
| `intel` 聚合接口落点 | 当前 `frontend_bff` 适配实现 | 继续将 `theme_service` 作为前端长期契约 | 现阶段允许内部复用，下游契约必须收口到 BFF |
| 工作台主键 | `subject_key` | `theme_id` 作为统一业务主键 | 当前题材树、rank、history 已统一到 `subject_key` |

---

## 2. Phase Objective（可量化）

1. 建立 `frontend_bff` 第一版服务边界，前端统一经由 `/api/*` 访问后端聚合能力。  
2. 提供 `GET /api/intel/feed`、`GET /api/theme-workspace/{subject_key}`、`GET /api/stock-workspace/{stock_id}` 三个稳定产品出口。  
3. 复用现有 `theme_service` 只读能力完成过渡适配，但不得让前端长期直接绑定领域接口。  
4. 保证 BFF 第一版真实 PostgreSQL 集成测试通过。  
5. 保持股票默认读取主股票池，`leader overlay` 仅作为可选增强。  

---

## 3. Acceptance Targets（门禁条件）

- [ ] 必须存在独立 `frontend_bff` 服务目录与应用入口。
- [ ] 前端产品层必须提供 `/api/intel/feed`、`/api/theme-workspace/{subject_key}`、`/api/stock-workspace/{stock_id}` 三个接口。
- [ ] 前端长期契约必须收口到 `/api/*`，不得再把 `theme_service` 直接作为前端正式出口。
- [ ] `theme-workspace` 必须聚合题材摘要、历史、子题材、股票池。
- [ ] `stock-workspace` 必须聚合个股基础信息与所属题材列表。
- [ ] BFF 真实 PostgreSQL 集成测试必须全部通过。
- [ ] 题材主键必须统一使用 `subject_key`，不得重新引入 `theme_id` 作为统一业务主键。

---

## 4. Required Commands（必须执行命令）

- `POSTGRES_DATABASE=stock_data_test .venv/bin/python -m pytest -q frontend_bff/tests/integration/test_p3_phasea_bff_real_db.py`
- `rg -n "frontend_bff|/api/intel/feed|/api/theme-workspace|/api/stock-workspace" /Users/admin/Desktop/ai_theme_app`
- `.venv/bin/python -m py_compile frontend_bff/app.py frontend_bff/repositories/bff_repository.py`

Acceptance-测试映射：
- `ACPT-P3A-001` -> `TC-P3A-001-bff-health` / `TC-P3A-002-bff-downstream-timeout` / `TC-P3A-003-bff-dto-stability`
- `ACPT-P3A-002` -> `TC-P3A-004-intel-feed-proxy`
- `ACPT-P3A-003` -> `TC-P3A-007-theme-workspace-view`
- `ACPT-P3A-004` -> `TC-P3A-008-stock-workspace-view`

---

## 5. Deliverables

- `frontend_bff` 服务骨架与应用入口。
- `FrontendBffRepository` 聚合适配层。
- `/api/intel/feed`、`/api/theme-workspace/{subject_key}`、`/api/stock-workspace/{stock_id}` 三个接口。
- 真实 PostgreSQL 集成测试：
  - `frontend_bff/tests/integration/test_p3_phasea_bff_real_db.py`
- 文档更新：
  - `docs/project_control/FEATURE_SPEC_P3.phaseA.md`
  - `docs/project_control/PHASE_CONTRACT_P3.phaseA.md`
  - `docs/project_control/reports/phase-P3.phaseA.md`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| BFF 只是透传未真正削弱耦合 | Medium | Medium | 前端仍按领域接口字段开发 | 平台负责人 | 强制以前端 DTO 作为唯一页面契约 |
| 下游字段漂移导致页面不稳定 | High | Medium | `theme_service` 返回结构变化 | 平台负责人 | 在 BFF 层做 DTO 稳定化与兜底 |
| `subject_key` 与 `theme_id` 再次混用 | High | Low | 新页面直接按 `theme_id` 跳转 | 架构负责人 | 明确 `subject_key` 为统一业务主键 |

---

## 7. Rollback Plan

- 代码回滚：
  - 若 BFF 不稳定，可暂时保留前端直连旧接口的开发开关，但不作为正式长期方案。
- 数据回滚：
  - 本阶段不写业务数据，无业务回滚成本。
- 接口回滚：
  - `/api/*` 可先保留最小字段，逐步恢复聚合字段。

---

## 8. Non-Goals

- 不实现 WebSocket / SSE 实时推送。
- 不独立拆出 `intel_service / workspace_service` 运行时服务。
- 不建设完整产业链图谱服务。
- 不重写 `theme_service` 的领域查询内核。
