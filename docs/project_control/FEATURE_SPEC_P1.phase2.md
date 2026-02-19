# FEATURE SPEC - P1.phase2

## 0. Meta
- Phase: `P1.phase2`
- 目标: 动态阈值与候选治理落地，分类真源复用，76案例三方评估与10%灰度门禁
- 约束: 不进入 phase3 的 LLM 最终裁决放量；不进入 phase4 发布收口
- 真源文档:
  - `docs/project_control/PHASE_CONTRACT_P1.phase2.md`
  - `docs/project_control/ACCEPTANCE.md` (Phase P1.phase2)
  - `docs/project_control/prd_p1.md` (`PRD-P1-P2-R01~R10`)
  - `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`
  - `docs/architecture/个人投资助理-项目架构设计-第二阶段.md`

## 1. 架构与代码基线（必须复用）

### 1.1 匹配主链路（现状锚点）
- `database_service/streams/handlers/theme_processor.py`
  - 分类优先入口与统计: `classification_stats`, `_infer_category_with_cache`, `_process_category_match_result`
  - 未匹配路径动作映射: `_get_action_for_decision_type`
- `database_service/streams/handlers/DecisionExecutor.py`
  - 执行幂等与契约校验: `_should_skip_duplicate_execution`, `_normalize_and_validate_decision_envelope`
  - pending 发布: `_execute_publish_clustering_fixed`
- `theme_service/services/theme_service.py`
  - 两阶段模式与分类优先: `discover_theme`, `discover_category_only`

### 1.2 语义匹配与阈值（现状锚点）
- `theme_service/matchers/semantic_matcher.py`
  - 阈值过滤核心: `_match_themes_semantic`
  - 当前为固定阈值配置读取: `semantic_threshold`
- `theme_service/services/theme_discovery_engine.py`
  - major/normal matcher 配置初始化（固定阈值 + fallback）
  - clustering 分析候选生成

### 1.3 新题材生成与分类（现状锚点）
- `theme_service/creators/theme_rule_generator.py`
  - 现状问题: `generate_theme_data_only()` 内部调用 `_match_categories()`，会在创建阶段再次分类推断
  - phase2目标: 复用首阶段分类结果，创建阶段禁止二次推断

### 1.4 真实集成测试基线（必须复用）
- `database_service/scripts/test_theme_processor.py`
  - `RealIntegrationTester.test_new_architecture_with_dataset()`
  - 已具备 real Redis/DB 流程、decision->pending->ack 验证、`t04_validation` 结构化证据

---

## 2. 任务级功能分解

## Task P1.phase2-T01 — 动态阈值 profile + 三段分层

### 1) 目标与边界
- 目标:
  - 阈值由事件分布动态计算（p95/p98）
  - 支持 `baseline/balanced/strict`
  - 输出 `Strong/Candidate/Weak` 命中统计
- 非目标:
  - 不做 phase3 的最终 LLM 裁决链路

### 2) 现状问题
- `semantic_matcher.py` 以固定 `semantic_threshold` 过滤为主
- `theme_discovery_engine.py` major/normal 固定阈值常量（0.92/0.88）

### 3) 子功能切片（可实施）
- `F-P1P2-T01-01` 阈值计算器
  - 输入: 相似度序列 + profile
  - 输出: `dynamic_threshold`
  - 规则: baseline/balanced/strict 对应不同分位和安全边界
- `F-P1P2-T01-02` 三段分层器
  - 规则: `score >= strong_th` -> Strong；`candidate_low <= score < strong_th` -> Candidate；其余 Weak
- `F-P1P2-T01-03` 分层指标埋点
  - 输出字段: `segment_hits.{strong,candidate,weak}`、`threshold_used`
- `F-P1P2-T01-04` profile 运行时切换
  - 配置入口: discovery engine / matcher 初始化参数

### 4) 接口与契约
- 输入契约:
  - `event_id`, `event_text`, `event_keywords`, `profile`
- 输出契约:
  - `dynamic_threshold`, `segment_bucket`, `candidate_count_before_rank`

### 5) 测试落点
- 新增: `database_service/tests/streams/test_phase2_behavior_tests.py::test_dynamic_threshold_profiles`
- 新增: `database_service/tests/streams/test_phase2_behavior_tests.py::test_strong_candidate_weak_segments`
- 复用: `database_service/scripts/test_theme_processor.py` 数据集流程

### 6) 验收映射
- `ACC-P1-P2-01`, `ACC-P1-P2-06`

---

## Task P1.phase2-T02 — 候选窗口治理（3~30）与爆炸比监控

### 1) 目标与边界
- 目标:
  - 候选治理必须在精排前执行
  - 候选窗口稳定 `3~30`
  - 输出 `candidate_explosion_ratio`
- 非目标:
  - 不调整下游执行器业务动作语义

### 2) 现状问题
- 候选规模控制分散在 matcher/engine，缺统一窗口门禁

### 3) 子功能切片
- `F-P1P2-T02-01` 候选窗口裁剪器
  - 预排序后先裁剪再精排
- `F-P1P2-T02-02` 超界回退策略
  - `<3` 或 `>30` 时触发 profile 回退/重算
- `F-P1P2-T02-03` 爆炸比计算器
  - 指标: `candidate_explosion_ratio = count(>window_upper)/total`
- `F-P1P2-T02-04` 观测输出
  - 输出: `candidate_count_raw`, `candidate_count_windowed`, `explosion_ratio`

### 4) 测试落点
- 新增: `test_candidate_window_stability`
- 新增: `test_candidate_explosion_ratio_below_5_percent`

### 5) 验收映射
- `ACC-P1-P2-02`, `ACC-P1-P2-01`

---

## Task P1.phase2-T03 — 分类真源复用，禁止创建阶段二次分类推断

### 1) 目标与边界
- 目标:
  - `generate_theme_data_only` 消费首阶段分类结果
  - 创建阶段不得再次 `_match_categories`
  - 保证匹配阶段分类与创建阶段分类一致
- 非目标:
  - 不改数据库分类表 schema

### 2) 现状问题（代码锚点）
- `theme_rule_generator.py::generate_theme_data_only()` 内仍调用 `_match_categories()`
- 违背 phase2 合约“分类真源唯一”要求

### 3) 子功能切片
- `F-P1P2-T03-01` DTO 入参扩展
  - 增加 `classification_result` 透传字段（来源 ThemeProcessor）
- `F-P1P2-T03-02` 生成器改造
  - 优先使用透传分类，禁止在创建路径触发 `_match_categories`
- `F-P1P2-T03-03` 保护性断言
  - 若缺失分类真源，进入受控失败，不静默回退到二次推断
- `F-P1P2-T03-04` 一致性审计
  - 输出 `classification_source=upstream` 与 `category_consistency=true/false`

### 4) 数据约束（对齐架构SQL）
- 分类编码必须符合 `financial_categories_schema.sql` 约束
- 题材分类字段必须对齐 `theme_master_schema.sql`:
  - `category1_code/category2_code/category3_code`
  - `level1_category/level2_category/level3_category`

### 5) 测试落点
- 新增: `test_generate_theme_data_only_reuses_upstream_classification`
- 新增: `test_generate_theme_data_only_forbids_secondary_category_inference`
- 复用: `test_theme_processor.py` 数据集回放验证分类一致性

### 6) 验收映射
- `ACC-P1-P2-03`

---

## Task P1.phase2-T04 — 10%灰度与ADR归档

### 1) 目标与边界
- 目标:
  - phase2 改造仅 10% 灰度
  - 输出可对比分桶证据
  - ADR记录阈值策略与分类真源决策

### 2) 子功能切片
- `F-P1P2-T04-01` 灰度分桶器
  - 字段: `traffic_bucket`, `strategy_profile`
- `F-P1P2-T04-02` 指标双轨输出
  - baseline 与 optimized 两套指标并存
- `F-P1P2-T04-03` ADR落盘
  - 记录: 决策背景/权衡/回滚条件/生效版本

### 3) 测试落点
- 新增: `test_ab_gray_10_percent`
- 新增: `test_bucket_evidence_and_profile_recorded`

### 4) 验收映射
- `ACC-P1-P2-05`

---

## Task P1.phase2-T05 — 76案例三方评估 + real DeepSeek证据

### 1) 目标与边界
- 目标:
  - 76案例三方对比（优化/基线/久赢恒丰）
  - 题材数收敛到 8~12
  - Precision/Completeness/Separation 不低于基线
  - `source_type=real` 且输出 DeepSeek 调用证据

### 2) 子功能切片
- `F-P1P2-T05-01` 评估聚合器
  - 输出 `theme_count, precision, completeness, separation`
- `F-P1P2-T05-02` 三方对比报告器
  - 输出三组结果与差异
- `F-P1P2-T05-03` real调用证据采集
  - 字段: `source_type`, `request_id`, `timestamp`, `model_name`
- `F-P1P2-T05-04` 门禁判定器
  - 不满足指标直接阻断 phase2 完成态

### 3) 测试落点（复用真实脚本）
- 复用: `database_service/scripts/test_theme_processor.py::test_new_architecture_with_dataset`
- 新增（或扩展）:
  - `test_phase2_triparty_metrics`
  - `test_phase2_real_deepseek_evidence`

### 4) 验收映射
- `ACC-P1-P2-04`, `ACC-P1-P2-07`

---

## 3. 统一实施规则（STEP2 前声明）

1. 先测后改: 每个任务先新增/更新自动化测试（期望先失败）再做最小代码改动。
2. 真实依赖: phase2验收路径禁止 mock/fake 代替 real Redis/DB/DeepSeek 证据。
3. 可追溯: 每个测试函数必须带 `TC-P1P2-*` 标识。
4. 状态门禁: `P1` 任务写入 `In review/done` 必须传 `--test-files` 且文件出现在 diff。
5. 收口标准: phase2 完成前必须有三方评估报告和 real 调用证据。
