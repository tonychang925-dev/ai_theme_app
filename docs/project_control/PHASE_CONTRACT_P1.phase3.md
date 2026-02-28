# Phase Execution Contract

## 0. Contract Meta

- Contract File: `docs/project_control/PHASE_CONTRACT_P1.phase3.md`
- Machine Copy: `tmp/phase_contract_P1.phase3.json`
- Scope: `phase:P1.phase3`
- Unified Guardrails: `docs/project_control/EXECUTION_GUARDRAILS.md`

---

## 1. Phase Identity

- Phase Name: LLM 最终裁决落地（Qwen2.5 + llama.cpp）
- Phase Code: P1.phase3
- Parent Milestone: P1（第一阶段）
- Risk Level: High
- Source Documents (priority order):
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/TEST_CASE_SPEC_P1.phase3.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/adrs/ADR_LIST.md`

---

## 2. Phase Objective（可量化）

1. 固化链路顺序：`语义粗筛 -> LLM 最终裁决`，分类命中样本必须全量进入 LLM 复核；最终落库结果来自 LLM 裁判结论。  
2. 10% 灰度下 `llm_final_judged_ratio >= 95%`。  
3. 裁判附加时延门禁：`arbiter_p95_latency < 800ms`。  
4. 超时/不可用必须受控降级并记录原因码（`timeout_fallback` / `model_unavailable`）。  
5. 模型栈固定 `Qwen2.5 + llama.cpp` 且审计证据完整（`request_id/timestamp/model_name`）。

### 2.1 动态2/8执行策略（新增）

- 原则：`AI优先自动处理 + 人工复核兜底`，2/8 仅为策略比喻，不是固定比例。
- 自动处理路径：高置信且门禁通过的样本由系统直接执行 `update_theme/create_new_theme/publish_clustering`。
- 人工复核路径：中低置信、模型不确定（`abstain/category_uncertain`）、或门禁异常样本进入 `pending_manual_review` 队列，由分析师决策。
- 比例调节：`manual_review_rate` 依据实时指标动态调整，不在合同中写死固定阈值。
- 强制审计字段：`review_status`, `llm_suggestion`, `review_reason`, `reviewer_id`, `trace_id`, `request_id`, `model_name`, `timestamp`。

---

## 3. Acceptance Targets（门禁条件，二元判定）

- [ ] 二阶段链路顺序固定为“语义粗筛 -> LLM 裁判最终裁决”，不得绕过粗筛直接裁判。  
  - 验证映射: `ACC-P1-P3-01`
- [ ] 分类命中后的候选结果必须全量进入 LLM 复核，不得仅对歧义样本复核。  
  - 验证映射: `ACC-P1-P3-01`
- [ ] 在第一阶段验收流量范围内，最终落库结果必须来自 LLM 裁判结论。  
  - 验证映射: `ACC-P1-P3-01`
- [ ] 裁判超时必须回退阶段一结果，不阻塞主链路。  
  - 验证映射: `ACC-P1-P3-02`
- [ ] P95 裁判附加时延 < 800ms。  
  - 验证映射: `ACC-P1-P3-02`
- [ ] 成本预算超阈触发告警与自动降级。  
  - 验证映射: `ACC-P1-P3-03`
- [ ] `model_service` 不可用时触发明确降级原因码。  
  - 验证映射: `ACC-P1-P3-03`
- [ ] 10% 灰度下 `llm_final_judged_ratio >= 95%`。  
  - 验证映射: `ACC-P1-P3-01`
- [ ] 裁判模型固定为 `Qwen2.5 + llama.cpp`，并保留真实调用证据（request_id/timestamp/model）。  
  - 验证映射: `ACC-P1-P3-01`

### 3.1 Acceptance × TestCase × WBS 汇总（MUST）

| Acceptance | WBS Task | Test Case | 通过判定（Binary） | 验证命令 |
| --- | --- | --- | --- | --- |
| ACC-P1-P3-01 | P1.phase3-T01/T02/T03 | TC-P1-P3-IT-001 | 强制两阶段顺序；分类命中样本全量复核；最终落库结果来自 LLM 裁判 | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "stage1_then_llm_full_review_then_final_persist"` |
| ACC-P1-P3-02 | P1.phase3-T02 | TC-P1-P3-ET-001 | 超时回退生效，不阻塞主链路，记录 `timeout_fallback` | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "arbiter_timeout_fallback_to_stage1_without_blocking"` |
| ACC-P1-P3-03 | P1.phase3-T02/T04 | TC-P1-P3-ET-002 | model 不可用时触发 `model_unavailable` 降级与熔断保护 | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "model_unavailable_sets_reason_and_circuit_breaker"` |
| ACC-P1-P3-03 | P1.phase3-T03a | TC-P1-P3-ST-002, TC-P1-P3-ET-003 | `source_type/quality_tag` 门禁生效；`mock` 样本不得进入生产采纳并记录原因码 | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "source_type_quality_gate_real_only_adoption or mock_source_rejected_with_reason_code"` |
| ACC-P1-P3-01 | P1.phase3-T03 | TC-P1-P3-ST-001 | 10% 灰度下 `llm_final_judged_ratio >= 95%` 且模型栈证据完整 | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "full_review_ratio_and_gray_gate_and_model_evidence"` |
| ACC-P1-P3-02 | P1.phase3-T04 | TC-P1-P3-PT-001 | `arbiter_p95_latency < 800ms` | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "arbiter_latency_budget"` |
| ACC-P1-P3-01/02/03 | P1.phase3-T03/T04 | TC-P1-P3-RT-001 | 最终裁决报告完整（精度/时延/成本/误判归因） | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "final_judge_report_contains_required_dimensions"` |
| ACC-P1-P3-01/02/03 | P1.phase3-T01~T04 | TC-P1-P3-ARCH-001 | 集成系统逻辑图(§2.5)关键路由与门禁不变量不可漂移（分类未命中但有近邻候选仍复核；gate fail 必走 manual；create 分支复用上游分类） | `.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_architecture_guard.py` |

---

## 4. Required Commands（必须执行命令）

- `/Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py`
- `/Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_architecture_guard.py`
- `/Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "stage1_then_llm_full_review_then_final_persist or arbiter_timeout_fallback_to_stage1_without_blocking or model_unavailable_sets_reason_and_circuit_breaker"`
- `/Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "full_review_ratio_and_gray_gate_and_model_evidence or arbiter_p95_latency_under_800ms or final_judge_report_contains_required_dimensions"`
- `rg -n "Qwen2\\.5|llama\\.cpp|llm_final_judged_ratio|arbiter_p95_latency|timeout_fallback|model_unavailable|request_id|model_name" /Users/admin/Desktop/ai_theme_app/database_service /Users/admin/Desktop/ai_theme_app/theme_service /Users/admin/Desktop/ai_theme_app/docs`

测试执行约束（新增，MUST）：

- 为避免沙盒/工作目录差异导致路径解析失败，phase3 测试命令必须优先使用绝对路径（示例：`/Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py`）。
- 统一在项目根执行：`cd /Users/admin/Desktop/ai_theme_app` 后再运行测试。
- 若出现环境限制导致相对路径失败，不得改用 mock 路径“跳过验收”；必须改为绝对路径重试并保留失败日志。

可直接复制命令清单（绝对路径）：

- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "stage1_then_llm_full_review_then_final_persist"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_architecture_guard.py`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "arbiter_timeout_fallback_to_stage1_without_blocking"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "model_unavailable_sets_reason_and_circuit_breaker"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "full_review_ratio_and_gray_gate_and_model_evidence"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "arbiter_p95_latency_under_800ms"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "final_judge_report_contains_required_dimensions"`

状态同步与对账基线（MUST）：

- 实时状态同步顺序：`Doing -> test-evidence -> In review/done -> milestone progress`
- `P0/P1` 任务写入 `In review/done` 时必须显式传 `--test-files` 且文件命中当前 `git diff`
- 阶段末完成度判断必须使用 `--milestone-id` 全量拉取后本地筛 phase

---

## 5. Deliverables（可验证路径）

- 二阶段最终裁决链路实现（强制顺序 + 分类命中全量复核 + 最终落库来源约束）。  
  - 路径: `database_service/streams/handlers/theme_processor.py`, `theme_service/services/theme_service.py`
- 裁判超时/不可用受控降级、熔断与告警实现。  
  - 路径: `theme_service/services/`, `database_service/streams/handlers/`
- 灰度与指标产物（10% 灰度、时延、成本、判定比例）。  
  - 路径: `database_service/scripts/`, `tmp/`, `docs/project_control/reports/phase-P1.phase3.md`
- 真实调用证据（`request_id/timestamp/model_name/source_type`）。  
  - 路径: `tmp/`, `logs/`, `docs/project_control/reports/`
- 执行器输入产物。  
  - 路径: `tmp/plan/wbs.md`, `docs/project_control/TEST_CASE_SPEC_P1.phase3.md`, `tmp/plan/test_traceability_P1.phase3.json`, `tmp/feature_traceability_P1.phase3.json`, `tmp/feature_validation_report_P1.phase3.json`

---

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 裁判链路未成为必经最终裁决，分类命中样本未全量复核 | High | Medium | 出现“分类命中但未复核已落库”样本 | Dev + Architect | 强制顺序断言 + 全量复核断言 + 落库前判定来源校验 |
| 裁判时延抖动导致主链路退化 | High | Medium | `arbiter_p95_latency >= 800ms` | Dev + QA | 超时回退 + 熔断窗口 + 预算门禁 |
| 模型不可用导致静默回退、无审计 | High | Medium | 无 `model_unavailable` 原因码 | Dev | 降级原因码强制 + 告警计数门禁 |
| 成本超预算但未触发降级 | Medium | Medium | `arbiter_cost_per_1k` 连续超阈 | PM + Dev | 预算阈值门禁 + 自动降级策略 |
| 人工复核入口缺失导致机器误判直落库 | High | Medium | `manual_review_rate` 长期接近0且误判上升 | Dev + Analyst | 启用 `pending_manual_review` 队列 + 人工终审门禁 |

---

## 7. Rollback Plan

触发条件（任一命中）：

- `llm_final_judged_ratio < 95%`（10%灰度）
- `arbiter_p95_latency >= 800ms`
- 连续超时或模型不可用超预算
- 模型栈或真实调用证据不合规

回滚分层：

- 代码回滚：从“强制最终裁决落库”回退到“全量复核但仅 shadow 不采纳”，并保留审计证据。
- 运行回滚：关闭 final_judge 开关，恢复阶段一结果直出（仅短期应急）。
- 数据回滚：按 `request_id/decision_id/trace_id` 回放恢复，确保可追踪。

---

## 8. Non-Goals

- 不进行全量生产切流（仅灰度和门禁验证范围）。
- 不在本阶段完成 phase4 发布收口与 replay gate。
- 不改变 phase2 已确认通过的分类真源复用语义。
- 不在本阶段实现完整前端人工复核界面，仅定义后端队列与审计契约。
- 本轮 phase3 测试不验收 `pending_manual_review/drop_event` 端到端闭环，仅验证自动链路（语义粗筛 -> LLM裁决 -> 决策执行）。

---

## 9. Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 裁决理由 |
| --- | --- | --- | --- |
| phase3 验收条款 | `ACCEPTANCE.md` phase3 | 旧版 phase3 合约简化条款 | ACCEPTANCE 为验收真源，需覆盖 timeout/model_unavailable/成本门禁 |
| phase3 需求颗粒度 | `prd_p1.md` (`PRD-P1-P3-R01~R10`) | `PRD.md` M2 总述级条款 | 合约需要可执行、可测试、可门禁化的细粒度条款 |
| 任务拆解与依赖 | `PLAN_WBS.md`（P1.phase3-T01~T04） | 临时执行路径约定 | 统一 WBS 作为执行顺序真源 |
| 技术风险优先级 | `ARCH_REVIEW.md` + `ADR_LIST.md` | 仅经验判断 | 已有架构风险与ADR决策，需纳入合同门禁 |

---

## 10. Self-Check（MUST）

- [x] Phase Identity 完整
- [x] Acceptance 条款二元可判定
- [x] Required Commands 可复制执行
- [x] Deliverables 全部映射到路径
- [x] Risk/Rollback/Non-Goals 无缺失
- [x] 生成 `.md + .json` 双格式
- [x] 冲突裁决记录已填写
- [x] 引用统一约束清单 `docs/project_control/EXECUTION_GUARDRAILS.md`
