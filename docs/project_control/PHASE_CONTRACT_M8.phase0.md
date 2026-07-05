# Phase Execution Contract — M8.phase0

## 1. Phase Identity

- Phase Name: Cognition Homepage
- Phase Code: `M8.phase0`
- Parent Milestone: M8 Market Cognition
- Risk Level: `P0`
- Source Documents:
  - `docs/project_control/PRD.md`
  - `docs/project_control/prd_p1.md`
  - `docs/project_control/prd_p2.md`
  - `docs/project_control/prd_p3.md`
  - `docs/project_control/prd_p4.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/project_control/ACCEPTANCE_P4.phase0.md`
  - `docs/project_control/P4_PHASE0_INTERACTION_ACCEPTANCE.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ARCH_REVIEW.md`
  - `docs/adrs/ADR_LIST.md`
  - `docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md`

## 2. Phase Objective

基于已有盘后快照生成可回放的 Market Thesis 首页，保持 DailyReviewV2、正式 Decision 与原 Notion 证据章节零破坏。

## 3. Acceptance Targets

- [ ] `ACPT-M8P0-001` Bundle 只汇聚现有 producer 输出且 lineage/quality/hash 完整。
- [ ] `ACPT-M8P0-002` 判断性 EvidenceRef 覆盖率 100%，缺失不伪装零值。
- [ ] `ACPT-M8P0-003` Context/Cognition/Thesis 确定性且 Hypothesis 可证伪。
- [ ] `ACPT-M8P0-004` Shadow replay hash 一致、Decision diff 为 0、无基础设施反向依赖。
- [ ] `ACPT-M8P0-005` Notion 三模式、双层顺序和失败回退符合契约。
- [ ] `ACPT-M8P0-006` 七日 replay 无状态码、unsupported claim、重复核心章节和未来泄漏。

## 4. Required Commands

- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_knowledge_evidence.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_cognition.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_m8_phase0_notion_dual_layer.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/integration/test_m8_phase0_replay.py`
- `.venv/bin/python -m pytest -q stock_processing_service/tests/unit/test_post_market_daily_review_v2_builder.py stock_processing_service/tests/unit/test_notion_post_market_recap_publisher.py`

## 5. Deliverables

- `stock_processing_service/contracts/market_cognition.py`
- `stock_processing_service/application/services/market_cognition/`
- `stock_processing_service/publishers/notion_post_market_report_renderer.py`
- `stock_processing_service/publishers/notion_post_market_recap_publisher.py`
- `stock_processing_service/tests/unit/test_m8_phase0_*.py`
- `stock_processing_service/tests/integration/test_m8_phase0_replay.py`
- `docs/project_control/reports/phase-M8.phase0.md`

## 6. Risk Matrix

| Risk | Impact | Likelihood | Trigger | Owner | Mitigation |
|---|---|---|---|---|---|
| Snapshot schema drift | High | High | Adapter 遇到未知/缺失字段 | M8 Owner | coverage/quality + fail closed |
| Legacy report regression | High | Medium | 旧标题/区块减少 | Notion Owner | legacy_only baseline + regression |
| Unsupported thesis | High | Medium | 命题无 EvidenceRef | QA/Risk | 构建时拒绝命题 |
| Scope leakage | High | Medium | 引入 Adaptive 对象 | Architect | Scope gate 阻断 |

## 7. Rollback Plan

- 代码回滚：撤销 M8 新模块和 renderer 最小接入。
- 数据回滚：无 schema 变更；保留只读 replay 产物，不删除现有 snapshot。
- 同步补偿回滚：Notion 设置 `M8_NOTION_RENDER_MODE=legacy_only`，重新发布旧报告。
- 触发条件：任一 P0 验收失败、旧证据章节减少、正式 Decision 漂移或 unsupported claim > 0。

## 8. Non-Goals

- World Model 自动学习、Goal、Attention、多策略、Counterfactual、Self Reflection、Episodic Retrieval。
- DailyReviewV3、自动交易、8002/8003。

## 9. Conflict Resolution

| 冲突项 | 采用来源 | 放弃来源 | 理由 |
|---|---|---|---|
| Phase 0 分期范围 | Overall Architecture v4.0 | M8 v1.3 早期 Phase 0 | v4.0 是冻结 Baseline |
| 报告演进方式 | Adapter + Dual Layer | Rewrite | 遵循 Adapter over Rewrite |

## 10. Execution Governance

- 状态同步顺序：`Doing -> test-evidence -> In review/done -> milestone progress`。
- P0/P1 写入 `In review/done` 必须传当前 diff 中的 `--test-files`。
- 阶段末必须按 `--milestone-id` 全量拉取并本地筛选 M8.phase0。
- 统一约束：`docs/project_control/EXECUTION_GUARDRAILS.md`。
