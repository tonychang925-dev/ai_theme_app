# Quality Gate Policy

## 1. Definition of Done (DoD)

- [x] 功能代码已在 feature branch (`codex/p1-phase0/runtime_contract`) 实施
- [x] phase0 目标模块完成静态收敛改造
- [x] 重复定义清理（以单实现保留 + legacy重命名方式）
- [x] phase0 目标模块 `print/traceback.print_exc` 清零
- [x] 文档已更新（合同、计划、报告）
- [x] 回滚方案已定义（见 `docs/project_control/PHASE_CONTRACT_P1.phase0.md`）
- [ ] 单元测试全绿（未达成）
- [ ] 无 P0/P1 未解决缺陷（未达成）

## 2. Required Checks（必跑检查项）

### 2.1 单元测试
- 命令：`pytest database_service/tests/streams -q`
- 结果：`FAILED`（62 failed, 28 passed）
- 主要失败类型：测试环境缺少 async 插件、历史用例基线失败。

### 2.2 静态检查（phase0定向）
- 重复定义检查：`PASS`（目标函数各保留一个生效定义）
- 运行时打印清理检查：`PASS`（目标模块无 `print/traceback.print_exc`）
- 语法检查：`PASS`（`.venv/bin/python -m py_compile`）

## 3. 验证证据

### 执行命令
- `.venv/bin/python -m py_compile database_service/streams/handlers/theme_processor.py theme_service/services/theme_service.py database_service/streams/handlers/news_stream_handler.py database_service/streams/schedulers/news_stream_scheduler.py database_service/streams/handlers/DecisionExecutor.py`
- `rg -n "def _get_action_for_decision_type\(" database_service/streams/handlers/theme_processor.py`
- `rg -n "def initialize_with_categories_only\(" theme_service/services/theme_service.py`
- `rg -n "def discover_category_only\(" theme_service/services/theme_service.py`
- `rg -n "def _process_storage_batch\(" database_service/streams/handlers/news_stream_handler.py`
- `rg -n "def _update_storage_stats\(" database_service/streams/handlers/news_stream_handler.py`
- `rg -n "print\(|traceback\.print_exc\(" database_service/streams/handlers/theme_processor.py theme_service/services/theme_service.py database_service/streams/handlers/news_stream_handler.py database_service/streams/schedulers/news_stream_scheduler.py database_service/streams/handlers/DecisionExecutor.py`
- `pytest database_service/tests/streams -q`

### 关键输出摘要
- Duplicate Definitions: `PASS`
- Runtime Print Cleanup: `PASS`
- Python Compile: `PASS`
- Streams Tests: `FAIL`（62 failed, 28 passed）

## 4. 失败处理流程（本次执行）

1. Triage：失败主要为历史测试环境/基线问题，不由本次 phase0 收敛改动引入。
2. Root Cause：大量 `async def` 测试未启用 async 插件；另有既有用例行为与实现不一致。
3. 最小修复：本阶段仅完成 P1.phase0 合约范围改动，不跨入测试体系大修。
4. 复测：已复跑必跑命令并记录。

## 5. Gate Decision

- Acceptance Gate: **FAILED**
- 决策依据：phase0 合约中的必跑测试命令未通过，禁止“带问题通过”。
