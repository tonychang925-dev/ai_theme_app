# PRD — P4.phase0 前端作战台与统一出口（第四阶段）

## Change Log
- 2026-04-30: 初版生成。依据 `docs/architecture/个人投资助理项目-前端技术设计（第四阶段）.md`、`docs/project_control/ACCEPTANCE.md`、`docs/project_control/PLAN_WBS.md`、`docs/project_control/PHASE_CONTRACT_P4.phaseA.md` 收敛为可门禁执行版本。

## 冲突裁决说明
- 路由口径冲突：文档中同时出现 `/api/v2/intel/strong-stocks/watch` 与 `/api/v2/strong_watch`。本 PRD 统一采用：前端页面调用 `/api/v2/intel/strong-stocks/watch`（BFF 出口口径）；`/api/v2/strong_watch` 作为服务内部/兼容口径，不作为页面契约。
- 实时通道策略：采用 `SSE 主通道 + feed 兜底`，`WS` 仅保留可选，不进入本阶段必交付。

## Phase P4.phase0 — 前端统一出口与三栏作战台

### 1) 目标（Objective）
- 在不破坏现有 P3 能力前提下，完成前端统一出口到 `/api/v2/*`，并交付 `/intel` 三栏作战台最小可用版本。
- 连续 5 个交易日达到：
  - `/api/v2/intel/feed` 成功率 >= 99%
  - `/api/v2/intel/stream` 连接成功率 >= 99%
  - Layer B confirmed 覆盖率 >= 95%

### 2) 范围（Scope）
- In Scope
  - `/intel` 三栏：ThemeRadarPanel / IntelStreamPanel / MarketValidationPanel。
  - 前端 `frontend/src` API 路径统一 `/api/v2/*`。
  - `SSE + feed fallback` 链路可用，含重连与降级。
  - v2 契约测试 + CI 阻断（非 v2 API 禁止）。
- Out of Scope
  - Tick 级行情平台、全量 WS Hub、产业链独立图谱服务化。
  - 第四阶段全面功能扩展（仅在 Gate 通过后进入）。

### 3) 功能需求（Functional Requirements）

#### PRD-REQ-P4-001 统一 API 出口
- 描述：前端业务请求仅允许 `/api/v2/*`。
- 触发：任意前端页面发起业务请求。
- 预期行为：`frontend/src` 中不存在非 `/api/v2/*` 的 `/api/*` 请求路径。
- 约束：CI 必须阻断违规提交。

#### PRD-REQ-P4-002 Intel Feed 可用
- 描述：`GET /api/v2/intel/feed` 提供中栏轮询兜底数据。
- 触发：SSE 不可用或用户主动拉取。
- 预期行为：返回标准 `IntelFeedViewModel`，含 `items/count/diagnostics`。
- 约束：请求超时与错误码语义固定。

#### PRD-REQ-P4-003 Intel Stream 可用
- 描述：`GET /api/v2/intel/stream` 作为 SSE 主通道。
- 触发：进入 `/intel` 页面并建立实时连接。
- 预期行为：输出标准 SSE 事件（`intel_item/heartbeat/error`）。
- 约束：事件白名单校验必须生效。

#### PRD-REQ-P4-004 强势股观察页 v2 口径
- 描述：强势股页面统一走 `/api/v2/intel/strong-stocks/watch`。
- 触发：访问 `/intel/strong-stocks/watch`。
- 预期行为：返回 `StrongStockWatchViewModel`，页面无 405。
- 约束：兼容期可保留旧别名，但前端不得依赖旧路径。

#### PRD-REQ-P4-005 三栏联动
- 描述：左栏题材选择驱动中栏过滤，中栏项选择驱动右栏验证。
- 触发：用户点击 ThemeRadar 或 IntelStreamItem。
- 预期行为：中/右栏在 1s 内完成联动刷新。
- 约束：任何单栏失败不应阻塞其他栏渲染。

#### PRD-REQ-P4-006 Workspace 三接口
- 描述：`/api/v2/workspace/theme-radar|intel-context|market-validation` 必须可用。
- 触发：`/intel` 页面加载与交互。
- 预期行为：返回 DTO 与约定字段一致，错误可降级展示。
- 约束：字段兼容“仅新增、不破坏语义”。

#### PRD-REQ-P4-007 Gate 与回放门禁
- 描述：A/B/D 核心门禁必须纳入发布检查。
- 触发：发布前 Gate 任务执行。
- 预期行为：A/B 回放无差异、B 覆盖率达标、D 输入收口测试通过。
- 约束：任一失败即禁止切换。

#### PRD-REQ-P4-008 灰度与回滚
- 描述：通过开关矩阵控制入口、SSE、三栏；支持 5 分钟内回滚。
- 触发：灰度发布与异常告警。
- 预期行为：可按矩阵逐级回退，不需改代码。
- 约束：回滚演练必须留档。

### 4) 非功能需求（NFR）
- NFR-P4-001 可用性：`/api/v2/intel/feed` 成功率 >= 99%（5 交易日滚动）。
- NFR-P4-002 实时连接：`/api/v2/intel/stream` 连接成功率 >= 99%（5 交易日滚动）。
- NFR-P4-003 性能：`/intel` 首屏 TTI P95 <= 2.5s（桌面网络基线）。
- NFR-P4-004 稳定性：SSE 失败后 3 次指数退避重连，失败后自动切 feed。
- NFR-P4-005 安全与边界：前端禁止直连 DB/SQL；仅通过 BFF/API Gateway。
- NFR-P4-006 可观测：SSE 连接数、重连次数、fallback 次数、接口错误率可观测。

### 5) 用例（Given/When/Then）

#### PRD-UC-P4-01 v2 路径门禁
- Given 代码变更涉及 `frontend/src`
- When CI 执行路径扫描
- Then 发现非 `/api/v2/*` 的 `/api/*` 即失败

#### PRD-UC-P4-02 SSE 主通道
- Given 用户进入 `/intel`
- When 建立 `/api/v2/intel/stream`
- Then 收到 `intel_item` 或 `heartbeat` 事件且连接保持

#### PRD-UC-P4-03 SSE 降级
- Given SSE 建连失败
- When 触发重连上限
- Then 自动切换 `/api/v2/intel/feed`，页面持续可用

#### PRD-UC-P4-04 三栏联动
- Given 已加载三栏
- When 点击左栏题材
- Then 中栏按题材过滤，右栏验证面板更新

#### PRD-UC-P4-05 强势股页
- Given 打开强势股页
- When 请求 `/api/v2/intel/strong-stocks/watch`
- Then 返回 200 且页面正常渲染，无 405

### 6) 验收映射（Acceptance Link）
- PRD-REQ-P4-001 -> ACPT-P3-UNIFIED-API-ENTRY, WBS-P4-API-GATE
- PRD-REQ-P4-002 -> ACPT-P4-INTEL-FEED, WBS-P4-FEED
- PRD-REQ-P4-003 -> ACPT-P4-INTEL-STREAM, WBS-P4-SSE
- PRD-REQ-P4-004 -> ACPT-P4-STRONG-WATCH-V2, WBS-P4-STRONG-WATCH
- PRD-REQ-P4-005 -> ACPT-P4-THREE-COLUMN-LINKAGE, WBS-P4-UI-LINKAGE
- PRD-REQ-P4-006 -> ACPT-P4-WORKSPACE-APIS, WBS-P4-WORKSPACE
- PRD-REQ-P4-007 -> ACPT-P3-AB-REPLAY-GATE, WBS-P4-QUALITY-GATE
- PRD-REQ-P4-008 -> ACPT-P4-GRAY-ROLLBACK, WBS-P4-RELEASE

### 7) 数据与接口样例（关键）
- GET `/api/v2/intel/feed?date=YYYY-MM-DD&type=all&session=all&limit=20`
- GET `/api/v2/intel/stream?date=YYYY-MM-DD&type=all&session=all&limit=20`
- GET `/api/v2/workspace/theme-radar?...`
- GET `/api/v2/workspace/intel-context?...`
- GET `/api/v2/workspace/market-validation?...`
- GET `/api/v2/intel/strong-stocks/watch?date=YYYY-MM-DD&window_days=7&limit=100`

### 8) 风险与假设（Risks/Assumptions）
- P0 风险：路由口径漂移导致 405 回归。
  - 缓解：v2 contract tests + 路由别名兼容 + CI 阻断。
- P0 风险：SSE 长连接不稳定导致中栏空白。
  - 缓解：自动重连 + feed fallback + 可观测告警。
- P1 风险：连续 5 交易日指标不达标。
  - 缓解：灰度限流 + 回滚矩阵 + 日报审计。

### 9) 发布与回滚约束（Release Constraints）
- 上线前置（全部满足）：
  - `frontend/src` 非 v2 API 扫描为 0
  - v2 contract tests 通过
  - A/B 回放 `Disagreement=0`
  - B confirmed 覆盖率 >= 95%
- 回滚触发（任一命中）：
  - `/api/v2/intel/stream` 连接成功率 < 99%
  - `/api/v2/intel/feed` 成功率 < 99%
  - 405/5xx 突增超阈值（按 SLO）
- 回滚执行：
  - 关闭 `ENABLE_INTEL_THREE_COLUMN`
  - 关闭 `ENABLE_INTEL_V2_STREAM`
  - 保留 `ENABLE_WEB_APP_SERVICE` 或按需回退入口

### 10) 通过判定（Exit Criteria）
- 以下条件必须全部满足（AND）：
  1. 20.1 Checklist 全部完成
  2. 20.2 指标连续 5 个交易日达标
  3. 回滚演练报告存在且 RTO <= 5 分钟
  4. 无未关闭 P0 阻断缺陷
