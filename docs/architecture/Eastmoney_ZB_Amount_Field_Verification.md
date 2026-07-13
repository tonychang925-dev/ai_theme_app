# Eastmoney ZB Amount Field Verification

PR: PR4.2.28d Eastmoney ZB Amount Field Verification
Status: Verified Supported / No Production Change
Frozen Date: 2026-07-13

## 1. Decision

Do not modify production data flow yet.

The goal of this PR is to verify whether `getTopicZBPool` can return an
amount-like field when requested with `f6/f62/f116`. It must not compute
`active_capital`, change `ReviewDocument`, or patch the frontend.

## 2. Probe Tool

Added verification-only script:

```text
stock_processing_service/scripts/probe_eastmoney_zb_amount_fields.py
```

The script requests:

```text
getTopicZBPool
fields=f12,f14,f2,f3,f4,f6,f7,f15,f16,f17,f62,f116,f184,f127
```

It reports one of:

| Capability | Meaning |
| --- | --- |
| `SUPPORTED` | Response contains an amount-like field such as `amount` or `f6`. |
| `UNAVAILABLE` | Response was received, but no amount-like field was present. |
| `UNKNOWN` | Live endpoint could not be verified, e.g. network timeout. |

The script does not persist data and is not used by ReviewDocument generation.

## 3. Fixture Verification

Two raw-response fixtures define the parser behavior:

| Fixture | Expected Capability |
| --- | --- |
| `eastmoney_zb_pool_with_f6.json` | `SUPPORTED` |
| `eastmoney_zb_pool_without_amount.json` | `UNAVAILABLE` |

This verifies the probe parser behavior independently from live network access.

## 4. Live Probe Result

Command attempted:

```text
.venv/bin/python stock_processing_service/scripts/probe_eastmoney_zb_amount_fields.py \
  --date 2026-07-09 \
  --page-size 5 \
  --timeout 15
```

Result from the network-capable local environment:

```json
{
  "amount_candidate_counts": {
    "amount": 5
  },
  "capability": "SUPPORTED",
  "decision": "ZB amount can be normalized from endpoint response after collector mapping.",
  "endpoint": "getTopicZBPool",
  "examples": [
    {
      "amount_fields": {
        "amount": 1480394240
      },
      "code": "601133",
      "name": "柏诚股份"
    },
    {
      "amount_fields": {
        "amount": 1027843488
      },
      "code": "600520",
      "name": "三佳科技"
    },
    {
      "amount_fields": {
        "amount": 922473536
      },
      "code": "603115",
      "name": "海星股份"
    },
    {
      "amount_fields": {
        "amount": 1018963104
      },
      "code": "603989",
      "name": "艾华集团"
    },
    {
      "amount_fields": {
        "amount": 624122224
      },
      "code": "301317",
      "name": "鑫磊股份"
    }
  ],
  "requested_fields": "f12,f14,f2,f3,f4,f6,f7,f15,f16,f17,f62,f116,f184,f127",
  "response_keys": [
    "amount",
    "c",
    "fbt",
    "hs",
    "hybk",
    "ltsz",
    "m",
    "n",
    "p",
    "tshare",
    "zbc",
    "zdp",
    "zf",
    "zs",
    "ztp",
    "zttj"
  ],
  "row_count": 5
}
```

Conclusion:

Live Eastmoney ZB amount capability is verified as `SUPPORTED` when `f6` is
included in the requested field list.

This does not change production data yet. The persisted 2026-07-09
`eastmoney_board_pool_daily` rows still have `ZB.amount = 0`, so
`BoardPoolSnapshot.zb.amount_yi` remains `MISSING` until the collector mapping is
updated and the board-pool snapshot is regenerated.

## 5. Forbidden Follow-Up

Do not interpret `SUPPORTED` as permission to bypass persistence.

Forbidden:

```text
ZT.amount_yi + inferred_gap
  -> active_capital.value_yi
```

```text
analyst_report.active_capital_yi
  -> production active_capital.value_yi
```

```text
ZB.turnover_rate
  -> ZB.amount_yi
```

```text
live endpoint amount
  -> runtime ReviewDocument generation
```

## 6. Next Step

```text
PR4.2.28e
  -> add amount to FriedBoardPoolStock
  -> persist ZB.amount
  -> BoardPoolSnapshot.zb.amount_yi = OK
```

Allowed in PR4.2.28e:

```text
Eastmoney getTopicZBPool(fields include f6)
  -> FriedBoardPoolStock.amount
  -> collect_eastmoney_board_pool.py persists amount
  -> eastmoney_board_pool_daily.ZB.amount
  -> BoardPoolSnapshot.zb.amount_yi
```

Still forbidden:

- Modify `ReviewDocument`.
- Modify frontend.
- Modify active capital output.
- Hardcode `2707`.
- Use `2.04`.
- Use runtime Eastmoney response directly in ReviewDocument generation.
