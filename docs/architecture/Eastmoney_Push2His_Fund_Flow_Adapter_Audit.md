# PR4.2.31d Eastmoney Push2His Fund Flow Adapter Audit

## Status

Audit only. No production logic changes.

## Decision Summary

Eastmoney stock fund-flow evidence should use `push2his` stock fflow daykline
as the primary stock-level daily source.

The source owner is:

```yaml
source_name: eastmoney_fund_flow
endpoint: eastmoney_stock_fflow_daykline
url: https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get
frequency: DAILY
window: 1D
market_scope: CN_A
source_version: eastmoney_fflow_daykline_f52_v1
semantics: vendor_defined_order_size_proxy
```

The current `stock_fund_flow_snapshot` schema and normalizer align with this
decision.

## Why Push2His, Not Clist

`push2.eastmoney.com/api/qt/clist/get` is a quote-list/ranking endpoint.

It may expose ranking fields such as `f62/f66/f72/f78/f84`, but it is more
sensitive to request environment and is not the correct source owner for
replayable stock-level historical fund-flow evidence.

`push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` is the correct source
for daily stock fund-flow history:

```yaml
fields2:
  f51: date
  f52: net_inflow_yuan
  f53: small_net_inflow_yuan
  f54: medium_net_inflow_yuan
  f55: large_net_inflow_yuan
  f56: super_large_net_inflow_yuan
```

This matches the current normalizer:

```text
EastmoneyStockFundFlowNormalizer.normalize_daykline_row()
```

## a-stock-data Reference Alignment

The local AkShare-compatible implementation exposes the same endpoint through
`stock_individual_fund_flow()`:

```text
https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get
```

It maps:

```yaml
f51: 日期
f52: 主力净流入-净额
f53: 小单净流入-净额
f54: 中单净流入-净额
f55: 大单净流入-净额
f56: 超大单净流入-净额
```

System terminology must not inherit the participant identity implied by
vendor labels such as "主力". Internally these values remain order-size proxy
evidence:

```yaml
net_inflow_yuan: vendor net fund-flow proxy
super_large_net_inflow_yuan: vendor super-large order proxy
large_net_inflow_yuan: vendor large order proxy
medium_net_inflow_yuan: vendor medium order proxy
small_net_inflow_yuan: vendor small order proxy
```

## Current Implementation State

Implemented:

- `EastmoneyFundFlowClient`
- `EastmoneyStockFundFlowNormalizer`
- `CollectEastmoneyFundFlowJob`
- `stock_fund_flow_snapshot`
- smoke/replay diagnostics
- source health status:
  - `ok`
  - `partial_failure`
  - `source_unavailable`

Observed:

- endpoint capability: `SUPPORTED`
- live ingestion reliability: `UNSTABLE`
- common failure: `RemoteProtocolError`

This is not a field semantics issue. It is a live collection reliability issue.

## Reliability Policy

For production collection, the source should use conservative request behavior:

```yaml
min_interval_ms: 2500
jitter_ms: 1500
max_retries: 3
backoff: exponential
session_reuse: false
headers:
  Referer: https://quote.eastmoney.com/
  Accept: "*/*"
  Connection: close
```

For smoke validation, fail-fast is preferred:

```yaml
timeout_ms: 5000
max_retries: 0
per_stock_progress: true
```

Smoke output must distinguish:

```yaml
live_success_stock_codes: []
stale_readback_stock_codes: []
source_health: UNAVAILABLE | DEGRADED | OK
```

## Source Selection

Do not switch to Sina just because Eastmoney is temporarily unavailable.

Sina probe result for `300223` showed only:

```yaml
net_inflow_yuan: netamount
super_large_net_inflow_yuan: r0_net
```

Missing:

```yaml
large_net_inflow_yuan
medium_net_inflow_yuan
small_net_inflow_yuan
```

Therefore Sina is not a full replacement for Eastmoney daykline evidence.

Future source arbitration should record each source independently:

```yaml
eastmoney_daykline:
  capability: SUPPORTED
  reliability: DEGRADED

sina_daily:
  capability: PARTIAL
  reliability: UNKNOWN
```

No source may silently overwrite or masquerade as another source.

## Forbidden Paths

```text
clist/get live ranking
  -> stock_fund_flow_snapshot canonical daily history
```

```text
eastmoney_fund_flow.net_inflow_yuan > 0
  -> institution_attention
```

```text
eastmoney_fund_flow.large_net_inflow_yuan > 0
  -> hot_money_style
```

```text
sina_fund_flow partial fields
  -> complete stock_fund_flow_snapshot replacement
```

```text
analyst report truth label
  -> stock_fund_flow_snapshot
```

## Next Stage

Do not connect frontend or ReviewDocument yet.

Recommended sequence:

1. `PR4.2.31e Evidence Source Arbitration`
   - classify source capability and reliability
   - keep source rows independent
   - define freshness/collection status contract
2. `PR4.2.32 Theme Fund Flow Evidence`
   - aggregate stock-level evidence into theme-level evidence
   - avoid stock double counting across multiple themes
3. `PR4.2.33 Institution Attention Producer`
   - use theme cycle, strength, continuity, and evidence
4. `PR4.2.34 Short-Term Attack Producer`
   - use limit-up, strong-stock, events, and evidence

Only after theme-level evidence exists should ReviewDocument capital style
sections be populated.
