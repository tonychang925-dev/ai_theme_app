# TEST CASE SPEC — M8.phase1 Cognitive Validation

## 执行顺序

```text
Contract UT -> Writer IT -> Verification UT -> Metrics UT -> 20-day Replay
```

下游任务在前置测试失败时必须 BLOCKED。

## 用例

| TC-ID | Task | Level | 验证目标 |
|---|---|---|---|
| TC-M8P1-T01-01 | T01 | UT | Record 字段、枚举、hash 稳定 |
| TC-M8P1-T01-02 | T01 | UT | 非 YES failure type 与禁止字段 |
| TC-M8P1-T02-01 | T02 | IT | append-only、duplicate skip、conflict reject |
| TC-M8P1-T02-02 | T02 | IT | Yesterday/Today 时点守卫 |
| TC-M8P1-T02-03 | T02 | IT | Manifest 扫描记录数与聚合 hash，缺失/篡改 fail fast |
| TC-M8P1-T03-01 | T03 | UT | YES/NO/PARTIAL/UNVERIFIABLE 工作流 |
| TC-M8P1-T03-02 | T03 | UT | Ground Truth 不由模型自动裁决 |
| TC-M8P1-T04-01 | T04 | UT | Binary Accuracy、Brier、ECE 固定样例 |
| TC-M8P1-T04-02 | T04 | UT | Timing Offset / Delay Accuracy 分布可复算 |
| TC-M8P1-T05-01 | T05 | RT | 连续 20 日 replay、Decision Drift=0 |

## 必跑命令

```bash
.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase1_validation_contract.py
.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase1_validation_metrics.py
.venv/bin/python -m pytest -q stock_processing_service/tests/integration/test_m8_phase1_validation_dataset.py
```
