# PRD_P3（第三阶段专用需求文档）

- 项目：个人投资助理（AI Theme App）
- 文档版本：v1.0
- 状态：Active Draft（P3 主文档）
- 更新日期：2026-04-23
- 适用范围：第三阶段 `P3.phase0 ~ P3.phase3`
- 真源声明：本文件是第三阶段需求收口主文档；历史内容以 `PRD.md` 为审计参考。

---

## 1. 第三阶段目标与边界

### 1.1 总目标
在不破坏现有主链的前提下，完成第三阶段从“统一产品出口”到“股票事实对象层与复盘闭环”，再到“实时增强”的渐进式交付。

### 1.2 分期定义
- `P3.phase0`：前端统一产品出口第一版（历史 `P3.phaseA`）
- `P3.phase1`：`stock_processing_service` 日频对象层与复盘快照主链
- `P3.phase1.0`：执行门禁硬化（CI/Pointer/Stream/Reconcile/Flag）
- `P3.phase2`：复盘增强与工作台深化
- `P3.phase3`：实时化与高级增强

### 1.3 非目标
- 不在 `P3.phase1/1.0/2` 引入秒级全市场实时行情平台
- 不将 Notion 作为业务真源
- 不允许前端直连底层领域表

---

## 2. Phase P3.phase0 — 前端统一产品出口第一版

### 2.1 目标
收口 `frontend_bff /api/*` 出口，建立前端只读契约基础。

### 2.2 关键需求
- 提供统一 BFF 读取出口，前端不直连领域层。
- 保留 REST first 兜底路径。
- 完成 P3 后续阶段可复用的接口契约基线。

### 2.3 通过判定
- 核心页面均通过 BFF 读取
- 接口契约冻结并可回放验证

---

## 3. Phase P3.phase1 — stock_processing_service 对象层收口（当前执行基线）

> 当前生效需求基线：`PRD-REQ-P3.phase1-011 ~ 018`

### 3.1 目标
建立 `stock_processing_service` 作为股票日频对象层唯一新生产链路，实现业务与数据解耦、快照真源冻结、双轨可回滚。

### 3.2 功能需求（FR）
- `PRD-REQ-P3.phase1-011` 唯一新生产链路：新功能仅落在 `stock_processing_service`，旧 `stock_service` 仅保留回退/对账/实验。
- `PRD-REQ-P3.phase1-012` `Gateway First`：股票侧读写统一走 `database_service.DatabaseGateway` 显式方法。
- `PRD-REQ-P3.phase1-013` `Domain Pure`：领域层不依赖数据库/缓存/消息总线实现。
- `PRD-REQ-P3.phase1-014` 冻结 6 个对象字段级最小 schema。
- `PRD-REQ-P3.phase1-015` 统一事件 envelope：`event_id/event_name/trade_date/batch_id/trace_id/producer/occurred_at/payload_version/payload`。
- `PRD-REQ-P3.phase1-016` 缓存失效与版本切换：先写新版本再原子切 `current`。
- `PRD-REQ-P3.phase1-017` 双轨对账产物：`summary + diff_samples.jsonl`。
- `PRD-REQ-P3.phase1-018` 编码前置门禁：contracts/ports/gateway/feature flag 全冻结。

### 3.2.1 DatabaseGateway 高层领域网关升级（P3 核心收口）
- `PRD-REQ-P3.phase1-019` 必须将 `database_service.DatabaseGateway` 从“客户端门面”升级为“股票域高层领域网关”，对业务侧仅暴露显式领域 API；触发条件为 `P3.phase1` 实施；预期行为为业务层只调用领域方法，不感知 `_client` 实现；约束为禁止在业务侧使用 `_client/_db` 能力判断分支。
- `PRD-REQ-P3.phase1-020` 必须限制 `interface.py` 中原始 SQL 能力（如 `execute_query`）为基础设施内部能力，不得作为业务常规入口；触发条件为任何股票域读写改造；预期行为为股票业务读写均通过 `get_*/upsert_*/publish_*` 显式协议；约束为新增业务代码不得依赖通用 SQL 接口。
- `PRD-REQ-P3.phase1-021` 必须补齐股票域标准化闭环：`输入事件 -> 快照对象 -> 发布事件`，并通过 Redis Stream 统一承载；触发条件为对象层任务运行；预期行为为流程可重放、可审计、可幂等；约束为禁止“请求时临时重算 + 本地文件补洞”作为主链路。
- `PRD-REQ-P3.phase1-022` 必须将现有股票侧实现对齐 6 个冻结对象建模，确保对象为唯一消费真源；触发条件为 `P3.phase1` 切流前；预期行为为前端/BFF/Notion 只读对象层；约束为禁止消费端二次拼装核心结论。

### 3.3 非功能需求（NFR）
- `NFR-P3.phase1-006` 静态扫描违规项为 0（`asyncpg/SQL/_client/_db`）。
- `NFR-P3.phase1-007` 对账任务输出完整 JSON 并保留近 30 次记录。
- `NFR-P3.phase1-008` 缓存版本切换无半成品窗口。
- `NFR-P3.phase1-009` 股票域新增/变更接口必须为显式领域 API，`DatabaseGateway` 股票域 API 覆盖率达到 100%（业务侧不允许调用通用 SQL 接口）。
- `NFR-P3.phase1-010` `execute_query` 在股票业务路径调用次数必须为 0（仅允许在基础设施层或离线运维脚本中出现）。
- `NFR-P3.phase1-011` 标准化闭环链路（输入事件 -> 快照对象 -> 发布事件）关键节点审计字段覆盖率必须为 100%（`trade_date/batch_id/trace_id/payload_version`）。

### 3.4 关键用例
- `PRD-UC-P3.phase1-06` 协议冻结门禁
- `PRD-UC-P3.phase1-07` 双轨对账输出
- `PRD-UC-P3.phase1-08` 缓存版本切换
- `PRD-UC-P3.phase1-09` 网关升级验收：业务服务仅调用 `DatabaseGateway` 股票域显式方法完成对象读写。
- `PRD-UC-P3.phase1-10` 闭环验收：输入事件经 Redis Stream 进入处理后，成功产出快照对象并发布标准化事件，且审计链完整。

### 3.5 验收映射
- `PRD-REQ-P3.phase1-011~018` -> `ACPT-P3B-011~018`
- `PRD-REQ-P3.phase1-019~022` -> `ACPT-P3B-019~022`（待在 `ACCEPTANCE.md` 增量补齐）

---

## 4. Phase P3.phase1.0 — 执行门禁硬化

### 4.1 目标
将 P3 架构原则转为“可执行门禁”，未通过不得进入 `P3.phase1.1` 业务实现。

### 4.2 需求条款
- `PRD-REQ-P3.phase1.0-001` CI 边界硬门禁：阻断 `asyncpg/SQL/_client/_db` 违规。
- `PRD-REQ-P3.phase1.0-002` Snapshot Pointer 原子切换协议落地并可回滚。
- `PRD-REQ-P3.phase1.0-003` Stream 运行时契约冻结（group/ack/retry/backoff/dlq_replay）。
- `PRD-REQ-P3.phase1.0-004` 对账阈值门禁与失败分级（P0/P1/P2）落地，阈值不达标自动阻断切流。
- `PRD-REQ-P3.phase1.0-005` Feature Flag Register 建立并完成回滚演练。

### 4.3 通过判定（AND）
- 五项门禁全部通过
- 门禁命令可重复执行且结果一致
- 阻断、回滚、审计证据齐全

### 4.4 验收映射
- `PRD-REQ-P3.phase1.0-001~005` -> `ACPT-P3P10-001~005`

---

## 5. Phase P3.phase2 — 复盘增强与工作台深化

### 5.1 目标
在 `P3.phase1` 对象层稳定后，增强龙虎榜、资金行为、个股工作台与 `/recap` 出口。

### 5.2 功能需求（FR）
- `PRD-REQ-P3.phase2-001` 龙虎榜结构化对象。
- `PRD-REQ-P3.phase2-002` 资金行为增强字段（可解释）。
- `PRD-REQ-P3.phase2-003` 龙头/前排/扩散/跟风角色增强。
- `PRD-REQ-P3.phase2-004` 个股工作台聚合（经 BFF）。
- `PRD-REQ-P3.phase2-005` `/recap` 只读出口。
- `PRD-REQ-P3.phase2-006` 复盘来源链完整可追溯。
- `PRD-REQ-P3.phase2-007` 新字段向后兼容。
- `PRD-REQ-P3.phase2-008` 实时化能力后置到 `P3.phase3`。

### 5.3 非功能需求（NFR）
- `NFR-P3.phase2-001` 增强对象重复生成一致率 100%
- `NFR-P3.phase2-002` 个股工作台接口 P95 < 1000ms
- `NFR-P3.phase2-003` 来源链覆盖率 100%
- `NFR-P3.phase2-004` DTO 向后兼容

### 5.4 验收映射
- `PRD-REQ-P3.phase2-001~008` -> `ACPT-P3C-001~008`

---

## 6. Phase P3.phase3 — 实时化与高级增强

### 6.1 目标
在前序阶段稳定后补齐 `SSE`、分钟级异动、情报联动、轻量产业链视图。

### 6.2 功能需求（FR）
- `PRD-REQ-P3.phase3-001` `/intel` SSE 实时出口（保留 REST 兜底）。
- `PRD-REQ-P3.phase3-002` 分钟级异动增强对象。
- `PRD-REQ-P3.phase3-003` 情报-题材-股票联动流。
- `PRD-REQ-P3.phase3-004` 轻量产业链只读视图。
- `PRD-REQ-P3.phase3-005` 前端增量刷新机制。
- `PRD-REQ-P3.phase3-006` 实时条目去重与优先级策略。
- `PRD-REQ-P3.phase3-007` 实时链不得破坏日频快照主链。
- `PRD-REQ-P3.phase3-008` 不承诺 Tick 平台与高频策略引擎。

### 6.3 非功能需求（NFR）
- `NFR-P3.phase3-001` SSE 端到端 P95 < 3s
- `NFR-P3.phase3-002` 断线可 REST 回补
- `NFR-P3.phase3-003` 分钟级对象重复生成一致率 100%
- `NFR-P3.phase3-004` 实时链故障不影响日频主链

### 6.4 验收映射
- `PRD-REQ-P3.phase3-001~008` -> `ACPT-P3D-001~008`

---

## 7. 统一发布门禁（P3）

以下条件必须全部满足（AND）：
1. 当前 phase 的 FR/NFR 全部通过验收映射。
2. 质量门禁无 P0/P1 开放缺陷。
3. 双轨对账达标（适用于 `P3.phase1/1.0`）。
4. 可回滚演练通过（5 分钟内切回）。

---

## 8. 文档关系与维护规则

- 本文件维护第三阶段需求主线。
- `PRD.md` 保留全局与历史审计；若冲突，以本文件第三阶段当前生效段为准。
- 变更要求：新增/变更第三阶段需求必须同步更新 `ACCEPTANCE.md` 与 `tmp/acceptance_traceability.json`。

---

## Change Log

- `2026-04-23`：首次创建 `prd_p3.md`，收口 `P3.phase0~P3.phase3`，新增 `P3.phase1.0` 门禁子阶段并映射验收合同。
- `2026-04-23`：补充 `P3.phase1` 核心任务“DatabaseGateway 高层领域网关升级”，新增 `PRD-REQ-P3.phase1-019~022`、`NFR-P3.phase1-009~011` 与用例 `PRD-UC-P3.phase1-09~10`。
