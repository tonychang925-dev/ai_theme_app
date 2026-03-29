---
phase: P1.phase1
run_id: 20260218_131829
---

# TEST CASE SPEC - P1.phase1

## TC-P1P1-001
- WBS: P1.phase1-T01
- Command:
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "unknown_action_fail_fast_to_dead_letter_behavior"`
- Expected: 未知动作必须 fail-fast 并进入 dead-letter 路径。

## TC-P1P1-002
- WBS: P1.phase1-T02
- Command:
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "strict_schema_missing_required_field_goes_dead_letter"`
- Expected: 严格 schema 校验与 reject 路径存在且可检索。

## TC-P1P1-003
- WBS: P1.phase1-T03
- Command:
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "duplicate_skip_for_same_idempotency_key"`
- Expected: 幂等键与重复写入阻断逻辑存在且可检索。

## TC-P1P1-004
- WBS: P1.phase1-T04
- Command:
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "normal_unmatched_event_flows_to_pending_via_decision_executor"`
- Expected:
  - 必须走项目真实“分类优先匹配框架”（`enable_classification_first=true`）。
  - 必须验证“normal 事件匹配失败过程”已发生（非仅验证结果流）：
    - `decision_type` 属于未匹配分支（`category_no_match/no_match_in_category/no_match_after_fallback` 之一）。
    - `reason` 包含未匹配语义（如“未匹配/匹配失败”）。
    - 分类推断统计递增（`category_inferences` 增加）。
  - 必须生成 `publish_clustering` 决策并写入 pending 流。
  - 原 decision 消息必须被 ACK（不应残留在 `decision_executors` pending 列表）。
  - 事件链路必须具备并透传 `trace_id`、`decision_id`（decision 与 pending 一致）。

## TC-P1P1-004B
- WBS: P1.phase1-T04
- Command:
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "test_phase1_dataset_baseline_via_test_theme_processor"`
- Expected:
  - 必须复用项目基线测试流程：`database_service/scripts/test_theme_processor.py::RealIntegrationTester.test_new_architecture_with_dataset`。
  - 不接受仅 True/False 的流程通过；必须返回结构化 `t04_validation` 证据。
  - `t04_validation` 必须同时满足：
    - `publish_clustering_decision=true`
    - `pending_written=true`
    - `pending_matches_publish_decision_id=true`
    - `pending_trace_id_present=true`
    - `decision_ack_verified=true`

## TC-P1P1-004C
- WBS: P1.phase1-T04
- Command:
  - `pytest -q database_service/tests/streams`
  - `pytest -q tests`
- Expected:
  - phase1 streams 测试集通过，且不回退到 mock/stub 验证主链路。

## TC-P1P1-005
- WBS: P1.phase1-T05
- Command:
  - `pytest -q database_service/tests/streams/test_phase1_behavior_tests.py -k "failure_message_controlled_to_dead_letter_no_hang"`
- Expected:
  - 连续失败消息必须进入受控 dead-letter 路径（至少可观测到 dead-letter 持续增长）。
  - 不要求 `decision_executors` pending 为 0（允许失败消息处于可追踪 pending 状态）。
  - 必须证明“不悬挂”：继续注入新失败消息后仍能被处理并进入 dead-letter，且执行器任务存活。
