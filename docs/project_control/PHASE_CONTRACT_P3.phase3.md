# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 实时化与高级增强
- Phase Code: `P3.phase3`
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
  - `docs/project_control/PHASE_CONTRACT_P3.phase2.md`

---

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 实时链形态 | `ADR-025` 中 `REST + SSE` 双轨 | 仅轮询或直接全量 WebSocket 化 | 需要兼顾实时性、复杂度和断线回补 |
| 分钟级异动进入时机 | `ADR-026` 中“晚于日频对象层，仅在 `P3.phase3` 进入” | 在 `P3.phase1/2` 提前建设分钟级链路 | 对象层与复盘链必须先稳定 |
| 大环境分钟指标口径 | 当前只允许 `daily_proxy`，分钟真值放入 `P3.phase3` | 在无真实分钟源时把代理值包装成分钟真值 | 必须避免错误精度和误导性展示 |
| 产业链视图边界 | `ADR-027` 中“轻量只读视图，不是正式图谱真源” | 在本阶段直接建设重型图谱服务 | 当前真源和范围不足以支撑重型图谱 |
| 实时解释口径 | `ADR-028` 中“候选归因，不做确定性真因” | 把资讯直接输出为涨停确定性真因 | 必须避免误导性的强因果结论 |
| 集合竞价范围 | `auction_result_validation.v1`，仅做结果层验证 | 把当前 `stk_auction` 方案直接等同于完整路径识别 | 当前尚无 `9:20~9:25` 时间序列与盘口队列 |
| 异动股票复盘口径 | `stock_abnormal_signal` 第一版仅覆盖高换手/放量倍量/尾盘抢筹 | 在无真实盘口时伪造“尾盘巨量未成交挂单”真值 | 必须先保证异动事实可追溯，后续再升级盘口层 |

---

## 2. Phase Objective（可量化）

1. 为 `/intel` 建立 `REST + SSE` 双轨实时链，保证新增事件到前端可见的 P95 延迟小于 `3s`。  
2. 引入 `minute_abnormal_event`，覆盖分钟级涨速、放量、封板/开板变化等可解释异动。  
3. 实现情报流、股票异动与题材角色变化的联动展示，并保留来源链与类型标签。  
4. 提供轻量产业链只读视图，支持题材 -> 环节 -> 股票的层级浏览。  
5. 保证实时链故障不影响 `P3.phase0~2` 已稳定的快照主链和复盘链。  
6. 为前一晚候选池补齐 `auction_result_validation.v1`，支持 9:25 后输出 `strong / watch / invalid` 和盘后日频验证。  
7. 增加 `stock_abnormal_signal`，为盘后复盘和次日观察池提供高换手、放量/倍量、尾盘抢筹的异动事实层。  

---

## 3. Acceptance Targets（门禁条件）

- [ ] 必须为 `/intel` 提供 `SSE` 实时出口。
- [ ] 必须保留既有 `REST` 接口作为断线恢复与回补路径。
- [ ] 必须增加分钟级异动增强对象。
- [ ] 只有在接入真实分钟数据源后，才允许把大环境中的“昨日涨停早盘表现 / 冲高回落比例 / 高标早盘强弱”升级成分钟真值。
- [ ] 必须实现情报流与股票异动的联动展示。
- [ ] 必须提供轻量产业链视图。
- [ ] 必须增加实时条目的去重与优先级排序策略。
- [ ] 必须增加 `stock_abnormal_signal`，且第一版至少覆盖高换手、放量/倍量、尾盘抢筹三类异动。
- [ ] 在无真实盘口/委托源时，不得把“尾盘巨量未成交挂单”写成正式真值。
- [ ] 实时链故障不得影响日频对象层、盘前必读和盘后复盘。
- [ ] 不得把“全市场秒级 Tick 平台”和“高频策略引擎”作为本阶段通过门槛。
- [x] 已完成 `auction_result_validation.v1`：
  - `auction_watch_universe`
  - `pre_market_auction_snapshot`
  - `pre_market_auction_signal`
  - `pre_market_auction_signal_validation`
- [x] 已验证 `stk_auction` 结果层接入可用，且 `2026-04-03` 真实信号链已跑通。
- [ ] 当前不得把 `auction_result_validation.v1` 对外描述为“完整集合竞价路径识别器”。
- [x] 当前大环境与板块环境已落地，但“冲高回落 / 日内回落”等字段仍明确标注为 `daily_proxy` 或 `intraday_mixed`，未冒充分钟真值。

---

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q`
- `rg -n "intel/stream|SSE|minute_abnormal_event|industry_chain|realtime" /Users/admin/Desktop/ai_theme_app`
- `rg -n "REST \\+ SSE|minute_abnormal_event|candidate attribution|industry chain" /Users/admin/Desktop/ai_theme_app/docs/project_control /Users/admin/Desktop/ai_theme_app/docs/adrs`
- `.venv/bin/python -m py_compile frontend_bff theme_service stock_service recap_service`

Acceptance-测试映射：
- `ACPT-P3D-001` -> `ACC-P3D-001` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-002` -> `ACC-P3D-002` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-003` -> `ACC-P3D-003` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-004` -> `ACC-P3D-004` -> `rg -n "industry_chain" /Users/admin/Desktop/ai_theme_app`
- `ACPT-P3D-005` -> `ACC-P3D-001` / `ACC-P3D-002` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-006` -> `ACC-P3D-003` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-007` -> `ACC-P3D-002` / `ACC-P3D-003` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-008` -> `ACC-P3D-003` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-009` -> `ACC-P3D-003` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3D-010` -> `ACC-P3D-003` -> `.venv/bin/python -m pytest -q`

---

## 5. Deliverables

- `/api/intel/stream` 的 `SSE` 实时出口契约。
- `REST + SSE` 双轨与回补策略说明。
- `minute_abnormal_event` 对象与解释规则。
- 大环境分钟指标升级方案：
  - `昨日涨停池 + 高标池` 分钟序列
  - `market_environment_metrics.v2.intraday_mixed`
- 情报流、股票异动、题材角色变化联动与优先级排序规则。
- `stock_abnormal_signal` 真源对象：
  - 高换手
  - 放量 / 倍量（`>= 2 * 50日均量`）
  - 尾盘成交放大抢筹
- 轻量产业链只读视图定义。
- `auction_result_validation.v1` 真源链：
  - `auction_watch_universe`
  - `pre_market_auction_snapshot`
  - `pre_market_auction_signal`
  - `pre_market_auction_signal_validation`
- 文档更新：
  - `docs/project_control/PHASE_CONTRACT_P3.phase3.md`
  - `tmp/phase_contract_P3.phase3.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| `SSE` 断线或回补失序 | High | Medium | 断线恢复后出现永久缺口或顺序错乱 | 前端/BFF 负责人 | `REST + SSE` 双轨和显式回补策略 |
| 分钟级异动噪声放大 | Medium | High | 大量低质量分钟事件污染情报流 | 算法/产品负责人 | 分钟级规则显式化与阈值门禁 |
| 无真实分钟源却错误展示为分钟真值 | Medium | High | 用户将 `daily_proxy` 指标误读为真实早盘分钟表现 | 产品/研发负责人 | 文档和前端必须明确标注代理口径，分钟真值只在接入真实分钟源后开放 |
| 实时链污染快照主链 | High | Medium | 实时链故障导致盘前/盘后任务失败 | 平台负责人 | 主链隔离与失败不反向阻塞 |
| 产业链视图范围膨胀 | Medium | Medium | 轻量视图被扩展成重型图谱真源 | 知识图谱负责人 | 固定只读边界和非目标 |
| 实时条目解释误导 | Medium | Medium | 将资讯直接当作确定性涨停真因输出 | 产品负责人 | 只允许候选归因与支撑证据 |
| 竞价路径识别被误认为已完成 | Medium | High | 使用 `stk_auction` 单点结果却对外宣称具备 `9:20~9:25` 路径稳定性识别 | 产品/研发负责人 | 明确标注 `auction_result_validation.v1` 仅为结果层验证 |
| 日频结果缺失导致盘后验证误判 | Medium | Medium | 当日 `subject_stock_daily_snapshot` 尚未入库，验证结果被误写成失败 | 数据链负责人 | 显式输出 `pending_daily_result` |
| 异动标签过度泛化 | Medium | Medium | 高换手或放量在高潮期被误读为强势信号 | 算法/产品负责人 | 将异动作为事实层，不直接替代主线/周期/龙头判断 |
| 无盘口源时尾盘解释过度 | Medium | High | 用日频或分钟代理值误写为“巨量未成交挂单” | 产品/研发负责人 | 明确区分尾盘成交放大与盘口挂单真值 |

---

## 7. Rollback Plan

- 代码回滚：
  - 触发条件：`SSE` 不稳定、客户端增量刷新失控、实时链严重污染主链。
  - 方式：关闭 `SSE` 与分钟级增强，回退到 `REST` 和 `P3.phase2` 既有页面能力。
- 数据回滚：
  - 触发条件：错误分钟级异动对象或错误实时排序规则导致批量错误展示。
  - 方式：按 `event_window / stream_offset / snapshot_version` 回滚实时增强对象。
- 同步补偿回滚：
  - 触发条件：断线回补失败或实时链与日频快照不一致。
  - 方式：保留 `REST` 兜底路径，按最后稳定游标重新补拉。

---

## 8. Non-Goals

- 不建设全市场秒级 Tick 实时平台。
- 不建设高频策略信号引擎。
- 不建设重型产业链图谱服务。
- 不让实时链反向成为盘前/盘后报告真源。
- 不输出“涨停确定性真因”。
- 不把异动股票复盘做成公告摘抄或异动新闻堆积页。

---

## 9. 状态同步与对账基线

- `Doing -> test-evidence -> In review/done -> milestone progress`
- 阶段内必须保留 `event_id / source_trace_id / stream_offset / event_type / occurred_at`。
- 阶段末对账必须区分：
  - `SSE` 实时出口
  - `REST` 回补链
  - `minute_abnormal_event`
  - `stock_abnormal_signal`
  - 联动后的情报条目
  - 轻量产业链视图
- 本阶段在正式 `TEST_CASE_SPEC` 补齐前，合同状态为 Draft，`gate_ready=false`。
