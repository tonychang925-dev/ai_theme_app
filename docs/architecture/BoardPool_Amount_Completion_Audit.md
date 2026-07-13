# BoardPool Amount Completion Audit

PR: PR4.2.28c BoardPool ZB/YZT Amount Source Audit  
Status: Audit Only  
Frozen Date: 2026-07-13

## 1. Decision

Do not compute `active_capital.value_yi` yet.

Current valid state:

```yaml
active_capital:
  value_yi: null
  quality: DEGRADED
  missing:
    - board_pool.zb.amount_yi
```

Reason:

`ZT.amount_yi = 2479.55` is only sealed limit-up turnover. It is not analyst
active capital. Analyst active capital for 2026-07-09 is defined as:

```text
今日所有涨停及触及涨停个股成交量之和 = 2707 亿
```

Therefore the missing component is the touched/fried board amount, primarily
`ZB.amount_yi`.

## 2. Current Evidence

Persisted source owner:

`eastmoney_board_pool_daily`

For 2026-07-09:

| Pool | Rows | Amount Rows | Amount Sum | Quality |
| --- | ---: | ---: | ---: | --- |
| `ZT` | 75 | 75 | 2479.55 亿 | OK |
| `ZB` | 17 | 0 | null | MISSING |
| `YZT` | 47 | 0 | null | MISSING |

The current `BoardPoolSnapshotAdapter` correctly reports:

```python
ZT = (75, 2479.55, "OK")
ZB = (17, None, "MISSING")
YZT = (47, None, "MISSING")
```

This is the correct fail-closed behavior.

## 3. Raw JSON Audit

Observed raw keys for 2026-07-09:

| Pool | Raw JSON Keys |
| --- | --- |
| `ZT` | `amount`, `break_times`, `code`, `first_seal`, `industry`, `last_seal`, `limit_days`, `name`, `pct`, `turnover`, `zt_stat` |
| `ZB` | `break_times`, `code`, `first_seal`, `industry`, `name`, `pct`, `turnover` |
| `YZT` | `code`, `industry`, `name` |

Conclusion:

- `ZB.raw_json` does not currently contain `amount`.
- `YZT.raw_json` does not currently contain today amount.
- This is not an adapter parsing bug inside `BoardPoolSnapshotAdapter`; the
  persisted payload is missing amount fields.

## 4. Eastmoney Client Audit

Current client:

`stock_processing_service/integrations/a_stock_data/clients/eastmoney_board_client.py`

`fetch_zt_pool` requests:

```text
fields = f12,f14,f2,f3,f4,f6,f7,f15,f16,f17,f18,f184,f127,f129,f191,f192
```

and maps:

```python
amount=float(item.get("amount", 0))
```

`fetch_zb_pool` requests:

```text
fields = f12,f14,f2,f3,f4,f7,f15,f16,f17,f184,f127
```

It does not request `f6`.

Interpretation:

`f6` is the likely Eastmoney amount field used by `ZT`. The current ZB endpoint
request does not ask for it, so the normalizer cannot persist `ZB.amount`.

This audit does not prove that `getTopicZBPool` supports `f6`; it proves that
the current client never requests it. The next implementation PR must verify
the endpoint response before changing the collector contract.

## 5. Candidate Amount Sources

### Option A: Eastmoney ZB `f6` Amount

Target path:

```text
Eastmoney getTopicZBPool(fields include f6)
  -> FriedBoardPoolStock.amount
  -> eastmoney_board_pool_daily.amount
  -> BoardPoolSnapshot.zb.amount_yi
```

Status:

Preferred, pending endpoint verification.

Reason:

- Same source family as `ZT.amount`.
- Keeps source owner in `eastmoney_board_pool_daily`.
- Avoids mixing amount units across providers.
- Replay remains stable after persistence.

### Option B: BoardPool Stock Set + Quote Amount Adapter

Target path:

```text
eastmoney_board_pool_daily.ZB.stock_code
  + canonical daily quote amount
  -> BoardPoolSnapshot.zb.amount_yi
```

Status:

Acceptable only with an explicit `BoardPoolAmountAdapter`.

Requirements:

- Declare the quote table owner.
- Declare unit conversion, e.g. `stock_daily_snapshot.amount` with
  `qian_yuan -> yi`.
- Prove the unit with test data.
- Do not mix Eastmoney raw `amount` and quote `amount` without per-component
  `amount_source`.

Risk:

Current direct SQL showed that treating `stock_daily_snapshot.amount` as yuan
produces invalid tiny values, so an explicit unit adapter is mandatory.

### Option C: Daily Quote Recompute

Target path:

```text
daily_quote
  -> high >= limit_price
  -> touched pool
  -> sum amount
```

Status:

Long-term backfill/training strategy, not the next small PR.

Reason:

It requires board rules, ST handling, BSE/STAR/ChiNext limits, new listings,
resumed trading, and rounding rules.

## 6. Forbidden Paths

```text
ZT.amount_yi
  -> active_capital.value_yi
```

```text
ZB.turnover_rate
  -> ZB.amount_yi
```

```text
analyst_report.active_capital_yi
  -> production active_capital.value_yi
```

```text
ZT.amount_yi + fixed_gap_or_factor
  -> active_capital.value_yi
```

```text
money_flow_enhanced.role_label
  -> active_capital.value_yi
```

```text
theme_capital_flow
  -> active_capital.value_yi
```

## 7. Recommended Next PR

Next PR should be:

```text
PR4.2.28d Eastmoney ZB Amount Field Verification
```

Allowed:

- Probe `getTopicZBPool` with `f6` included in fields.
- If `f6` exists, add `amount` to `FriedBoardPoolStock`.
- Persist `ZB.amount` to `eastmoney_board_pool_daily.amount`.
- Add adapter tests proving `BoardPoolSnapshot.zb.amount_yi` becomes `OK`.

Forbidden:

- Modify `ReviewDocument`.
- Modify frontend.
- Modify active capital output.
- Use `2.04`.
- Hardcode `2707`.
- Use analyst markdown as production input.

If `f6` is unavailable, next PR should build a dedicated
`BoardPoolAmountAdapter` over a canonical daily quote source and keep
`active_capital.quality = DEGRADED` until that adapter is proven.
