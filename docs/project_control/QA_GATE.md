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

---

## P2.phase0 Gate Refresh（2026-03-30）

### A. 当前门禁对象
- `P2.phase0`
- 当前目标：在进入 `100` 条最终真实验收前，完成文档、测试口径、真实命令与证据路径冻结。

### B. 当前真实通过项
- `ThemeMatchEngine` 真实单元层：
  - `10` 条 `AI/AR眼镜`：`top1_accuracy = 1.0`
  - `30` 条 `AI/AR眼镜`：`top1_accuracy = 1.0`
- `theme_processor.py` 真实集成层：
  - `30` 条：`top1_accuracy = 1.0`
- `news_stream_processor.py -> theme_processor.py` 真实跨组件层：
  - `10` 条：`top1_accuracy = 1.0`
- `stream:news:raw -> decision` 真实全链路预演：
  - `10` 条：`top1_accuracy = 1.0`
  - 已提供实时进度输出

### C. 当前真实必跑命令
- `cd /Users/admin/Desktop/ai_theme_app && export DEEPSEEK_API_KEY='***' && /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/model_service/tests/test_p2_phase0_model_service_contract.py`
- `cd /Users/admin/Desktop/ai_theme_app && POSTGRES_DATABASE=stock_data_test /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/theme_service/tests/unit/test_p2_phase0_theme_match_engine_real_db.py`
- `cd /Users/admin/Desktop/ai_theme_app && PYTHONPATH=/Users/admin/Desktop/ai_theme_app POSTGRES_DATABASE=stock_data_test /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/integration/test_p2_phase0_theme_processor_real_integration.py`
- `cd /Users/admin/Desktop/ai_theme_app && export DEEPSEEK_API_KEY='***' && export P2_PHASE0_SAMPLE_SIZE=10 && export PYTHONPATH=/Users/admin/Desktop/ai_theme_app && export POSTGRES_DATABASE=stock_data_test && /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/tmp/run_news_processor_to_theme_processor_5.py`
- `cd /Users/admin/Desktop/ai_theme_app && export DEEPSEEK_API_KEY='***' && export PYTHONPATH=/Users/admin/Desktop/ai_theme_app && export POSTGRES_DATABASE=stock_data_test && /opt/miniconda3/envs/theme_matcher_env/bin/python -u /Users/admin/Desktop/ai_theme_app/tmp/run_full_chain_10_to_decision_with_progress.py`
- `cd /Users/admin/Desktop/ai_theme_app && export DEEPSEEK_API_KEY='***' && export PYTHONPATH=/Users/admin/Desktop/ai_theme_app && export POSTGRES_DATABASE=stock_data_test && /opt/miniconda3/envs/theme_matcher_env/bin/python -u /Users/admin/Desktop/ai_theme_app/tmp/run_full_chain_100_to_decision_with_progress.py`

### D. 当前核心证据
- `tmp/p2_phase0_theme_match_engine_10.preview.json`
- `tmp/p2_phase0_theme_match_engine_30_from_test_cases.preview.json`
- `tmp/p2_phase0_theme_processor_integration_30.preview.json`
- `tmp/p2_phase0_news_to_theme_5.preview.json`
- `tmp/p2_phase0_full_chain_10_to_decision.preview.json`

### E. 当前 blocker 状态
- `news_stream_handler.py` 组件本体的 `_ensure_consumer_group()` 已正式修复。
- `10` 条真实全链路已在无运行时补偿条件下复测通过。
- 当前未关闭项仅为 `100` 条最终 Gate 的执行结果与报告归档。

### F. 当前 Gate 状态
- `P2.phase0`：**CONDITIONAL PASS（10条预演通过，100条正式 Gate 未执行）**
- 下一步准入条件：
  1. 执行 `100` 条真实全链路最终验收
  2. 归档最终 QA 报告与门禁结论

## P2.phase0 Gate Refresh（2026-03-31）

### A. 最终真实结果
- `100` 条真实全链路：
  - `events = 100`
  - `processed = 100`
  - `top1_hits = 96`
  - `top1_accuracy = 0.96`

### B. 新增关键证据
- [p2_phase0_full_chain_100_to_decision.report.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_to_decision.report.json)
- [p2_phase0_full_chain_100_match_detail.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_match_detail.json)
- [p2_phase0_full_chain_100_match_metrics.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_match_metrics.json)
- [p2_phase0_full_chain_100_mismatches.json](/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_full_chain_100_mismatches.json)

### C. 稳定性收口
- 默认 parser 已切换为 [reliable_deepseek_parser.py](/Users/admin/Desktop/ai_theme_app/model_service/llm_parser/reliable_deepseek_parser.py)
- 本轮 `100` 条真实全链路已完整跑完，未再因早期 DeepSeek 抖动导致整批中断

### D. 当前 Gate 状态
- `P2.phase0`：**CONDITIONAL PASS（100条正式 Gate 已达标，保留少量误判与旧初始化噪音观察项）**
