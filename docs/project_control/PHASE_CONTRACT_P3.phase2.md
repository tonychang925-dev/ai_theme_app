# Phase Execution Contract

## 1. Phase Identity

- Phase Name: 复盘增强与工作台深化
- Phase Code: `P3.phase2`
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
  - `docs/project_control/PHASE_CONTRACT_P3.phase1.md`

---

## 1.1 Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| 资金行为范围 | `PRD.md` + `ARCH_REVIEW.md` 中“轻量增强字段，不承诺完整主力资金行为体系” | 将完整资金行为分析作为 `P3.phase2` 必交 | 当前数据源稳定性与成本不足以支撑全量体系 |
| 复盘聚合责任 | `ADR-023` 中 `recap_service` 作为唯一报告聚合层 | 由前端/BFF/Notion 各自拼装复盘 | 必须避免多出口长期漂移 |
| 字段兼容策略 | `ACCEPTANCE.md` 中“字段只增不改” | 通过重命名或语义改写修复旧 DTO | `P3.phase2` 必须建立在 `P3.phase1` 稳定 DTO 之上 |
| 实时化范围 | `PRD.md` + `ADR-026` 中将 `SSE/分钟级异动` 后置到 `P3.phase3` | 在 `P3.phase2` 提前引入实时链 | 复盘增强必须优先收口日频对象和来源链 |

---

## 2. Phase Objective（可量化）

1. 在 `P3.phase1` 稳定对象层之上，增加龙虎榜结构化对象与轻量资金行为增强字段。  
2. 强化 `theme_stock_leaderboard`，稳定输出龙头、前排、扩散股和跟风股等角色。  
3. 深化个股工作台与 `/recap` 只读产品出口，确保前端不再自行拼装股票多源数据。  
4. 为盘后复盘建立 `100%` 的来源链覆盖率，任何关键结论都可回溯到原始证据。  
5. 保持增强字段向后兼容，不因 `P3.phase2` 破坏 `P3.phase1` DTO 和 Notion 模板。  

---

## 3. Acceptance Targets（门禁条件）

- [x] 必须增加龙虎榜结构化对象，且可回溯到原始来源。
- [x] 必须增加资金行为增强字段，但不要求完整主力资金行为体系。
- [x] 必须增强龙头、前排、扩散股和跟风股规则。
- [x] 必须深化个股工作台，前端不得自行拼装股票多源数据。
- [x] 必须提供 `/recap` 只读产品出口。
- [x] 必须为复盘结论提供完整来源链。
- [x] 新增增强字段必须向后兼容，不破坏 `P3.phase1` DTO。
- [x] `recap_service` 必须是唯一报告聚合层。
- [x] 不得引入 `SSE` 或分钟级实时异动作为本阶段通过门槛。

---

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest -q`
- `rg -n "dragon_tiger|money_flow|theme_stock_leaderboard|/recap|workspace" /Users/admin/Desktop/ai_theme_app`
- `rg -n "recap_service|source_trace|workspace_route" /Users/admin/Desktop/ai_theme_app/docs/project_control /Users/admin/Desktop/ai_theme_app/docs/adrs`
- `.venv/bin/python -m py_compile stock_service recap_service frontend_bff`

Acceptance-测试映射：
- `ACPT-P3C-001` -> `ACC-P3C-001` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3C-002` -> `ACC-P3C-002` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3C-003` -> `ACC-P3C-002` -> `rg -n "theme_stock_leaderboard" /Users/admin/Desktop/ai_theme_app`
- `ACPT-P3C-004` -> `ACC-P3C-003` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3C-005` -> `ACC-P3C-003` / `ACC-P3C-004` -> `rg -n "/recap" /Users/admin/Desktop/ai_theme_app`
- `ACPT-P3C-006` -> `ACC-P3C-004` -> `.venv/bin/python -m pytest -q`
- `ACPT-P3C-007` -> `ACC-P3C-003` / `ACC-P3C-004` -> `.venv/bin/python -m pytest -q`

---

## 5. Deliverables

- 龙虎榜结构化对象定义与来源链协议。
- 资金行为增强字段与轻量解释规则。
- 增强后的 `theme_stock_leaderboard` 角色规则。
- 个股工作台增强 DTO 与 `/recap` 只读产品出口契约。
- `recap_service` 报告聚合边界说明。
- 文档更新：
  - `docs/project_control/PHASE_CONTRACT_P3.phase2.md`
  - `tmp/phase_contract_P3.phase2.json`

### 5.1 2026-04-02 已完成交付（增量记录）

已完成的核心交付物：

- `theme_mainline_judgement`
  - 规则服务
  - 真库构建脚本
  - 单元测试
- `theme_cycle_judgement`
  - 状态机服务
  - 真库构建脚本
  - 单元测试
- `theme_leader_candidate`
  - 五维评分与角色分层服务
  - 真库构建脚本
  - 单元测试
- `pre_market_execution_plan`
  - 承接验证服务
  - 真库构建脚本
  - 单元测试
- `RecapService` 已完成数据源切换
  - `post_market` -> 读取 3 张真源表
  - `pre_market` -> 读取 `pre_market_execution_plan`

已完成真实验证：

- `2026-04-01` 真实库构建通过
- `post_market` 真快照生成通过
- `pre_market` 真快照生成通过

当前未完成项：

- 规则调优与误判样本分析
- 展示层继续贴近交易模板优化
- 最终发布门禁确认

### 5.2 2026-04-02 晚间状态补充（增量）

截至 `2026-04-02` 晚，以下门禁目标已具备事实完成依据：

- 龙虎榜结构化对象：
  - 已接入 `Tushare top_list/top_inst`
  - 已完成 `2026-04-01` 真数据 smoke test
- 资金行为增强字段：
  - 已形成 `money_flow_enhanced`
  - 已接入盘后复盘
- 个股工作台深化：
  - 已完成股票基础信息、所属题材、资金行为、龙虎榜、角色标签统一 DTO
- `/recap` 只读产品出口：
  - 已完成 BFF 与前端消费
- 复盘来源链：
  - `theme_mainline_judgement / theme_cycle_judgement / theme_leader_candidate / money_flow_enhanced`
    已统一补齐来源链字段
- 跨交易日一致性回测：
  - 已完成 `2026-04-01 / 2026-04-02`
  - 覆盖率结果：`source_type/source_trace_id/source_trace/source_version/rule_version = 100%`

### 5.3 2026-04-02 合同状态收口（增量）

截至 `2026-04-02`，`P3.phase2` 可正式记为：

- 合同状态：`接近完成（Near Done）`
- 核心主链状态：`已完成`
- 测试材料状态：
  - `TEST_CASE_SPEC_P3.phase2.md` 已补齐
  - `TEST_REPORT.md` 已补齐
- 剩余工作：
  - 规则调优与误判样本分析
  - 展示层继续贴近交易模板优化
  - 最终发布门禁确认

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 龙虎榜/资金行为口径不稳 | High | Medium | 同一交易日增强结果不一致 | 数据负责人 | 增强字段显式化 + 可追溯来源 |
| 工作台重新退回前端拼装 | High | Medium | 前端直接拼表或拼多源对象 | 前端/BFF 负责人 | 统一 DTO 契约和回归门禁 |
| 复盘来源链缺失 | High | Medium | 关键结论无法回溯证据 | 产品架构负责人 | 来源链缺失即阻断进入正式快照 |
| `recap_service` 边界被绕过 | High | Medium | BFF 或 Notion 直接重算结论 | 平台负责人 | 冻结唯一聚合层 ADR |
| 实时范围错误前移 | Medium | Medium | 在 `P3.phase2` 引入 `SSE/分钟级异动` | 架构负责人 | 明确后置到 `P3.phase3` |

---

## 7. Rollback Plan

- 代码回滚：
  - 触发条件：增强字段破坏兼容性、工作台 DTO 漂移、`/recap` 契约不稳定。
  - 方式：回退到 `P3.phase1` 既有 DTO，停用增强字段输出。
- 数据回滚：
  - 触发条件：龙虎榜/资金行为增强对象错误批量写入，或来源链缺失。
  - 方式：按 `trade_date / recap_id / source_trace_id` 回滚增强对象，不影响 `P3.phase1` 基础对象层。
- 同步补偿回滚：
  - 触发条件：复盘增强结果与基础快照不一致。
  - 方式：基于 `P3.phase1` 基础对象重新生成增强对象和复盘快照。

---

## 8. Non-Goals

- 不引入 `SSE`。
- 不引入分钟级实时异动。
- 不建设完整主力资金行为体系。
- 不建设重型产业链图谱服务。
- 不改变 `P3.phase1` 基础对象层字段语义。

---

## 9. 状态同步与对账基线

- `Doing -> test-evidence -> In review/done -> milestone progress`
- 阶段内所有增强对象必须保留 `trade_date / stock_id / subject_key / source_trace_id / recap_id`。
- 阶段末对账必须区分：
  - 龙虎榜结构化对象
  - 资金行为增强对象
  - 增强后的 `theme_stock_leaderboard`
  - 个股工作台 DTO
  - `/recap` 只读出口
- 本阶段 `TEST_CASE_SPEC` 与测试报告已补齐；当前合同状态更新为 `Near Done`。在完成最终发布门禁确认前，仍保留 `gate_ready=false` 的保守口径。
