---
phase: P1.phase0
run_id: 20260217_165458
---

# TEST CASE SPEC - P1.phase0

## TC-P1P0-001
- WBS: P1.phase0-T01
- Command:
  - `pytest -q database_service/tests/streams/test_phase0_behavior_tests.py -k "runtime_entry_uses_single_execute_chain"`
- Expected: 主路径仅保留单生效实现；旧路径不可作为可触发入口。

## TC-P1P0-002
- WBS: P1.phase0-T02
- Command:
  - `pytest -q database_service/tests/streams/test_phase0_behavior_tests.py -k "decision_envelope_v1_required_fields_validation"`
- Expected: 合同关键字段在验收与PRD中一致可检索。

## TC-P1P0-003
- WBS: P1.phase0-T03
- Command:
  - `pytest -q database_service/tests/streams/test_phase0_behavior_tests.py -k "processing_path_does_not_use_print_calls"`
- Expected: 运行时主链路不允许存在 print/traceback.print_exc。

## TC-P1P0-004
- WBS: P1.phase0-T04
- Command:
  - `pytest -q database_service/tests/streams/test_phase0_behavior_tests.py -k "trace_id_and_payload_version_are_normalized_for_v0_input"`
  - `pytest -q database_service/tests/streams/test_message_serializer.py`
  - `pytest -q database_service/tests/streams/test_stream_config.py`
  - `pytest database_service/tests/streams -q`
- Expected: 全部通过，trace_id/payload_version 链路相关断言满足。
