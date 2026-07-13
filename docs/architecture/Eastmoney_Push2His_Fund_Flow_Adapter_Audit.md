# PR4.2.31d-1 Eastmoney Official Client Reverse Audit

## Status

Audit and request-contract alignment only. No ReviewDocument, frontend, source
arbitration, or Capital Intelligence changes.

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

The referenced `simonlin1212/a-stock-data` `SKILL.md` exposes daily stock
fund-flow through `stock_fund_flow_120d(code)`:

```text
https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get
```

The request shape in that code block is:

```yaml
params:
  secid: "0.300223"
  fields1: f1,f2,f3,f7
  fields2: f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65
  lmt: "120"
headers:
  User-Agent: UA
  Referer: https://quote.eastmoney.com/
  Origin: https://quote.eastmoney.com
transport:
  helper: em_get()
  session_reuse: true
  min_interval: ">=1s + jitter"
```

It maps:

```yaml
f51: date
f52: main_net
f53: small_net
f54: mid_net
f55: large_net
f56: super_net
```

Repository tree check:

```yaml
repo: simonlin1212/a-stock-data
branch: main
observed_files:
  - SKILL.md
python_source_files: []
decision: "Treat a-stock-data as a documented code-block reference, not an importable source package."
```

The same `SKILL.md` explicitly warns that `push2/push2his` can be intermittently
blocked at connection level for some mainland residential IPs. The recommended
handling is lower frequency, retry later, or switch network. That means repeated
`RemoteProtocolError` is a live-ingestion reliability finding, not enough by
itself to disprove endpoint capability.

## AKShare Reference Difference

AKShare's `stock_individual_fund_flow()` also uses the same daykline endpoint,
but its request shape differs:

```yaml
params:
  lmt: "0"
  klt: "101"
  ut: b2884a393a59ad64002292a3e90d46a5
  _: "<milliseconds timestamp>"
  fields1: f1,f2,f3,f7
  fields2: f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65
headers:
  User-Agent: Mozilla/5.0 ...
```

These are two known client variants. The production client should not silently
mix variants; each probe should label the variant it is testing.

## Browser Request Status

Browser network capture has not yet been provided. It remains the final external
truth check for the official page request. Until that capture is available,
the code contract follows the `a-stock-data` `stock_fund_flow_120d()` request
shape, with AKShare kept as a documented alternative probe shape.

Required HAR comparison fields:

```yaml
url:
  - scheme
  - host
  - path
query:
  - secid
  - fields1
  - fields2
  - lmt
  - klt
  - ut
  - cb
  - invt
  - fqt
  - "_"
headers:
  - Host
  - User-Agent
  - Accept
  - Accept-Encoding
  - Accept-Language
  - Referer
  - Origin
  - Cookie
transport:
  - http_version
  - tls
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
session_reuse: true
headers:
  Referer: https://quote.eastmoney.com/
  Origin: https://quote.eastmoney.com
  Accept: "*/*"
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

1. `PR4.2.31d-2 Eastmoney Official Request Verification`
   - run the `a-stock-data` request shape live
   - optionally run the AKShare request shape as a separately labeled variant
   - compare with browser network capture when available
   - keep failures as source health diagnostics, not fake data
2. `PR4.2.32 Theme Fund Flow Evidence`
   - aggregate stock-level evidence into theme-level evidence
   - avoid stock double counting across multiple themes
3. `PR4.2.33 Institution Attention Producer`
   - use theme cycle, strength, continuity, and evidence
4. `PR4.2.34 Short-Term Attack Producer`
   - use limit-up, strong-stock, events, and evidence

Only after theme-level evidence exists should ReviewDocument capital style
sections be populated.
