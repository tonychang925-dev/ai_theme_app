# Phase 4.5.6 Formal Review Stabilization Report

## 1. 基本信息

- Milestone: `Phase 4.5.6`
- PR: `PR5 Formal Review Stabilization`
- 测试负责人: `Codex`
- 执行时间: `2026-07-11`
- 风险等级: `Medium`

## 2. 测试范围

覆盖模块：

- `FormalReviewProjectionCompiler`
- `formal_review` 六章模型
- `FormalReviewView`
- Recap Workbench First 契约

覆盖功能点：

- 六章 schema 稳定性。
- 2026-07-09 Projection Diff 黄金样本。
- 五类代表性市场状态的 projection 稳定性：
  - 主线明确日
  - 多题材轮动日
  - 退潮日
  - 图表数据降级日
  - 无 Approved Snapshot 场景
- 前端只读 `formal_review`。

未覆盖范围：

- 尚未完成 5 个真实交易日的 approved snapshot 双轨人工观察。
- 尚未统计真实 96 字段全量 coverage 比例。
- 尚未执行 PR6 Legacy Removal。

## 3. 执行命令记录

| 序号 | 命令 | 执行结果 | 关键输出 |
|---|---|---|---|
| 1 | `/opt/miniconda3/envs/theme_matcher_env/bin/python -m pytest stock_processing_service/tests/unit/test_projection_stabilization_scenarios.py stock_processing_service/tests/unit/test_projection_formal_schema.py stock_processing_service/tests/unit/test_projection_diff_20260709.py stock_processing_service/tests/unit/test_projection_capital_plan.py stock_processing_service/tests/unit/test_projection_theme_stock_merge.py -q` | 通过 | `17 passed in 0.41s` |
| 2 | `node scripts/test-formal-review-view-contract.mjs` | 通过 | `formal review view contract passed` |
| 3 | `node scripts/test-recap-workbench-first-contract.mjs` | 通过 | `recap workbench-first contract passed` |
| 4 | `node scripts/test-workbench-generate-flow-contract.mjs` | 通过 | `workbench generate flow contract passed` |
| 5 | `npm run build` | 通过 | `✓ built`；仅 Vite chunk size warning |

## 4. 测试结果统计

| 项目 | 数值 |
|---|---:|
| 自动化后端用例 | 17 |
| 前端契约脚本 | 3 |
| 前端构建 | 1 |
| 通过数 | 21 |
| 失败数 | 0 |
| 跳过数 | 0 |
| 通过率 | 100% |

## 5. 五场景稳定性结论

| 场景 | 覆盖目的 | 结果 |
|---|---|---|
| clear_mainline | 主线明确日，验证主题/股票/资金正常路径 | PASS |
| multi_theme_rotation | 多题材轮动日，验证主题实体不丢 | PASS |
| fade_day | 退潮日，验证弱 watch/风险状态可编译 | PASS |
| degraded_chart_data | 图表数据降级日，验证缺少 chart facts 时不崩溃 | PASS |
| no_approved_snapshot | 无 Approved Snapshot，验证 preview/空情绪路径稳定 | PASS |

## 6. 真实交易日观察状态

当前本地可见运行态：

- `tmp/analyst_workbench/2026-07-07/session.json`
- `tmp/analyst_workbench/2026-07-08/session.json`
- `tmp/analyst_workbench/2026-07-09/session.json`
- `tmp/analyst_workbench/2026-07-10/session.json`

限制：

- 当前仅发现 `2026-07-09` 历史备份中存在 `snapshot.json`。
- 现有运行态不足 5 个完整 approved snapshot。
- 因此不能宣称“真实 5 交易日观察完成”。

结论：

- 自动化稳定性测试：`PASS`
- 真实 5 交易日双轨观察：`INCOMPLETE`
- PR6 Legacy Removal：`BLOCKED`

## 7. 缺陷记录

| 缺陷ID | 严重级别 | 描述 | 当前状态 |
|---|---|---|---|
| P456-PR5-001 | P2 | 本地缺少 5 个完整 approved snapshot，无法完成真实多交易日观察 | 待补真实交易日数据 |

## 8. 风险评估

当前残余风险：

- 技术风险：低。FormalReview v1 schema、projection diff、前端契约均通过。
- 数据一致性风险：中。尚未用 5 个真实 approved snapshot 覆盖多交易日。
- 可扩展性风险：中。PR6 删除 legacy 前必须确认没有语义字段遗漏。
- 性能风险：低。本阶段没有新增重计算或接口链路，仅增加 projection 展示与测试。

风险等级：`Medium`

理由：

- 自动化稳定性已通过，但真实交易日观察未完成。
- 不建议进入 PR6。

## 9. 发布建议

- ✅ PR5 自动化稳定性部分建议通过。
- ❌ 不建议启动 PR6 Legacy Removal。

下一步：

1. 使用真实 approved snapshots 补齐不少于 5 个交易日双轨观察。
2. 生成 Coverage Report / Missing Semantic Report / User Reading Report。
3. 观察稳定后再进入 PR6 legacy 字段和旧组件移除。

PR6 准入跟踪文件：

- `docs/test_reports/formal_review_legacy_coverage.md`
- `docs/test_reports/formal_review_observation_log.md`
