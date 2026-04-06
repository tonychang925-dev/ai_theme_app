# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 情报列表页前置交付
- Phase Code: `P4.phaseA`
- Parent Milestone: `P4`（第四阶段前置）
- Risk Level: `P1`
- Source Documents:
  - `docs/architecture/个人投资助理项目-前端技术设计（第四阶段前置版）.md`
  - `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
  - `docs/project_control/FEATURE_SPEC_P4.phaseA.md`
  - `docs/project_control/FEATURE_SPEC_P3.phaseA.md`
  - `docs/project_control/ACCEPTANCE.md`

---

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 前端接入方式 | `frontend_bff:/api/*` | 直接长期依赖 `theme_service` | 已完成第三阶段前置 BFF，前端应直接切换 |
| 页面范围 | `P4.phaseA` 的 `intel -> theme workspace -> stock workspace` 最小闭环 | 一次性做完整交易终端 | 现阶段目标是可展示情报产品，不是完整行情终端 |
| 股票映射口径 | 默认主股票池，leader overlay 可选 | 默认混合返回全部增强关系 | 当前产品层必须先保证语义稳定 |

---

## 2. Phase Objective（可量化）

1. 建立 `frontend/` 前端工程并完成可构建交付。  
2. 交付 `/intel` 情报列表页，集中展示当天新闻事件、题材异动、新题材候选。  
3. 完成题材工作台与个股工作台联动，形成 `intel -> theme -> stock` 最小页面闭环。  
4. 页面状态支持 URL 同步，刷新后可恢复关键筛选与选中状态。  
5. 前端生产构建必须稳定通过。  

---

## 3. Acceptance Targets（门禁条件）

- [ ] 必须存在独立 `frontend/` 工程目录，并可执行 `npm run build`。
- [ ] 必须存在 `/intel` 页面，且能读取 `/api/intel/feed`。
- [ ] 必须存在 `/themes/:subject_key` 页面。
- [ ] 必须存在 `/stocks/:stock_id` 页面。
- [ ] `/intel` 页面必须具备题材工作台联动与个股工作台联动。
- [ ] 页面必须支持 URL 状态同步，至少覆盖 `date/type/session/item/stock`。
- [ ] 三类情报 `event / theme_move / new_theme` 必须有明确视觉分型。
- [ ] 前端接口调用必须经由 `frontend_bff:/api/*`，不得继续将 `theme_service` 作为长期页面契约。

---

## 4. Required Commands（必须执行命令）

- `cd /Users/admin/Desktop/ai_theme_app/frontend && npm run build`
- `rg -n "/intel|/themes/:subject_key|/stocks/:stock_id|theme-workspace|stock-workspace" /Users/admin/Desktop/ai_theme_app/frontend/src`
- `POSTGRES_DATABASE=stock_data_test .venv/bin/python -m pytest -q frontend_bff/tests/integration/test_p3_phasea_bff_real_db.py`

Acceptance-测试映射：
- `ACPT-P4A-001` -> `TC-P4A-005-intel-page-load`
- `ACPT-P4A-002` -> `TC-P4A-006-intel-filters`
- `ACPT-P4A-003` -> `TC-P4A-007-intel-item-select`
- `ACPT-P4A-004` -> `npm run build`

---

## 5. Deliverables

- `frontend/` 工程脚手架与构建配置。
- `/intel` 页面。
- `/themes/:subject_key` 页面。
- `/stocks/:stock_id` 页面。
- 页面联动与 URL 状态同步。
- 文档更新：
  - `docs/project_control/FEATURE_SPEC_P4.phaseA.md`
  - `docs/project_control/PHASE_CONTRACT_P4.phaseA.md`
  - `docs/project_control/reports/phase-P4.phaseA.md`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 页面继续耦合底层领域接口 | High | Medium | 前端直接请求 `theme_service` | 前端负责人 | 强制走 BFF adapter |
| 情报流密度高导致可读性差 | Medium | Medium | 列表信息层级混乱 | 产品负责人 | 强化视觉分型与详情抽屉 |
| 构建环境不稳定 | Medium | Medium | `npm install/build` 失败 | 前端负责人 | 锁定依赖并保留构建结果校验 |

---

## 7. Rollback Plan

- 页面回滚：
  - 若工作台联动异常，可先保留 `/intel` 列表页，关闭详情跳转。
- 构建回滚：
  - 若样式/路由改动导致构建失败，可回滚到上一个可构建提交。
- 接口回滚：
  - 若 BFF 聚合字段不稳定，可先只保留 `/api/intel/feed` 基础列表能力。

---

## 8. Non-Goals

- 不实现实时行情图、分时图与交易终端。
- 不实现完整复盘系统。
- 不实现消息推送与桌面通知。
- 不实现完整权限体系与登录系统。
