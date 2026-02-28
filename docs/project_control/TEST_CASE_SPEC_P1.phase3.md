# TEST CASE SPEC — P1.phase3

## 0. 范围与原则
- 目标：按 `docs/project_control/FEATURE_SPEC_P1.phase3.md` 的功能分解（`F-P1.phase3-*`）建立一一对应测试分解。
- 执行模式：`execution_mode=real`，`allow_mock=false`。
- 关键依赖：`redis,mysql,llm`。
- 证据字段：`trace_id,decision_id,request_id,model_name,timestamp,source_type`。
- 当前范围约束：本轮不验收 `pending_manual_review/drop_event` 前端闭环，仅验证自动链路。

## 1. 验收级 TC（保持兼容）
- `TC-P1-P3-IT-001` 最终裁决必经链路（语义粗筛 -> LLM）。
- `TC-P1-P3-ET-001` 裁判超时回退不阻塞主链路。
- `TC-P1-P3-ST-001` 10%灰度最终裁决比例与模型栈证据。
- `TC-P1-P3-ET-002` model 不可用降级与熔断。
- `TC-P1-P3-PT-001` 裁判附加时延预算。
- `TC-P1-P3-RT-001` 最终裁决报告完整性回归。
- `TC-P1-P3-ST-002` source_type 与质量标签门禁。
- `TC-P1-P3-ET-003` mock 样本拒绝采纳与原因码。
- `TC-P1-P3-ARCH-001` 架构门禁：集成系统逻辑图（§2.5）关键路由与门禁不变量防漂移。

## 2. 功能分解对齐矩阵（Feature -> Test，MUST）

| Feature 子功能 | 需求/约束 | 验收级TC | 子用例ID | 优先级 | 状态 |
| --- | --- | --- | --- | --- | --- |
| `F-P1.phase3-T01-01` 全量复核分发器 | 分类命中后候选全量进入LLM | IT-001 | `TC-P1-P3-F-T01-01` | P0 | In Scope |
| `F-P1.phase3-T01-02` 回退策略定义器 | 超时/异常回退 stage1 | ET-001 | `TC-P1-P3-F-T01-02` | P0 | In Scope |
| `F-P1.phase3-T01-03` 裁判契约字段冻结 | `judge_*` 与审计字段必填 | IT-001 | `TC-P1-P3-F-T01-03` | P0 | In Scope |
| `F-P1.phase3-T02-01` Arbiter客户端接入 | `Qwen2.5+llama.cpp` 真实调用 | ST-001 | `TC-P1-P3-F-T02-01` | P0 | In Scope |
| `F-P1.phase3-T02-02` 超时回退执行器 | `timeout_fallback` 不阻塞 | ET-001 | `TC-P1-P3-F-T02-02` | P0 | In Scope |
| `F-P1.phase3-T02-03` 不可用熔断器 | `model_unavailable` + circuit | ET-002 | `TC-P1-P3-F-T02-03` | P1 | In Scope |
| `F-P1.phase3-T03-01` 灰度分桶与路由 | 100%复核 + 10%采纳 | ST-001 | `TC-P1-P3-F-T03-01` | P0 | In Scope |
| `F-P1.phase3-T03-02` 裁决比例门禁 | `llm_final_judged_ratio>=0.95` | ST-001 | `TC-P1-P3-F-T03-02` | P0 | In Scope |
| `F-P1.phase3-T03-03` 真实调用证据采集器 | evidence 完整率门禁 | RT-001 | `TC-P1-P3-F-T03-03` | P1 | In Scope |
| `F-P1.phase3-T03-04` 人工复核分流器 | `pending_manual_review` 分流 | - | `TC-P1-P3-F-T03-04` | P2 | Deferred |
| `F-P1.phase3-T04-01` 时延门禁器 | `arbiter_p95_latency < 800ms` | PT-001 | `TC-P1-P3-F-T04-01` | P0 | In Scope |
| `F-P1.phase3-T04-02` 成本门禁器 | 超预算告警与降级 | RT-001 | `TC-P1-P3-F-T04-02` | P1 | In Scope |
| `F-P1.phase3-T04-03` 真实调用占比门禁器 | `real_call_ratio=1.0` 验收口径 | ST-002/ET-003 | `TC-P1-P3-F-T04-03` | P1 | In Scope |

## 3. 子用例详细分解（按 Feature）

### TC-P1-P3-F-T01-01（对应 `F-P1.phase3-T01-01`）
- 级别：IT，优先级：P0。
- 目标：分类命中样本的候选集 100% 进入 LLM 复核。
- 前置：输入包含 `classification_result` 与 `candidate_list`。
- 核心断言：
  - `need_judge=true`。
  - `judge_trigger_reason=classification_matched_full_review`。
  - `judge_full_review_ratio==1.0`（分类命中样本全集）。

### TC-P1-P3-F-T01-02（对应 `F-P1.phase3-T01-02`）
- 级别：ET，优先级：P0。
- 目标：超时/异常统一回退 stage1 且不中断主链路。
- 核心断言：
  - `fallback_applied=true`。
  - `fallback_reason in {timeout_fallback, model_unavailable}`。
  - 处理结果可继续进入 decision 流，不阻塞 ACK。

### TC-P1-P3-F-T01-03（对应 `F-P1.phase3-T01-03`）
- 级别：IT，优先级：P0。
- 目标：冻结裁判契约字段并强校验。
- 核心断言：
  - 输出包含 `judge_source/judge_applied/request_id/model_name`。
  - 缺字段样本拒绝进入执行器并记录 `contract_validation_fail_count`。

### TC-P1-P3-F-T02-01（对应 `F-P1.phase3-T02-01`）
- 级别：ST，优先级：P0。
- 目标：真实模型接入与结果解析可用。
- 核心断言：
  - `model_name` 命中 `Qwen2.5` 与 `llama.cpp`。
  - 返回 `decision/confidence/request_id/timestamp`。
  - `arbiter_call_success_rate` 可统计。

### TC-P1-P3-F-T02-02（对应 `F-P1.phase3-T02-02`）
- 级别：ET，优先级：P0。
- 目标：调用超时立即回退。
- 核心断言：
  - `judge_applied=false`。
  - `fallback_reason=timeout_fallback`。
  - `fallback_latency_ms` 未超主链预算。

### TC-P1-P3-F-T02-03（对应 `F-P1.phase3-T02-03`）
- 级别：ET，优先级：P1。
- 目标：不可用触发熔断与短路。
- 核心断言：
  - `circuit_state` 按 `closed->open->half_open` 受控变化。
  - 触发后短路模型调用并走受控降级。

### TC-P1-P3-F-T03-01（对应 `F-P1.phase3-T03-01`）
- 级别：ST，优先级：P0。
- 目标：灰度分桶与路由正确。
- 核心断言：
  - 分类命中样本 `judge_full_review_ratio==1.0`。
  - `ab_gray_traffic_ratio` 约等于 0.1（容差按实现定义）。
  - 分桶异常默认 shadow 并告警。

### TC-P1-P3-F-T03-02（对应 `F-P1.phase3-T03-02`）
- 级别：ST，优先级：P0。
- 目标：裁决比例门禁有效。
- 核心断言：
  - `llm_final_judged_ratio >= 0.95`。
  - 未达阈值时 gate fail，阻断扩量。

### TC-P1-P3-F-T03-03（对应 `F-P1.phase3-T03-03`）
- 级别：RT，优先级：P1。
- 目标：证据采集完整可审计。
- 核心断言：
  - evidence 包含 `request_id/timestamp/model_name/source_type`。
  - `evidence_integrity_rate==1.0`（验收样本口径）。

### TC-P1-P3-F-T03-04（对应 `F-P1.phase3-T03-04`，Deferred）
- 级别：ST，优先级：P2。
- 状态：Deferred（待前端人工复核流程联调时启用）。
- 预置断言：`abstain/category_uncertain -> pending_manual_review`。

### TC-P1-P3-F-T04-01（对应 `F-P1.phase3-T04-01`）
- 级别：PT，优先级：P0。
- 目标：时延门禁生效。
- 核心断言：
  - `arbiter_p95_latency < 800ms`。
  - 超阈触发 `latency_gate_fail_count` 增长与降级动作。

### TC-P1-P3-F-T04-02（对应 `F-P1.phase3-T04-02`）
- 级别：RT，优先级：P1。
- 目标：成本门禁生效。
- 核心断言：
  - 超预算触发 `budget_alert_count` 与 `budget_fallback`。
  - 预算恢复后门禁可回到 pass。

### TC-P1-P3-F-T04-03（对应 `F-P1.phase3-T04-03`）
- 级别：ST/ET，优先级：P1。
- 目标：真实调用占比门禁。
- 核心断言：
  - 验收统计口径内 `real_call_ratio == 1.0`。
  - `source_type=mock` 样本不得进入生产采纳，并记录原因码。

## 4. 子用例 -> pytest 函数映射（落地计划）

| 子用例ID | 推荐函数名 | 现状 |
| --- | --- | --- |
| `TC-P1-P3-F-T01-01` | `test_stage1_then_llm_full_review_then_final_persist` | 已有骨架 |
| `TC-P1-P3-F-T01-02` | `test_arbiter_timeout_fallback_to_stage1_without_blocking` | 已有骨架 |
| `TC-P1-P3-F-T01-03` | `test_judge_contract_required_fields_and_reject_on_missing` | 已有骨架 |
| `TC-P1-P3-F-T02-01` | `test_llm_client_returns_required_fields_and_model_stack` | 已有骨架 |
| `TC-P1-P3-F-T02-02` | `test_timeout_fallback_sets_flags_and_non_blocking` | 复用 ET-001 |
| `TC-P1-P3-F-T02-03` | `test_model_unavailable_sets_reason_and_circuit_breaker` | 已有骨架 |
| `TC-P1-P3-F-T03-01` | `test_full_review_ratio_and_gray_gate_and_model_evidence` | 已有骨架 |
| `TC-P1-P3-F-T03-02` | `test_llm_final_judged_ratio_gate_blocks_on_threshold_breach` | 已有骨架 |
| `TC-P1-P3-F-T03-03` | `test_final_judge_report_contains_required_dimensions` | 已有骨架 |
| `TC-P1-P3-F-T03-04` | `test_uncertain_samples_route_to_pending_manual_review` | Deferred |
| `TC-P1-P3-F-T04-01` | `test_arbiter_p95_latency_under_800ms` | 已有骨架 |
| `TC-P1-P3-F-T04-02` | `test_cost_gate_triggers_budget_fallback_and_alert` | 已有骨架 |
| `TC-P1-P3-F-T04-03` | `test_source_type_quality_gate_real_only_adoption` / `test_mock_source_rejected_with_reason_code` | 已有骨架 |
| `TC-P1-P3-ARCH-001` | `test_phase3_architecture_guard_*`（文件级） | 已实现 |

## 5. 必跑命令（绝对路径）
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "stage1_then_llm_full_review_then_final_persist or arbiter_timeout_fallback_to_stage1_without_blocking or model_unavailable_sets_reason_and_circuit_breaker"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "full_review_ratio_and_gray_gate_and_model_evidence or arbiter_p95_latency_under_800ms or final_judge_report_contains_required_dimensions"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_behavior_tests.py -k "source_type_quality_gate_real_only_adoption or mock_source_rejected_with_reason_code"`
- `cd /Users/admin/Desktop/ai_theme_app && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase3_architecture_guard.py`

## 6. 与 feature_spec 的一致性结论
- `F-P1.phase3-T01-01 ~ T04-03` 已全部建立测试映射。
- `F-P1.phase3-T03-04` 已明确 `Deferred`（符合当前“人工终审后续联调”范围约束）。
- 本文件作为 P1.phase3 专项真源，后续变更以本文件优先。
