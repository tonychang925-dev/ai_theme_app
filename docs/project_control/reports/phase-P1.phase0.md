# Phase Report - P1.phase0

- Phase: `P1.phase0`
- Contract: `docs/project_control/PHASE_CONTRACT_P1.phase0.md`
- Branch: `codex/p1-phase0/runtime_contract`
- Status: `Gate Failed`
- Date: `2026-02-15`

## 1. Scope Completed

- P1.phase0-T01 运行时单链路与入口收敛：完成（重复定义收敛为单实现）。
- P1.phase0-T02 DecisionEnvelope v1 与 dual-read：完成（执行器新增归一化与必填校验）。
- P1.phase0-T03 重复定义清理与静态门禁：完成（目标函数去重 + 静态扫描证据）。
- P1.phase0-T04 trace_id/payload_version 贯通：完成（执行器字段兜底生成与链路日志约束）。

## 2. Code Changes

- `database_service/streams/handlers/theme_processor.py`
  - 重命名旧实现 `_get_action_for_decision_type_legacy`，保留唯一生效 `_get_action_for_decision_type`。
  - `print_stats` 输出改为 `logger.info`。

- `theme_service/services/theme_service.py`
  - 重命名旧实现 `_initialize_with_categories_only_legacy`、`_discover_category_only_legacy`。
  - `print/traceback.print_exc` 改为结构化日志。

- `database_service/streams/handlers/news_stream_handler.py`
  - 重命名旧实现 `_process_storage_batch_legacy`、`_update_storage_stats_legacy`。
  - `_extract_from_legacy_format` 与 `_extract_news_data_from_payload` 新增 `max_depth` 递归上限（默认3）。
  - `print/traceback.print_exc` 改为结构化日志。

- `database_service/streams/handlers/DecisionExecutor.py`
  - 新增 `_normalize_and_validate_decision_envelope()`：v0/v1 dual-read 归一 + v1 必填校验。
  - 处理入口 `_process_decision()` 接入契约校验失败即 dead-letter。
  - `print_stats` 输出改为 `logger.info`。

- `database_service/streams/schedulers/news_stream_scheduler.py`
  - `traceback.print_exc` 替换为 `logger.exception`。

## 3. Validation Evidence

- 语法检查：`PASS`
  - `.venv/bin/python -m py_compile ...`

- 重复定义门禁：`PASS`
  - `_get_action_for_decision_type` 仅保留一处生效定义。
  - `initialize_with_categories_only` 仅保留一处生效定义。
  - `discover_category_only` 仅保留一处生效定义。
  - `_process_storage_batch` 仅保留一处生效定义。
  - `_update_storage_stats` 仅保留一处生效定义。

- 运行时 print/traceback 门禁（phase0目标模块）：`PASS`
  - 目标模块 `rg` 无匹配。

- 必跑测试：`FAIL`
  - `pytest database_service/tests/streams -q`
  - 结果：`62 failed, 28 passed`
  - 失败主因：async 测试插件缺失 + 历史基线失败。

## 4. Risk & Rollback

- 风险残留：全量 streams 测试体系当前不可作为放行依据（环境与基线双问题）。
- 回滚方式：
  - 本次以最小改动为主，已保留 legacy 实现命名；可按函数级回切。
  - 契约收敛变更可通过恢复 `_process_decision` 中新校验调用实现快速回退。

## 5. Gate Summary

- Gate Result: **FAIL**
- 原因：阶段必跑测试命令未通过。
- 建议：进入 REWORK（优先修复测试环境/基线，再复验 phase0 门禁）。
