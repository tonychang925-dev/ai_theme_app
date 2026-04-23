# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 复盘增强与工作台深化
- Phase Code: `P3.phase2`
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
| 复盘聚合层 | `recap_service` 唯一聚合 | 多服务拼装复盘 | 控制一致性 |
| 增强范围 | 日频增强优先 | 提前引入实时链 | 先稳后快 |

## 2. Phase Objective（可量化）

1. 完成龙虎榜与资金行为增强对象收口。
2. 强化龙头/前排/扩散/跟风规则并接入工作台。
3. `/recap` 成为稳定只读出口，来源链覆盖 100%。

## 3. Acceptance Targets（门禁条件）

- [x] 必须增加龙虎榜结构化对象。
- [x] 必须增加资金行为增强字段，但不要求完整主力资金行为体系。
- [x] 必须增强龙头、前排、扩散股规则。
- [x] 必须深化个股工作台，前端不得自行拼装股票多源数据。
- [x] 必须提供 `/recap` 只读产品出口。
- [x] 必须为复盘结论提供来源链。
- [x] 新增增强字段必须向后兼容，不破坏 `P3.phase1` DTO。

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q recap_service/tests`
- `.venv/bin/python -m pytest -q frontend_bff/tests`
- `rg -n "dragon_tiger|money_flow|/recap|workspace" recap_service frontend_bff database_service`

## 5. Deliverables

- 龙虎榜结构化对象与来源链
- 资金行为增强对象
- 工作台统一 DTO
- `/recap` 只读出口
- `tmp/phase_contract_P3.phase2.json`
- `tmp/phase_contract_consistency_P3.phase2.json`

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 来源链缺失 | High | Medium | 无法溯源 | Data | 来源链门禁 |
| DTO 兼容破坏 | High | Medium | 前端回归失败 | BFF | 向后兼容测试 |

## 7. Rollback Plan

- 代码回滚：回退增强字段与角色规则。
- 数据回滚：按 `trade_date/recap_id` 回滚增强快照。
- 同步补偿回滚：基于 `P3.phase1` 对象重建增强对象。

## 8. Non-Goals

- 不引入 SSE。
- 不实现分钟级异动。
