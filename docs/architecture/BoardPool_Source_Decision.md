# BoardPool Source Decision

PR: PR4.2.28b-pre BoardPool Source Owner Decision  
Status: Audit / Decision Only  
Frozen Date: 2026-07-13

## 1. Decision

Use `eastmoney_board_pool_daily` as the persisted source owner for the
`BoardPoolSnapshot` contract.

Do not use `ths_hot_reason_snapshot` as the active-capital source owner. It can
remain a reason/evidence table, but it cannot represent the analyst definition:

```text
今日所有涨停及触及涨停个股成交量之和
```

Do not implement `ActiveCapitalProducer` until `BoardPoolSnapshot` exposes
amount-complete components for both:

- `ZT`: sealed limit-up pool
- `ZB`: touched/fried board pool

## 2. Required Contract

`BoardPoolSnapshot` must be persisted and replayable:

```yaml
board_pool:
  trade_date: date
  source: eastmoney_board_pool_daily
  unit: yi
  pools:
    zt:
      rows: int
      amount_yi: float
      amount_source: eastmoney_board_pool_daily.amount
      quality: OK | MISSING
    zb:
      rows: int
      amount_yi: float
      amount_source: eastmoney_board_pool_daily.amount
      quality: OK | MISSING
    yzt:
      rows: int
      today_amount_yi: float | null
      quality: OK | MISSING
  diagnostics:
    persisted: true
    replayable: true
    multiplier_used: false
    hardcoded_analyst_truth: false
```

`ActiveCapitalSnapshot` may consume `BoardPoolSnapshot`, but it must not query
third-party APIs directly.

## 3. Current Source Evidence

Current persisted table:

`stock_processing_service/database/migrations/create_eastmoney_board_pool.sql`

Current collector:

`stock_processing_service/scripts/collect_eastmoney_board_pool.py`

Current provider:

`stock_processing_service/application/services/market_metrics/board_pool_provider.py`

The table persists:

| Field | Meaning |
| --- | --- |
| `pool_type` | `ZT`, `ZB`, `DT`, `YZT` |
| `amount` | turnover amount from Eastmoney when available |
| `turnover` | turnover rate, not turnover amount |
| `raw_json` | raw source payload |

## 4. 2026-07-09 Evidence

`eastmoney_board_pool_daily` exists and has rows for 2026-07-09:

| Pool | Rows | Amount Rows | Amount Sum |
| --- | ---: | ---: | ---: |
| `ZT` | 75 | 75 | 2479.55 亿 |
| `ZB` | 17 | 0 | 0 亿 |
| `YZT` | 47 | 0 | 0 亿 |
| `DT` | 12 | 0 | 0 亿 |

Interpretation:

- `ZT.amount` is usable and already explains the sealed limit-up component.
- `ZB` exists as a stock set, but amount is missing in the persisted payload.
- `turnover` in `ZB` is turnover rate, not turnover amount.
- `stock_daily_snapshot.amount` has a different unit and cannot be mixed with
  Eastmoney raw `amount` without an explicit unit adapter.

For 2026-07-09:

| Metric | Value |
| --- | ---: |
| Analyst active capital | 2707 亿 |
| Eastmoney `ZT.amount` | 2479.55 亿 |
| Remaining gap | 227.45 亿 |
| Eastmoney `ZB` rows | 17 |
| Eastmoney `ZB.amount` | missing |

This is directionally consistent with the analyst definition: active capital is
larger than sealed `ZT` amount and needs touched/fried board turnover.

## 5. Historical Sanity Check

Analyst active capital compared with persisted Eastmoney `ZT.amount`:

| Date | Analyst Active, 亿 | EM `ZT.amount`, 亿 | ZB Rows | Gap, 亿 |
| --- | ---: | ---: | ---: | ---: |
| 2026-06-29 | 2253 | 1303.40 | 38 | 949.60 |
| 2026-06-30 | 2882 | 1847.19 | 26 | 1034.81 |
| 2026-07-01 | 2279 | 1130.95 | 74 | 1148.05 |
| 2026-07-02 | 1146 | 511.86 | 40 | 634.14 |
| 2026-07-03 | 2122 | 701.28 | 52 | 1420.72 |
| 2026-07-06 | 1280 | 572.76 | 41 | 707.24 |
| 2026-07-07 | 897 | 438.72 | 23 | 458.28 |
| 2026-07-08 | 739 | 347.52 | 14 | 391.48 |
| 2026-07-09 | 2707 | 2479.55 | 17 | 227.45 |

Conclusion:

`ZT.amount` is a valid component, not the final active-capital value.

## 6. Source Options

### Option A: Daily Quote Recompute

Compute board pool from full daily quotes:

```text
daily_quote
  -> limit price rule by board type
  -> high >= limit_price as touched
  -> close >= limit_price as sealed
  -> sum turnover amount
```

Strength:

- Fully replayable.
- Independent of third-party board classifications.
- Good for training data and historical backfill.

Risk:

- Requires precise limit-price rules for ST, main board, ChiNext, STAR, BSE,
  new listings, resumed trading, and rounding.
- More implementation scope than PR4.2.28b should take.

Decision:

Keep as long-term fallback/backfill strategy, not v1 owner.

### Option B: Persisted Eastmoney Board Pool

Use:

```text
eastmoney_board_pool_daily.ZT
eastmoney_board_pool_daily.ZB
eastmoney_board_pool_daily.YZT
```

Strength:

- Already persisted.
- Replayable.
- Directly models sealed and fried/touched board pools.
- Matches existing `BoardPoolProvider` architecture.

Risk:

- Current `ZB.amount` is missing.
- Current `YZT.today_amount_yi` is missing.
- The collector must either request/normalize amount for ZB/YZT or join a
  canonical quote amount adapter with explicit unit conversion.

Decision:

Use as PR4.2.28b source owner, but first fix amount completeness.

### Option C: Third-Party Runtime API Directly

Call Eastmoney/a-stock-data from `ActiveCapitalProducer` at generation time.

Decision:

Rejected for ReviewDocument generation.

Reason:

- Not replayable.
- Fails Golden Replay when API data changes or disappears.
- Reintroduces hidden external state into ReviewDocument.

## 7. PR4.2.28b Entry Criteria

Before implementing `ActiveCapitalProducer`, PR4.2.28b must satisfy:

1. `BoardPoolSnapshot` reads from persisted `eastmoney_board_pool_daily`.
2. `ZT.amount_yi` is populated from `amount` with unit `yuan -> yi`.
3. `ZB.amount_yi` is populated from a declared amount owner.
4. `YZT.today_amount_yi` is either populated or explicitly marked `MISSING`.
5. No multiplier is used.
6. No analyst markdown value is used as production input.
7. No frontend or ReviewDocument schema change is needed.

If `ZB.amount_yi` cannot be populated, the producer must return:

```yaml
quality: DEGRADED
missing:
  - board_pool.zb.amount_yi
```

It must not approximate the gap with a fixed factor.

## 8. Forbidden Paths

```text
ZT.amount
  -> fixed_factor
  -> active_capital
```

```text
ZB.turnover_rate
  -> amount_yi
```

```text
stock_daily_snapshot.amount
  -> mixed with Eastmoney amount without explicit unit adapter
```

```text
analyst_report.active_capital_yi
  -> production active_amount
```

```text
runtime Eastmoney API
  -> ReviewDocument artifact
```

```text
theme_capital_flow
  -> active_capital.value_yi
```

## 9. Recommended Next PR

Next PR should be:

```text
PR4.2.28b BoardPoolSnapshot Amount Completeness
```

Allowed:

- Add a `BoardPoolSnapshot` adapter over `eastmoney_board_pool_daily`.
- Add amount normalization tests for `ZT`.
- Add diagnostics proving `ZB.amount_yi` is missing for 2026-07-09.
- Keep `ActiveCapitalProducer` disabled or degraded until amount-complete.

Forbidden:

- Modify frontend.
- Modify emotion.
- Modify ReviewDocument schema.
- Use `2.04`.
- Hardcode `2707`.
- Use analyst markdown as production data.
