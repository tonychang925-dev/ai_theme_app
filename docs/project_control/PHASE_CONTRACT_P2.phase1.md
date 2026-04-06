# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 题材知识库与产品输出
- Phase Code: P2.phase1
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
| 第二阶段对象模型 | `docs/project_control/prd_p2.md` 中 `P2.phase1` | 架构文档中未分期的完整数据蓝图 | 合同需要冻结本 phase 可交付的知识对象与接口 |
| 展示层/画像层职责 | `ACCEPTANCE.md` 的 `P2.phase1` 条款 | 旧 PRD 中对展示能力的宽泛描述 | 验收强调对象分层和来源追溯，优先采用 |
| WBS 真源 | 本合同内交付项定义 | `PLAN_WBS.md` 无 P2.phase1 | 当前仓库缺少正式第二阶段 WBS |

---

## 2. Phase Objective（可量化）

1. 在已复刻 `theme_master / theme_profile_ext / subject_detail / stocks / subject_stock_map / subject_rank_daily` 和 `theme_data_complete/*` 的基础上，建立 `Core / Profile / Knowledge` 三层题材对象模型。  
2. 建立 `subject_key` 统一业务主键基线与 `真源 -> staging -> serving` 标准化链；`theme_id` 仅作为 L3 实体引用。  
3. 优先建设视图整合层：`vw_subject_theme_binding / vw_theme_rank_current / vw_theme_detail_joined / vw_theme_stock_map_candidate / vw_theme_tree_candidate / vw_theme_history_candidate`。  
4. 在确有版本冻结、审计、人工修订或性能兜底需要时，再落地 `theme_detail_snapshot / theme_history_event / theme_tree_relation / theme_stock_map` 四类 serving 知识对象。  
5. 提供 `/themes`、`/themes/rank`、`/themes/{subject_key}`、`/themes/{subject_key}/history`、`/themes/{subject_key}/children`、`/themes/{subject_key}/stocks` 五类核心接口，其中 `theme_rank_api` 第一版允许直接基于 `subject_rank_daily`/视图层。  
6. 详情/榜单接口查询时延满足 `P95 < 500ms`。  
7. 详情、历史、股票映射均可追溯来源。  
8. 建立久赢恒丰日常增量同步方案：固定 `远端 API -> theme_data_complete -> 增量导库 -> serving 刷新` 路线，并冻结批次 manifest、文件/subject 增量判定与幂等重放规则。

---

## 3. Acceptance Targets（门禁条件）

- [ ] 系统必须建立 `Core / Profile / Knowledge` 三层题材对象模型，禁止混表混职责。
- [ ] `theme_master / theme_profile_ext / subject_detail / stocks` 必须被固定为本 phase 真源输入，不得重复新建等价平行主表。
- [ ] `subject_stock_map / subject_rank_daily` 与 `theme_data_complete/history / children / details / daily / stock_details / lists` 必须被固定为本 phase 真源输入。
- [ ] 必须形成 `subject_node_staging / theme_hierarchy_staging / subject_history_staging / subject_children_staging / subject_stock_detail_staging` 标准化层，之后才允许推进 serving 表与 API。
- [ ] 必须先完成 `subject_key` 统一业务主键基线，后续 serving 回填不得跳过该层；`theme_id` 不得被误当作 L1/L2/L3 通用主键。
- [ ] 必须优先交付视图整合层，未证明视图不足前不得直接扩张 serving 表数量。
- [ ] `theme_detail_snapshot` 与 `theme_history_event` 必须可追溯到 `event_id` 或明确外部来源。
- [ ] `theme_tree_relation` 与 `theme_stock_map` 必须输出结构化关系类型与证据来源。
- [ ] 系统必须提供 `/themes`、`/themes/rank`、`/themes/{subject_key}`、`/themes/{subject_key}/history`、`/themes/{subject_key}/children`、`/themes/{subject_key}/stocks`、`/stocks/{stock_id}/themes` 核心只读接口。
- [ ] 展示快照不得直接承担在线检索索引职责。
- [ ] 详情/榜单接口查询时延 P95 必须小于 `500ms`。
- [ ] 必须形成唯一久赢采集入口、`jyhf_sync_batch / jyhf_sync_file_manifest / jyhf_sync_subject_state` 三张同步状态表，以及 `nodes/history/detail/stock` 四条增量导库链。
- [ ] 日常同步不得继续依赖 patch 脚本和全量清空重建；失败补偿必须支持按 `subject_key` 重放。

---

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q`
- `rg -n "theme_master|theme_profile_ext|subject_detail|stocks|theme_detail_snapshot|theme_history_event|theme_tree_relation|theme_stock_map" .`
- `rg -n -F "/themes/rank" docs/project_control/prd_p2.md docs/project_control/ACCEPTANCE.md`
- `rg -n -F "/themes/{subject_key}" docs/project_control/prd_p2.md docs/project_control/ACCEPTANCE.md`
- `rg -n -F "/stocks/{stock_id}/themes" docs/project_control/prd_p2.md docs/project_control/ACCEPTANCE.md`
- `rg -n "import_jyhf_data_optimized|import_jyhf_full_theme_and_children_patch|import_jyhf_to_financial_and_theme|import_single_subject_knowledge|import_jyhf_gate_profile|theme_collector|audit_jyhf_subject_coverage" .`

Acceptance-测试映射：
- `ACPT-P2.phase1-001` -> `ACC-P2.phase1-04` -> `rg -n "theme_master|theme_profile_ext|subject_detail|stocks|theme_detail_snapshot|theme_history_event|theme_tree_relation|theme_stock_map" .`
- `ACPT-P2.phase1-002` -> `ACC-P2.phase1-02` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase1-003` -> `ACC-P2.phase1-03` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase1-004` -> `ACC-P2.phase1-01` / `ACC-P2.phase1-02` / `ACC-P2.phase1-03` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase1-005` -> `ACC-P2.phase1-04` -> `rg -n "theme_master|theme_profile_ext|subject_detail|stocks|theme_detail_snapshot|theme_history_event|theme_tree_relation|theme_stock_map" .`
- `ACPT-P2.phase1-006` -> `ACC-P2.phase1-01` -> `.venv/bin/python -m pytest -q`
- `ACPT-P2.phase1-007` -> `ACC-P2.phase1-05` -> `rg -n "import_jyhf_data_optimized|import_jyhf_full_theme_and_children_patch|import_jyhf_to_financial_and_theme|theme_collector" .`

---

## 5. Deliverables

- 三层题材对象模型定义与字段边界说明。
- 已复刻真源表清单与使用边界说明：`theme_master / theme_profile_ext / subject_detail / stocks / subject_stock_map / subject_rank_daily`。
- 文件真源清单与使用边界说明：`theme_data_complete/history / children / details / daily / stock_details / lists`。
- `subject_theme_binding` 与 staging 规范说明。
- 视图整合层清单与字段契约说明。
- `theme_detail_snapshot` / `theme_history_event` / `theme_tree_relation` / `theme_stock_map` 结构定义。
- 核心查询 API 契约说明。
- 来源追溯与快照版本策略。
- 久赢恒丰增量同步设计说明：唯一采集入口、批次 manifest、文件/subject 状态表、四条增量导库链、脚本职责矩阵。
- 文档更新：
  - `docs/project_control/PHASE_CONTRACT_P2.phase1.md`
  - `tmp/phase_contract_P2.phase1.json`
  - `tmp/phase_contract_consistency_P2.phase1.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 展示层与画像层混写 | High | Medium | 同对象同时承担展示与检索 | 数据架构负责人 | Core/Profile/Knowledge 强分层 |
| 历史驱动来源断链 | Medium | Medium | history 无法回溯 event/source | 数据负责人 | 强制来源字段与快照版本 |
| 股票映射证据薄弱 | Medium | Medium | relation_type/evidence_source 缺失 | 产品数据负责人 | 关系类型标准化 + 审计字段 |
| API 契约不稳定 | High | Medium | 不同接口返回结构漂移 | 平台负责人 | 统一 schema 与回归测试 |
| 接口时延超阈值 | Medium | Medium | P95 超过 500ms | 平台负责人 | 索引/缓存/快照读路径优化 |

---

## 7. Rollback Plan

- 代码回滚：
  - 触发条件：对象模型耦合失控、API 契约不稳定。
  - 方式：回切到上一个稳定读路径，保留数据快照。
- 数据回滚：
  - 触发条件：错误快照覆盖、历史追溯断链、错误股票映射批量写入。
  - 方式：按 `snapshot_version/theme_id` 回滚。
- 同步补偿回滚：
  - 触发条件：知识对象与展示接口数据不一致。
  - 方式：从主对象重建快照与索引。

---

## 8. Non-Goals

- 不实现热度公式和生命周期状态机（P2.phase3）。
- 不提供投资建议或交易策略。
- 不重做 P2.phase0 匹配内核。
- 不重复建设与 `theme_master / theme_profile_ext / subject_detail / stocks` 等价的平行基础表。

---

## 9. 状态同步与对账基线

- `Doing -> test-evidence -> In review/done -> milestone progress`
- 对账必须区分对象层：Core / Profile / Knowledge
- 接口验收必须同步检查来源追溯字段
