# FEATURE SPEC - P3.phase0

## 0. Meta
- Phase: `P3.phase0`
- Historical Alias: `P3.phaseA`
- Canonical File: `FEATURE_SPEC_P3.phase0.md`
- 目标: 建立前端统一产品出口 `frontend_bff / /api/*` 第一版边界，收口 `/intel`、题材工作台、个股工作台的长期前端契约。
- 范围:
  - `GET /api/intel/feed`
  - `GET /api/theme-workspace/{subject_key}`
  - `GET /api/stock-workspace/{stock_id}`
  - BFF DTO、错误码、超时与 partial diagnostics
- 非目标:
  - 不实现 `SSE/WebSocket`
  - 不重写 `theme_service` 领域查询逻辑
  - 不建设完整产业链图谱服务
- 冲突裁决说明:
  - `P3.phaseA` 现统一视为 `P3.phase0` 历史别名。
  - 前端长期契约采用 `frontend_bff / /api/*`，而不是继续直接绑定 `theme_service`。

## 0.1 当前实现状态
- 已存在 `frontend_bff` 服务骨架与核心接口。
- 本文档目标不是重复实现说明，而是把历史 `phaseA` 设计统一收敛到正式 `phase0` 编码。

## Task `P3.phase0-T01` — `frontend_bff` 边界冻结与请求上下文

### 1) 目标与边界
- 目标:
  - 冻结 `frontend_bff` 作为前端唯一产品出口。
  - 统一 `request_id / diagnostics / downstream timeout` 语义。
- 非目标:
  - 不在本任务中引入新业务计算。
  - 不改变 `subject_key` 作为题材业务主键。

### 1.1 子功能分解
- `F-P3.phase0-T01-01` BFF 服务边界冻结
  - 输入: 前端 `/api/*` 请求
  - 处理: 参数校验、路由分发、请求上下文注入
  - 输出: 统一产品层响应
  - 失败处理: 非法参数返回 `400`
  - 可观测证据: `request_id`, `route_name`, `latency_ms`
- `F-P3.phase0-T01-02` 下游超时与错误码治理
  - 输入: `theme_service`/后续领域服务调用结果
  - 处理: 超时控制、依赖失败映射
  - 输出: `424/500` 等稳定错误码
  - 失败处理: 关键依赖失败时整体失败，非关键区块允许 partial
  - 可观测证据: `downstream_service`, `downstream_status`, `partial`
- `F-P3.phase0-T01-03` 历史命名兼容
  - 输入: `P3.phaseA` 旧文档与旧测试命名
  - 处理: 保留 alias，统一输出 `P3.phase0`
  - 输出: 新旧命名映射表
  - 失败处理: 发现新文档继续使用 `phaseA` 时阻断评审
  - 可观测证据: alias mapping 清单

### 2) 接口与契约
- 服务边界:
  - `frontend_bff`
- 外部契约:
  - 前端仅允许访问 `/api/*`
- 错误码:
  - `400` 参数非法
  - `404` 资源不存在
  - `409` 下游数据口径冲突
  - `424` 下游依赖失败
  - `500` BFF 内部错误
- 超时:
  - 单下游请求默认 `800ms`
  - BFF 总超时目标 `< 1500ms`
- 幂等/重试:
  - 只读查询天然幂等
  - 下游请求超时不自动无限重试

### 3) 数据模型与状态变更
- 不新增业务表。
- 新增或冻结 DTO 元字段：
  - `request_id`
  - `diagnostics.partial`
  - `diagnostics.sources`
  - `diagnostics.missing_sections`
- 兼容策略:
  - 第一版允许 BFF 内部复用 `theme_service`
  - 不允许前端继续依赖领域服务字段细节

### 4) 实现步骤（最小可执行序列）
- Step-1: 冻结 `frontend_bff` 入口、全局 request context 和错误模型。
- Step-2: 统一 `/api/*` 路由注册和参数校验。
- Step-3: 接入下游超时控制和 `partial diagnostics` 包装。
- Step-4: 建立历史 `P3.phaseA -> P3.phase0` 命名映射与扫描门禁。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3A-001-bff-health`
  - `TC-P3A-002-bff-downstream-timeout`
  - `TC-P3A-003-bff-dto-stability`
- 必跑命令:
  - `.venv/bin/python -m py_compile frontend_bff/*.py`
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration`
- 预期结果:
  - BFF 基础健康与集成测试通过
  - DTO 稳定字段不缺失
- 失败时定位入口:
  - `frontend_bff/app.py`
  - `frontend_bff/repositories/bff_repository.py`

### 6) 风险与回滚
- 风险:
  - BFF 只是透传，未真正建立稳定 DTO 层
  - 历史 `phaseA` 命名继续扩散
- 缓解:
  - 用 DTO 稳定层和文档扫描门禁约束
- 回滚触发条件:
  - BFF 请求上下文或错误模型不稳定，影响前端联调
- 回滚操作:
  - 回退到上一版 BFF 入口，保留新 alias 文档

### 7) 验收映射
- `ACPT-P3A-001`

---

## Task `P3.phase0-T02` — `/api/intel/feed` 情报聚合出口

### 1) 目标与边界
- 目标:
  - 把 `/intel` 页面正式收口到 BFF。
  - 冻结筛选参数、列表 DTO、空结果与部分结果语义。
- 非目标:
  - 不改变底层情报生成逻辑。
  - 不加入实时推送。

### 1.1 子功能分解
- `F-P3.phase0-T02-01` 情报请求规范化
  - 输入: `date/session/type/subject_key/stock_id/limit`
  - 处理: 参数标准化与默认值裁决
  - 输出: 下游可执行查询
  - 失败处理: 非法参数返回 `400`
  - 可观测证据: 规范化后的 query log
- `F-P3.phase0-T02-02` 情报 DTO 稳定器
  - 输入: 下游情报流结果
  - 处理: 字段裁剪、空值兜底、diagnostics 封装
  - 输出: `IntelFeedView`
  - 失败处理: 字段缺失返回 `partial=true`
  - 可观测证据: `dto_version`, `partial`
- `F-P3.phase0-T02-03` 空数据与失败区分
  - 输入: 空结果、下游失败、部分成功
  - 处理: 区分 `[]` 与 `424/500`
  - 输出: 稳定错误/空结果语义
  - 失败处理: 下游失败不伪装成空结果
  - 可观测证据: `diagnostics.sources`

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
  - `items`
  - `count`
  - `date`
  - `session`
  - `type`
  - `diagnostics`
- 超时:
  - 下游 `< 800ms`
  - 总体 `< 1200ms`

### 3) 数据模型与状态变更
- 不新增写库。
- DTO 字段冻结：
  - `IntelFeedView`
  - `IntelFeedItem`
- 兼容策略:
  - 保留旧筛选语义兼容层

### 4) 实现步骤（最小可执行序列）
- Step-1: 冻结 `/api/intel/feed` route 与 query schema。
- Step-2: 封装下游 adapter 与 DTO 稳定器。
- Step-3: 加入空结果/失败/partial 三类语义分支。
- Step-4: 增补真实集成测试与空数据回归验证。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3A-004-intel-feed-proxy`
  - `TC-P3A-005-intel-feed-filter-compat`
  - `TC-P3A-006-intel-feed-partial-response`
- 必跑命令:
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_intel_feed_api.py`
- 失败时定位入口:
  - `frontend_bff/repositories/bff_repository.py`
  - `/intel` 对应前端接口适配层

### 6) 风险与回滚
- 风险:
  - 当天无数据被前端误判为接口失败
- 缓解:
  - 空结果与依赖失败必须显式区分
- 回滚触发条件:
  - DTO 变更导致 `/intel` 页面无法消费
- 回滚操作:
  - 回退到上一版 DTO，保留 diagnostics 字段兼容

### 7) 验收映射
- `ACPT-P3A-002`

---

## Task `P3.phase0-T03` — `/api/theme-workspace/{subject_key}` 题材工作台聚合出口

### 1) 目标与边界
- 目标:
  - 为题材页提供单请求聚合出口。
  - 聚合详情、历史、子题材、股票池四类区块。
- 非目标:
  - 不提供编辑能力。
  - 不生成产业链图谱。

### 1.1 子功能分解
- `F-P3.phase0-T03-01` 题材详情聚合
  - 输入: `subject_key`
  - 处理: 拉取 detail
  - 输出: `detail`
  - 失败处理: detail 缺失直接 `404`
  - 可观测证据: detail latency
- `F-P3.phase0-T03-02` 联动区块并发聚合
  - 输入: history/children/stocks 查询参数
  - 处理: 并发拉取非关键区块
  - 输出: 可选 sections
  - 失败处理: 单 section 失败返回 partial
  - 可观测证据: `missing_sections`
- `F-P3.phase0-T03-03` 股票池口径治理
  - 输入: `stock_mapping_scope/include_leaders`
  - 处理: 以 `pool` 为默认口径
  - 输出: 稳定股票池 section
  - 失败处理: 参数冲突返回 `400`
  - 可观测证据: `mapping_scope`

### 2) 接口与契约
- 接口:
  - `GET /api/theme-workspace/{subject_key}`
- 参数:
  - `include_history`
  - `include_children`
  - `include_stocks`
  - `include_leaders`
  - `stock_mapping_scope=pool|leader_overlay|all`
  - `history_limit/children_limit/stocks_limit`
- 返回:
  - `subject_key`
  - `detail`
  - `history?`
  - `children?`
  - `stocks?`
  - `diagnostics`

### 3) 数据模型与状态变更
- 不新增写库。
- 主键统一:
  - `subject_key`
- 允许部分区块缺失，但必须标记 `missing_sections`。

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义 `ThemeWorkspaceView` DTO。
- Step-2: 接入四路 adapter。
- Step-3: 增加并发聚合与 partial response。
- Step-4: 增加默认股票池口径门禁。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3A-007-theme-workspace-happy-path`
  - `TC-P3A-008-theme-workspace-partial`
  - `TC-P3A-009-theme-workspace-pool-default`
- 必跑命令:
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_theme_workspace_api.py`

### 6) 风险与回滚
- 风险:
  - 一次拉取过多区块导致时延升高
- 缓解:
  - 默认 detail + stocks，其他区块按参数开启
- 回滚触发条件:
  - 并发聚合导致页面超时或不稳定
- 回滚操作:
  - 缩回到 detail + stocks 最小集合

### 7) 验收映射
- `ACPT-P3A-003`

---

## Task `P3.phase0-T04` — `/api/stock-workspace/{stock_id}` 个股工作台聚合出口

### 1) 目标与边界
- 目标:
  - 为个股页提供单请求聚合出口。
  - 聚合个股详情与所属题材列表。
- 非目标:
  - 不实现盘口、分时、资金流服务。

### 1.1 子功能分解
- `F-P3.phase0-T04-01` 个股主题反查
  - 输入: `stock_id`
  - 处理: 拉取 `themes`
  - 输出: 所属题材列表
  - 失败处理: 无主题返回空数组
  - 可观测证据: theme count
- `F-P3.phase0-T04-02` 个股详情适配
  - 输入: stock detail source
  - 处理: 裁剪为页面稳定字段
  - 输出: `stock_detail`
  - 失败处理: 缺失时 partial 返回
  - 可观测证据: `detail_source`
- `F-P3.phase0-T04-03` overlay 控制器
  - 输入: `mapping_scope/include_leaders`
  - 处理: 控制是否叠加 leader 关系
  - 输出: 稳定主题列表
  - 失败处理: 参数非法返回 `400`
  - 可观测证据: `overlay_hit_count`

### 2) 接口与契约
- 接口:
  - `GET /api/stock-workspace/{stock_id}`
- 参数:
  - `include_themes`
  - `include_leaders`
  - `mapping_scope=pool|leader_overlay|all`
  - `themes_limit`
- 返回:
  - `stock_id`
  - `stock_detail?`
  - `themes?`
  - `diagnostics`

### 3) 数据模型与状态变更
- 不新增写库。
- 第一版允许 `stock_detail` 为轻量字段。
- 主题口径默认 `pool`。

### 4) 实现步骤（最小可执行序列）
- Step-1: 定义 `StockWorkspaceView` DTO。
- Step-2: 接入 `/stocks/{stock_id}/themes`。
- Step-3: 接入 stock detail adapter。
- Step-4: 增加 overlay 参数控制与真实集成测试。

### 5) 测试设计与命令
- 对应测试用例:
  - `TC-P3A-010-stock-workspace-happy-path`
  - `TC-P3A-011-stock-workspace-overlay`
  - `TC-P3A-012-stock-workspace-no-theme`
- 必跑命令:
  - `.venv/bin/python -m pytest -q frontend_bff/tests/integration/test_stock_workspace_api.py`

### 6) 风险与回滚
- 风险:
  - stock detail 来源短期不稳定
- 缓解:
  - 第一版允许只有 `themes`
- 回滚触发条件:
  - stock detail adapter 不稳定，影响整体出口
- 回滚操作:
  - 回退到仅返回 `themes`

### 7) 验收映射
- `ACPT-P3A-004`
