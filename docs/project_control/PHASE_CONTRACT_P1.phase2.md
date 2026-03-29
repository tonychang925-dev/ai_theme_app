# Phase Execution Contract

## 0. Contract Meta

- Contract File: `docs/project_control/PHASE_CONTRACT_P1.phase2.md`
- Machine Copy: `tmp/phase_contract_P1.phase2.json`
- Scope: `phase:P1.phase2`
- Unified Guardrails: `docs/project_control/EXECUTION_GUARDRAILS.md`

---

## 1. Phase Identity

- Phase Name: 动态阈值与候选治理
- Phase Code: P1.phase2
- Parent Milestone: P1（第一阶段）
- Risk Level: High
- Source Documents (priority order):
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/adrs/ADR_LIST.md`

---

## 2. Phase Objective（可量化）

1. 动态阈值按事件分布（p95/p98）计算并支持 `baseline/balanced/strict` 切换。  
2. 候选窗口稳定在 `3~30`，候选爆炸比 `< 5%`。  
3. 新题材创建复用首阶段分类结果，`generate_theme_data_only` 侧二次分类推断触发率 `= 0`。  
4. 30 案例集形成三方对比报告，且优化系统在题材数与质量指标上不低于基线。  
5. 阶段验收使用真实 DeepSeek 调用（`source_type=real`），禁止模拟数据替代正式结论。
6. 分类关键词反向索引补全：`L2 <- L3(tags.keywords)`，`L1 <- L2(keywords)`，并可量化提升分类命中覆盖率。

---

## 3. Acceptance Targets（门禁条件，二元判定）

- [ ] 动态阈值按事件分布（p95/p98）计算并可切换 `baseline/balanced/strict`。
  - 验证映射: `ACC-P1-P2-01`, `ACC-P1-P2-02`
- [ ] 动态阈值必须实现 `Strong/Candidate/Weak` 三段分层并记录分层命中分布。
  - 验证映射: `ACC-P1-P2-06`
- [ ] 候选治理先于精排，候选窗口稳定在 3~30。
  - 验证映射: `ACC-P1-P2-02`
- [ ] 生产路径禁止随机向量/零向量结果作为最终决策依据。
  - 验证映射: `ACC-P1-P2-03`
- [ ] 创建阶段有上游分类结果时必须复用；无上游分类结果时走 `create_concept_category_path`（主/子概念创建），禁止二次 `_match_categories` 推断。
  - 验证映射: `ACC-P1-P2-03`
- [ ] 输出 `source_type(real/mock)` 质量指标并设置门禁阈值。
  - 验证映射: `ACC-P1-P2-07`
- [ ] 30 案例集 A/B 报告必须包含：候选爆炸比、完整性、分离度、精度代理。
  - 验证映射: `ACC-P1-P2-01`
- [ ] 30 案例集必须形成三方对比：优化系统 vs 基线系统（纯聚类） vs 久赢恒丰标准。
  - 验证映射: `ACC-P1-P2-04`
- [ ] 30 案例集验收指标必须满足：题材数量收敛到 8~12，且 Precision/Completeness/Separation 三指标均不低于基线系统。
  - 验证映射: `ACC-P1-P2-04`
- [ ] A/B 灰度必须先在 10% 流量执行，通过后才允许扩大范围。
  - 验证映射: `ACC-P1-P2-05`
- [ ] 本阶段验收必须使用真实 DeepSeek 调用（`source_type=real`），禁止模拟数据替代正式结论。
  - 验证映射: `ACC-P1-P2-07`
- [ ] 分类关键词索引补全完成：L2 分类关键词来自 L3 题材关键词去重聚合，L1 分类关键词来自 L2 关键词去重聚合。
  - 验证映射: `ACC-P1-P2-11`
- [ ] 关键词回填具备幂等性，且输出覆盖率对比证据（before/after）。
  - 验证映射: `ACC-P1-P2-12`
- [ ] 决策审计必须基于 `stream:events:decision` 全量读取，不得采用“最近N条时间窗口抽样”。
  - 验证映射: `ACC-P1-P2-09`（流程补充）
- [ ] 语义匹配器必须具备向量缓存复用能力，二次初始化不得重复编码全量题材。
  - 验证映射: `ACC-P1-P2-01`（流程补充）

### 3.1 Acceptance × TestCase × Feature 汇总（MUST）

| Acceptance | WBS Task | Test Case | Feature Slice | 通过判定（Binary） | 验证命令 |
| --- | --- | --- | --- | --- | --- |
| ACC-P1-P2-01 | P1.phase2-T01/T02 | TC-P1P2-001 | F-P1P2-T01-01/04 | 固定阈值下边界样本可复现“过筛/漏筛”差异，支持后续动态阈值改造对照 | `PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_fixed_threshold_sensitivity"` |
| ACC-P1-P2-02 | P1.phase2-T02 | TC-P1P2-002 | F-P1P2-T02-01/02/03 | 候选窗口 `3~30` 且 `candidate_explosion_ratio < 5%` | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_window_stability or candidate_explosion_ratio_below_5_percent"` |
| ACC-P1-P2-03 | P1.phase2-T03 | TC-P1P2-003A/003B/003C/003D | F-P1P2-T03-01/02/03/04 | 禁止随机/零向量最终决策；有上游分类必须复用；无上游分类走概念主/子分类新建路径；ADR 合规可审计 | `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_tc003_architecture_guard.py` |
| ACC-P1-P2-04 | P1.phase2-T05 | TC-P1P2-004 | F-P1P2-T05-01/02/04 | 三方对比完整；`theme_count 8~12`；三指标不低于基线 | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_triparty_metrics"` |
| ACC-P1-P2-05 | P1.phase2-T04 | TC-P1P2-005 | F-P1P2-T04-01/02 | 仅 10% 灰度命中，保留分桶与 profile 证据 | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "ab_gray_10_percent or bucket_evidence_and_profile_recorded"` |
| ACC-P1-P2-06 | P1.phase2-T01 | TC-P1P2-006 | F-P1P2-T01-02/03 | 语义分数分层结果可区分 strong/good/weak 区间 | `PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_semantic_score_segmentation"` |
| ACC-P1-P2-07 | P1.phase2-T05 | TC-P1P2-007 | F-P1P2-T05-03 | `source_type=real` 且具备 `request_id/timestamp/model_name` | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_real_deepseek_evidence"` |
| ACC-P1-P2-11 | P1.phase2-T06 | TC-P1P2-011 | F-P1P2-T06-01/02 | 分类关键词补全符合 `L2 <- L3`、`L1 <- L2` 继承原则，且关键词集合去重 | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_from_theme_master or l1_keywords_aggregated_from_l2_keywords"` |
| ACC-P1-P2-12 | P1.phase2-T06 | TC-P1P2-012 | F-P1P2-T06-03/04 | 重复回填结果一致（幂等），覆盖率指标含 before/after | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_idempotent or category_keyword_coverage_metrics_present"` |

### 3.1.1 分解测试项汇总（来自 TEST_CASE_SPEC / FEATURE_SPEC）

| Acceptance | WBS Task | Test Case | Feature Slice | 通过判定（Binary） | 验证命令 |
| --- | --- | --- | --- | --- | --- |
| ACC-P1-P2-08 | P1.phase2-T02 | TC-P1P2-008 | F-P1P2-T02-04 | 输出包含 `candidate_count_raw/candidate_count_windowed/candidate_explosion_ratio` | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_observability_outputs_present"` |
| ACC-P1-P2-09 | P1.phase2-T03 | TC-P1P2-009 | F-P1P2-T03-04 | `t03_validation` 中存在分类来源统计，且 create_new_theme 决策均携带 `classification_source` | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "generate_theme_data_only_reuses_upstream_classification or forbids_secondary_category_inference"` |
| ACC-P1-P2-10 | P1.phase2-T04 | TC-P1P2-010 | F-P1P2-T04-03 | ADR 决策归档完整（`ADR-005/ADR-011`）且行为侧 `decision_ack_verified=true` | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_adr_decisions_documented"` |
| ACC-P1-P2-11 | P1.phase2-T06 | TC-P1P2-011 | F-P1P2-T06-01/02 | 分类 `keywords` 回填后，L1/L2 非空率较回填前提升 | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_from_theme_master or l1_keywords_aggregated_from_l2_keywords"` |
| ACC-P1-P2-12 | P1.phase2-T06 | TC-P1P2-012 | F-P1P2-T06-03/04 | 同批次重复执行无新增重复词，覆盖率指标完整输出 | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_idempotent or category_keyword_coverage_metrics_present"` |

### 3.2 验收补充标准（新增）

- [ ] `P1.phase2-T01~T05` 每个任务在写入 `In review/done` 前必须提交 `--test-files`，且文件命中当前 `git diff`。
- [ ] `T01`（`TC-P1P2-001/006`）必须由 `test_phase2_semantic_matcher_unit.py` 覆盖；流程类用例由 `test_phase2_behavior_tests.py` 覆盖。
- [ ] 关键路径测试必须在 `theme_matcher_env` 执行，禁止以 mock/fake 替代 Redis/DB/DeepSeek 验收证据。
- [ ] 阶段收口前必须产出三方评估与真实调用证据（来自 `test_theme_processor.py` 与 phase2 行为测试）。
- [ ] 常规回归使用 `PHASE2_THRESHOLD_SAMPLE=24, PHASE2_THRESHOLD_GRID_SIZE=80`；阶段验收切换 `PHASE2_THRESHOLD_SAMPLE=30, PHASE2_THRESHOLD_GRID_SIZE=100`。

### 3.3 测试分层策略（提速版）

- `PR 快测`：`PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80`
- `合并前门禁`：`PHASE2_THRESHOLD_SAMPLE=36 PHASE2_THRESHOLD_GRID_SIZE=100`
- `阶段验收`：`PHASE2_THRESHOLD_SAMPLE=30 PHASE2_THRESHOLD_GRID_SIZE=100`
- 要求：`TC-P1P2-001/006` 至少命中前两档之一；阶段收口使用 `30/100` 档。

---

## 4. Required Commands（必须执行命令）

- `PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py`（PR 快测）
- `PHASE2_THRESHOLD_SAMPLE=36 PHASE2_THRESHOLD_GRID_SIZE=100 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py`（合并前门禁）
- `PHASE2_THRESHOLD_SAMPLE=30 PHASE2_THRESHOLD_GRID_SIZE=100 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py`（阶段验收）
- `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py`
- `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_observability_outputs_present"`
- `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "generate_theme_data_only_reuses_upstream_classification or forbids_secondary_category_inference"`
- `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_adr_decisions_documented"`
- `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_from_theme_master or l1_keywords_aggregated_from_l2_keywords"`
- `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "category_keywords_backfill_idempotent or category_keyword_coverage_metrics_present"`
- `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_semantic_embedding_cache_unit.py`
- `/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/phase2_update_mapping_audit.py --sample-size 24 --out /Users/admin/Desktop/ai_theme_app/tmp/phase2_update_mapping_audit.json`
- `printf "9\n" | /opt/miniconda3/envs/theme_matcher_env/bin/python database_service/scripts/test_theme_processor.py`
- `printf "11\n" | /opt/miniconda3/envs/theme_matcher_env/bin/python database_service/scripts/test_theme_processor.py`
- `rg -n "dynamic_threshold|Strong|Candidate|Weak|candidate_window|source_type|_match_categories|generate_theme_data_only|zero vector|random vector" database_service theme_service docs`

状态同步与对账基线（MUST）：

- 实时状态同步顺序：`Doing -> test-evidence -> In review/done -> milestone progress`
- `P0/P1` 写入 `In review/done` 时必须显式传 `--test-files` 且这些文件必须出现在当前 `git diff`。
- 阶段末完成度判断必须使用 `--milestone-id` 全量拉取后本地筛 phase，禁止仅依赖 `--task-prefix + --status`。

---

## 5. Deliverables（可验证路径）

- 动态阈值 profile 与三段分层实现（`baseline/balanced/strict` + `Strong/Candidate/Weak`）。
  - 路径: `theme_service/matchers/semantic_matcher.py`, `theme_service/services/theme_discovery_engine.py`
- 候选窗口治理与爆炸比监控（窗口 3~30 + 爆炸比统计）。
  - 路径: `theme_service/matchers/semantic_matcher.py`, `database_service/streams/handlers/theme_processor.py`
- 分类真源复用改造（禁止创建阶段再次 `_match_categories`）。
  - 路径: `theme_service/creators/theme_rule_generator.py`
- 分类关键词反向索引补全（`theme_master.tags.keywords -> financial_categories.keywords`，`L2 <- L3`、`L1 <- L2`）。
  - 路径: `database_service/scripts/`, `theme_service/services/`, `docs/architecture/financial_categories_data_only.sql`, `docs/architecture/theme_master_data_only.sql`
- 30 案例三方评估与 A/B 灰度证据（含 real 调用标记）。
  - 路径: `database_service/scripts/test_theme_processor.py`, `docs/project_control/reports/phase-P1.phase2.md`
- 决策流全量审计与映射准确率报告。
  - 路径: `database_service/scripts/phase2_update_mapping_audit.py`, `tmp/phase2_update_mapping_audit.json`, `tmp/phase2_update_mapping_audit_sanitized_title.json`
- 语义向量缓存复用实现与单测。
  - 路径: `theme_service/matchers/semantic_matcher.py`, `database_service/tests/streams/test_semantic_embedding_cache_unit.py`
- 执行器输入产物。
  - 路径: `tmp/plan/wbs.md`, `docs/project_control/TEST_CASE_SPEC_P1.phase2.md`, `tmp/plan/test_traceability_P1.phase2.json`, `tmp/feature_traceability_P1.phase2.json`, `tmp/feature_validation_report_P1.phase2.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 动态阈值抖动导致召回不稳定 | High | High | 候选窗口持续超界（<3 或 >30） | Dev + QA | 分位数平滑、profile 回退、阈值上限保护 |
| 随机/零向量回退污染最终决策 | High | Medium | 模型异常路径被主链路采用 | Dev | 禁止作为最终决策，改为受控降级并审计 |
| 分类真源不唯一导致匹配/建题材不一致 | High | High | 创建阶段仍触发 `_match_categories` | Dev + Architect | 复用首阶段分类结果，禁二次推断并加回归测试 |
| A/B 灰度与 real 调用证据不足 | High | Medium | `source_type=real` 占比未达门槛 | QA + PM | 先 10% 灰度，达标再扩量，失败阻断发布 |

---

## 7. Rollback Plan

触发条件（任一命中）：

- 候选爆炸比 `>= 5%` 或候选窗口无法稳定在 `3~30`。
- 发现随机/零向量结果进入最终决策链路。
- 分类复用改造后出现分类不一致或回放偏移。
- `source_type=real` 不达验收门槛。

回滚分层：

- 代码回滚：回退到上一稳定 profile/匹配策略版本，恢复可验证基线阈值路径。
- 数据回滚：按评估批次与审计日志回放校正，撤销异常批次结论。
- 同步补偿回滚：Notion 状态回写失败写入 `pending_sync`，网络恢复后重放补偿。

---

## 8. Non-Goals

- 不引入/放量 LLM 最终裁决链路（P1.phase3 范围）。
- 不覆盖发布门禁与回放收口（P1.phase4 范围）。
- 不进行第二阶段 CQRS/生命周期状态机改造。

---

## 9. Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| phase2 验收目标细粒度 | `ACCEPTANCE.md`（10条） | 旧 `PHASE_CONTRACT_P1.phase2.md`（4条） | ACCEPTANCE 为验收真源，旧合同粒度不足且缺强约束 |
| phase2 需求细节（动态阈值/随机向量禁用/source_type 门禁） | `prd_p1.md`（`PRD-P1-P2-R01~R10`） | `PRD.md` M2 总述级条款 | 合同需可执行细粒度需求，优先 phase 专项 PRD |
| 分类复用改造优先级 | `PLAN_WBS.md` + `ARCH_REVIEW.md`（P1-ISS-13） | 旧文档中的泛化“分类优化”表述 | 需明确“移除二次推断”这一可验证动作 |

---

## 10. Self-Check（MUST）

- [x] Phase Identity 完整
- [x] Acceptance 条款二元可判定
- [x] Required Commands 可复制执行且安全
- [x] Deliverables 全部映射到路径
- [x] Risk/Rollback/Non-Goals 无缺失
- [x] 生成 `.md + .json` 双格式
- [x] 冲突裁决记录已填写
- [x] 引用统一约束清单 `docs/project_control/EXECUTION_GUARDRAILS.md`
- [x] 多 PRD 文件已纳入并完成裁决（`PRD.md` + `prd_p1.md`）
- [x] 一致性报告通过（`is_consistent=true`）
