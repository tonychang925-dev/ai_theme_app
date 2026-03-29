# Phase2 执行记录（2026-02-19）

## 执行口径
- 验收标准：`30` 数据集口径
- 解释器：`/opt/miniconda3/envs/theme_matcher_env/bin/python`
- 命令路径：全部使用绝对路径

## 本轮执行结果

### 1) TC-P1P2-004（关键链路集成）
- Command:
  - `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -s -vv /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_triparty_metrics"`
- Result:
  - `PASSED`
  - `1 passed, 17 deselected`
  - 耗时：`237.54s`（约 `0:03:57`）
- 关键指标（日志）:
  - `events_published=True`
  - `decisions_generated=True`（决策流 `10`）
  - `theme_updates_generated=True`（题材更新 `10`）
  - `dead_letter=0`
  - `DecisionExecutor`: 接收 `10` / 执行 `10` / 失败 `0`

### 2) TC-P1P2-003A~D（架构守卫）
- Command:
  - `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_tc003_architecture_guard.py`
- Result:
  - `5 passed`

### 3) T01 动态阈值单测（30/100）
- Command:
  - `PHASE2_THRESHOLD_SAMPLE=30 PHASE2_THRESHOLD_GRID_SIZE=100 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -s -vv /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_fixed_threshold_sensitivity_tc_p1p2_001 or t01_semantic_score_segmentation_tc_p1p2_006"`
- Result:
  - `2 passed, 1 warning in 13.55s`
  - 覆盖 `TC-P1P2-001`、`TC-P1P2-006` 两个阶段验收关键用例
  - 运行模式：非沙盒（规避沙盒对 `torch` 的 OpenMP SHM 限制）

### 3.1) T01 动态阈值快测补齐（24/80）
- Command:
  - `PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_semantic_matcher_unit.py`
- Result:
  - `2 passed, 1 warning in 13.59s`
  - 覆盖 `TC-P1P2-001`、`TC-P1P2-006` 快测门禁
  - 首次在沙盒内执行失败（`Abort trap`），已按既定口径切换为非沙盒执行并通过

### 4) Phase2 行为验收补充集（ACC-02/05/07/08/09/10）
- Command:
  - `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -s -vv /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_window_stability or candidate_explosion_ratio_below_5_percent or candidate_observability_outputs_present or generate_theme_data_only_reuses_upstream_classification or forbids_secondary_category_inference or ab_gray_10_percent or bucket_evidence_and_profile_recorded or phase2_adr_decisions_documented or phase2_real_deepseek_evidence"`
- Result:
  - `9 passed, 9 deselected, 1 warning in 241.34s`

### 5) T06 分类关键词回填专项（ACC-11/12）
- Command:
  - `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill or l1_keywords_aggregated_from_l2_keywords or category_keyword_coverage_metrics_present or category_keywords_backfill_idempotent"`
- Result:
  - `4 passed, 14 deselected`

## 阶段结论（本轮）
- 已形成可用通过证据：
  - TC003 架构守卫（通过）
  - TC004 关键链路集成（通过）
  - T01 动态阈值（30/100，关键用例通过）
  - ACC-02/05/07/08/09/10 行为验收（通过）
  - ACC-11/12 关键词回填验收（通过）
