# v2.8a Strategy Lab 验收报告

> 验收日期: 2026-05-28
> 验收人: Claude Code
> 版本: v2.8a (implemented → acceptance)

## 验收结论: ✅ PASS (3/3)

---

## 验收用例 1: 复刻 v2.0 baseline

**参数**:
```
hold_days: 5
position_pct: 0.10
max_daily_buys: 3
max_positions: 10
support_types: [previous_low]
min_support_strength: 0
exit_rule: fixed_hold
signal_source: w2s_signal_validation_v1_1b
```

**结果对比**:

| 指标 | v2.0 baseline | v2.8a run | 偏差 |
|------|-------------|-----------|------|
| Total Return | +33.05% | +33.05% | 0.00% ✅ |
| Max Drawdown | 2.63% | 2.63% | 0.00% ✅ |
| Win Rate | 59.2% | 59.2% | 0.00% ✅ |
| Profit Factor | 3.10 | 3.10 | 0.00 ✅ |
| Trade Count | 49 | 49 | 0 ✅ |

**run_id**: `lab_20260528172043_2365f4`

**结论**: ✅ 完全匹配 v2.0 frozen baseline

---

## 验收用例 2: 重复运行一致性

**方法**: 同一参数组连续运行两次

| 指标 | Run 1 | Run 2 | 一致? |
|------|-------|-------|-------|
| Total Return | +33.05% | +33.05% | ✅ |
| Max Drawdown | 2.63% | 2.63% | ✅ |
| Win Rate | 59.2% | 59.2% | ✅ |
| Profit Factor | 3.10 | 3.10 | ✅ |
| Trade Count | 49 | 49 | ✅ |
| Equity Points | 35 | 35 | ✅ |
| Trade Records | 49 | 49 | ✅ |
| All equity values | — | — | ✅ |

**run_id_1**: `lab_20260528172201_e5d981`
**run_id_2**: `lab_20260528172214_799b98`

**结论**: ✅ Runner 完全确定性，无排序不稳定或随机因素

---

## 验收用例 3: 只读约束

| 生产表 | 行数 | 被写入? |
|--------|------|---------|
| `w2s_signal_validation_v1_1b` | 197 | ❌ 未修改 |
| `w2s_candidate_rebuild` | 226 | ❌ 未修改 |
| `weak_to_strong_candidate_pool` | 1895 | ❌ 未修改 |

| 回测表 | 新写入 |
|--------|--------|
| `backtest_run` | 3 rows |
| `backtest_equity_curve` | 105 rows |
| `backtest_trade` | 147 rows |
| `backtest_monthly_return` | 9 rows |

**结论**: ✅ 只写 backtest_* 表，未修改任何生产表、UseCase、候选池

---

## 通用检查项

| 检查项 | 状态 |
|--------|------|
| 不重新生成 A/B/C/D 候选 | ✅ runner 只读 `w2s_signal_validation_v1_1b` |
| 不调用 StrongStockTrackingService | ✅ |
| 不调用 BuildWeakToStrongCandidateUseCase | ✅ |
| 不修改 UseCase 阈值 | ✅ |
| `param_set_id` 写入 backtest_run | ✅ |
| `config_json` 写入 backtest_run | ✅ |
| `signal_source` 写入 backtest_run | ✅ |
| `source_chain` 写入 backtest_run | ✅ |
| `strategy_param_set` 表存在 | ✅ |

---

## 版本标记

```
v2.8a: ACCEPTED → FROZEN
```

下一步: v2.8b small-grid search (建议 support_strength × hold_days × position_pct × max_daily_buys × exit_rule = 72 组)
