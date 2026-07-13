# Active Capital Methodology Audit

PR: PR4.2.24a Active Capital Methodology Audit  
Status: Audit Only  
Frozen Date: 2026-07-13

## 1. Decision

`capital.active_amount` must represent analyst-style short-term active capital.
It must not be treated as:

- all-market turnover
- a fixed multiplier of limit-up pool turnover
- a frontend display unit conversion

The current `2.04` multiplier is a historical calibration artifact. It is not a
fact source and must not be used as the permanent active-capital methodology.

## 2. Analyst Truth Source

Source document:

`docs/architecture/7月9日复盘_DeepSeek完整结构版.md`

Section 7, "活跃资金成交量", gives the analyst reference series:

| Date | Analyst active capital, 亿 |
| --- | ---: |
| 2026-06-25 | 2823 |
| 2026-06-26 | 1843 |
| 2026-06-29 | 2253 |
| 2026-06-30 | 2882 |
| 2026-07-01 | 2279 |
| 2026-07-02 | 1146 |
| 2026-07-03 | 2122 |
| 2026-07-06 | 1280 |
| 2026-07-07 | 897 |
| 2026-07-08 | 739 |
| 2026-07-09 | 2707 |

For 2026-07-09, the business truth target for active capital is `2707亿`, not
`5058.28亿`.

## 3. Current System Chain

Current implementation:

```text
ths_hot_reason_snapshot
  -> join stock_daily_snapshot.amount
  -> limit-up pool turnover
  -> multiply by fixed 2.04 calibration factor
  -> MarketMetricsSnapshot.capital.active_limitup_amount_yi
  -> active_capital chart
  -> draft_context.capital_state.active_amount
  -> ReviewDocument.capital.active_amount
```

Current 2026-07-09 DB evidence:

| Metric | Value |
| --- | ---: |
| THS limit-up rows | 75 |
| THS distinct stock codes | 75 |
| limit-up pool raw turnover | 2479.55亿 |
| current fixed multiplier | 2.04 |
| current system active amount | 5058.28亿 |
| analyst active amount | 2707亿 |
| implied analyst factor | 1.092 |

The `2.04` factor matches some prior days better than 2026-07-09, but the factor
varies materially by date. A constant multiplier is therefore not a stable
source-owner contract.

## 4. Field Definitions

Future ReviewDocument and MarketMetrics naming must keep these concepts
separate:

| Field | Definition | Unit | Source owner |
| --- | --- | --- | --- |
| `market_turnover` | all-market turnover | 亿 | market metrics / market breadth source |
| `limit_up_pool_turnover` | turnover of structured limit-up pool | 亿 | THS limit-up snapshot + stock daily amount |
| `active_capital` | analyst-style short-term active capital estimate | 亿 | `ActiveCapitalProducer` |
| `active_capital.components[]` | component-level contribution and source | 亿 | `ActiveCapitalProducer` |
| `active_capital.confidence` | quality of the estimate | 0-1 | `ActiveCapitalProducer` |
| `active_capital.method` | versioned model name | string | `ActiveCapitalProducer` |

`capital.active_amount` may remain a backward-compatible alias only after the
producer clearly states it maps to `active_capital.value_yi`.

## 5. Target Producer Contract

Future owner:

```text
ActiveCapitalProducer
  inputs:
    - limit_up_snapshot
    - strong_stock_watch_history
    - theme_strength_snapshot
    - market_turnover
  output:
    - active_capital.value_yi
    - active_capital.components[]
    - active_capital.confidence
    - active_capital.method
```

Candidate output:

```json
{
  "value_yi": 2707,
  "method": "weighted_activity_model.v1",
  "confidence": 0.82,
  "components": [
    {
      "source": "limit_up_pool",
      "amount_yi": 2479.55
    },
    {
      "source": "strong_stock_pool",
      "amount_yi": null,
      "quality": "MISSING"
    }
  ]
}
```

The model may use a calibrated weighting strategy, but it must expose
components, method, and confidence. A hidden fixed multiplier is forbidden.

## 6. Capital Trend Source Ownership

`trend_series.capital` is currently labeled as active capital in the UI, but the
current trend builder writes:

```text
trend_series.capital[].amount = total_turnover_yi / 10000
```

That is all-market turnover in 万亿. It is not the analyst "活跃资金成交量" series
in 亿. This is a source ownership mismatch and must be fixed in a separate PR:

`PR4.2.24b Capital Trend Source Fix`

Target direction:

```text
trend_series.capital[].value = active_capital.value_yi
trend_series.capital[].unit = "yi"
trend_series.capital[].metric = "active_capital"
```

The schema change is not part of PR4.2.24a.

## 7. Golden Replay Implications

Current golden assertions contain:

```yaml
capital.active_amount = 5058.28
market.up_count = 3561
market.down_count = 1609
```

These values are not aligned with the analyst report:

- analyst active capital for 2026-07-09 is `2707亿`
- analyst market up ratio for 2026-07-09 is `0.46`
- current regenerated `2357 / (2357 + 2642) = 0.471`
- old golden `3561 / (3561 + 1609) = 0.689`

Therefore, Golden Replay must be treated as stale for these fields until the
business truth source is re-frozen. Do not "fix" production code to match stale
golden values.

## 8. Forbidden Paths

The following paths are forbidden:

```text
limit_up_pool_turnover
  -> fixed_factor(2.04)
  -> active_capital
```

```text
market_turnover
  -> active_capital
```

```text
trend_series.capital
  -> total_turnover_yi / 10000
```

```text
frontend display formatting
  -> active_capital correction
```

```text
stale golden value 5058.28
  -> production truth
```

## 9. Non-Goals

- No production code change.
- No frontend change.
- No ReviewDocument schema change.
- No Golden baseline edit.
- No replacement active-capital formula in this audit PR.
- No change to market power score in this audit PR.

## 10. Follow-Up PRs

| PR | Purpose | Scope |
| --- | --- | --- |
| PR4.2.24b | Capital Trend Source Fix | use active capital instead of total turnover |
| PR4.2.24c | Market Power Score Audit | compare report composite score 6 vs system score 0 |
| PR4.2.24d | ActiveCapitalProducer Design | freeze model components and confidence contract |
