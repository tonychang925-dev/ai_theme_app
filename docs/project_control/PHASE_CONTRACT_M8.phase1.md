# Phase Execution Contract — M8.phase1 Cognitive Validation

## 1. Phase Identity

- Phase Code：`M8.phase1`
- Risk：`P0`
- Parent：M8 Market Cognition
- Source：PRD、ACCEPTANCE、PLAN_WBS、Overall Architecture v4.0、Phase 0 GA Report

## 2. Objective

建立 Yesterday Thesis 到 Today Reality 的可审计验证数据集和指标闭环，不实施 Belief/Learning。

## 3. Acceptance Targets

- `ACPT-M8P1-001` Validation Record 完整；
- `ACPT-M8P1-002` 标签/失败类型合法；
- `ACPT-M8P1-003` 无未来泄漏；
- `ACPT-M8P1-004` append-only、幂等与 Manifest Integrity；
- `ACPT-M8P1-005` 指标可复算；
- `ACPT-M8P1-006` 20 日真实 Shadow。

## 4. Required Commands

- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase1_validation_contract.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase1_validation_metrics.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/integration/test_m8_phase1_validation_dataset.py`

## 5. Rollback

- 停止 Validation Writer；
- 保留已生成的 immutable records；
- 不影响 Phase 0、DailyReviewV2、Notion 或 Decision。

## 6. Non-Goals

- Belief、Learning、Memory、多 Hypothesis、自动交易。

## 7. Completion

工程任务 T01～T04 完成后进入 Shadow；T05 需连续 20 个真实交易日，完成前 Phase 1 不宣告 GA。
