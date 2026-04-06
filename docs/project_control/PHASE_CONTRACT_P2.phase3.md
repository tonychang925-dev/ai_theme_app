# Phase Execution Contract

## 1. Phase Identity

- Phase Name: Unknown 与新题材闭环
- Phase Code: P2.phase3
- Parent Milestone: P2（第二阶段）
- Risk Level: P1
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
| Unknown 范围 | `docs/project_control/prd_p2.md` 与 `docs/project_control/ACCEPTANCE.md` 的 `P2.phase3` | `ARCH_REVIEW.md` 中对 `P2.phase0` 的“只做事件级 Unknown”限制 | 该限制仅适用于首期，P2.phase3 正式进入聚类与草案闭环 |
| 任务真源 | 本合同内交付项定义 | `PLAN_WBS.md` 中无 P2 任务 | 仓库尚无第二阶段 WBS，需先冻结执行边界 |
| 自动建题材能力 | `ACCEPTANCE.md` 的审核优先路径 | 架构文档中的最终全自动愿景 | 当前阶段只允许草案与审核闭环，不允许直接上线正式题材 |

---

## 2. Phase Objective（可量化）

1. 将全部 `UNKNOWN` 事件稳定写入 `unknown_event_pool`，入池成功率 `100%`。  
2. 建立基于时间窗、相似度、对象词稳定性的 Unknown 聚类机制。  
3. 满足阈值的聚类结果只生成 `new_theme_draft`，不得直接创建正式题材。  
4. 建立 `create_theme / merge_to_existing_theme / defer_observation` 审核闭环，并确保动作可回放。  

---

## 3. Acceptance Targets（门禁条件）

- [ ] 所有 `UNKNOWN` 结果必须进入统一 `unknown_event_pool`，且保留 `event_id/trace_id/reason/evidence`。
- [ ] Unknown 聚类必须基于时间窗、相似度和对象词稳定性执行，阈值必须可配置。
- [ ] 达到阈值的 Unknown 簇只能生成 `new_theme_draft`，不得直接创建正式题材。
- [ ] 新题材草案必须进入合并审核流程，并支持 `create_theme / merge_to_existing_theme / defer_observation` 三类结果。
- [ ] 所有聚类与审核动作必须具备可回放审计记录。
- [ ] Unknown 池事件不得丢失，入池成功率必须达到 `100%`。

---

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q`
- `rg -n "new_theme_draft|unknown_event_pool|theme_merge_review|theme_master" .`

Acceptance-测试映射：
- `ACPT-P2.phase3-001` -> `ACC-P2.phase3-01` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase3-002` -> `ACC-P2.phase3-02` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase3-003` -> `ACC-P2.phase3-03` -> `rg -n "new_theme_draft|unknown_event_pool|theme_merge_review|theme_master" .`
- `ACPT-P2.phase3-004` -> `ACC-P2.phase3-04` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase3-005` -> `ACC-P2.phase3-02` / `ACC-P2.phase3-04` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase3-006` -> `ACC-P2.phase3-01` -> `.venv/bin/python -m pytest -q`

---

## 5. Deliverables

- `unknown_event_pool` 对象与入池协议。
- Unknown 聚类规则与阈值配置说明。
- `new_theme_draft` 草案结构与生成规则。
- `theme_merge_review` 审核动作与审计协议。
- 文档更新：
  - `docs/project_control/PHASE_CONTRACT_P2.phase3.md`
  - `tmp/phase_contract_P2.phase3.json`
  - `tmp/phase_contract_consistency_P2.phase3.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| Unknown 池丢事件 | High | Medium | `UNKNOWN` 未入池或无法追溯 | 平台负责人 | 入池成功率监控 + 强制审计字段 |
| 聚类阈值过松导致草案爆炸 | High | Medium | 草案数量异常上升 | 算法负责人 | 保守阈值 + 审核门禁 |
| 聚类阈值过严导致漏发现 | Medium | Medium | 长期 Unknown 无成团 | 算法负责人 | 周期性复盘与阈值校准 |
| 草案绕过审核直接上线 | High | Low | 直接写入 `theme_master` | 平台负责人 | 明确禁止路径并做结构扫描 |
| 审核动作不可回放 | Medium | Medium | 审核结果无 trace | 数据负责人 | 审核动作全量审计 |

---

## 7. Rollback Plan

- 代码回滚：
  - 触发条件：聚类任务异常、草案生成错误、审核链路不稳定。
  - 方式：保留 Unknown 入池，停用聚类与草案生成任务。
- 数据回滚：
  - 触发条件：错误草案批量生成或误合并。
  - 方式：按 `cluster_id/draft_id` 回滚草案与审核记录，不影响原始 Unknown 池。
- 同步补偿回滚：
  - 触发条件：Unknown 池、聚类结果、审核结果状态不一致。
  - 方式：从 Unknown 池重放聚类与审核计算。

---

## 8. Non-Goals

- 不上线正式自动新题材创建。
- 不实现久赢式详情/历史/股票映射（P2.phase1）。
- 不实现热度/生命周期状态机（P2.phase2）。
- 不回改 `P2.phase0` 的三态决策契约。

---

## 9. 状态同步与对账基线

- `Doing -> test-evidence -> In review/done -> milestone progress`
- 阶段内所有草案与审核动作必须保留可审计证据
- 阶段末对账必须区分 `unknown_event_pool`、`new_theme_draft`、`theme_merge_review`
