# Phase Execution Contract

## 1. Phase Identity

- Phase Name: OneToTwo 盘后观察清单回测与算法校准
- Phase Code: P5.phase2.6
- Parent Milestone: P5（1进2买入法）
- Risk Level: High
- Source Documents:
  - `docs/architecture/one_to_two_daily_review_architecture.md`
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ACCEPTANCE.md`
  - `docs/adrs/ADR_LIST.md`

## 2. Phase Objective（可量化）

1. 用历史交易日重放 `OneToTwoSetupPlanEngine`，冻结 `post_market_setup_plan` / `one_to_two_candidate_feature` / `strategy_signal_daily` / `strategy_signal_validation` 的统一回测链路。
2. 完成 OneToTwo 盘后观察清单的可回放、可审计、可对账能力，且不引入未来函数。
3. 对 `focus / observe_only / pending_review_only / reject` 四类分层做统计验证，确认空结果为正常样本。
4. 产出按 `decision / market_regime / reject_reason / score_bucket` 分层的回测汇总报告。

## 3. Acceptance Targets（门禁条件）

- [ ] 回测仅使用 T 日及以前事实，不得读取 T+1/T+n 数据参与候选生成。
- [ ] `post_market_setup_plan` 必须可回放，且 `__SUMMARY__` 行唯一。
- [ ] `one_to_two_candidate_feature` 必须保留 reject 审计，且 reject 行必须有非空 `veto_reasons`。
- [ ] `strategy_signal_daily` 只能从 `focus / observe_only / pending_review_only` 生成，不得输出 buy 语义。
- [ ] `strategy_signal_validation` 必须产出 T+1 二板触达/封板/炸板/失败等 outcome label。
- [ ] 审计对账脚本必须通过，且 buy / must_buy / recommend_buy 不得出现在回测数据中。

## 4. Required Commands（必须执行命令）

- `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_setup_plan_audit.py -q`
- `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_setup_plan_persistence_contract.py -q`
- `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_one_to_two_setup_plan_engine.py -q`
- `./scripts/check_one_to_two_setup_plan_audit.sh --trade-date 2026-06-04`
- `.venv/bin/python -m pytest stock_processing_service/tests/unit/test_daily_review_watchlists_api.py stock_processing_service/tests/unit/test_daily_review_v2_one_to_two_watchlists.py -q`

## 5. Deliverables

- 新增回测/校准服务：
  - `stock_processing_service/application/services/backtest/one_to_two_*`
- 新增或复用回测表：
  - `post_market_setup_plan`
  - `one_to_two_candidate_feature`
  - `strategy_signal_daily`
  - `strategy_signal_validation`
- 新增审计脚本：
  - `scripts/check_one_to_two_setup_plan_audit.sh`
  - `scripts/check_one_to_two_setup_plan_audit.py`
- 新增测试：
  - `stock_processing_service/tests/unit/test_one_to_two_setup_plan_audit.py`
  - `stock_processing_service/tests/unit/test_one_to_two_setup_plan_persistence_contract.py`
- 文档更新：
  - `docs/project_control/PLAN_WBS.md`
  - `docs/project_control/ACCEPTANCE.md`

## 6. Risk Matrix

| Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- |
| 未来函数污染历史回放 | High | Medium | 强制 T 日冻结快照，验证阶段仅读 T+1/T+n |
| reject 审计丢失 | High | Medium | reject 行强制落库并要求 veto_reasons 非空 |
| 回测孤岛化 | Medium | Medium | 复用统一 strategy_* 回测链路，不另起炉灶 |
| 空结果误判为失败 | Medium | Medium | 明确 empty_is_valid，并保留 summary 行 |
| 信号语义漂移为 buy | High | Low | 回测阶段只允许 long_watch，不允许 buy tokens |

## 7. Rollback Plan

- 回滚方式：
  - 回滚 OneToTwo 回测服务代码提交，保留生产 OneToTwo 计划层不变。
- 数据恢复策略：
  - 删除对应 `run_id` 的回测快照、信号、验证记录即可重新重放。
- 同步补偿回滚：
  - 若回测字段扩展影响报表展示，则回退到只读计划层视图，不影响 `post_market_setup_plan`。

## 8. Non-Goals

- 不进入盘前竞价确认。
- 不进入盘中二板触发确认。
- 不做自动交易执行。
- 不读取 Layer C / D1 作为回测候选源。
- 不在回测脚本中手写 1进2 规则。

