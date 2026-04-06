# FEATURE SPEC - P3.phase0（历史文件名保留 `P3.phaseA`）

> 历史别名文件。当前 canonical 文档已迁移至 [FEATURE_SPEC_P3.phase0.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/FEATURE_SPEC_P3.phase0.md)。
> 本文件保留用于兼容既有引用，不再作为后续增量维护主文件。

## 0. Meta
- Phase: `P3.phase0`
- Historical Alias: `P3.phaseA`
- 目标: 建立前端统一产品出口 `frontend_bff / api_gateway` 第一版边界，承接当前前置 `/intel` 页面与后续题材/个股工作台。
- 范围:
  - 新增 `/api/intel/feed`
  - 新增 `/api/theme-workspace/{subject_key}`
  - 新增 `/api/stock-workspace/{stock_id}`
  - 定义 BFF DTO、聚合规则、错误码与超时策略
- 非目标:
  - 不实现 WebSocket/SSE
  - 不重写 `theme_service` 领域查询逻辑
  - 不建设完整产业链图谱服务
- 冲突裁决说明:
  - 当前 `theme_service` 已提供 `/intel/feed` 和 `/themes/*`、`/stocks/*`，但这些接口属于领域服务与过渡聚合输出，不应作为长期前端契约。
  - 本文件历史命名为 `P3.phaseA`，当前统一口径将其视为 `P3.phase0`。
  - `P3.phase0` 以“统一出口层”收口前端访问边界，允许内部继续复用现有领域接口，但禁止前端直接依赖内部表结构与服务拼接方式。

## 0.2 当前实现状态（2026-03-31）

- 已完成：
  - `frontend_bff` 服务骨架
  - `GET /api/intel/feed`
  - `GET /api/theme-workspace/{subject_key}`
  - `GET /api/stock-workspace/{stock_id}`
  - 真实 PostgreSQL 集成测试
- 已验证：
  - `POSTGRES_DATABASE=stock_data_test .venv/bin/python -m pytest -q frontend_bff/tests/integration/test_p3_phasea_bff_real_db.py`
  - 结果：`3 passed`
- 当前仍未完成：
  - `ACCEPTANCE / PHASE_CONTRACT / TEST_CASE_SPEC` 的正式映射
  - `stock_service` 独立详情接口接入

## Task P3.phaseA-T01 — `frontend_bff` 第一版边界与适配层

### 1) 目标与边界
- 目标:
  - 建立独立于 `theme_service` 的前端统一出口层
  - 定义统一 DTO、错误码和 adapter 边界
  - 确保现有前端前置页面后续能平滑切换到 BFF
- 非目标:
  - 不新增业务计算内核
  - 不改变 `subject_key` 作为业务主键

### 2) 接口与契约
- 服务边界:
  - `frontend_bff`
- 内部依赖:
  - `theme_service`
  - `stock_service`（后续）
  - `intel_service`（后续）
- 外部契约:
  - 前端只调用 `/api/*`
- 错误码:
  - `400`: 参数非法
  - `404`: 资源不存在
  - `409`: 下游数据口径冲突
  - `424`: 下游依赖失败
  - `500`: BFF 内部错误
- 超时:
  - 单下游请求默认 `800ms`
  - BFF 总超时目标 `< 1500ms`
- 幂等:
  - 只读查询接口天然幂等

### 3) 数据模型与状态变更
- 不新增业务表
- 新增 DTO 边界:
  - `IntelFeedView`
  - `ThemeWorkspaceView`
  - `StockWorkspaceView`
- 兼容策略:
  - 第一版允许 BFF 内部直接调用 `theme_service` 现有 REST/仓库
  - 第二版再替换为 `intel_service / workspace_service`

### 4) 子功能分解
- `F-P3.phaseA-T01-01` BFF 路由层
  - 输入: 前端 `/api/*` 请求
  - 处理: 参数校验、下游调度、错误码统一
  - 输出: 统一 JSON 响应
  - 失败处理: 下游失败映射为 `424`
  - 可观测证据: `request_id/downstream_service/latency_ms`
- `F-P3.phaseA-T01-02` DTO 适配层
  - 输入: 下游领域接口返回
  - 处理: 重命名、裁剪、结构统一
  - 输出: 页面稳定 DTO
  - 失败处理: 字段缺失时返回部分结果并记录 `partial=true`
  - 可观测证据: 字段映射版本号
- `F-P3.phaseA-T01-03` 依赖治理层
  - 输入: 多个下游服务
  - 处理: 超时、fallback、部分成功
  - 输出: 聚合响应 + diagnostics
  - 失败处理: 关键模块失败则整体失败，非关键模块可降级
  - 可观测证据: `downstream_fail_count/partial_response_count`

### 5) 实现步骤
- Step-1: 新建 `frontend_bff` 目录与服务入口
- Step-2: 定义统一错误模型和 request context
- Step-3: 封装 `theme_service` adapter
- Step-4: 定义三类页面 DTO
- Step-5: 补充真实集成测试骨架
- 实际完成情况:
  - 已完成 Step-1 ~ Step-5

### 6) 测试设计与命令
- 测试用例:
  - `TC-P3A-001-bff-health`
  - `TC-P3A-002-bff-downstream-timeout`
  - `TC-P3A-003-bff-dto-stability`
- 必跑命令:
  - `.venv/bin/python -m py_compile frontend_bff/*.py`
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration`
- 失败定位:
  - adapter 先看 `frontend_bff/adapters/*`
  - DTO 再看 `frontend_bff/schemas/*`

### 7) 风险与回滚
- 风险:
  - BFF 只是简单透传，未真正削弱耦合
  - 字段映射过度，导致丢失下游能力
- 回滚:
  - 保留现有 `theme_service` 只读接口
  - 前端 adapter 可临时回退直连

### 8) 验收映射
- `ACPT-P3A-001`

---

## Task P3.phaseA-T02 — `/api/intel/feed` 情报聚合出口

### 1) 目标与边界
- 目标:
  - 将前端对 `/intel/feed` 的依赖迁移到 BFF
  - 稳定情报流 DTO 与筛选参数
- 非目标:
  - 不改变当前 `event/theme_move/new_theme` 生成逻辑
  - 不加入实时推送

### 2) 接口与契约
- 接口:
  - `GET /api/intel/feed`
- 参数:
  - `date`
  - `session=all|pre|intra|post`
  - `type=all|event|theme_move|new_theme`
  - `subject_key?`
  - `stock_id?`
  - `limit=1..500`
- 返回:

```ts
interface IntelFeedView {
  items: IntelFeedItem[]
  count: number
  date?: string
  session: 'all' | 'pre' | 'intra' | 'post'
  type: 'all' | 'event' | 'theme_move' | 'new_theme'
  diagnostics?: {
    partial: boolean
    sources: string[]
  }
}
```

- 下游依赖:
  - `theme_service:/intel/feed`
- 超时:
  - 下游 `800ms`
  - 总体 `< 1200ms`

### 3) 数据模型与状态变更
- 不新增写库
- BFF 层统一补充:
  - `diagnostics.partial`
  - `sources`

### 4) 子功能分解
- `F-P3.phaseA-T02-01` 情报请求透传与校验
  - 输入: 前端查询参数
  - 处理: 参数规范化
  - 输出: 下游可执行请求
  - 失败处理: 非法参数直接 `400`
  - 可观测证据: 规范化参数日志
- `F-P3.phaseA-T02-02` 情报 DTO 稳定器
  - 输入: 下游 `/intel/feed`
  - 处理: 响应裁剪与字段兜底
  - 输出: `IntelFeedView`
  - 失败处理: 字段缺失则 `partial=true`
  - 可观测证据: DTO 版本
- `F-P3.phaseA-T02-03` 筛选兼容层
  - 输入: 旧前端筛选条件
  - 处理: 与 BFF 新契约对齐
  - 输出: 兼容响应
  - 失败处理: 不兼容字段丢弃并告警
  - 可观测证据: 兼容字段命中数

### 5) 实现步骤
- Step-1: 定义 `/api/intel/feed` route
- Step-2: 封装下游 adapter
- Step-3: 加 diagnostics 包装
- Step-4: 增加真实 smoke test
- 实际完成情况:
  - 已完成 Step-1 ~ Step-4

### 6) 测试设计与命令
- 测试用例:
  - `TC-P3A-004-intel-feed-proxy`
  - `TC-P3A-005-intel-feed-filter-compat`
  - `TC-P3A-006-intel-feed-partial-response`
- 必跑命令:
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_intel_feed_api.py`

### 7) 风险与回滚
- 风险:
  - 下游当天数据为空导致前端误判接口失败
- 回滚:
  - 返回空列表而非 500

### 8) 验收映射
- `ACPT-P3A-002`

---

## Task P3.phaseA-T03 — `/api/theme-workspace/{subject_key}` 题材工作台聚合出口

### 1) 目标与边界
- 目标:
  - 为 `/themes/:subject_key` 页面提供单请求聚合出口
  - 聚合题材详情、历史、子树、股票池
- 非目标:
  - 不提供编辑能力
  - 不生成产业链环节图谱

### 2) 接口与契约
- 接口:
  - `GET /api/theme-workspace/{subject_key}`
- 参数:
  - `include_history=true|false`
  - `include_children=true|false`
  - `include_stocks=true|false`
  - `include_leaders=true|false`
  - `stock_mapping_scope=pool|leader_overlay|all`
  - `history_limit`
  - `children_limit`
  - `stocks_limit`
- 返回:

```ts
interface ThemeWorkspaceView {
  subject_key: string
  detail: Record<string, unknown>
  history?: Record<string, unknown>[]
  children?: Record<string, unknown>[]
  stocks?: Record<string, unknown>[]
  diagnostics?: {
    partial: boolean
    missing_sections: string[]
  }
}
```

- 下游依赖:
  - `theme_service:/themes/{subject_key}`
  - `theme_service:/themes/{subject_key}/history`
  - `theme_service:/themes/{subject_key}/children`
  - `theme_service:/themes/{subject_key}/stocks`

### 3) 数据模型与状态变更
- 不新增写库
- BFF 聚合后的 section 允许部分缺失
- 主键统一:
  - `subject_key`

### 4) 子功能分解
- `F-P3.phaseA-T03-01` 题材详情聚合
  - 输入: `subject_key`
  - 处理: 拉取 detail
  - 输出: `detail`
  - 失败处理: detail 缺失则整体 `404`
  - 可观测证据: detail 拉取耗时
- `F-P3.phaseA-T03-02` 题材联动 section 聚合
  - 输入: history/children/stocks 查询
  - 处理: 并发拉取非关键区块
  - 输出: 可选 sections
  - 失败处理: 单 section 失败时 partial 返回
  - 可观测证据: missing_sections
- `F-P3.phaseA-T03-03` 股票池口径治理
  - 输入: `stock_mapping_scope/include_leaders`
  - 处理: 保持 pool 为默认口径
  - 输出: 稳定股票池 section
  - 失败处理: 参数冲突时 `400`
  - 可观测证据: mapping_scope

### 5) 实现步骤
- Step-1: 定义 `theme-workspace` DTO
- Step-2: 实现 4 路 adapter
- Step-3: 做并发聚合与 partial response
- Step-4: 增加真实集成测试
- 实际完成情况:
  - 已完成 Step-1 ~ Step-4

### 6) 测试设计与命令
- 测试用例:
  - `TC-P3A-007-theme-workspace-happy-path`
  - `TC-P3A-008-theme-workspace-partial`
  - `TC-P3A-009-theme-workspace-pool-default`
- 必跑命令:
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_theme_workspace_api.py`

### 7) 风险与回滚
- 风险:
  - 一次拉取过多区块，导致延迟升高
- 回滚:
  - 默认只返回 detail + stocks

### 8) 验收映射
- `ACPT-P3A-003`

---

## Task P3.phaseA-T04 — `/api/stock-workspace/{stock_id}` 个股工作台聚合出口

### 1) 目标与边界
- 目标:
  - 为个股页提供单请求聚合出口
  - 聚合个股详情与所属题材列表
- 非目标:
  - 不实现盘口、分时、资金流服务

### 2) 接口与契约
- 接口:
  - `GET /api/stock-workspace/{stock_id}`
- 参数:
  - `include_themes=true|false`
  - `include_leaders=true|false`
  - `mapping_scope=pool|leader_overlay|all`
  - `themes_limit`
- 返回:

```ts
interface StockWorkspaceView {
  stock_id: string
  stock_detail?: Record<string, unknown>
  themes?: Record<string, unknown>[]
  diagnostics?: {
    partial: boolean
    missing_sections: string[]
  }
}
```

- 下游依赖:
  - `theme_service:/stocks/{stock_id}/themes`
  - `stocks` 详情查询接口或仓库（后续可由 `stock_service` 提供）

### 3) 数据模型与状态变更
- 不新增写库
- 第一版允许 `stock_detail` 为轻量信息
- 主题口径默认 `pool`

### 4) 子功能分解
- `F-P3.phaseA-T04-01` 个股主题反查
  - 输入: `stock_id`
  - 处理: 拉取 themes
  - 输出: `themes`
  - 失败处理: 无主题时返回空数组
  - 可观测证据: 主题数
- `F-P3.phaseA-T04-02` 个股详情适配
  - 输入: stock detail source
  - 处理: 裁剪为页面稳定字段
  - 输出: `stock_detail`
  - 失败处理: 缺失则 partial 返回
  - 可观测证据: detail source
- `F-P3.phaseA-T04-03` overlay 控制器
  - 输入: `mapping_scope/include_leaders`
  - 处理: 控制是否叠加 leader 关系
  - 输出: 稳定主题列表
  - 失败处理: 参数非法则 `400`
  - 可观测证据: overlay hit count

### 5) 实现步骤
- Step-1: 定义 `stock-workspace` DTO
- Step-2: 接入 `/stocks/{stock_id}/themes`
- Step-3: 接入 stock detail adapter
- Step-4: 增加真实集成测试
- 实际完成情况:
  - 已完成 Step-1 ~ Step-4

### 6) 测试设计与命令
- 测试用例:
  - `TC-P3A-010-stock-workspace-happy-path`
  - `TC-P3A-011-stock-workspace-overlay`
  - `TC-P3A-012-stock-workspace-no-theme`
- 必跑命令:
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_stock_workspace_api.py`

### 7) 风险与回滚
- 风险:
  - stock detail 来源短期不稳定
- 回滚:
  - 第一版仅返回 `themes`

### 8) 验收映射
- `ACPT-P3A-004`
