# FEATURE SPEC - P3（第三阶段项目功能设计）

## 0. Meta
- Phase: `P3`
- Scope: `P3.phase0 ~ P3.phase3`
- Source Priority:
  1. 用户最新指令
  2. `PHASE_CONTRACT_P3.phase0~phase3.md`
  3. `ACCEPTANCE.md`
  4. `PRD.md` + `prd_p3.md`
  5. `PLAN_WBS.md`
  6. `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`
- 输出目标：形成可实施、可测试、可回滚的 P3 全阶段任务级设计。

## 0.1 冲突裁决说明
- 冲突 1：`P3.phaseA` vs `P3.phase0`
  - 裁决：统一使用 `P3.phase0`，`phaseA` 仅保留别名。
- 冲突 2：`database_service` 网关是薄门面 vs 高层领域网关
  - 裁决：P3.phase1 必须升级为股票域显式 API，业务侧禁止 `_client/_db`。
- 冲突 3：业务路径允许 `execute_query` vs 领域 API 收口
  - 裁决：P3.phase1 必须完成 `execute_query` 业务路径清零。

---

## Task `P3.phase0-T02` — 冻结 `frontend_bff` 与 `/api/*` 长期契约

### 1) 目标与边界
- 目标：统一前端出口，冻结 `/api/intel/feed`、`/api/theme-workspace/{subject_key}`、`/api/stock-workspace/{stock_id}` 契约。
- 非目标：不引入 SSE，不重写领域服务。

### 1.1 子功能分解
- `F-P3.phase0-T02-01` 路由契约冻结
  - 输入：前端 HTTP 请求
  - 处理：参数校验与 DTO 包装
  - 输出：稳定响应 DTO
  - 失败处理：400/404/424
  - 可观测证据：`request_id,route,latency_ms`
- `F-P3.phase0-T02-02` 错误码与 partial 语义统一
  - 输入：下游超时/错误
  - 处理：错误映射
  - 输出：统一错误语义
  - 失败处理：下游失败时保持可诊断
  - 可观测证据：`partial_response_count`
- `F-P3.phase0-T02-03` DTO 版本规则
  - 输入：BFF 聚合结果
  - 处理：字段版本控制
  - 输出：向后兼容 DTO
  - 失败处理：兼容性失败阻断发布
  - 可观测证据：DTO diff 报告

### 2) 接口与契约
- 输入：`subject_key`, `stock_id`, query filters
- 输出：`intel/theme/stock workspace DTO`
- 幂等：只读接口天然幂等
- 超时：单请求 P95 < 1000ms

### 3) 数据模型与状态变更
- 无新增业务真源表。
- 新增/冻结 BFF DTO 模型与错误对象模型。

### 4) 实现步骤
1. 冻结 `/api/*` DTO 与错误码。
2. 增加超时与 partial diagnostics。
3. 回归接口兼容性测试。

### 5) 测试设计与命令
- TC: `ACC-P3A-001~003`
- 命令：
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration`
  - `rg -n "/api/intel/feed|/api/theme-workspace|/api/stock-workspace" frontend_bff`

### 6) 风险与回滚
- 风险：前端继续直连下游服务。
- 缓解：路由扫描门禁 + 契约回归。
- 回滚触发：BFF 契约破坏导致页面不可用。
- 回滚操作：回退到上一个稳定 BFF tag。

### 7) 验收映射
- `ACPT-P3A-001~006`

---

## Task `P3.phase1-T02` — 冻结 `DatabaseGateway` 股票域显式 API 与 ports 签名

### 1) 目标与边界
- 目标：冻结 `get_*/upsert_*/publish_*` 股票域 API；业务层只依赖 ports。
- 非目标：不直接改造前端页面逻辑。

### 1.1 子功能分解
- `F-P3.phase1-T02-01` 读接口冻结
  - 输入：trade_date/stock_ids/subject_keys
  - 处理：领域读取聚合
  - 输出：DTO（非裸 SQL 行）
  - 失败处理：无数据返回空对象，不抛 SQL 细节
  - 可观测证据：API 覆盖清单
- `F-P3.phase1-T02-02` 写接口冻结
  - 输入：6 对象 rows/docs
  - 处理：批量 upsert
  - 输出：影响行数与 batch_id
  - 失败处理：事务失败全回滚
  - 可观测证据：upsert 审计日志
- `F-P3.phase1-T02-03` 事件接口冻结
  - 输入：event_name + envelope
  - 处理：发布 stream 事件
  - 输出：message_id
  - 失败处理：DLQ + 重放标记
  - 可观测证据：stream trace

### 2) 接口与契约
- DTO 入口：`contracts/dto/*`
- Snapshot 入口：`contracts/snapshots/*`
- Event 入口：`contracts/events/*`
- 幂等：`job_key + batch_id`
- 超时：网关调用失败可重试 3 次

### 3) 数据模型与状态变更
- `database_service` 网关接口签名冻结。
- 禁止业务侧调用 `_client/_db`。

### 4) 实现步骤
1. 列出股票域 API 清单并冻结签名。
2. 绑定 ports 到 gateway adapters。
3. 加入签名变更审查门禁。

### 5) 测试设计与命令
- TC: `PRD-UC-P3.phase1-09`
- 命令：
  - `.venv/bin/python -m pytest -q database_service/tests`
  - `rg -n "_client\.|_db\." stock_processing_service database_service | rg -v "tests|docs"`

### 6) 风险与回滚
- 风险：旧调用链残留。
- 缓解：静态扫描 + 代码评审强制。
- 回滚触发：网关调用错误导致主链中断。
- 回滚操作：flag 回退旧链路（只读）并重放任务。

### 7) 验收映射
- `ACPT-P3B-012`, `ACPT-P3B-019`

---

## Task `P3.phase1-T03` — 冻结 6 个对象字段级最小 schema 与 upsert 策略

### 1) 目标与边界
- 目标：冻结 6 个对象主键、必填字段、可空字段、覆盖策略。
- 非目标：不扩展实时字段。

### 1.1 子功能分解
- `F-P3.phase1-T03-01` 对象 schema 冻结
  - 输入：对象定义草案
  - 处理：字段级评审
  - 输出：冻结 schema 表
  - 失败处理：字段冲突阻断
  - 可观测证据：schema version
- `F-P3.phase1-T03-02` upsert 语义冻结
  - 输入：写入策略
  - 处理：文档型/行式对象策略区分
  - 输出：覆盖策略矩阵
  - 失败处理：覆盖冲突告警
  - 可观测证据：upsert policy report
- `F-P3.phase1-T03-03` 兼容迁移策略
  - 输入：历史字段
  - 处理：兼容映射
  - 输出：迁移脚本设计
  - 失败处理：不兼容禁止切流
  - 可观测证据：migration checklist

### 2) 接口与契约
- 对象：
  - `stock_daily_snapshot`
  - `subject_stock_daily_snapshot`
  - `stock_abnormal_event`
  - `theme_stock_leaderboard`
  - `pre_market_brief_snapshot`
  - `post_market_recap_snapshot`

### 3) 数据模型与状态变更
- 固化主键、索引与唯一约束。

### 4) 实现步骤
1. 建立最小 schema 清单。
2. 固化 upsert 策略。
3. 输出兼容迁移计划。

### 5) 测试设计与命令
- TC: `ACPT-P3B-014`, `ACPT-P3B-022`
- 命令：
  - `.venv/bin/python -m pytest -q stock_processing_service/tests`
  - `rg -n "stock_daily_snapshot|subject_stock_daily_snapshot|stock_abnormal_event|theme_stock_leaderboard|pre_market_brief_snapshot|post_market_recap_snapshot"`

### 6) 风险与回滚
- 风险：字段漂移。
- 缓解：schema version + review gate。
- 回滚：按对象版本回退。

### 7) 验收映射
- `ACPT-P3B-014`, `ACPT-P3B-022`

---

## Task `P3.phase1-T06` — 网关升级（高层领域 API）

### 1) 目标与边界
- 目标：将 `DatabaseGateway` 从薄门面升级为股票域高层网关。
- 非目标：不新增临时 SQL 旁路。

### 1.1 子功能分解
- `F-P3.phase1-T06-01` 去透传 `_client` 语义
- `F-P3.phase1-T06-02` 领域方法闭包（read/write/event/idempotency）
- `F-P3.phase1-T06-03` 调用链替换与审计

### 2) 接口与契约
- 明确禁止业务层通过 `_client._db` 能力判断。

### 3) 数据模型与状态变更
- 无新表，属于访问层抽象升级。

### 4) 实现步骤
1. 列出现有透传方法。
2. 替换为领域方法。
3. 完成业务调用链切换。

### 5) 测试设计与命令
- TC: `ACPT-P3B-019`
- 命令：
  - `.venv/bin/python -m pytest -q database_service/tests`
  - `rg -n "_client\._db|_client\." stock_processing_service database_service | rg -v "tests|docs"`

### 6) 风险与回滚
- 风险：历史调用遗漏。
- 回滚：临时兼容层 + 调用清单补全。

### 7) 验收映射
- `ACPT-P3B-019`

---

## Task `P3.phase1-T07` — `execute_query` 业务路径收口

### 1) 目标与边界
- 目标：股票业务路径 `execute_query` 调用清零。
- 非目标：不影响基础设施脚本保留通用能力。

### 1.1 子功能分解
- `F-P3.phase1-T07-01` 业务路径扫描
- `F-P3.phase1-T07-02` 调用替换到显式领域 API
- `F-P3.phase1-T07-03` CI 阻断规则落地

### 2) 接口与契约
- 业务层仅允许调用显式网关方法。

### 3) 数据模型与状态变更
- 无。

### 4) 实现步骤
1. 扫描 `execute_query` 调用。
2. 替换调用。
3. 接入 CI 阻断。

### 5) 测试设计与命令
- TC: `ACPT-P3B-020`
- 命令：
  - `rg -n "execute_query\(" stock_processing_service database_service | rg -v "scripts|tests|docs"`
  - `.venv/bin/python scripts/ci/check_sps_boundaries.py`

### 6) 风险与回滚
- 风险：遗漏隐式调用。
- 回滚：补充 allowlist 后再逐步清零（限基础设施）。

### 7) 验收映射
- `ACPT-P3B-020`

---

## Task `P3.phase1-T12` — 闭环验收（输入事件 -> 快照对象 -> 发布事件）

### 1) 目标与边界
- 目标：形成可重放、可审计、可幂等闭环。
- 非目标：不覆盖分钟级实时链。

### 1.1 子功能分解
- `F-P3.phase1-T12-01` 输入事件接入
- `F-P3.phase1-T12-02` 快照对象产出
- `F-P3.phase1-T12-03` 事件发布与重放验证

### 2) 接口与契约
- 统一 envelope：`event_id,event_name,trade_date,batch_id,trace_id,producer,occurred_at,payload_version,payload`

### 3) 数据模型与状态变更
- 6 对象落库 + stream 发布审计。

### 4) 实现步骤
1. 跑通单日闭环。
2. 跑通重放一致性。
3. 输出审计报告。

### 5) 测试设计与命令
- TC: `PRD-UC-P3.phase1-10`, `ACPT-P3B-021`
- 命令：
  - `.venv/bin/python scripts/qa/run_reconcile_gate.py --trade-date 2026-04-22`
  - `.venv/bin/python scripts/qa/check_stream_runtime_contract.py`

### 6) 风险与回滚
- 风险：链路某节点漏审计。
- 回滚：按 batch 重放并补齐审计字段。

### 7) 验收映射
- `ACPT-P3B-015`, `ACPT-P3B-021`

---

## Task `P3.phase2-T05` — `/recap` 只读出口与唯一聚合边界

### 1) 目标与边界
- 目标：`recap_service` 成为唯一报告聚合层。
- 非目标：不将复盘拼装下沉至前端。

### 1.1 子功能分解
- `F-P3.phase2-T05-01` `/recap` 契约冻结
- `F-P3.phase2-T05-02` 聚合边界冻结
- `F-P3.phase2-T05-03` 来源链校验

### 2) 接口与契约
- `/recap` 只读 DTO
- 兼容：字段只增不改

### 3) 数据模型与状态变更
- 读取 `post_market_recap_snapshot` 与增强对象。

### 4) 实现步骤
1. 冻结 `/recap` 合同。
2. 下游只读接入。
3. 验证来源链覆盖率。

### 5) 测试设计与命令
- TC: `ACPT-P3C-005~008`
- 命令：
  - `.venv/bin/python -m pytest -q recap_service/tests`
  - `.venv/bin/python -m pytest -q frontend_bff/tests`

### 6) 风险与回滚
- 风险：多出口并存导致口径漂移。
- 回滚：禁用旁路出口，仅保留 recap。

### 7) 验收映射
- `ACPT-P3C-005`, `ACPT-P3C-006`, `ACPT-P3C-007`

---

## Task `P3.phase3-T01` — `REST + SSE` 双轨实时链

### 1) 目标与边界
- 目标：建立 SSE 推送与 REST 回补双轨。
- 非目标：不做 Tick 级平台。

### 1.1 子功能分解
- `F-P3.phase3-T01-01` SSE 通道
- `F-P3.phase3-T01-02` REST 回补
- `F-P3.phase3-T01-03` 断线恢复游标

### 2) 接口与契约
- `/api/intel/stream`
- `/api/intel/feed` 回补

### 3) 数据模型与状态变更
- 新增实时游标与回补窗口状态。

### 4) 实现步骤
1. 打通 SSE。
2. 增加回补。
3. 断线重连验证。

### 5) 测试设计与命令
- TC: `ACPT-P3D-001`, `ACPT-P3D-002`
- 命令：
  - `.venv/bin/python -m pytest -q intel_service/tests`
  - `.venv/bin/python -m pytest -q frontend_bff/tests`

### 6) 风险与回滚
- 风险：SSE 抖动。
- 回滚：仅保留 REST 回补模式。

### 7) 验收映射
- `ACPT-P3D-001`, `ACPT-P3D-002`

---

## Task `P3.phase3-T02` — `minute_abnormal_event` 对象与解释规则

### 1) 目标与边界
- 目标：分钟级异动对象可解释、可回放。
- 非目标：不输出确定性因果结论。

### 1.1 子功能分解
- `F-P3.phase3-T02-01` 分钟异动对象模型
- `F-P3.phase3-T02-02` 异动规则（涨速/放量/开板）
- `F-P3.phase3-T02-03` 去重与优先级

### 2) 接口与契约
- 输出 `minute_abnormal_event` 结构化对象。

### 3) 数据模型与状态变更
- 新增分钟级对象表/缓存键。

### 4) 实现步骤
1. 定义对象与规则。
2. 接入联动流。
3. 完成回放验证。

### 5) 测试设计与命令
- TC: `ACPT-P3D-003`, `ACPT-P3D-006`
- 命令：
  - `.venv/bin/python -m pytest -q intel_service/tests`
  - `rg -n "minute_abnormal_event|dedup|priority"`

### 6) 风险与回滚
- 风险：噪声过高。
- 回滚：规则阈值提升/关闭分钟对象写入。

### 7) 验收映射
- `ACPT-P3D-003`, `ACPT-P3D-006`

---

## Task `P3.phase3-T05` — 实时链与日频主链隔离门禁

### 1) 目标与边界
- 目标：实时链故障不影响盘前/盘后主链。
- 非目标：不修改日频主链业务逻辑。

### 1.1 子功能分解
- `F-P3.phase3-T05-01` 故障注入
- `F-P3.phase3-T05-02` 主链隔离策略
- `F-P3.phase3-T05-03` 回补与恢复演练

### 2) 接口与契约
- 实时失败只影响实时消费，不阻断日频快照任务。

### 3) 数据模型与状态变更
- 新增故障注入审计记录。

### 4) 实现步骤
1. 构建注入脚本。
2. 执行隔离验证。
3. 输出隔离报告。

### 5) 测试设计与命令
- TC: `ACPT-P3D-007`
- 命令：
  - `.venv/bin/python -m pytest -q tests/integration`
  - `.venv/bin/python scripts/qa/check_stream_runtime_contract.py`

### 6) 风险与回滚
- 风险：异常传播导致主链失败。
- 回滚：关闭实时入口并保留日频任务。

### 7) 验收映射
- `ACPT-P3D-007`

---

## 8. 全阶段必跑命令（P3）
- `.venv/bin/python -m pytest -q frontend_bff/tests`
- `.venv/bin/python -m pytest -q database_service/tests`
- `.venv/bin/python -m pytest -q recap_service/tests`
- `.venv/bin/python -m pytest -q intel_service/tests`
- `rg -n "execute_query\(" stock_processing_service database_service | rg -v "scripts|tests|docs"`
- `rg -n "_client\.|_db\." stock_processing_service database_service | rg -v "tests|docs"`

## 9. 通过门禁（P3）
- `feature_traceability_P3.json` 中无关键 gaps。
- `feature_validation_report_P3.json` 为 `gate_ready=true`。

## 9.1 Gate Ready 清零清单（当前为 false）

以下事项全部完成后，才允许将 `feature_validation_report_P3.json.gate_ready` 置为 `true`：

1. `D2` 门禁脚本从“命令存在”升级为“方法级实现完成”：
   - `scripts/ci/check_sps_boundaries.py`
   - `scripts/qa/verify_snapshot_pointer_atomicity.py`
   - `scripts/qa/check_stream_runtime_contract.py`
   - `scripts/qa/run_reconcile_gate.py`
   - `scripts/qa/check_flag_register.py`
2. `P3.phase1-T06/T07/T12` 完成真实证据闭环：
   - 网关升级去透传 `_client/_db`
   - `execute_query` 业务路径清零
   - 输入事件 -> 快照对象 -> 发布事件回放可复验
3. `feature_traceability_P3.json.gaps` 清空或降级为非阻断项并有 ADR 说明。
4. `PLAN_WBS.md`、`FEATURE_SPEC_P3.md`、`feature_traceability_P3.json` 三方日程与任务映射一致性复核通过。

## 10. P3 实施日程对齐（D1-D10）

> 本节与 `PLAN_WBS.md` 第10节保持一一对应；若两者冲突，必须同日双向修订。

| Day | 实施目标 | 任务锚点 | 设计产出 | 验收命令 |
| --- | --- | --- | --- | --- |
| D1 | 冻结窗口与基线清理 | `P3.phase0-T01` | 边界冻结与清理清单、D1守卫报告 | `.venv/bin/python scripts/p3_d1_workspace_guard.py --output tmp/p3_d1_workspace_guard_report.json` |
| D2 | 门禁脚本补齐 | `P3.phase1-T05/T08/T09/T10/T11` | 五个门禁脚本设计与入口 | `.venv/bin/python scripts/ci/check_sps_boundaries.py --help` |
| D3 | 网关 API 冻结 | `P3.phase1-T02` | 显式股票域 API 签名 | `rg -n "def get_|def upsert_|def publish_" database_service/gateway.py` |
| D4 | SQL 通道收口 | `P3.phase1-T07` | `execute_query` 业务路径清零方案 | `rg -n "execute_query\\(" stock_processing_service database_service | rg -v "scripts|tests|docs"` |
| D5 | 新服务适配补全 | `P3.phase1-T06` | gateway adapter 非占位实现 + 强类型 ports 贯通 | `rg -n "NotImplementedError" stock_processing_service/infrastructure/gateway_adapters` |
| D6 | 6对象 schema 落地 | `P3.phase1-T03` | schema + upsert 策略矩阵 | `.venv/bin/python -m pytest -q stock_processing_service/tests` |
| D7 | 闭环主链打通 | `P3.phase1-T12` | 输入->对象->发布 审计闭环 | `.venv/bin/python scripts/qa/check_stream_runtime_contract.py` |
| D8 | 双轨对账 | `P3.phase1-T10` | `summary + diff_samples.jsonl` | `.venv/bin/python scripts/qa/run_reconcile_gate.py --trade-date 2026-04-22` |
| D9 | BFF 灰度切流 | `P3.phase0-T02/T04` | 切流与回滚演练记录 | `.venv/bin/python scripts/qa/check_flag_register.py` |
| D10 | 阶段验收归档 | `P3.phase1-T13` | Phase1/1.0 验收证据包 | `.venv/bin/python -m pytest -q` |

### 10.1 防分歧规则
- 本文 `D1-D10` 与 `PLAN_WBS.md` 第10节必须保持一致（任务ID、命令、阻塞关系）。
- 阻塞规则：
  - 未完成 `P3.phase1-T06`（网关升级）不得进入 `P3.phase1-T07` 收口验收。
  - 未完成 `P3.phase1-T07` 不得推进 `P3.phase1-T12` 闭环验收。
  - 未完成 `P3.phase1-T12` 不得进入 `P3.phase2` 研发。
- 变更规则：新增或调整 P3 任务时，必须同步更新：
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/FEATURE_SPEC_P3.md`
  - `tmp/feature_traceability_P3.json`
