# FEATURE SPEC - P2.phase1

## 0. Meta
- Phase: `P2.phase1`
- 目标: 建立 `Core / Profile / Knowledge` 三层题材对象，沉淀详情、历史、层级树、股票映射与核心查询接口。
- 约束: 展示快照不得承担在线检索职责；热度与生命周期不在本 phase。
- 当前数据库真源基线:
  - `theme_master` 已全量复刻，作为 Core 主档真源
  - `theme_profile_ext` 已全量复刻，作为 Profile 真源
  - `subject_detail` 已全量复刻，作为详情真源输入
  - `stocks` 已全量复刻，作为股票主档真源
  - `subject_stock_map` 已建表，作为题材-股票映射真源层
  - `subject_rank_daily` 已有数据，作为榜单/历史真源层
- 当前文件真源基线:
  - `theme_data_complete/details`
  - `theme_data_complete/history`
  - `theme_data_complete/children`
  - `theme_data_complete/daily`
  - `theme_data_complete/stock_details`
  - `theme_data_complete/lists`
- 冲突裁决说明:
  - 采用三层对象模型，不采用“一个大对象同时承载展示+索引”的旧式混合方案。
  - 不再设计与 `theme_master / theme_profile_ext / subject_detail / stocks` 等价的平行主表。
  - 真源整合优先采用数据库视图；只有在版本冻结、审计、人工修订或性能兜底需要时才落成 serving 表。
  - `subject_key` 作为题材树、rank、history、children 的统一业务主键；`theme_id` 仅作为 `theme_master` L3 叶子实体 ID，可为空。
  - `full_theme_list.jsonl` 视为 L1 节点主档快照，不再单独作为完整树真源；树边优先来自 `theme_hierarchy.jsonl`，`children/*` 作为富关系补充。
  - 日常久赢同步固定采用 `远端 API -> theme_data_complete -> 增量导库 -> serving 刷新`，不再以 patch 脚本和全量重建替代正式同步链。
  - `P2.phase1` 只冻结对象边界和核心接口，不在本阶段展开热度公式。
- 真源文档:
  - `docs/architecture/个人投资助理-项目架构设计-第二阶段（题材匹配重构版）.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PHASE_CONTRACT_P2.phase1.md`
  - `docs/project_control/PLAN_WBS.md`

## Task P2.phase1-T01 — 设计 Core/Profile/Knowledge 三层题材对象模型

### 1) 目标与边界
- 目标:
  - 冻结三层职责
  - 明确字段与更新边界
- 非目标:
  - 不定义热度和生命周期字段

### 2) 接口与契约
- 输入:
  - 已复刻正式题材主档、在线画像、详情与股票主档
- 输出:
  - `ThemeCoreView`, `ThemeProfileView`, `theme_knowledge_*`
- 约束:
  - 不允许一个对象同时服务展示和检索

### 3) 数据模型与状态变更
- `Core`: 复用 `theme_master`
- `Profile`: 复用 `theme_profile_ext`
- `Knowledge`: `theme_detail_snapshot`, `theme_history_event`, `theme_tree_relation`, `theme_stock_map`
- `Staging/View`: `vw_subject_theme_binding`, `vw_theme_rank_current`, `vw_theme_detail_joined`, `vw_theme_stock_map_candidate`, `vw_theme_tree_candidate`, `vw_theme_history_candidate`
- `Staging/Table`: `subject_node_staging`, `subject_history_staging`, `subject_children_staging`, `subject_stock_staging`, `subject_stock_detail_staging`
- 当前已落地规模:
  - `subject_node_staging = 630`
  - `theme_hierarchy_staging = 721`
  - `subject_history_staging = 3596`
  - `subject_children_staging = 3614`
  - `subject_stock_detail_staging = 1755`

### 4) 子功能分解
- `F-P2.phase1-T01-01` Core 主档边界器
  - 输入: 题材主数据
  - 处理逻辑: 读取并约束 `theme_master` 的 serving 使用边界
  - 输出: `ThemeCoreView`
  - 失败处理: 主键冲突阻断写入
  - 可观测证据: 主档版本
- `F-P2.phase1-T01-02` Profile 在线画像层
  - 输入: 匹配画像字段
  - 处理逻辑: 复用 `theme_profile_ext` 并独立维护检索索引对象
  - 输出: `ThemeProfileView`
  - 失败处理: 字段不完整标记不可用
  - 可观测证据: 画像版本
- `F-P2.phase1-T01-03` Knowledge 展示层
  - 输入: `subject_detail`、事件映射、关系对象
  - 处理逻辑: 分对象落库，不重复复制基础真源表
  - 输出: 可展示知识对象
  - 失败处理: 来源不明对象拒绝写入
  - 可观测证据: 来源覆盖率

### 5) 实现步骤
- Step-1: 输出三层字段矩阵。
- Step-2: 冻结 `subject_key` 统一业务主键规则，以及 `theme_id` 仅作为 L3 实体引用的边界。
- Step-2a: 先导入 `full_theme_list.jsonl` 到 `subject_node_staging`，将其固定为节点主档 staging。
- Step-3: 先定义视图层整合规则，再定义真源 -> staging -> serving 的跨层引用规则。
- Step-4: 设计层间同步与版本控制。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase1-01-layer-boundary`
  - `TC-P2.phase1-02-no-mixed-object`
  - `TC-P2.phase1-03-versioned-model`
  - `TC-P2.phase1-03a-subject-theme-binding`
- 必跑命令:
  - `rg -n "theme_master|theme_profile_ext|subject_detail|stocks|theme_detail_snapshot|theme_history_event|theme_tree_relation|theme_stock_map" .`
  - `.venv/bin/python -m pytest -q`

### 7) 风险与回滚
- 风险:
  - 分层不彻底
- 回滚:
  - 回切到上一版对象层，不迁移混写对象；保留 `theme_master / theme_profile_ext / subject_detail / stocks` 作为只读真源

### 8) 验收映射
- `ACPT-P2.phase1-001`
- `ACPT-P2.phase1-005`

---

## Task P2.phase1-T02 — 定义详情/历史对象与来源追溯协议

### 1) 目标与边界
- 目标:
  - 建立详情快照与历史驱动对象
  - 保证来源可追溯
- 非目标:
  - 不做热度曲线

### 2) 接口与契约
- 输入:
  - `subject_detail`、`subject_rank_daily`、`theme_data_complete/history/*`、正式题材、新闻事件、外部数据源
- 输出:
  - `theme_detail_snapshot`
  - `theme_history_event`
- 约束:
  - 历史必须可回溯到 `event_id` 或明确外部来源

### 3) 数据模型与状态变更
- `theme_detail_snapshot`
  - `theme_id`, `snapshot_version`, `content`, `source_type`, `source_ref`, `subject_key`
- `theme_history_event`
  - `subject_key`, `theme_id(nullable)`, `event_id`, `driver_summary`, `event_date`, `source_type`

### 4) 子功能分解
- `F-P2.phase1-T02-01` 详情快照器
  - 输入: `subject_detail.detail_html/reason_short`
  - 处理逻辑: 从 `subject_detail` 版本化派生 `theme_detail_snapshot`
  - 输出: `detail_snapshot`
  - 失败处理: 无来源时不落库
  - 可观测证据: `snapshot_version`
- `F-P2.phase1-T02-02` 历史驱动归档器
  - 输入: `subject_rank_daily + theme_data_complete/history/* + event_theme_map + news_event + news_raw`
  - 处理逻辑: 先通过 `vw_theme_history_candidate` 生成候选历史，再视需要沉淀日级/事件级记录
  - 输出: `history_event`
  - 失败处理: 无法关联来源时标记外部来源
  - 可观测证据: 来源类型分布
- `F-P2.phase1-T02-03` 来源追溯守卫
  - 输入: 详情/历史对象
  - 处理逻辑: 检查 `event_id/source_ref`
  - 输出: 合格对象
  - 失败处理: 追溯断链则拒绝发布
  - 可观测证据: 追溯覆盖率

### 5) 实现步骤
- Step-1: 冻结快照和历史 schema。
- Step-2: 先定义 `vw_theme_history_candidate` 视图。
- Step-3: 定义 `event_id/source_ref` 约束。
- Step-4: 增加来源完整性扫描。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase1-04-detail-versioning`
  - `TC-P2.phase1-05-history-source-chain`
  - `TC-P2.phase1-06-no-source-no-publish`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "theme_detail_snapshot|theme_history_event|event_id|source_ref|source_type" .`

### 7) 风险与回滚
- 风险:
  - 详情和历史来源断链
- 回滚:
  - 停止新快照发布，回切旧版本

### 8) 验收映射
- `ACPT-P2.phase1-002`

---

## Task P2.phase1-T03 — 定义层级树与股票映射关系类型、证据来源与更新策略

### 1) 目标与边界
- 目标:
  - 建立父子题材关系和题材-股票映射
  - 冻结关系类型和证据来源
- 非目标:
  - 不做实时行情驱动推荐

### 2) 接口与契约
- 输入:
  - 题材关系、`theme_master.related_stocks`、`subject_stock_map`、`stocks`、`theme_data_complete/children/*`、`theme_data_complete/lists/theme_hierarchy.jsonl`、外部/人工数据
- 输出:
  - `theme_tree_relation`
  - `theme_stock_map`
- 约束:
  - 关系类型与证据来源必须结构化

### 3) 数据模型与状态变更
- `theme_tree_relation`
  - `parent_subject_key`, `child_subject_key`, `parent_theme_id(nullable)`, `child_theme_id(nullable)`, `relation_type`, `evidence_source`
- `theme_stock_map`
  - `subject_key`, `theme_id(nullable)`, `stock_id`, `relation_type`, `evidence_source`, `effective_at`

### 4) 子功能分解
- `F-P2.phase1-T03-01` 题材层级关系器
  - 输入: `theme_hierarchy.jsonl` 与 `children/*`
  - 处理逻辑: `vw_theme_tree_candidate` 同时输出 `parent_child` 标准边和 `children_snapshot` 富关系快照，再按需沉淀 `theme_tree_relation`
  - 输出: `theme_tree_relation`
  - 失败处理: 循环依赖拒绝写入
  - 可观测证据: 层级深度分布
- `F-P2.phase1-T03-02` 股票映射关系器
  - 输入: `subject_stock_map`、`subject_stock_detail_staging`、`theme_master.related_stocks`、`stocks` 与题材关系证据
  - 处理逻辑: `subject_stock_map` 必须先吃 `theme_data_complete/stock_details/*_stocks.jsonl` 的完整股票池，再融合 `children lead_stock` 作为增强信号；其后形成 `vw_theme_stock_map_candidate`，并优先补齐股票详情字段，再按需输出 `leader/core/member/edge`
  - 输出: `theme_stock_map`
  - 失败处理: 缺证据时不升级关系等级
  - 可观测证据: 各关系类型数量
  - API 口径: `/themes/{subject_key}/stocks` 与 `/stocks/{stock_id}/themes` 默认仅返回 `mapping_scope=pool`；`leader_overlay` 需显式开启
- `F-P2.phase1-T03-03` 更新策略治理器
  - 输入: 增量更新与全量回填任务
  - 处理逻辑: 定义刷新策略和幂等更新
  - 输出: 更新规则
  - 失败处理: 更新冲突时保持旧版本并告警
  - 可观测证据: 刷新批次号

### 5) 实现步骤
- Step-1: 冻结关系类型枚举。
- Step-2: 建立 `subject_stock_map/children` 的标准化 staging。
- Step-3: 定义证据来源模板。
- Step-4: 设计增量更新与全量重建规则。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase1-07-tree-no-cycle`
  - `TC-P2.phase1-08-stock-relation-evidence`
  - `TC-P2.phase1-09-refresh-idempotent`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "theme_tree_relation|theme_stock_map|relation_type|evidence_source|related_stocks|stocks" .`

### 7) 风险与回滚
- 风险:
  - 关系类型漂移
  - 股票映射证据薄弱
- 回滚:
  - 暂停更新任务，回退到上一批次快照

### 8) 验收映射
- `ACPT-P2.phase1-003`

---

## Task P2.phase1-T04 — 设计 `/themes/*` 与 `/stocks/{stock_id}/themes` 核心接口契约

### 1) 目标与边界
- 目标:
  - 冻结五类核心接口
  - 保证响应与对象模型对齐
- 非目标:
  - 不实现投资建议接口

### 2) 接口与契约
- 输出接口:
  - `/themes/rank`
  - `/themes/{subject_key}`
  - `/themes/{subject_key}/history`
  - `/themes/{subject_key}/children`
  - `/themes/{subject_key}/stocks`
  - `/stocks/{stock_id}/themes`
- 约束:
  - 响应字段只来自三层对象模型
  - P95 `< 500ms`

### 3) 数据模型与状态变更
- 接口视图:
  - `ThemeRankView`
  - `ThemeDetailView`
  - `ThemeHistoryView`
  - `ThemeChildrenView`
  - `ThemeStocksView`

### 4) 子功能分解
- `F-P2.phase1-T04-01` 榜单视图组装器
  - 输入: `subject_rank_daily` 与题材对象
  - 处理逻辑: 第一版直接基于 `vw_theme_rank_current` 输出排名视图
  - 输出: `/themes/rank`
  - 失败处理: 无榜单源时返回上次快照
  - 可观测证据: 查询时延
- `F-P2.phase1-T04-02` 详情聚合器
  - 输入: Core/Profile/Knowledge
  - 处理逻辑: 聚合详情、历史、层级、股票信息
  - 输出: `/themes/{subject_key}`
  - 失败处理: 子对象缺失时返回降级字段并审计
  - 可观测证据: 聚合缺失率
- `F-P2.phase1-T04-03` 股票反查视图器
  - 输入: `theme_stock_map`
  - 处理逻辑: 按 `stock_id` 反查题材
  - 输出: `/stocks/{stock_id}/themes`
  - 失败处理: 映射表不可用时返回显式错误
  - 可观测证据: 反查命中率

### 5) 实现步骤
- Step-1: 输出 API schema。
- Step-2: 优先上线基于 `vw_theme_rank_current` 的 `theme_rank_api` 第一版。
- Step-2a: 第一批只读接口先落 `/themes`、`/themes/rank`、`/themes/{subject_key}`、`/themes/{subject_key}/children`、`/themes/{subject_key}/history`、`/themes/{subject_key}/stocks`、`/stocks/{stock_id}/themes`。
- Step-3: 将接口字段逐一映射到对象层。
- Step-4: 增加时延和降级策略。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase1-10-rank-schema`
  - `TC-P2.phase1-11-detail-aggregate`
  - `TC-P2.phase1-12-stock-theme-lookup`
  - `TC-P2.phase1-13-read-api-real-db`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "themes/rank|themes/\\{subject_key\\}|stocks/\\{stock_id\\}/themes" docs/project_control/prd_p2.md docs/project_control/ACCEPTANCE.md`

### 7) 风险与回滚
- 风险:
  - API 结构漂移
  - 接口时延超阈
- 回滚:
  - 回切到上一版只读视图，保留对象层数据

### 8) 验收映射
- `ACPT-P2.phase1-004`
- `ACPT-P2.phase1-006`

---

## Task P2.phase1-T05 — 完成对象边界、接口与来源追溯门禁验证

### 1) 目标与边界
- 目标:
  - 核验三层边界、来源追溯和接口性能
  - 输出 phase1 归档
- 非目标:
  - 不推进热度阶段

### 2) 接口与契约
- 输入:
  - phase1 全链路对象和接口证据
- 输出:
  - 门禁结论

### 3) 数据模型与状态变更
- 指标:
  - `traceability_coverage`
  - `api_p95_ms`
  - `mixed_object_count`

### 4) 子功能分解
- `F-P2.phase1-T05-01` 对象边界检查器
  - 输入: 三层对象 schema
  - 处理逻辑: 扫描混写字段
  - 输出: 边界检查结果
  - 失败处理: 发现混写直接 gate fail
  - 可观测证据: 混写计数
- `F-P2.phase1-T05-02` 来源追溯核验器
  - 输入: 详情、历史、关系对象
  - 处理逻辑: 统计来源覆盖率
  - 输出: 追溯报告
  - 失败处理: 覆盖率不足不允许结项
  - 可观测证据: 追溯覆盖率
- `F-P2.phase1-T05-03` API 性能门禁器
  - 输入: 查询时延日志
  - 处理逻辑: 校验 P95
  - 输出: 性能结论
  - 失败处理: 超阈值阻断
  - 可观测证据: `api_p95_ms`

### 5) 实现步骤
- Step-1: 汇总 phase2 指标。
- Step-1: 汇总 phase1 指标。
- Step-2: 执行结构扫描与接口压测。
- Step-3: 输出归档和残留问题。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase1-13-boundary-gate`
  - `TC-P2.phase1-14-traceability-gate`
  - `TC-P2.phase1-15-api-p95-gate`
- 必跑命令:
  - `.venv/bin/python -m pytest -q`
  - `rg -n "theme_master|theme_profile_ext|subject_detail|stocks|theme_detail_snapshot|theme_history_event|theme_tree_relation|theme_stock_map" .`

### 7) 风险与回滚
- 风险:
  - 门禁报告与真实对象状态不一致
- 回滚:
  - phase1 不结项，保持对象层只读验收态

### 8) 验收映射
- `ACPT-P2.phase1-005`
- `ACPT-P2.phase1-006`

---

## Task P2.phase1-T06 — 建立久赢恒丰增量同步链

### 1) 目标与边界
- 目标:
  - 将当前“久赢恒丰 -> 本地 `theme_data_complete` -> 数据库”的既有方案升级为正式增量同步链
  - 冻结唯一采集入口、批次元数据、文件/subject 增量判定和幂等重放规则
- 非目标:
  - 不在本任务内重做前端页面
  - 不在本任务内一次性删除全部旧导入脚本

### 2) 接口与契约
- 输入:
  - 久赢恒丰合法 token
  - 远端数据类型：`details / history / children / daily / stock_details / lists`
  - 本地文件真源：`theme_data_complete/*`
- 输出:
  - `jyhf_sync_batch`
  - `jyhf_sync_file_manifest`
  - `jyhf_sync_subject_state`
  - `changed_subjects.json`
  - 四条增量导库链执行结果
- 约束:
  - 日常同步必须先落本地文件，再导库
  - 不允许以 `DELETE + 全量重建` 作为日常同步主路径
  - 所有导库任务必须支持 `--batch-id`
  - 所有 subject 级重放任务必须支持幂等重复执行

### 3) 数据模型与状态变更
- `jyhf_sync_batch`
  - `batch_id`, `started_at`, `finished_at`, `status`, `subject_count`, `file_count`, `error_count`
- `jyhf_sync_file_manifest`
  - `batch_id`, `file_path`, `data_type`, `subject_key(nullable)`, `file_hash`, `source_updated_at`, `sync_status`
- `jyhf_sync_subject_state`
  - `subject_key`, `last_batch_id`, `last_success_at`, `last_file_hash`, `status`, `error_msg`
- 本地元数据文件:
  - `theme_data_complete/_manifests/<batch_id>.json`
  - `theme_data_complete/_state/sync_cursor.json`

### 4) 子功能分解
- `F-P2.phase1-T06-01` 唯一采集入口
  - 输入: 久赢 token、同步范围、批次参数
  - 处理逻辑: 基于 `theme_collector.py` 收敛为 `sync_jyhf_to_local.py`，统一采集 `lists/details/history/children/daily/stock_details`
  - 输出: 本地批次文件与 manifest
  - 失败处理: 记录失败 subject，不中断整批 manifest 生成
  - 可观测证据: `batch_id`, `changed_files`, `failed_subjects`
- `F-P2.phase1-T06-02` 增量判定器
  - 输入: manifest、旧 cursor、文件 hash、source 更新时间
  - 处理逻辑: 输出 `changed_subjects`
  - 输出: subject 级变更列表
  - 失败处理: 判定失败时回退到文件级重放，不允许直接清库
  - 可观测证据: `changed_subject_count`, `unchanged_subject_count`
- `F-P2.phase1-T06-03` 四路增量导库链
  - 输入: `changed_subjects + batch_id`
  - 处理逻辑:
    - `import_jyhf_nodes_incremental.py`
    - `import_jyhf_history_incremental.py`
    - `import_jyhf_detail_incremental.py`
    - `import_jyhf_stock_incremental.py`
  - 输出: 对应 staging/serving 刷新结果
  - 失败处理: 按 `subject_key` 标记失败，可单题材重放
  - 可观测证据: 各链路成功数/失败数
  - 当前实现说明:
    - `nodes` 增量链已落到 `import_jyhf_to_financial_and_theme.py`
    - `history` 增量链已落到 `database_service/scripts/import_jyhf_history_incremental.py`
    - `detail` 增量链已落到 `database_service/scripts/import_jyhf_detail_incremental.py`
    - `stock` 增量链已落到 `database_service/scripts/import_jyhf_stock_incremental.py`
    - `history` 链路会按 `subject_key` 精确重放 `subject_history_staging / subject_rank_daily / theme_history_event`
    - `detail` 链路会按 `subject_key` 精确重放 `subject_detail / theme_profile_ext / theme_detail_snapshot`
    - `stock` 链路会按 `subject_key` 精确重放 `subject_stock_map / subject_stock_staging / theme_stock_map`
    - 样本验证已通过：
      - `history`: `subjects=3`, `history_rows=21`, `rank_rows=21`
      - `detail`: `subjects=3`, `detail_rows=3`, `profile_rows=3`
      - `stock`: `subjects=3`, `map_rows=1`, `staging_rows=1`, `serving_rows=1`
- `F-P2.phase1-T06-04` 旧脚本重定位器
  - 输入: 现有导入脚本集合
  - 处理逻辑:
    - `import_jyhf_data_optimized.py` -> 初始化/历史全量恢复
    - `import_jyhf_full_theme_and_children_patch.py` -> 吸收进 nodes 增量链
    - `import_jyhf_to_financial_and_theme.py` -> staging 到正式层的增量回灌，不再允许全量清空
    - `import_single_subject_knowledge.py` -> 单题材修复工具
    - `import_jyhf_gate_profile.py` -> detail/profile 增量链组成部分
    - `theme_collector.py` -> 采集层基础模块
  - 输出: 脚本职责矩阵
  - 失败处理: 职责冲突则阻断日常同步上线
  - 可观测证据: 脚本责任清单

### 5) 实现步骤
- Step-1: 盘点并冻结现有久赢采集/导库脚本责任矩阵。
- Step-2: 新增批次/文件/subject 三张同步状态表。
- Step-3: 基于 `theme_collector.py` 统一出唯一采集入口。
- Step-4: 实现 `changed_subjects` 增量判定。
- Step-5: 将现有导入链拆为 `nodes/history/detail/stock` 四条增量导库链。
- Step-6: 为四条链统一补 `--batch-id / --subjects-file`。
- Step-7: 定义 serving 增量刷新策略，禁止每次全表重建。
- Step-8: 固化正式执行手册 `JYHF_INCREMENTAL_SYNC_SOP.md`。

### 6) 测试设计与命令
- 测试用例:
  - `TC-P2.phase1-16-jyhf-script-inventory`
  - `TC-P2.phase1-17-batch-manifest`
  - `TC-P2.phase1-18-changed-subject-detection`
  - `TC-P2.phase1-19-idempotent-subject-replay`
  - `TC-P2.phase1-20-no-full-rebuild-daily-sync`
- 必跑命令:
  - `rg -n "import_jyhf|theme_collector|audit_jyhf|fetch_theme_list|test_history_api" .`
  - `.venv/bin/python -m pytest -q`

### 7) 风险与回滚
- 风险:
  - 继续依赖 patch 脚本导致日常同步路径分叉
  - 缺失批次/文件状态导致失败不可重试
- 回滚:
  - 保留初始化全量导入脚本作为灾备恢复路径
  - 增量失败时允许按 `subject_key` 单独重放，不允许触发清库式回滚

### 8) 验收映射
- `ACPT-P2.phase1-007`

---

## 4.1 推荐视图清单与 SQL 草案

### V-P2.phase1-01 `vw_subject_theme_binding`

用途：
- 统一 `subject_key` 业务主键，并提供可选的 `theme_id` 叶子实体引用，作为 phase1 所有回填与 API 的前置绑定层。

核心字段：
- `subject_key`
- `theme_id`
- `theme_name`
- `node_level`
- `source_table`
- `parent_subject_key`
- `ancestors`
- `source_system`
- `source_id`
- `binding_status`
- `last_verified_at`

SQL 草案：

```sql
create or replace view vw_subject_theme_binding as
select
  sns.subject_key,
  tm.id as theme_id,
  coalesce(tm.name, sns.subject_name) as theme_name,
  coalesce(sns.node_level::varchar(10), 'L1') as node_level,
  'subject_node_staging'::varchar(50) as source_table,
  coalesce(tm.source_system, 'jyhf') as source_system,
  coalesce(tm.source_id, sns.subject_key) as source_id,
  sns.parent_subject_key,
  sns.ancestors,
  case
    when tm.id is not null and tm.status = 'active' then 'active_binding'
    when tm.id is not null then 'inactive_binding'
    else 'staging_only'
  end as binding_status,
  coalesce(tm.updated_at, sns.updated_at) as last_verified_at
from subject_node_staging sns
left join theme_master tm
  on tm.source_system = 'jyhf'
 and tm.source_id = sns.subject_key;
```

说明：
- `subject_node_staging` 来自 `full_theme_list.jsonl`，承担节点主档职责。
- `theme_master` 只负责为可映射的 L3 节点补齐 `theme_id`。
- 当前 `subject_node_staging` 已完成导入，行数 `630`。

### V-P2.phase1-02 `vw_theme_rank_current`

用途：
- 第一版 `theme_rank_api` 直接读取当前榜单视图，不先复制到 serving 表；主键统一使用 `subject_key`，`theme_id` 可空。

核心字段：
- `subject_key`
- `theme_id`
- `theme_name`
- `rank_date`
- `heat`
- `heat_name`
- `pct_chg`
- `his_pct_chg`
- `red`
- `description`

SQL 草案：

```sql
create or replace view vw_theme_rank_current as
with ranked as (
  select
    srd.*,
    row_number() over (
      partition by srd.subject_key
      order by srd.rank_date desc, srd.id desc
    ) as rn
  from subject_rank_daily srd
)
select
  r.subject_key,
  b.theme_id,
  b.theme_name,
  r.rank_date,
  r.heat,
  r.heat_name,
  r.pct_chg,
  r.his_pct_chg,
  r.red,
  r.description,
  r.source_system
from ranked r
left join vw_subject_theme_binding b
  on b.subject_key = r.subject_key
where r.rn = 1;
```

### V-P2.phase1-03 `vw_theme_detail_joined`

用途：
- 详情 API 第一版统一聚合 `theme_master + theme_profile_ext + subject_detail`。

核心字段：
- `theme_id`
- `subject_key`
- `theme_name`
- `summary`
- `detail_html`
- `reason_short`
- `detail_version`
- `is_current`

SQL 草案：

```sql
create or replace view vw_theme_detail_joined as
select
  b.theme_id,
  b.subject_key,
  tm.name as theme_name,
  tpe.summary,
  sd.detail_html,
  sd.reason_short,
  sd.detail_version,
  sd.is_current,
  sd.updated_at as detail_updated_at
from vw_subject_theme_binding b
join theme_master tm
  on tm.id = b.theme_id
left join theme_profile_ext tpe
  on tpe.subject_key = b.subject_key
left join subject_detail sd
  on sd.subject_key = b.subject_key
 and sd.is_current = true;
```

### V-P2.phase1-04 `vw_theme_stock_map_candidate`

用途：
- 统一股票映射候选，主键仍使用 `subject_key`，后续若需 serving 表再由该视图回填。

核心字段：
- `theme_id`
- `subject_key`
- `stock_id`
- `stock_name`
- `relation_type_candidate`
- `top`
- `sort`
- `reason`
- `remark`
- `confidence`

SQL 草案：

```sql
create or replace view vw_theme_stock_map_candidate as
select
  b.theme_id,
  ssm.subject_key,
  ssm.stock_id,
  coalesce(ssm.name, s.name) as stock_name,
  case
    when ssm.top = true then 'leader'
    when coalesce(ssm.sort, 9999) <= 3 then 'core'
    else 'member'
  end as relation_type_candidate,
  ssm.top,
  ssm.sort,
  ssm.reason,
  ssm.remark,
  ssm.confidence,
  ssm.source_type,
  ssm.start_date,
  ssm.end_date,
  ssm.evidence_json
from subject_stock_map ssm
join vw_subject_theme_binding b
  on b.subject_key = ssm.subject_key
left join stocks s
  on s.stock_id = ssm.stock_id;
```

### V-P2.phase1-05 `vw_theme_tree_candidate`

用途：
- 先产出标准 parent-child 候选边；树边统一使用 `parent_subject_key / child_subject_key`，`theme_id` 仅作为可选叶子引用。

核心字段：
- `parent_subject_key`
- `parent_theme_id`
- `child_subject_key`
- `child_theme_id`
- `child_name`
- `relation_type`
- `source_type`

SQL 草案：

```sql
create or replace view vw_theme_tree_candidate as
select
  th.parent_id::varchar(80) as parent_subject_key,
  pb.theme_id as parent_theme_id,
  th.child_id::varchar(80) as child_subject_key,
  cb.theme_id as child_theme_id,
  th.child_name,
  'parent_child' as relation_type,
  'jyhf_hierarchy' as source_type
from (
  select
    parent_id,
    child_id,
    child_name
  from theme_hierarchy_staging
) th
left join vw_subject_theme_binding pb
  on pb.subject_key = th.parent_id::varchar(80)
left join vw_subject_theme_binding cb
  on cb.subject_key = th.child_id::varchar(80);
```

说明：
- `theme_hierarchy_staging` 表示先把 `theme_data_complete/lists/theme_hierarchy.jsonl` 导入 staging，再由视图消费。

### S-P2.phase1-01 `subject_node_staging`

用途：
- 将 `full_theme_list.jsonl` 固化为节点主档 staging，作为 `subject_key` 业务主键体系的节点真源。

核心字段：
- `subject_key`
- `subject_name`
- `node_level`
- `parent_subject_key`
- `ancestors`
- `reason`
- `first_letter`
- `importance`
- `sort`
- `pct_chg`
- `status`
- `raw_json`

来源：
- `theme_data_complete/lists/full_theme_list.jsonl`

说明：
- 该表不直接对外 serving。
- 该表的职责是稳定节点元数据，避免 `rank/history/tree` 只能依赖 `theme_master`。

### S-P2.phase1-02 `subject_children_staging`

用途：
- 固化 `children/*` 的富子题材快照，为 `theme_tree_relation` 和 children API 提供补充真源。

核心字段建议：
- `parent_subject_key`
- `child_subject_key`
- `child_name`
- `full_name`
- `pct_chg`
- `stock_count`
- `limit_up_count`
- `lead_stock_id`
- `lead_stock_name`
- `ancestors`
- `raw_json`

来源：
- `theme_data_complete/children/*.jsonl`

当前状态：
- 已完成导入，行数 `3614`
- 通过递归 flatten 保留 `depth / lead_stock_id / lead_stock_name / pct_chg / stock_count / limit_up_count`

### S-P2.phase1-03 `subject_stock_detail_staging`

用途：
- 固化 `stock_details/*`，用于增强 `theme_stock_map` 的证据、股票补充字段和 leader/core/member 判断。

来源：
- `theme_data_complete/stock_details/*_detail.json`

当前状态：
- 已完成导入，行数 `1755`
- 已处理临时文件与 `\u0000` 脏数据

### V-P2.phase1-06 `vw_theme_history_candidate`

用途：
- 先把久赢历史和站内事件历史整合成候选历史视图；历史主键统一使用 `subject_key`，不再强依赖 `theme_id`。

核心字段：
- `theme_id`
- `subject_key`
- `rank_date`
- `description`
- `heat`
- `heat_name`
- `pct_chg`
- `his_pct_chg`
- `event_id`
- `source_type`
- `source_ref`

SQL 草案：

```sql
create or replace view vw_theme_history_candidate as
select
  b.theme_id,
  srd.subject_key,
  srd.rank_date,
  srd.description,
  srd.heat,
  srd.heat_name,
  srd.pct_chg,
  srd.his_pct_chg,
  null::integer as event_id,
  'jyhf_rank_daily' as source_type,
  srd.id::text as source_ref
from subject_rank_daily srd
join vw_subject_theme_binding b
  on b.subject_key = srd.subject_key

union all

select
  etm.theme_id,
  tm.source_id as subject_key,
  ne.event_time::date as rank_date,
  ne.summary as description,
  null::integer as heat,
  null::varchar(50) as heat_name,
  null::numeric(8,4) as pct_chg,
  null::numeric(8,4) as his_pct_chg,
  ne.id as event_id,
  'event_theme_map' as source_type,
  ne.id::text as source_ref
from event_theme_map etm
join news_event ne
  on ne.id = etm.event_id
join theme_master tm
  on tm.id = etm.theme_id
where tm.source_system = 'jyhf'
  and tm.source_id is not null;
```

### 视图与 serving 表的判定规则

- 仅查询聚合、无版本冻结需求：优先使用视图
- 需要 `snapshot_version / batch_id / audit fields`：落 serving 表
- 需要人工修订或手工审核回写：落 serving 表
- 视图查询无法满足 `P95 < 500ms`：落 serving 表或物化视图
