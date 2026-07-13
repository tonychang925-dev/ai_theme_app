# PR4.2.29 Active Capital Golden Replay Validation

Date: 2026-07-13
Trade date: 2026-07-09

## Scope

This validation only checks that the active-capital fact now flows from
`BoardPoolSnapshot` into charts, draft context, and `ReviewDocument`.

No formula changes, frontend renderer changes, ReviewDocument schema changes,
or Capital Intelligence changes are part of this PR.

## Source Contract

Active capital production source:

```text
eastmoney_board_pool_daily
  -> BoardPoolSnapshot
  -> ActiveCapitalProducer
  -> MarketMetricsSnapshot.capital.active_limitup_amount_yi
  -> active_capital chart
  -> DraftContext.capital_state.active_amount
  -> ReviewDocument.capital.active_amount
```

Producer output for 2026-07-09:

```yaml
active_capital:
  value_yi: 2664.84
  method: board_pool_zt_zb_v1
  quality: PARTIAL
  confidence: 0.85
  components:
    - type: ZT
      amount_yi: 2479.55
      source: eastmoney_board_pool_daily.amount
    - type: ZB
      amount_yi: 185.29
      source: eastmoney_board_pool_daily.amount
  missing:
    - board_pool.yzt.amount_yi
```

`PARTIAL` is intentional because YZT amount coverage is still missing.

## Regeneration Evidence

Command:

```bash
curl -sS --max-time 180 -X POST \
  http://127.0.0.1:8090/api/v1/analyst-workbench/2026-07-09/generate
```

Result summary:

```text
status: completed
steps_completed:
  - derived_data
  - charts
  - emotion
  - draft_context
  - workbench
draft_version: 21
```

## Artifact Checks

`frontend/public/api/analyst-charts/2026-07-09.json`:

```yaml
active_amount_yi: 2664.84
active_amount_display: 2665亿
```

`tmp/analyst_workbench/2026-07-09/draft_context.json`:

```yaml
capital_state:
  active_amount: 2664.84
  active_amount_yi: 2664.84
```

`tmp/analyst_workbench/2026-07-09/review_document.json`:

```yaml
capital:
  active_amount: 2664.84
```

`ReviewDocument.evidence.trend_series.capital` after historical board-pool
backfill:

```yaml
- { date: 2026-06-23, amount: 1870.06 }
- { date: 2026-06-24, amount: 3593.97 }
- { date: 2026-06-25, amount: 2586.15 }
- { date: 2026-06-26, amount: 1764.36 }
- { date: 2026-06-29, amount: 2106.71 }
- { date: 2026-06-30, amount: 2845.81 }
- { date: 2026-07-01, amount: 2193.12 }
- { date: 2026-07-02, amount: 1115.34 }
- { date: 2026-07-03, amount: 2077.90 }
- { date: 2026-07-06, amount: 1251.43 }
- { date: 2026-07-07, amount: 891.53 }
- { date: 2026-07-08, amount: 736.75 }
- { date: 2026-07-09, amount: 2664.84 }
```

`2026-06-22` remains `0.0` because the Eastmoney board-pool collector returned
no ZT/ZB/YZT rows for that date. This is source coverage, not frontend logic.

Public chart GET after regeneration:

```text
GET /api/v1/analyst-charts/2026-07-09
active_amount_yi = 2664.84
```

## Golden Replay Result

Command:

```bash
.venv/bin/python scripts/verify_review_document.py --date 2026-07-09
```

Current expected result:

```text
READY=False
capital.active_amount expected 2707, got 2664.84
```

This is not a producer regression. The Golden baseline uses analyst truth
`2707`, while the production fact layer now emits the replayable board-pool
value `2664.84`.

The difference must be handled by a later Golden recalibration / analyst
feedback layer. Do not hardcode `2707` into production and do not restore the
old `5058.28` fixed-factor path.

## Validation Commands

```bash
.venv/bin/python -m pytest \
  stock_processing_service/tests/unit/test_active_capital_producer.py \
  stock_processing_service/tests/unit/test_market_metrics_active_capital_board_pool.py \
  stock_processing_service/tests/contracts/test_active_capital_golden_replay_validation.py \
  -q
```

Expected:

```text
6 passed
```
