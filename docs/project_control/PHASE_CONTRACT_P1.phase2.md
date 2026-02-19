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
4. 76 案例集形成三方对比报告，且优化系统在题材数与质量指标上不低于基线。  
5. 阶段验收使用真实 DeepSeek 调用（`source_type=real`），禁止模拟数据替代正式结论。

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
- [ ] 输出 `source_type(real/mock)` 质量指标并设置门禁阈值。
  - 验证映射: `ACC-P1-P2-07`
- [ ] 76 案例集 A/B 报告必须包含：候选爆炸比、完整性、分离度、精度代理。
  - 验证映射: `ACC-P1-P2-01`
- [ ] 76 案例集必须形成三方对比：优化系统 vs 基线系统（纯聚类） vs 久赢恒丰标准。
  - 验证映射: `ACC-P1-P2-04`
- [ ] 76 案例集验收指标必须满足：题材数量收敛到 8~12，且 Precision/Completeness/Separation 三指标均不低于基线系统。
  - 验证映射: `ACC-P1-P2-04`
- [ ] A/B 灰度必须先在 10% 流量执行，通过后才允许扩大范围。
  - 验证映射: `ACC-P1-P2-05`
- [ ] 本阶段验收必须使用真实 DeepSeek 调用（`source_type=real`），禁止模拟数据替代正式结论。
  - 验证映射: `ACC-P1-P2-07`

### 3.1 Acceptance × TestCase × Feature 汇总（MUST）

| Acceptance | WBS Task | Test Case | Feature Slice | 通过判定（Binary） | 验证命令 |
| --- | --- | --- | --- | --- | --- |
| ACC-P1-P2-01 | P1.phase2-T01/T02 | TC-P1P2-001 | F-P1P2-T01-01/04 | 固定阈值下边界样本可复现“过筛/漏筛”差异，支持后续动态阈值改造对照 | `PHASE2_THRESHOLD_SAMPLE=10 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_fixed_threshold_sensitivity"` |
| ACC-P1-P2-02 | P1.phase2-T02 | TC-P1P2-002 | F-P1P2-T02-01/02/03 | 候选窗口 `3~30` 且 `candidate_explosion_ratio < 5%` | `conda run -n theme_matcher_env python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "candidate_window_stability or candidate_explosion_ratio_below_5_percent"` |
| ACC-P1-P2-03 | P1.phase2-T03 | TC-P1P2-003A/003B/003C/003D | F-P1P2-T03-01/02/03 | 禁止随机/零向量最终决策，创建侧禁止二次分类推断，且 ADR 合规可审计 | `PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_tc003_architecture_guard.py` |
| ACC-P1-P2-04 | P1.phase2-T05 | TC-P1P2-004 | F-P1P2-T05-01/02/04 | 三方对比完整；`theme_count 8~12`；三指标不低于基线 | `conda run -n theme_matcher_env python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_triparty_metrics"` |
| ACC-P1-P2-05 | P1.phase2-T04 | TC-P1P2-005 | F-P1P2-T04-01/02 | 仅 10% 灰度命中，保留分桶与 profile 证据 | `conda run -n theme_matcher_env python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "ab_gray_10_percent or bucket_evidence_and_profile_recorded"` |
| ACC-P1-P2-06 | P1.phase2-T01 | TC-P1P2-006 | F-P1P2-T01-02/03 | 语义分数分层结果可区分 strong/good/weak 区间 | `PHASE2_THRESHOLD_SAMPLE=10 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py -k "t01_semantic_score_segmentation"` |
| ACC-P1-P2-07 | P1.phase2-T05 | TC-P1P2-007 | F-P1P2-T05-03 | `source_type=real` 且具备 `request_id/timestamp/model_name` | `conda run -n theme_matcher_env python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py -k "phase2_real_deepseek_evidence"` |

### 3.2 验收补充标准（新增）

- [ ] `P1.phase2-T01~T05` 每个任务在写入 `In review/done` 前必须提交 `--test-files`，且文件命中当前 `git diff`。
- [ ] `T01`（`TC-P1P2-001/006`）必须由 `test_phase2_semantic_matcher_unit.py` 覆盖；流程类用例由 `test_phase2_behavior_tests.py` 覆盖。
- [ ] 关键路径测试必须在 `theme_matcher_env` 执行，禁止以 mock/fake 替代 Redis/DB/DeepSeek 验收证据。
- [ ] 阶段收口前必须产出三方评估与真实调用证据（来自 `test_theme_processor.py` 与 phase2 行为测试）。
- [ ] 常规回归使用 `PHASE2_THRESHOLD_SAMPLE=10`；阶段验收切换 `PHASE2_THRESHOLD_SAMPLE=76`。

---

## 4. Required Commands（必须执行命令）

- `PHASE2_THRESHOLD_SAMPLE=10 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py`
- `PHASE2_THRESHOLD_SAMPLE=76 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q database_service/tests/streams/test_phase2_semantic_matcher_unit.py`（阶段验收）
- `conda run -n theme_matcher_env python -m pytest -q database_service/tests/streams/test_phase2_behavior_tests.py`
- `printf "9\n" | conda run -n theme_matcher_env python database_service/scripts/test_theme_processor.py`
- `printf "11\n" | conda run -n theme_matcher_env python database_service/scripts/test_theme_processor.py`
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
- 76 案例三方评估与 A/B 灰度证据（含 real 调用标记）。
  - 路径: `database_service/scripts/test_theme_processor.py`, `docs/project_control/reports/phase-P1.phase2.md`
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
