# Active Capital Source Audit

PR: PR4.2.28a Active Capital Source Audit  
Status: Audit Only  
Frozen Date: 2026-07-13

## 1. Decision

Prioritize `capital.active_amount` before broader Capital Intelligence work.
This field is a fact-model problem, not an AI cognition-calibration problem.

For 2026-07-09:

| Metric | Value |
| --- | ---: |
| Current ReviewDocument `capital.active_amount` | 5058.28 亿 |
| Analyst truth | 2707 亿 |
| Absolute error | 2351.28 亿 |
| Relative error | 86.86% |

The current value is not acceptable as a production truth target.

## 2. Analyst Source Definition

Primary source:

`docs/architecture/7月9日复盘.md`

The analyst report defines active capital in section "图 8：活跃资金成交量表":

| Field | 2026-07-09 |
| --- | ---: |
| 中午：今日所有涨停及触及涨停个股成交量之和 | 591 亿 |
| 中午：昨日所有涨停及触及涨停个股的今日成交量之和 | 730 亿 |
| 下午：今日所有涨停及触及涨停个股成交量之和 | 2707 亿 |
| 下午：昨日所有涨停及触及涨停个股的今日成交量之和 | 969 亿 |

The displayed "活跃资金成交量趋势" also gives:

| Date | Analyst active capital, 亿 |
| --- | ---: |
| 2026-06-29 | 2253 |
| 2026-06-30 | 2882 |
| 2026-07-01 | 2279 |
| 2026-07-02 | 1146 |
| 2026-07-03 | 2122 |
| 2026-07-06 | 1280 |
| 2026-07-07 | 897 |
| 2026-07-08 | 739 |
| 2026-07-09 | 2707 |

Structured source:

`docs/architecture/7月9日复盘_DeepSeek完整结构版.md`

It repeats `active_capital_yi: 2707`.

## 3. Current Production Chain

Current code owner:

`stock_processing_service/application/services/market_metrics/service.py::_build_capital`

Current chain:

```text
ths_hot_reason_snapshot
  -> join stock_daily_snapshot.amount
  -> SUM(amount)
  -> normalize_to_yi(..., "qian_yuan")
  -> fixed multiplier 2.04
  -> MarketMetricsSnapshot.capital.active_limitup_amount_yi
  -> active_capital chart
  -> DraftContextBuilder.capital_state.active_amount
  -> ReviewDocument.capital.active_amount
```

Current DB evidence for 2026-07-09:

| Query Result | Value |
| --- | ---: |
| `ths_hot_reason_snapshot` rows | 75 |
| distinct THS stock codes | 75 |
| raw THS+SDS limit-up pool amount | 2479.55 亿 |
| fixed multiplier | 2.04 |
| current active amount | 5058.28 亿 |
| analyst active amount | 2707 亿 |
| implied analyst factor vs THS+SDS pool | 1.092 |

The current factor was calibrated from prior dates and is not stable enough for
daily truth. For 2026-07-09 it overstates active capital by 86.86%.

## 4. Candidate Source Inventory

### 4.1 Limit-Up / Touch-Limit Pool

Owner candidates:

- `ths_hot_reason_snapshot`
- `stock_daily_snapshot`
- future `a-stock-data` board-pool adapter

Current availability:

| Source | 2026-07-09 Status | Notes |
| --- | --- | --- |
| `ths_hot_reason_snapshot` | available, 75 rows | Captures THS hot-reason rows, but appears to represent a narrower sealed/hot-reason set than analyst "所有涨停及触及涨停". |
| `stock_daily_snapshot.amount` | available | Used for turnover join; unit currently normalized through `qian_yuan`. |
| `subject_stock_daily_snapshot.limit_up` | available | Has 1139 subject-stock limit-up rows, but duplicates stocks across themes. Distinct stock sum is 149 stocks / 4979.45 亿, which is too broad without board-pool semantics. |
| `BoardPoolProvider` / Eastmoney `zt_pool` | code exists | Better source shape for true board pool, but not currently the owner of `MarketMetricsSnapshot.capital`. |

Conclusion:

The producer should not continue using a hidden multiplier. It needs an explicit
pool source contract that distinguishes:

- sealed limit-up pool
- touched/fried board pool
- yesterday limit-up pool today turnover
- duplicate subject membership rows

### 4.2 Strong Stock Pool

Owner candidate:

`strong_stock_watch_history`

Current DB evidence:

| Metric | Value |
| --- | ---: |
| rows | 15 |
| named rows | 9 |
| distinct subjects | 4 |

Strength:

- Useful as an activity component and high-attention filter.
- Contains `relay_role`, `watch_score`, `pool_entry_type`, and evidence JSON.

Limitation:

- No direct turnover field. It needs a join to stock turnover data before it can
contribute amount components.
- Independent leader rows are valid activity evidence but may lack theme identity.

### 4.3 Theme / Subject Activity

Candidate sources:

- `theme_strength_snapshot`
- `subject_daily_feature`
- `subject_stock_daily_snapshot`
- `theme_capital_flow` concept from recap/report context

Current DB evidence for 2026-07-09:

| Source | Rows | Notes |
| --- | ---: | --- |
| `theme_strength_snapshot` | 0 | Not available for this date. Cannot be PR4.2.28b dependency. |
| `subject_daily_feature` | 0 | Not available for this date. Cannot be PR4.2.28b dependency. |
| `subject_stock_daily_snapshot` | 31629 | Available, but subject-stock rows duplicate stocks across themes. Must deduplicate by stock before amount aggregation. |
| `theme_capital_flow` | no standalone table verified | It exists as recap/report-context concept in tests and docs, but this audit found no concrete production amount table owner to use for PR4.2.28b. |

Conclusion:

`subject_stock_daily_snapshot` can support theme distribution and evidence, but
it is not a clean amount source unless the producer deduplicates stocks and
separates "amount attribution" from "theme attribution".

`theme_capital_flow` must not be used as the active-capital amount owner until
there is a concrete persisted table/API contract with amount units, dedupe
rules, and date completeness guarantees.

### 4.4 Dragon Tiger / Seat Money

Candidate sources:

- `dragon_tiger_object`
- `hot_money_trading_activity`
- `post_market_recap_snapshot.recap_doc.seat_money_summary`

Current DB evidence:

| Source | 2026-07-09 Status |
| --- | --- |
| `dragon_tiger_object` | 0 rows |
| `hot_money_trading_activity` | 0 rows |
| `seat_money_summary.diagnostics.source` | `none` |
| `institution_buy_rows` | empty |
| `hot_money_buy_rows` | empty |

Conclusion:

龙虎榜 should remain evidence enhancement only. It cannot be the base active
capital producer for 2026-07-09.

### 4.5 Recap Hotspot Subjects

Source:

`post_market_recap_snapshot.payload.recap_doc.strong_hotspot_subjects`

Current DB evidence:

| Metric | Value |
| --- | ---: |
| latest recap snapshot rows | 1 |
| `strong_hotspot_subjects` count | 77 |

Strength:

- Good source for topic classification and Capital Intelligence evidence.

Limitation:

- It is not an amount source by itself.
- It should not directly output `active_amount`.

## 5. Target ActiveCapitalProducer Contract

The next implementation PR should introduce an explicit producer contract:

```json
{
  "active_capital": {
    "value_yi": 2707,
    "method": "active_capital.v1",
    "confidence": 0.85,
    "components": [
      {
        "name": "today_limit_touch_pool",
        "amount_yi": 2707,
        "source": "board_pool",
        "quality": "OK"
      },
      {
        "name": "yesterday_limit_pool_today_turnover",
        "amount_yi": 969,
        "source": "board_pool",
        "quality": "OK"
      },
      {
        "name": "strong_stock_pool",
        "amount_yi": null,
        "source": "strong_stock_watch_history + stock_daily_snapshot",
        "quality": "CANDIDATE"
      },
      {
        "name": "dragon_tiger_evidence",
        "amount_yi": null,
        "source": "dragon_tiger_object",
        "quality": "MISSING"
      }
    ],
    "diagnostics": {
      "forbidden_multiplier_used": false,
      "dedupe_key": "stock_id",
      "unit": "yi"
    }
  }
}
```

Backward compatibility:

```text
ReviewDocument.capital.active_amount
  = active_capital.value_yi
```

This keeps the current UI contract stable while making the source model auditable.

## 6. PR4.2.28b Implementation Boundary

Allowed:

- Add `ActiveCapitalProducer` or equivalent adapter under the market metrics /
  analyst workbench source layer.
- Replace the fixed `2.04` multiplier path.
- Add contract tests for component output and `2026-07-09 -> 2707`.
- Preserve `ReviewDocument.capital.active_amount` as a scalar alias.

Forbidden:

```text
limit_up_pool_turnover
  -> fixed_factor(2.04)
  -> active_capital
```

```text
theme_capital_flow
  -> active_amount
```

```text
money_flow_enhanced.role_label
  -> institution/hot_money/active_amount
```

```text
dragon_tiger rows missing
  -> inferred hot_money amount
```

```text
frontend formatting
  -> active amount correction
```

```text
date == 2026-07-09
  -> hardcoded 2707
```

## 7. Open Questions for PR4.2.28b

1. Which concrete board-pool source can provide both sealed and touched/fried
   stocks with turnover for historical dates?
2. Is `ths_hot_reason_snapshot` intended to represent sealed limit-up only, or
   can it be expanded to touched/fried board rows?
3. Should `subject_stock_daily_snapshot` be used only for theme attribution after
   amount deduplication, or excluded from the amount model entirely?
4. Should the analyst reference values from markdown ingestion be used as a
   calibration dataset for model training, but never as same-day production
   fallback?

## 8. Recommendation

Proceed to `PR4.2.28b Active Capital Producer` only after selecting the concrete
board-pool owner.

Minimum acceptable v1:

```text
board_pool today's limit/touch amount
  -> active_capital.value_yi
  -> components[]
  -> confidence
  -> ReviewDocument.capital.active_amount
```

If the exact touched-board historical pool is unavailable, the producer must
return a structured degraded result rather than reintroducing the `2.04`
multiplier.
