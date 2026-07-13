# PR4.2.31d Sina Fund Flow Backup Probe

## Scope

This PR is probe-only.

It verifies whether a Sina stock fund-flow endpoint can serve as a backup
evidence source for `stock_fund_flow_snapshot`.

It must not:

- write `stock_fund_flow_snapshot`
- modify ReviewDocument
- modify frontend
- produce `institution_attention`
- produce `hot_money_style`
- override Eastmoney rows

## Candidate Source

```yaml
source_name: sina_fund_flow
endpoint: sina_stock_fund_flow_daily
candidate_urls:
  - https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs
  - http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs
frequency: DAILY
window: 1D
market_scope: CN_A
source_version: sina_moneyflow_daily_probe_v1
production_write_allowed: false
```

## Semantics

Sina fund-flow values are treated as vendor-defined order-size proxies.

They are not:

- institution identity
- hot-money identity
- retail identity
- analyst truth labels

Expected normalized evidence fields:

```yaml
net_inflow_yuan:
  meaning: vendor net fund-flow proxy
  unit: yuan

super_large_net_inflow_yuan:
  meaning: vendor super-large order proxy
  unit: yuan

large_net_inflow_yuan:
  meaning: vendor large order proxy
  unit: yuan

medium_net_inflow_yuan:
  meaning: vendor medium order proxy
  unit: yuan

small_net_inflow_yuan:
  meaning: vendor small order proxy
  unit: yuan
```

## Capability Decision

The probe may return:

```yaml
capability: SUPPORTED
```

only when all normalized fields are found in live or fixture response data:

- `net_inflow_yuan`
- `super_large_net_inflow_yuan`
- `large_net_inflow_yuan`
- `medium_net_inflow_yuan`
- `small_net_inflow_yuan`

Otherwise:

```yaml
capability: UNKNOWN
decision: do not add collector
```

## Forbidden Paths

```text
sina_fund_flow.net_inflow_yuan > 0
  -> institution_attention

sina_fund_flow.large_net_inflow_yuan > 0
  -> hot_money_style

sina_fund_flow
  -> ReviewDocument.capital.institution

sina_fund_flow
  -> ReviewDocument.capital.hot_money

eastmoney_fund_flow failed
  -> silently overwrite with sina_fund_flow
```

If Sina is later collected, it must remain an independent source:

```yaml
source_name: sina_fund_flow
source_version: sina_moneyflow_daily_v1
```

It must not masquerade as Eastmoney.

## Evidence Freshness Contract

This PR does not implement freshness storage, but future Evidence Layer rows
should expose collection freshness explicitly:

```yaml
source_name: eastmoney_fund_flow
source_version: eastmoney_fflow_daykline_f52_v1
trade_date: 2026-07-09
acquired_at: 2026-07-13T...
collection_status: source_unavailable | ok | partial_failure
is_live_capture: true | false
stale: true | false
```

This is required because stale artifacts and stale evidence rows can otherwise
be mistaken for current live capture.

## Next Step Gate

Only after `probe_sina_fund_flow_fields.py` returns `SUPPORTED` from live data
should a separate collector PR be considered.

The collector PR must still remain evidence-only.
