# TEST CASE SPEC — P1.phase2

## 覆盖目标
对齐 `PHASE_CONTRACT_P1.phase2.md` 的 12 条验收目标，建立可追溯 TC-ID 与执行命令。

## Test Cases

### TC-P1P2-001 动态阈值 profile 切换
- Acceptance: ACC-P1-P2-01
- Given: baseline/balanced/strict 三档可配置
- When: 运行同批事件评估
- Then: 阈值按分布计算并随 profile 切换
- Command: `PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_fixed_threshold_sensitivity"`

### TC-P1P2-002 候选窗口治理
- Acceptance: ACC-P1-P2-02
- Given: 高噪声输入
- When: 执行候选治理
- Then: 候选窗口稳定在 3~30
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_window_stability or candidate_explosion_ratio_below_5_percent"`

### TC-P1P2-003A 异常向量门禁（禁随机/零向量最终决策）
- Acceptance: ACC-P1-P2-03
- Given: 语义匹配异常路径（零向量/无效向量）
- When: 执行 `_match_themes_semantic` 判定
- Then: 不得产出最终匹配结果（禁止进入最终主题决策）
- Command: `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_tc003_architecture_guard.py -k "no_zero_vector_final_decision_runtime"`

### TC-P1P2-003B 分类真源复用（禁二次分类推断）
- Acceptance: ACC-P1-P2-03
- Given: 上游已提供 `classification_result`
- When: 执行 `generate_theme_data_only`
- Then: 不得触发 `_match_categories` 二次推断
- Command: `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_tc003_architecture_guard.py -k "generator_must_not_secondary_inference_when_upstream_given"`

### TC-P1P2-003C 缺失真源处理（概念主/子分类新建）
- Acceptance: ACC-P1-P2-03
- Given: 缺失上游 `classification_result`
- When: 执行创建路径
- Then: 不触发 `_match_categories` 二次推断；基于AI关键词创建 concept 主/子分类路径
- Command: `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_tc003_architecture_guard.py -k "missing_upstream_classification_creates_concept_path"`

### TC-P1P2-003D ADR 合规审计（006/011）
- Acceptance: ACC-P1-P2-03
- Given: phase2 架构与验收文档
- When: 审核 ADR 列表与验收条款映射
- Then: ADR-006/011 必须完整并与 ACC-P1-P2-03 对齐
- Command: `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_tc003_architecture_guard.py -k "adr_list_audit or acceptance_feature_alignment"`

### TC-P1P2-004 三方评估与指标门槛
- Acceptance: ACC-P1-P2-04
- Given: 30 案例集
- When: 运行统一评估
- Then: 题材数 8~12 且三项质量指标不低于基线
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_triparty_metrics"`

### TC-P1P2-005 10% 灰度
- Acceptance: ACC-P1-P2-05
- Given: 灰度开关
- When: 设置 10% 流量
- Then: 优化策略仅命中 10%，保留分桶证据
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "ab_gray_10_percent or bucket_evidence_and_profile_recorded"`

### TC-P1P2-006 三段分层统计
- Acceptance: ACC-P1-P2-06
- Given: 高/中/低相似混合集
- When: 运行分层策略
- Then: Strong/Candidate/Weak 均可观测
- Command: `PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_semantic_score_segmentation"`

### TC-P1P2-007 真实 DeepSeek 调用证据
- Acceptance: ACC-P1-P2-07
- Given: phase2 验收执行环境
- When: 运行评估
- Then: source_type=real 且有 request_id/timestamp/model
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_real_deepseek_evidence"`

### TC-P1P2-008 候选治理观测输出完整性
- Feature Slice: F-P1P2-T02-04
- Acceptance: ACC-P1-P2-01
- Given: 候选治理流程执行完成
- When: 输出阶段统计
- Then: 必须包含 `candidate_count_raw/candidate_count_windowed/candidate_explosion_ratio`
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_observability_outputs_present"`

### TC-P1P2-009 分类一致性审计字段（流程补充）
- Feature Slice: F-P1P2-T03-04
- Acceptance: ACC-P1-P2-03（流程级补充，不替代 003A~003D）
- Given: 创建新题材走复用分类真源路径
- When: 处理完成并输出审计字段
- Then: `t03_validation` 中统计 `classification_source(upstream/created_from_ai_keywords)`，且 create_new_theme 决策均携带 `classification_source`
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "generate_theme_data_only_reuses_upstream_classification or forbids_secondary_category_inference"`

### TC-P1P2-010 ADR 决策归档完整性
- Feature Slice: F-P1P2-T04-03
- Acceptance: ACC-P1-P2-05
- Given: phase2 决策已固化
- When: 校验 ADR 索引
- Then: 必须包含 `ADR-005`（动态阈值）与 `ADR-011`（禁止二次分类推断）
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_adr_decisions_documented"`

### TC-P1P2-011 分类关键词反向索引继承正确性
- Feature Slice: F-P1P2-T06-01/F-P1P2-T06-02
- Acceptance: ACC-P1-P2-11
- Given: `theme_master.tags.keywords` 与 `financial_categories` 的 L1/L2 分类关系
- When: 执行关键词回填构建
- Then: 满足 `L2 <- L3` 与 `L1 <- L2` 继承规则，且关键词集合去重
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_from_theme_master or l1_keywords_aggregated_from_l2_keywords"`

### TC-P1P2-012 分类关键词回填幂等与覆盖率审计
- Feature Slice: F-P1P2-T06-03/F-P1P2-T06-04
- Acceptance: ACC-P1-P2-12
- Given: 同一批分类/题材输入
- When: 连续两次执行关键词回填构建
- Then: 第二次无新增更新，覆盖率指标包含 before/after 字段
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_idempotent or category_keyword_coverage_metrics_present"`

### TC-P1P2-013 决策流全量审计（禁时间窗口抽样）
- Feature Slice: F-P1P2-T03-04（流程审计增强）
- Acceptance: ACC-P1-P2-09（流程级补充）
- Given: 数据集回放处理完成
- When: 审计脚本收集 `decision_details`
- Then: 必须使用 `xrange("-", "+")` 全量读取 `stream:events:decision`，且审计明细数与决策流总数一致
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/phase2_update_mapping_audit.py --sample-size 24 --out /Users/admin/Desktop/ai_theme_app/tmp/phase2_update_mapping_audit.json`

### TC-P1P2-014 语义向量缓存复用（初始化提速守卫）
- Feature Slice: F-P1P2-T02-04（可观测性）+ T01执行性能补充
- Acceptance: ACC-P1-P2-01（流程补充）
- Given: 同一题材集二次初始化语义匹配器
- When: 执行缓存单测
- Then: 第二次初始化应命中缓存，不得重复编码全量题材
- Command: `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_semantic_embedding_cache_unit.py`

## Feature Slice 覆盖矩阵

| Task | Feature Slice | TC-ID |
| --- | --- | --- |
| P1.phase2-T01 | F-P1P2-T01-01 | TC-P1P2-001 |
| P1.phase2-T01 | F-P1P2-T01-02 | TC-P1P2-006 |
| P1.phase2-T01 | F-P1P2-T01-03 | TC-P1P2-006 |
| P1.phase2-T01 | F-P1P2-T01-04 | TC-P1P2-001 |
| P1.phase2-T02 | F-P1P2-T02-01 | TC-P1P2-002 |
| P1.phase2-T02 | F-P1P2-T02-02 | TC-P1P2-002 |
| P1.phase2-T02 | F-P1P2-T02-03 | TC-P1P2-002 |
| P1.phase2-T02 | F-P1P2-T02-04 | TC-P1P2-008 |
| P1.phase2-T03 | F-P1P2-T03-01 | TC-P1P2-003A |
| P1.phase2-T03 | F-P1P2-T03-02 | TC-P1P2-003B |
| P1.phase2-T03 | F-P1P2-T03-03 | TC-P1P2-003C |
| P1.phase2-T03 | F-P1P2-T03-04 | TC-P1P2-009 |
| P1.phase2-T04 | F-P1P2-T04-01 | TC-P1P2-005 |
| P1.phase2-T04 | F-P1P2-T04-02 | TC-P1P2-005 |
| P1.phase2-T04 | F-P1P2-T04-03 | TC-P1P2-010 |
| P1.phase2-T05 | F-P1P2-T05-01 | TC-P1P2-004 |
| P1.phase2-T05 | F-P1P2-T05-02 | TC-P1P2-004 |
| P1.phase2-T05 | F-P1P2-T05-03 | TC-P1P2-007 |
| P1.phase2-T05 | F-P1P2-T05-04 | TC-P1P2-004 |
| P1.phase2-T06 | F-P1P2-T06-01 | TC-P1P2-011 |
| P1.phase2-T06 | F-P1P2-T06-02 | TC-P1P2-011 |
| P1.phase2-T06 | F-P1P2-T06-03 | TC-P1P2-012 |
| P1.phase2-T06 | F-P1P2-T06-04 | TC-P1P2-012 |
| P1.phase2-T03 | F-P1P2-T03-04 | TC-P1P2-013 |
| P1.phase2-T02 | F-P1P2-T02-04 | TC-P1P2-014 |

## 与 TEST_EXEC_PLAN_P1 对齐说明
- T01（语义阈值算法）任务级门禁走 `database_service/tests/streams/test_phase2_semantic_matcher_unit.py`。
- T01 常规回归先跑 `PHASE2_THRESHOLD_SAMPLE=24, PHASE2_THRESHOLD_GRID_SIZE=80`；阶段验收采用 `PHASE2_THRESHOLD_SAMPLE=30, PHASE2_THRESHOLD_GRID_SIZE=100`。
- 其余流程与集成行为门禁走 `database_service/tests/streams/test_phase2_behavior_tests.py`。
- `test_semantic_matcher.py / test_transformer_matcher.py / test_theme_processor.py(菜单9/11)` 作为补充评估入口保留在 `TEST_EXEC_PLAN_P1`，用于算法与数据集专项验证。
- 审计与性能补充门禁：
  - 决策映射审计使用 `phase2_update_mapping_audit.py`（必须全量读取 decision stream）。
  - 缓存复用守卫使用 `test_semantic_embedding_cache_unit.py`。
