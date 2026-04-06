# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 热度、生命周期与榜单运营化
- Phase Code: P2.phase2
- Parent Milestone: P2（第二阶段）
- Risk Level: P2
- Source Documents:
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/adrs/ADR_LIST.md`

---

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 热度与生命周期范围 | `docs/project_control/prd_p2.md` 中 `P2.phase2` | 架构文档中的长周期终态描述 | 合同只冻结本阶段可执行指标、状态机与榜单能力 |
| 热榜时延指标 | `docs/project_control/ACCEPTANCE.md` 中 `P2.phase2` | 架构文档中未量化表述 | 验收已有明确 P95 目标 |
| WBS 真源 | 本合同交付项定义 | `PLAN_WBS.md` 无 P2.phase2 | 第二阶段正式任务拆解仍缺失 |

---

## 2. Phase Objective（可量化）

1. 建立可解释的题材热度模型，热度构成字段完整率 `100%`。  
2. 建立生命周期状态机：`seed/emerging/hot/diffusing/cooling/archive`。  
3. 榜单更新链路满足刷新延迟 `P95 < 5 分钟`。  
4. 热度与生命周期状态变更可回放，可追溯到 `event_id/theme_id/trace_id`。  
5. 榜单接口在刷新窗口内不得返回空榜。  

---

## 3. Acceptance Targets（门禁条件）

- [ ] 系统必须建立可解释的题材热度模型，且热度构成字段完整率达到 `100%`。
- [ ] 每个题材必须维护 `seed/emerging/hot/diffusing/cooling/archive` 生命周期状态，迁移规则必须显式配置。
- [ ] 榜单更新链路必须稳定输出，刷新延迟 P95 小于 `5 分钟`。
- [ ] 热度与生命周期变更必须支持审计回放，可回溯到 `event_id/theme_id/trace_id`。
- [ ] 榜单接口在刷新窗口内不得返回空榜。

---

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q`
- `rg -n "heat_value|heat_level|lifecycle_state|state_transition_reason|rank_refresh_latency_ms" .`

Acceptance-测试映射：
- `ACPT-P2.phase2-001` -> `ACC-P2.phase2-01` / `ACC-P2.phase2-03` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase2-002` -> `ACC-P2.phase2-02` / `ACC-P2.phase2-03` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase2-003` -> `ACC-P2.phase2-01` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase2-004` -> `ACC-P2.phase2-03` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase2-005` -> `ACC-P2.phase2-01` -> `.venv/bin/python -m pytest -q`

---

## 5. Deliverables

- 热度因子模型与计算口径说明。
- 生命周期状态机与迁移规则说明。
- 榜单刷新链路与回放协议。
- 热度/状态审计字段规范。
- 文档更新：
  - `docs/project_control/PHASE_CONTRACT_P2.phase2.md`
  - `tmp/phase_contract_P2.phase2.json`
  - `tmp/phase_contract_consistency_P2.phase2.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 热度模型不可解释 | High | Medium | 无法解释榜单结果 | 产品负责人 | 强制输出因子明细 |
| 生命周期规则漂移 | Medium | Medium | 状态迁移不可复现 | 架构负责人 | 显式状态机配置 |
| 榜单刷新超时 | Medium | Medium | P95 超过 5 分钟 | 平台负责人 | 批处理优化与监控 |
| 榜单空榜 | High | Low | 刷新窗口返回空响应 | 平台负责人 | 刷新保护与回退快照 |
| 审计链不完整 | Medium | Medium | 无法回放某题材状态变化 | 数据负责人 | 统一 trace_id/theme_id/event_id 约束 |

---

## 7. Rollback Plan

- 代码回滚：
  - 触发条件：热榜异常抖动、状态迁移错误、刷新链路不稳定。
  - 方式：回切到上一个稳定榜单与状态读路径。
- 数据回滚：
  - 触发条件：错误热度批次或错误状态批量写入。
  - 方式：按日期批次和 `theme_id` 回滚热度/状态数据。
- 同步补偿回滚：
  - 触发条件：榜单接口、热度表、生命周期表之间不一致。
  - 方式：依据事件与快照重算热度批次并重放状态机。

---

## 8. Non-Goals

- 不实现自动投资建议或交易决策。
- 不重做 P2.phase1 的知识对象体系。
- 不修改 P2.phase0/P2.phase3 的匹配和 Unknown 主链路。

---

## 9. 状态同步与对账基线

- `Doing -> test-evidence -> In review/done -> milestone progress`
- 榜单刷新批次必须与热度批次、生命周期批次对账
- 回放验证必须覆盖 `theme_id/event_id/trace_id`
