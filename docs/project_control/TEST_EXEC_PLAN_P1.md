# 第一阶段测试执行任务清单（P1）

- 文档版本：v1.0
- 生成日期：2026-02-13
- 关联文档：
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/TEST_CASE_SPEC.md`

---

## 1. 执行前准备

### 1.1 环境检查

```bash
cd /Users/admin/Desktop/ai_theme_app
python -V
pytest --version
redis-cli ping
```

### 1.2 环境口径说明（必须确认）

- `ACCEPTANCE.md` 要求：macOS + Python 3.13 + `theme_matcher_env`。
- 当前仓库 `theme_matcher_env.yml` 为 Python 3.12.11。

执行策略：
- 通用链路测试用系统 Python 3.13（若本机满足）。
- transformer / 深度匹配相关测试用 `theme_matcher_env`。
- 若严格执行架构第12章门禁，应将 `theme_matcher_env` 升级到 Python 3.13 后再做最终验收。

---

## 2. Phase 执行顺序（命令级）

## Phase0：运行时收敛与契约冻结

### 2.1 静态契约扫描（P0）

```bash
# 重复定义扫描（重点模块）
rg -n "^\s*def (_get_action_for_decision_type|initialize_with_categories_only|discover_category_only|_process_storage_batch|_update_storage_stats)\b" \
  database_service/streams/handlers/theme_processor.py \
  theme_service/services/theme_service.py \
  database_service/streams/handlers/news_stream_handler.py

# 生产路径 print/traceback 扫描
rg -n "\bprint\(|traceback\.print_exc\(" \
  database_service/streams/handlers \
  database_service/streams/schedulers \
  theme_service
```

通过判定：
- 重复定义计数=0。
- 生产路径 `print/traceback.print_exc` 计数=0（测试脚本目录可例外）。

### 2.2 Stream 序列化契约测试（P0）

```bash
pytest -q database_service/tests/streams/test_message_serializer.py
pytest -q database_service/tests/streams/test_stream_config.py
```

通过判定：
- 两个用例文件全部通过。

---

## Phase1：路由统一与幂等执行

### 2.3 Stream 重试与集成链路（P0/P1）

```bash
pytest -q database_service/tests/streams/test_retry_manager.py
pytest -q database_service/tests/streams/test_retry_manager_integration.py
pytest -q database_service/tests/streams/test_stream_integration.py
```

### 2.4 DecisionExecutor 参数与执行路径验证（P0）

```bash
python test_fixed_decision_executor.py
```

通过判定：
- 幂等/重试链路测试通过。
- DecisionExecutor 参数提取检查通过，未知操作不可静默跳过。

---

## Phase2：动态阈值与候选治理

### 2.5 语义匹配器测试（P0）

```bash
# T01 算法级门禁（MUST，三档口径）
PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_semantic_matcher_unit.py
PHASE2_THRESHOLD_SAMPLE=36 PHASE2_THRESHOLD_GRID_SIZE=100 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_semantic_matcher_unit.py
PHASE2_THRESHOLD_SAMPLE=30 PHASE2_THRESHOLD_GRID_SIZE=100 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_semantic_matcher_unit.py

# TC003 架构守卫（MUST）
PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_tc003_architecture_guard.py

# 任务级门禁（MUST）
/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py

# 缓存复用守卫（MUST）
/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_semantic_embedding_cache_unit.py

# 算法专项补充（SHOULD，建议在 theme_matcher_env）
/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/test_semantic_matcher.py
/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/test_transformer_matcher.py
```

### 2.6 10% 灰度与 30 案例评估入口（P0）

```bash
# 数据集快速检查（选项11）
printf "11\n" | /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/test_theme_processor.py

# 新架构+数据集完整工作流（选项9）
printf "9\n" | /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/test_theme_processor.py

# 映射审计（全量读取 decision 流）
/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/phase2_update_mapping_audit.py --sample-size 24 --out /Users/admin/Desktop/ai_theme_app/tmp/phase2_update_mapping_audit.json
```

通过判定：
- phase2行为测试文件执行完成（task级门禁可回放）。
- 输出包含候选治理与数据集评估结果。
- 评估报告可用于 `theme_count/precision/completeness/separation` 三方对比。

---

## Phase3：LLM 裁判灰度集成

### 2.7 裁判链路验证（P0/P1）

```bash
# 本地 llama 裁判链路（若具备模型文件）
python test_llm_theme_judge_batch.py
```

### 2.8 真实模型证据检查（P0）

```bash
# 执行正式评估后，检查报告或日志中的真实调用字段
rg -n "source_type|model_name|request_id|timestamp|DeepSeek" \
  evaluate_service/data/results \
  evaluate_service/results \
  logs
```

通过判定：
- 有可审计模型调用证据。
- `source_type=real` 证据可追溯。

---

## Phase4：回放安全与发布门禁

### 2.9 回放一致性与门禁检查（P0）

```bash
# 轻量阶段回归入口
python database_service/tests/run_phase1_tests.py

# 汇总门禁字段证据
rg -n "replay_consistency|dead_letter_rate|backlog_minutes|issues_closed_ratio|release_gate|blocked" \
  test_results \
  evaluate_service/data/results \
  evaluate_service/results
```

通过判定：
- 回放一致率=100%。
- 门禁指标全部满足且无 `blocked=true` 放行情况。

---

## 3. 一键执行建议（从严顺序）

```bash
cd /Users/admin/Desktop/ai_theme_app

# Phase0
pytest -q database_service/tests/streams/test_message_serializer.py
pytest -q database_service/tests/streams/test_stream_config.py

# Phase1
pytest -q database_service/tests/streams/test_retry_manager.py
pytest -q database_service/tests/streams/test_retry_manager_integration.py
pytest -q database_service/tests/streams/test_stream_integration.py
python test_fixed_decision_executor.py

# Phase2
PHASE2_THRESHOLD_SAMPLE=24 PHASE2_THRESHOLD_GRID_SIZE=80 /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_semantic_matcher_unit.py
PHASE2_TC003_MODE=arch_guard /opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_tc003_architecture_guard.py
/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_phase2_behavior_tests.py
/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest -q /Users/admin/Desktop/ai_theme_app/database_service/tests/streams/test_semantic_embedding_cache_unit.py
/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/test_semantic_matcher.py
/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/test_transformer_matcher.py
printf "11\n" | /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/test_theme_processor.py
printf "9\n" | /opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/test_theme_processor.py
/opt/miniconda3/envs/theme_matcher_env/bin/python /Users/admin/Desktop/ai_theme_app/database_service/scripts/phase2_update_mapping_audit.py --sample-size 24 --out /Users/admin/Desktop/ai_theme_app/tmp/phase2_update_mapping_audit.json

# Phase3
python test_llm_theme_judge_batch.py

# Phase4
python database_service/tests/run_phase1_tests.py
```

---

## 4. 结果记录模板（建议）

每条命令记录：
- 命令
- 开始/结束时间
- 退出码
- 报告路径
- 验收映射（ACC / TC ID）

建议输出文件：
- `test_results/p1_exec_log_YYYYMMDD_HHMMSS.md`

---

## 5. 失败即阻断规则

以下任一命中，停止后续发布流程：
- 任一 P0 命令非 0 退出。
- 缺少 `source_type=real` 证据。
- 缺少 30 案例指标输出（`theme_count/precision/completeness/separation`）。
- 发现 `release_gate` 结果与阈值不一致。
