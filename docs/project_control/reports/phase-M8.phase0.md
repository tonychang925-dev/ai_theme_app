# M8.phase0 阶段报告 — Cognition Homepage

## 1. 目标与范围

本阶段在不改变 Layer A/B/C/D、DailyReviewV2 与正式 Decision 的前提下，建立只读认知编排链：

```text
MarketKnowledgeBundle
-> MarketEvidenceSnapshot
-> CLOSE MarketContext
-> CognitionState
-> MarketThesisSnapshot
-> Notion Dual Layer
```

已实现：

- Stable Core 契约和 canonical hash；
- DailyReviewV2/recap 实际嵌套路径 Adapter；
- 固定模板 Belief/Hypothesis/Thesis；
- 无副作用 Shadow Replay；
- Notion `legacy_only/cognition_shadow/dual_layer`；
- cognition 失败自动回退原报告；
- 七日真实快照回放。

未实现且未越界：

- World Model 学习；
- Goal/Attention；
- 多策略与正式 Decision 修改；
- Counterfactual、Self Reflection、Episodic Retrieval；
- 8002/8003。

## 2. 变更文件清单

核心实现：

- `stock_processing_service/contracts/market_cognition.py`
- `stock_processing_service/application/services/market_cognition/knowledge_evidence.py`
- `stock_processing_service/application/services/market_cognition/cognition.py`
- `stock_processing_service/application/services/market_cognition/replay.py`
- `stock_processing_service/publishers/notion_market_thesis_renderer.py`
- `stock_processing_service/publishers/notion_post_market_recap_publisher.py`

测试：

- `stock_processing_service/tests/unit/test_m8_phase0_knowledge_evidence.py`
- `stock_processing_service/tests/unit/test_m8_phase0_cognition.py`
- `stock_processing_service/tests/unit/test_m8_phase0_notion_dual_layer.py`
- `stock_processing_service/tests/integration/test_m8_phase0_replay.py`

控制文档：

- `docs/project_control/PRD.md`
- `docs/project_control/ACCEPTANCE.md`
- `docs/project_control/PLAN_WBS.md`
- `docs/project_control/PHASE_CONTRACT_M8.phase0.md`
- `docs/project_control/TEST_CASE_SPEC_M8.phase0.md`
- `docs/project_control/FEATURE_SPEC_M8.phase0.md`

## 3. 验证命令与结果

### 3.1 自动化测试

```bash
.venv/bin/python -m pytest -q \
  stock_processing_service/tests/unit/test_m8_phase0_knowledge_evidence.py \
  stock_processing_service/tests/unit/test_m8_phase0_cognition.py \
  stock_processing_service/tests/unit/test_m8_phase0_notion_dual_layer.py \
  stock_processing_service/tests/integration/test_m8_phase0_replay.py \
  stock_processing_service/tests/unit/test_post_market_daily_review_v2_builder.py \
  stock_processing_service/tests/unit/test_notion_post_market_recap_publisher.py
```

结果：`76 passed`。

### 3.2 真实七日 Replay

数据源：`stock_data_test.post_market_recap_snapshot`，只读。

交易日：

- 2026-07-03
- 2026-07-02
- 2026-07-01
- 2026-06-30
- 2026-06-29
- 2026-06-26
- 2026-06-25

结果：

| 指标 | 结果 |
|---|---:|
| Snapshot | 7 |
| Ready | 7/7 |
| 双次 replay hash 一致 | 7/7 |
| Decision unchanged | 7/7 |
| Unsupported claims | 0 |
| 核心 Thesis EvidenceRef coverage | 100% |

机读证据：`tmp/runs/20260704_081828/real_replay_summary.json`。

### 3.3 真实 Notion Preview

2026-07-03 快照以 `dual_layer` 构建：

- 总 blocks：58；
- `市场认知首页`：存在；
- 原证据章节：完整保留；
- cognition 首页位于报告标题之后、交易结论之前；
- 内部状态码：未进入认知首页。

### 3.4 静态门禁

- `compileall`：PASS；
- M8 contracts/services 禁止依赖扫描：PASS；
- `git diff --check`：PASS；
- `ruff`：仓库 `.venv` 未安装，标记 `NOT CONFIGURED`，未临时安装依赖。

## 4. 风险与限制

1. Phase 0 没有跨日持久化 Cognition State，因此“昨日假设结果”当前明确显示尚未接入；不得解释为已完成 Hypothesis Timeline。
2. Phase 0 Thesis 使用固定 policy，目标是证据可追溯和页面可读，不宣称已达到成熟分析师的跨日判断能力。
3. Notion 默认仍为 `legacy_only`；启用灰度需设置 `M8_NOTION_RENDER_MODE=cognition_shadow`，人工确认后才能切 `dual_layer`。
4. 当前工作区包含进入 Phase 0 前已有的未提交改动；本阶段未清理或重置这些文件。

## 5. 回滚

- 运行时：设置 `M8_NOTION_RENDER_MODE=legacy_only`；
- 代码：移除 M8 新模块和 publisher 的最小组合逻辑；
- 数据：无数据库 schema 或现有 snapshot 写入，无需数据回滚；
- 触发：旧证据章节减少、Decision 漂移、unsupported claim > 0、双层渲染异常。

## 6. Review Checklist

- [x] 5 个 Notion 任务均为 done
- [x] PRD/Acceptance/Phase Contract/Feature/Test Spec 完整
- [x] 测试先行证据完整
- [x] UT -> IT -> Replay/Regression 顺序通过
- [x] 真实 7 日 replay 通过
- [x] DailyReviewV2 零破坏
- [x] 默认 legacy 回滚可用
- [ ] 用户 Phase 0 验收决策
