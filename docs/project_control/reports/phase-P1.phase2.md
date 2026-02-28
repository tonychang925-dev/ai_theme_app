# Phase P1.phase2 执行报告（2026-02-19）

## 验收口径
- 已按项目最新决议将 phase2 验收标准统一为 `30` 数据集口径。
- 测试命令采用绝对路径解释器与绝对路径测试文件。

## 关键执行结果

### TC-P1P2-004（关键链路集成）
- 命令：
  - `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -s -vv /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_triparty_metrics"`
- 结果：
  - `PASSED`
  - `1 passed, 17 deselected`
  - 约 `237.54s`
- 核心指标：
  - `events_published=True`
  - `decisions_generated=True`
  - `theme_updates_generated=True`
  - `dead_letter=0`
  - `DecisionExecutor` 接收/执行/失败：`10/10/0`

### TC-P1P2-003A~D（架构守卫）
- 命令：
  - `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_tc003_architecture_guard.py`
- 结果：
  - `5 passed`

### T01 动态阈值（30/100）
- 命令：
  - `PHASE2_THRESHOLD_SAMPLE=30 PHASE2_THRESHOLD_GRID_SIZE=100 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -s -vv /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_fixed_threshold_sensitivity_tc_p1p2_001 or t01_semantic_score_segmentation_tc_p1p2_006"`
- 结果：
  - `2 passed, 1 warning in 13.55s`
  - 覆盖 `TC-P1P2-001` 与 `TC-P1P2-006`
  - 说明：沙盒会触发 `torch` OpenMP SHM 限制，正式验收在非沙盒模式执行

### 行为与回填补充验收
- 行为链路（ACC-02/05/07/08/09/10）：
  - `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -s -vv /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_window_stability or candidate_explosion_ratio_below_5_percent or candidate_observability_outputs_present or generate_theme_data_only_reuses_upstream_classification or forbids_secondary_category_inference or ab_gray_10_percent or bucket_evidence_and_profile_recorded or phase2_adr_decisions_documented or phase2_real_deepseek_evidence"`
  - 结果：`9 passed, 9 deselected, 1 warning in 241.34s`
- 关键词回填（ACC-11/12）：
  - `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill or l1_keywords_aggregated_from_l2_keywords or category_keyword_coverage_metrics_present or category_keywords_backfill_idempotent"`
  - 结果：`4 passed, 14 deselected`

## 阶段结论
- Phase2 关键验收项已完成并通过（30 样本口径）。
- 所有验收命令均使用绝对路径；涉及 `torch` 的 T01 验收在非沙盒模式执行并通过。
- 本次执行（run_id=`20260219_135148`）按用户指令复用既有通过证据，未重复执行已确认通过的语义全量历史项。
- Closeout Gate 状态：`functional tests = pass`，`process closeout = blocked`（里程碑 phase2 任务仍为 Todo，且缺少 `P1.phase2-T06` 任务条目）。

## 增量优化与复验（2026-02-19）

### 1) 语义向量缓存复用（提速）
- 代码：`theme_service/matchers/semantic_matcher.py`
- 单测：`database_service/tests/streams/test_semantic_embedding_cache_unit.py`
- 结果：`2 passed`
- 集成日志证据：24条回放后续轮次出现 `向量缓存命中: 300, 新计算: 0`，确认全量题材初始化不再重复编码。

### 2) 决策流审计修正（全量读取）
- 代码：`database_service/scripts/test_theme_processor.py`
- 变更：审计逻辑改为处理结束后 `xrange("-", "+")` 全量读取 `stream:events:decision`。
- 复验结果：24条回放输出 `决策全量读取完成: 24 条, 审计明细: 24 条`，修复“最近3条窗口抽样”偏差。

### 3) 映射准确率规则修正（同题材簇可接受）
- 代码：`database_service/scripts/phase2_update_mapping_audit.py`
- 修正项：
  - 准确率字段读取改为 `matched_theme_name`（兼容回退 `best_theme_name`）。
  - 新增同题材簇等价规则（覆盖 SpaceX/太空军事同题材复用场景）。
- 复算结果（基于 `tmp/phase2_update_mapping_audit_sanitized_title.json`）：
  - `update_theme_mappings=13`
  - `accuracy=13/13=1.0`

### 4) 业务判定澄清（已固化）
- “SpaceX事件 -> 美军采购72颗导弹预警卫星概念”在当前业务定义中属于同题材簇复用，判定为可接受。
- 重大错误口径为 “SpaceX -> 核聚变” 跨题材错配；本轮复验未出现该类结论。

## 原始执行证据
- `tmp/phase2_execution_record_20260219.md`
- `tmp/phase2_dynamic_ab_30.json`
- `tmp/phase2_integration_30_summary.json`
- `tmp/phase2_post_backfill_30.json`
- `tmp/phase2_update_mapping_audit.json`
- `tmp/phase2_update_mapping_audit_sanitized_title.json`
- `tmp/runs/20260219_135148/validation_summary.json`
- `tmp/runs/20260219_135148/reconcile_report.json`
- `tmp/runs/20260219_135148/gate_decision.json`
