# FEATURE SPEC - P4.phaseA

## 0. Meta
- Phase: `P4.phaseA`
- 目标: 前置交付一个类似久赢恒丰的“情报列表页”，集中展示当天新闻事件、题材异动、新题材候选与关联股票。
- 范围:
  - 新增 `/intel/feed` 聚合接口
  - 新增 `/intel` 前端页面
  - 新增右侧详情抽屉与题材/股票联动
- 非目标:
  - 不实现实时分时图
  - 不实现复杂交易终端
  - 不实现完整复盘系统
- 冲突裁决说明:
  - 现阶段优先交付“情报展示与认知放大”，不等待完整第四阶段行情工作台。
  - 前端默认复用现有 phase0/phase1 数据对象，不重新设计平行 DTO。
  - 当前允许前端暂时直连 `theme_service` 的只读/聚合接口，但这只是过渡方案；长期必须迁移到第三阶段定义的 `frontend_bff / api_gateway`。

## 0.2 当前实现状态（2026-03-31）

- 已完成：
  - `frontend/` 工程初始化
  - `/intel` 页面骨架
  - 情报列表加载
  - 右侧题材工作台联动
  - 个股工作台联动
  - URL 状态同步
  - `/themes/:subject_key` 与 `/stocks/:stock_id` 页面化跳转
- 已验证：
  - 本机构建命令 `npm run build`
  - 多次构建通过，最新产物已生成于 `frontend/dist`
- 当前接口依赖口径：
  - 前端已切到 `frontend_bff:/api/*`
  - 不再以 `theme_service` 作为长期前端契约

## 0.1 与第三阶段架构的兼容约束

- `P4.phaseA` 当前定位为“产品前置验证层”，不是最终产品输出层。
- `GET /intel/feed` 当前已实现于 `theme_service`，应视为 `REST first` 的过渡聚合接口，而不是最终实时资讯流引擎。
- 前端不得自行重建排序、权重和实体归一逻辑，列表权重与联动关系必须由后端输出。
- 页面主键统一使用 `subject_key`，不得重新引入以 `theme_id` 为统一业务主键的方案。
- 股票列表默认只读取主股票池，`leader overlay` 只作为可选增强。
- 后续第三阶段落地 `frontend_bff / api_gateway` 后，`P4.phaseA` 前端必须可平滑迁移，不得把页面逻辑深度绑定到 `theme_service` 的内部实现。

## Task P4.phaseA-T01 — `/intel/feed` 聚合接口

### 1) 目标与边界
- 目标:
  - 提供统一情报流接口，聚合 `event`、`theme_move`、`new_theme`
  - 让前端不再直接拼 `news_event / event_theme_map / subject_rank_daily / subject_node_staging`
- 非目标:
  - 不做实时推送
  - 不做前端自排序
  - 不承担最终 `BFF` 角色

### 2) 接口与契约
- 接口:
  - `GET /intel/feed`
- 当前落点:
  - 过渡阶段：`theme_service`
- 长期落点:
  - `intel_service` 或 `frontend_bff`
- 参数:
  - `date: YYYY-MM-DD`
  - `session: pre | intra | post | all`
  - `type: all | event | theme_move | new_theme`
  - `subject_key?: string`
  - `stock_id?: string`
  - `limit: 1..500`
- 返回:

```ts
interface IntelFeedItem {
  item_id: string
  item_type: 'event' | 'theme_move' | 'new_theme'
  occurred_at: string
  title: string
  summary: string
  theme_subject_keys: string[]
  theme_names: string[]
  stock_ids: string[]
  stock_names: string[]
  confidence?: number
  impact_score?: number
  source_type: string
}
```

- 错误码:
  - `400`: 参数非法
  - `404`: 指定日期无数据
  - `500`: 聚合查询失败
- 幂等:
  - 同条件查询结果稳定
- 超时:
  - 单次查询目标 `< 1.5s`

### 3) 数据模型与状态变更
- 读取来源:
  - `news_raw`
  - `news_event`
  - `event_theme_map`
  - `subject_rank_daily`
  - `theme_history_event`
  - `subject_node_staging`
- 不新增写库表
- 如需实现，优先新增只读聚合视图或仓库方法，不新增 serving 表

### 4) 子功能分解
- `F-P4.phaseA-T01-01` 新闻事件聚合器
  - 输入: `news_event + event_theme_map + news_raw`
  - 处理: 聚合标题、摘要、命中题材、关联股票
  - 输出: `item_type=event`
  - 失败处理: 单条事件缺题材时仍可展示，但标注 `unmapped`
  - 可观测证据: 当日事件数
- `F-P4.phaseA-T01-02` 题材异动聚合器
  - 输入: `subject_rank_daily + theme_history_event`
  - 处理: 生成题材异动条目
  - 输出: `item_type=theme_move`
  - 失败处理: 历史缺失时仅展示 rank 快照
  - 可观测证据: 当日题材异动数
- `F-P4.phaseA-T01-03` 新题材候选聚合器
  - 输入: `subject_node_staging diff`、`publish_clustering/human_review`（如已接入）
  - 处理: 生成新题材条目
  - 输出: `item_type=new_theme`
  - 失败处理: 无 diff 时返回空列表
  - 可观测证据: 新题材候选数

### 5) 实现步骤
- Step-1: 新增 `IntelFeedRepository` 或等价聚合仓库
- Step-2: 先分别实现 `event/theme_move/new_theme` 三类查询
- Step-3: 定义统一 DTO 并做时间倒序合并
- Step-4: 新增 `GET /intel/feed`
- Step-5: 用真实 DB 跑聚合接口验证
- Step-6: 在文档中标记为“过渡接口”，为后续迁移到 `frontend_bff` 预留出口
- 实际完成情况:
  - 已完成 Step-1 ~ Step-6

### 6) 测试设计与命令
- 测试用例:
  - `TC-P4A-001-intel-feed-event`
  - `TC-P4A-002-intel-feed-theme-move`
  - `TC-P4A-003-intel-feed-new-theme`
  - `TC-P4A-004-intel-feed-filtering`
- 必跑命令:
  - `.venv/bin/python -m py_compile theme_service/app.py`
  - `.venv/bin/python -m pytest -q theme_service/tests/integration/test_p4_phaseA_intel_feed_real_db.py`
- 失败定位:
  - 仓库查询先看 `theme_service/repositories/*`
  - DTO 组装再看 API 层

### 7) 风险与回滚
- 风险:
  - 三类数据时间口径不一致
  - 新题材数据源阶段性为空
  - 若长期停留在 `theme_service`，前端会继续耦合到底层领域服务
- 回滚:
  - 接口降级为仅返回 `event + theme_move`
  - 不影响现有 `/themes/*` 路径

### 8) 验收映射
- `ACPT-P4A-001`
- `ACPT-P4A-002`

---

## Task P4.phaseA-T02 — `/intel` 情报列表页

### 1) 目标与边界
- 目标:
  - 提供高密度情报流页面，类似久赢恒丰“情报”列表
  - 支持时间、类型、题材、股票维度筛选
- 非目标:
  - 不做复杂图表
  - 不做桌面端原生能力
  - 不替代未来统一产品工作台

### 2) 接口与契约
- 页面:
  - `/intel`
- 依赖接口:
  - `GET /intel/feed`
- 兼容约束:
  - 当前可直连 `theme_service`
  - 组件层必须通过统一 adapter 调接口，后续可切换到 `frontend_bff` 而不重写页面状态逻辑
- 前端状态:
  - `currentDate`
  - `currentType`
  - `currentSession`
  - `currentSubjectKey?`
  - `currentStockId?`
  - `selectedIntelItemId?`

### 3) 数据模型与状态变更
- 前端 DTO:
  - `IntelFeedItem`
- 全局状态最小化:
  - 列表状态
  - 详情选中状态
- 不允许前端自行重新计算题材权重、排序分数

### 4) 子功能分解
- `F-P4.phaseA-T02-01` 顶部筛选栏
  - 输入: 日期/类型/题材/股票
  - 处理: 触发列表刷新
  - 输出: 新的查询条件
  - 失败处理: 参数非法时回退默认筛选
  - 可观测证据: URL query 与状态同步
- `F-P4.phaseA-T02-02` 情报列表区
  - 输入: `/intel/feed` 返回结果
  - 处理: 高密度渲染、颜色编码、标签化
  - 输出: `IntelFeedItemCard[]`
  - 失败处理: 接口失败时展示空态/错误态
  - 可观测证据: 列表数量与接口返回一致
- `F-P4.phaseA-T02-03` 列表项交互
  - 输入: 点击某条情报
  - 处理: 打开详情抽屉并同步选中态
  - 输出: `selectedIntelItemId`
  - 失败处理: 项目不存在时不切换
  - 可观测证据: 选中态高亮

### 5) 实现步骤
- Step-1: 新建前端工程目录 `frontend/`
- Step-2: 初始化 `React + TypeScript + Vite + Tailwind + Zustand`
- Step-3: 落 `/intel` 路由和页面骨架
- Step-4: 接通筛选栏与情报列表
- Step-5: 调整为高密度表格/列表样式
- Step-6: 抽象 API adapter，避免页面层直接写死底层服务路径
- 实际完成情况:
  - 已完成 Step-1 ~ Step-6

### 6) 测试设计与命令
- 测试用例:
  - `TC-P4A-005-intel-page-load`
  - `TC-P4A-006-intel-filters`
  - `TC-P4A-007-intel-item-select`
- 必跑命令:
  - `npm run build`
  - `npm run test`
- 失败定位:
  - 先看状态管理，再看 API adapter

### 7) 风险与回滚
- 风险:
  - 列表密度过高导致可读性差
  - 接口字段变化导致渲染失败
  - 页面若直接耦合底层接口，后续迁移成本会放大
- 回滚:
  - 先保留简化版列表，不阻塞后端

### 8) 验收映射
- `ACPT-P4A-003`

---

## Task P4.phaseA-T03 — 详情抽屉与题材/股票联动

### 1) 目标与边界
- 目标:
  - 用户点击一条情报后，能看到题材详情、历史、子树、股票池
  - 实现“新闻 -> 题材 -> 股票”闭环
- 非目标:
  - 不做实时盘口

### 2) 接口与契约
- 依赖接口:
  - `GET /themes/{subject_key}`
  - `GET /themes/{subject_key}/history`
  - `GET /themes/{subject_key}/children`
  - `GET /themes/{subject_key}/stocks`
  - `GET /stocks/{stock_id}/themes`
- 股票口径:
  - 默认 `mapping_scope=pool`
  - 显式 `include_leaders=true` 才叠加 leader overlay
- 长期接口口径:
  - 当前复用 `/themes/*`、`/stocks/*`
  - 后续应收敛到 `theme-workspace` / `stock-workspace` 风格的 BFF 接口

### 3) 数据模型与状态变更
- 详情模型:
  - `ThemeDetail`
  - `ThemeHistory[]`
  - `ThemeChild[]`
  - `ThemeStock[]`
- 抽屉状态:
  - `drawerOpen`
  - `activeSubjectKey`
  - `stockMappingScope`
  - `includeLeaders`

### 4) 子功能分解
- `F-P4.phaseA-T03-01` 题材详情联动器
  - 输入: `subject_key`
  - 处理: 拉取详情、历史、子树
  - 输出: 详情抽屉主体
  - 失败处理: 单个模块失败不阻断整页
  - 可观测证据: 抽屉内模块独立加载态
- `F-P4.phaseA-T03-02` 股票池面板
  - 输入: `subject_key + mapping_scope + include_leaders`
  - 处理: 渲染完整股票池并支持龙头增强切换
  - 输出: `ThemeStockPanel`
  - 失败处理: 无股票时展示空态
  - 可观测证据: pool/overlay 数量切换
- `F-P4.phaseA-T03-03` 股票反查联动器
  - 输入: `stock_id`
  - 处理: 拉取该股所属题材列表
  - 输出: 反查结果
  - 失败处理: 无归属题材则展示空态
  - 可观测证据: 反查结果数量

### 5) 实现步骤
- Step-1: 做右侧详情抽屉骨架
- Step-2: 接入题材详情/历史/children
- Step-3: 接入 `/themes/{subject_key}/stocks`
- Step-4: 增加 `leader overlay` 开关
- Step-5: 增加股票反查联动
- Step-6: 为后续 `theme-workspace / stock-workspace` 聚合接口预留前端状态边界
- 实际完成情况:
  - 已完成 Step-1 ~ Step-6

### 6) 测试设计与命令
- 测试用例:
  - `TC-P4A-008-theme-detail-drawer`
  - `TC-P4A-009-stock-pool-default`
  - `TC-P4A-010-stock-leader-overlay`
  - `TC-P4A-011-stock-theme-reverse-lookup`
- 必跑命令:
  - `npm run build`
  - `.venv/bin/python -m pytest -q theme_service/tests/integration/test_p2_phase1_read_api_real_db.py`
- 失败定位:
  - 先验证后端 API 再看前端联动

### 7) 风险与回滚
- 风险:
  - 抽屉信息过多，交互复杂
  - pool/leader 两类股票关系混淆
  - 直接拼多个领域接口，后续容易在页面侧堆积聚合逻辑
- 回滚:
  - 默认只展示 `pool`
  - leader overlay 做可选增强

### 8) 验收映射
- `ACPT-P4A-004`
- `ACPT-P4A-005`
