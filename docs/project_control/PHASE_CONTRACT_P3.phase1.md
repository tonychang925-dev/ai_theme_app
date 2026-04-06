# Phase Execution Contract

## 1. Phase Identity

- Phase Name: Stock Service 双源事实层与复盘快照
- Phase Code: `P3.phase1`
- Parent Milestone: `P3`（第三阶段）
- Risk Level: `P1`
- Source Documents:
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/adrs/ADR_LIST.md`
  - `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
  - `docs/project_control/PHASE_CONTRACT_P3.phaseA.md`

---

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 股票事实真源 | `PRD.md` + `ADR-020` 中 `Tushare` 作为股票日频真源 | 将 `JYHF` 继续当作股票事实唯一真源 | 第三阶段首批必须把题材语义和股票事实分离 |
| 首批上线门槛 | `ACCEPTANCE.md` + `ARCH_REVIEW.md` 中“快照优先、实时后置” | 将“秒级全市场实时行情/全量资金行为分析”作为 `P3.phase1` 门槛 | 当前阶段目标是稳定对象层与复盘快照，不是实时平台 |
| 服务边界 | `ADR-022/023/024` 中 `stock_service=事实对象层`、`recap_service=唯一报告聚合层`、`Notion=输出层` | 在 `stock_service` 中同时实现报告拼装和 Notion 发布 | 避免职责膨胀与报告真源漂移 |
| 第三阶段前置依赖 | `PLAN_WBS.md` 中 `P3.phase0 -> P3.phase1` | 直接绕过 `frontend_bff` / `P3.phase0` 进入事实层开发 | 第三阶段必须建立在统一产品出口和长期契约之上 |

---

## 2. Phase Objective（可量化）

1. 接入 `Tushare + JYHF` 双源，并按交易日产出可完整回放的 `stock_daily_snapshot` 与 `subject_stock_daily_snapshot`。  
2. 在对象层上稳定生成 `stock_abnormal_event` 与 `theme_stock_leaderboard`，保证规则显式、可追溯、可重复。  
3. 生成 `pre_market_brief_snapshot` 与 `post_market_recap_snapshot`，并保证同一交易日重复生成结果一致率 `100%`。  
4. 前端与 Notion 必须只消费同一份报告快照；`Notion` 发布失败不得阻塞主链。  
5. 本阶段明确不以 `SSE`、分钟级异动、秒级全市场实时行情或全量资金行为分析作为上线门槛。  

---

## 3. Acceptance Targets（门禁条件）

- [ ] 必须完成 `Tushare` 日频真源接入，并形成可回放的股票原始快照与标准化入库链。
- [ ] 必须完成 `JYHF` 题材事件与题材股票池复用，并与股票快照形成稳定绑定。
- [ ] 必须生成 `stock_daily_snapshot` 与 `subject_stock_daily_snapshot`。
- [ ] 必须生成 `stock_abnormal_event` 与 `theme_stock_leaderboard`。
- [ ] 必须生成 `pre_market_brief_snapshot` 与 `post_market_recap_snapshot`。
- [ ] `frontend_bff` 与 `notion_publisher` 必须消费同一份报告快照。
- [ ] `stock_service` 不得承担 Notion 发布与报告拼装职责。
- [ ] 任一交易日对象层与报告快照必须支持完整回放。
- [ ] Notion 发布失败不得阻塞快照落库，且必须保留失败原因。
- [ ] 不得把“秒级全市场实时行情”和“全量资金行为分析”作为本阶段通过门槛。

---

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q`
- `rg -n "stock_daily_snapshot|subject_stock_daily_snapshot|stock_abnormal_event|theme_stock_leaderboard|pre_market_brief_snapshot|post_market_recap_snapshot" /Users/admin/Desktop/ai_theme_app`
- `rg -n "Tushare|JYHF|notion_publisher|stock_service|recap_service" /Users/admin/Desktop/ai_theme_app/docs/project_control /Users/admin/Desktop/ai_theme_app/docs/adrs`
- `.venv/bin/python -m py_compile stock_service recap_service frontend_bff`

Acceptance-测试映射：
- `ACPT-P3B-001` -> `ACC-P3B-001` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3B-002` -> `ACC-P3B-001` / `ACC-P3B-002` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3B-003` -> `ACC-P3B-001` -> `rg -n "stock_daily_snapshot|subject_stock_daily_snapshot" /Users/admin/Desktop/ai_theme_app`
- `ACPT-P3B-004` -> `ACC-P3B-002` -> `rg -n "stock_abnormal_event|theme_stock_leaderboard" /Users/admin/Desktop/ai_theme_app`
- `ACPT-P3B-005` -> `ACC-P3B-003` -> `rg -n "pre_market_brief_snapshot|post_market_recap_snapshot" /Users/admin/Desktop/ai_theme_app`
- `ACPT-P3B-006` -> `ACC-P3B-004` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3B-007` -> `ACC-P3B-003` / `ACC-P3B-004` -> `.venv/bin/python -m pytest -q`

---

## 5. Deliverables

- `stock_service` 事实对象层边界定义。
- `Tushare + JYHF` 双源字段所有权与冲突裁决规则。
- `stock_daily_snapshot / subject_stock_daily_snapshot` 对象定义与标准化链。
- `stock_abnormal_event / theme_stock_leaderboard` 派生规则定义。
- `pre_market_brief_snapshot / post_market_recap_snapshot` 报告快照定义。
- `frontend_bff` 只读消费契约。
- `notion_publisher` 输出契约与失败重试策略。
- 文档更新：
  - `docs/project_control/PHASE_CONTRACT_P3.phase1.md`
  - `tmp/phase_contract_P3.phase1.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 双源字段口径漂移 | High | Medium | 同一业务字段由 `Tushare` 和 `JYHF` 同时提供且结果不一致 | 数据架构负责人 | 冻结字段所有权与冲突裁决规则 |
| `stock_service` 职责膨胀 | High | High | 报告拼装、Notion 写入直接压入 `stock_service` | 平台负责人 | 强制维持事实对象层边界 |
| 报告快照与 Notion 漂移 | High | Medium | 页面与 Notion 核心字段不一致 | 产品架构负责人 | 冻结快照唯一真源 |
| Notion 发布阻塞主链 | Medium | Medium | 发布失败导致日频任务整体失败 | 平台负责人 | 异步重试 + 主链隔离 |
| 将实时能力错误前移 | High | Medium | 评审或实施中出现 `SSE/分钟级异动` 作为首批门槛 | 架构负责人 | 严格按 `P3.phase1 -> P3.phase3` 顺序推进 |

---

## 7. Rollback Plan

- 代码回滚：
  - 触发条件：对象层职责失控、BFF/Notion 契约漂移、报告生成逻辑不可重复。
  - 方式：回切到上一版稳定对象层与报告模板，保留原始快照文件。
- 数据回滚：
  - 触发条件：某交易日快照缺失、错误覆盖或报告快照不一致。
  - 方式：按 `trade_date / snapshot_version / report_id` 回滚对象层和快照。
- 同步补偿回滚：
  - 触发条件：`Tushare` 原始快照、标准化对象、报告快照三层不一致。
  - 方式：从原始快照重新标准化并重建当日对象层与报告快照。

---

## 8. Non-Goals

- 不实现 `SSE / WebSocket` 实时推送。
- 不实现分钟级异动对象。
- 不实现全量资金行为分析。
- 不建设 Tick 级全市场实时行情平台。
- 不把 Notion 作为业务真源或回写源。

---

## 9. 状态同步与对账基线

- `Doing -> test-evidence -> In review/done -> milestone progress`
- 阶段内所有对象层、报告快照、Notion 发布记录都必须保留 `trade_date / report_id / publish_status`。
- 阶段末对账必须区分：
  - `stock_daily_snapshot`
  - `subject_stock_daily_snapshot`
  - `stock_abnormal_event`
  - `theme_stock_leaderboard`
  - `pre_market_brief_snapshot`
  - `post_market_recap_snapshot`
- 本阶段在正式 `TEST_CASE_SPEC` 补齐前，合同状态为 Draft，`gate_ready=false`。
