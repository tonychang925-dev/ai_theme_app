# Change Plan 快速入口

请查看正式文件：`tmp/plan/change_plan.md`

## 本轮执行记录（2026-02-19）

- 记录文件：`tmp/phase2_execution_record_20260219.md`
- 摘要：
  - `TC-P1P2-004`（`phase2_triparty_metrics`）通过
  - `TC-P1P2-003A~D`（`architecture_guard`）通过
  - `T01(24/80)` 已补测通过（非沙盒执行，规避 `torch/transformers` SHM 崩溃）
  - `T01(30/100)` 历史通过结果可复用（本轮不重复全量）

## 增量优化记录（2026-02-19 16:00+）

- `semantic_matcher` 增加向量缓存复用（Redis优先 + 本地兜底 + 统计埋点）
- 新增缓存单测：`database_service/tests/streams/test_semantic_embedding_cache_unit.py`（`2 passed`）
- `test_theme_processor` 审计改为“处理后全量读取 decision 流”，修复窗口抽样偏差
- 24条真实回放完成并产出：
  - `tmp/phase2_update_mapping_audit.json`
  - `tmp/phase2_update_mapping_audit_sanitized_title.json`
- `phase2_update_mapping_audit.py` 修正准确率规则：
  - 字段读取修复（`matched_theme_name`）
  - 同题材簇等价规则（SpaceX/太空军事复用场景）
  - 复算结果：`13/13 = 1.0`
