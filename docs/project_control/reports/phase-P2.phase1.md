# Phase P2.phase1 执行报告（2026-03-31）

## 执行口径

- 执行协议：按 [PHASE_CONTRACT_P2.phase1.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/PHASE_CONTRACT_P2.phase1.md) 执行。
- 执行方式：优先复用已通过的真实数据库与真实 API 证据，不对已确认通过的用例重复重测。
- 严格遵循：
  - 不新增与 `theme_master / theme_profile_ext / subject_detail / stocks` 等价的平行主表
  - 先建立 `subject_key` 统一业务主键基线，再推进 tree/history/stock/rank
  - 优先走 `真源 -> staging -> view`，仅在必要时再落 serving 表

## 本次复用与新增的真实证据

### 1. 标准化层落库结果
- 证据来源：
  - [load_subject_node_staging.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_subject_node_staging.py)
  - [load_theme_hierarchy_staging.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_theme_hierarchy_staging.py)
  - [load_subject_history_staging.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_subject_history_staging.py)
  - [load_subject_children_staging.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_subject_children_staging.py)
  - [load_subject_stock_detail_staging.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_subject_stock_detail_staging.py)
  - [load_subject_stock_map_from_children.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_subject_stock_map_from_children.py)
  - [load_subject_stock_staging.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/load_subject_stock_staging.py)
- 真实库状态：
  - `subject_node_staging = 630`
  - `theme_hierarchy_staging = 721`
  - `subject_history_staging = 3596`
  - `subject_children_staging = 3614`
  - `subject_stock_detail_staging = 1755`
  - `subject_stock_map = 3614`
  - `subject_stock_staging = 3614`
- 结论：
  - `theme_data_complete/lists|history|children|stock_details` 已进入数据库标准化层。

### 2. 视图整合层结果
- 证据来源：
  - [create_phase1_views.sql](/Users/admin/Desktop/ai_theme_app/database_service/create_phase1_views.sql)
  - [apply_phase1_views.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/apply_phase1_views.py)
- 真实库状态：
  - `vw_subject_theme_binding = 3955`
  - `vw_theme_rank_current = 551`
  - `vw_theme_history_candidate = 7071`
  - `vw_theme_tree_candidate = 4335`
    - `parent_child = 721`
    - `children_snapshot = 3614`
  - `vw_theme_stock_map_candidate = 3614`
- 结论：
  - `subject_key` 主键体系已跑通，`rank/history/tree/stock` 不再被 `theme_id` 内连接锁死。

### 2a. serving 表物化结果
- 证据来源：
  - [materialize_phase1_serving.py](/Users/admin/Desktop/ai_theme_app/database_service/scripts/materialize_phase1_serving.py)
- 真实库状态：
  - `theme_detail_snapshot = 3035`
  - `theme_history_event = 7071`
  - `theme_tree_relation = 4335`
  - `theme_stock_map = 3614`
- 结论：
  - `theme_detail_snapshot / theme_history_event / theme_tree_relation / theme_stock_map` 四张 serving 表已完成第一版真实物化。

### 3. Phase1 真实只读 API
- 代码：
  - [phase1_read_repository.py](/Users/admin/Desktop/ai_theme_app/theme_service/repositories/phase1_read_repository.py)
  - [app.py](/Users/admin/Desktop/ai_theme_app/theme_service/app.py)
- 已落地接口：
  - `GET /themes`
  - `GET /themes/rank`
  - `GET /themes/{subject_key}`
  - `GET /themes/{subject_key}/children`
  - `GET /themes/{subject_key}/history`
  - `GET /themes/{subject_key}/stocks`
  - `GET /stocks/{stock_id}/themes`
- 结论：
  - 第一批 phase1 只读 API 已真实接到 PostgreSQL，不再返回 mock 数据。

### 4. 真实 API 集成测试
- 证据：
  - [test_p2_phase1_read_api_real_db.py](/Users/admin/Desktop/ai_theme_app/theme_service/tests/integration/test_p2_phase1_read_api_real_db.py)
- 执行命令：
  - `POSTGRES_DATABASE=stock_data_test .venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/theme_service/tests/integration/test_p2_phase1_read_api_real_db.py`
- 结果：
  - `7 passed in 0.89s`
- 覆盖：
  - `themes list`
  - `themes rank`
  - `theme detail`
  - `theme children`
  - `theme history`
  - `theme stocks`
  - `stock themes`

### 5. serving 表真实集成测试
- 证据：
  - [test_p2_phase1_serving_tables_real_db.py](/Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase1_serving_tables_real_db.py)
- 执行命令：
  - `POSTGRES_DATABASE=stock_data_test .venv/bin/python -m pytest -q --run-integration /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase1_serving_tables_real_db.py`
- 结果：
  - `3 passed in 0.18s`
- 覆盖：
  - 四张 serving 表已物化
  - `theme_history_event` 来源追溯字段存在
  - `theme_tree_relation / theme_stock_map` 关系类型与来源字段结构化

## 本轮关键设计收口

### 1. `subject_key` 统一业务主键
- `theme_master` 仅承载 `L3`，不能继续充当全层级统一主键。
- 已收口为：
  - `subject_key`：tree/rank/history/children/stocks 统一业务主键
  - `theme_id`：仅作为 `theme_master` 的 L3 实体引用，可空

### 2. `full_theme_list.jsonl` 角色重定
- 已确认它不是完整树真源，而是更接近 `L1` 节点主档快照。
- 当前树关系主真源：
  - `theme_hierarchy_staging`
  - `subject_children_staging`

### 3. 股票映射链打通
- 初版 `subject_stock_map` 采用保守策略：
  - 仅从 `subject_children_staging.lead_stock_id/lead_stock_name` 反灌
  - 仅建立显式 `leader` 映射
  - 不做父节点扩散推断
- 结果：
  - 已形成 `subject_stock_map -> subject_stock_staging -> vw_theme_stock_map_candidate` 的真实链路。

### 4. 新增 rework 范围：久赢恒丰增量同步
- 用户已追加新要求：在完成历史数据复刻基础上，系统必须支持“久赢恒丰新增数据 -> 本地 `theme_data_complete` -> 增量导库 -> serving 刷新”的正式同步能力。
- 已盘点现有相关脚本：
  - `import_jyhf_data_optimized.py`
  - `import_jyhf_full_theme_and_children_patch.py`
  - `import_jyhf_to_financial_and_theme.py`
  - `import_single_subject_knowledge.py`
  - `import_jyhf_gate_profile.py`
  - `import_jyhf_stock_facts_llm.py`
  - `theme_collector.py`
  - `audit_jyhf_subject_coverage.py`
- 已收口的设计方向：
  - 保留 `久赢恒丰 -> theme_data_complete -> 数据库` 总路线
  - 新增 `jyhf_sync_batch / jyhf_sync_file_manifest / jyhf_sync_subject_state`
  - 收敛唯一采集入口
  - 收敛 `nodes/history/detail/stock` 四条增量导库链
  - 禁止以 patch 脚本和全量重建作为日常同步主路径

## Gate 对账

### 已满足
- [x] 固定真源输入：`theme_master / theme_profile_ext / subject_detail / stocks / subject_rank_daily / subject_stock_map / theme_data_complete/*`
- [x] 形成标准化层：`subject_node_staging / theme_hierarchy_staging / subject_history_staging / subject_children_staging / subject_stock_detail_staging`
- [x] 完成 `subject_key` 统一业务主键基线
- [x] 优先交付视图整合层
- [x] 提供 `themes/rank/detail/history/children/stocks` 与 `stocks/{stock_id}/themes` 真实接口
- [x] 股票与树关系输出结构化关系类型和来源

### 未完全关闭
- [ ] `P95 < 500ms` 尚无独立压测证据，仅有功能级真实查询与集成测试
- [ ] 久赢恒丰增量同步已实现脚本与小样本验证，但尚未在正式日常批次上完成完整人工验收

## Gate 结论

- `P2.phase1`：**CONDITIONAL PASS**

判定依据：
- 真实数据标准化层已形成；
- 真实 view 层已形成；
- 四张 serving 表已物化；
- 7 个核心只读接口已连接真实库并通过真实集成测试；
- 但性能门禁尚未单独验证完成；
- 且用户新增的“久赢恒丰增量同步”能力虽已落地脚本与 SOP，但仍待正式批次人工验收。

## Review Checklist

- [x] `subject_key` 统一业务主键基线已建立
- [x] `subject_node_staging / theme_hierarchy_staging / subject_history_staging / subject_children_staging / subject_stock_detail_staging` 已落库
- [x] `subject_stock_map -> subject_stock_staging -> vw_theme_stock_map_candidate` 已打通
- [x] `/themes`
- [x] `/themes/rank`
- [x] `/themes/{subject_key}`
- [x] `/themes/{subject_key}/history`
- [x] `/themes/{subject_key}/children`
- [x] `/themes/{subject_key}/stocks`
- [x] `/stocks/{stock_id}/themes`
- [x] 真实 PostgreSQL 集成测试 `7 passed`
- [x] phase1 serving 物化表已落地
- [ ] phase1 性能压测未执行
- [x] 久赢恒丰增量同步链脚本已实现
- [ ] 久赢恒丰增量同步正式批次未验收

## 等待用户决策

- `ACCEPT`
- `REWORK`
- `REQUEST CHANGES`
