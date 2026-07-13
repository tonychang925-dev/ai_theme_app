# PR4.2.31b Eastmoney Fund Flow Capability Audit

Status: Audit + endpoint probe only  
Frozen Date: 2026-07-13

## Goal

Decide whether Eastmoney/a-stock-data can provide reliable stock fund-flow
evidence for `stock_fund_flow_snapshot`.

This audit does not add a collector, does not change ReviewDocument, and does
not produce capital intelligence fields. PR4.2.31c-1 may add a probe script that
prints endpoint capability JSON, but the probe must not persist data.

## Current Local Inventory

The local `stock_processing_service/integrations/a_stock_data` package currently
contains:

| Area | Local File | Capability |
|---|---|---|
| Eastmoney concept/industry/region blocks | `clients/eastmoney_client.py` | Block list and block members |
| Eastmoney board pools | `clients/eastmoney_board_client.py` | ZT/ZB/DT/YZT pools |
| THS hot reason | `clients/ths_client.py` | Hot reason collection |
| Research reports | `clients/research_report_client.py` | Report metadata |

There is no local `EastmoneyFundFlowClient` or collector that writes
`stock_fund_flow_snapshot`.

## Candidate Capabilities To Verify

| Capability | Candidate Source | Required Fields | Local Status | Decision |
|---|---|---|---|---|
| Stock daily fund flow | Eastmoney fund-flow endpoint through a-stock-data adapter | stock code, stock name, net inflow, super-large, large, medium, small order flow | Not implemented locally | Verify live endpoint before collector |
| Stock intraday/minute fund flow | Eastmoney or a-stock-data endpoint | timestamp, stock code, net inflow, order-size buckets | Unknown | Audit only; do not assume support |
| Concept/theme fund flow | Eastmoney concept fund-flow endpoint | concept code/name, net flow, rank, period | Unknown | Future PR4.2.31d, not PR4.2.31c |
| Industry fund flow | Eastmoney industry fund-flow endpoint | industry code/name, net flow, rank, period | Unknown | Future evidence source |

## Required Field Semantics

Eastmoney fund-flow labels such as "main force", super-large order, large order,
medium order, and small order are vendor-defined order-size proxies.

They must be stored as evidence, not as participant identity:

```text
fund-flow value
  -> stock_fund_flow_snapshot
  -> evidence
```

They must not become:

```text
fund-flow value
  -> institution_attention
```

or:

```text
large order value
  -> short_term_attack_style
```

## Period And Window Semantics

Before PR4.2.31c writes live rows, the evidence contract must decide whether to
extend `stock_fund_flow_snapshot` with:

```yaml
frequency:
  allowed:
    - DAILY
    - INTRADAY

window:
  allowed:
    - 1D
    - 5D
    - 10D
    - 20D
  reason: Eastmoney fund-flow endpoints may expose multiple statistical windows.

market_scope:
  allowed:
    - CN_A
  reason: Future adapters may cover HK/US or mixed universe sources.

source_version:
  example: eastmoney_fund_flow_f62_mapping_v1
  reason: Eastmoney field mappings may drift across endpoints or over time.
```

Do not use `period_type=5D`. A five-day value is a window, not a frequency.

If the live source cannot provide a period/window, PR4.2.31c must write
`frequency=DAILY` and `window=1D` only when the endpoint semantics are explicitly
daily.

## PR4.2.31c-1 Endpoint Probe

The first implementation step is a verification-only probe:

```text
stock_processing_service/scripts/probe_eastmoney_fund_flow_fields.py
```

The probe may call a candidate Eastmoney endpoint or read a saved raw fixture.
It must only print capability JSON. It must not write raw snapshots,
`stock_fund_flow_snapshot`, ReviewDocument, or frontend artifacts.

The probe should use Eastmoney-compatible request headers and try both HTTPS
and HTTP candidate URLs before returning `UNKNOWN`:

```text
https://push2.eastmoney.com/api/qt/clist/get
http://push2.eastmoney.com/api/qt/clist/get
```

If every candidate fails, the probe must report per-URL errors and keep
`production_write_allowed=false`.

The probe defaults to `trust_env=false` so `HTTP_PROXY`, `HTTPS_PROXY`, and
`ALL_PROXY` do not silently affect endpoint verification. If proxy behavior
needs to be tested explicitly, run the probe with `--trust-env`. The output must
include proxy environment diagnostics.

Required probe output:

```json
{
  "endpoint": "eastmoney_stock_fund_flow",
  "request_url": "...",
  "candidate_urls": ["..."],
  "requested_fields": "f12,f14,f62,f66,f72,f78,f84",
  "frequency": "DAILY",
  "window": "1D",
  "market_scope": "CN_A",
  "source_version": "eastmoney_fund_flow_f62_mapping_v1",
  "trust_env": false,
  "proxy_env_present": {"HTTPS_PROXY": false},
  "field_mapping": {
    "f62": {"meaning": "net_inflow_yuan", "unit": "yuan"},
    "f66": {"meaning": "super_large_net_inflow_yuan", "unit": "yuan"},
    "f72": {"meaning": "large_net_inflow_yuan", "unit": "yuan"},
    "f78": {"meaning": "medium_net_inflow_yuan", "unit": "yuan"},
    "f84": {"meaning": "small_net_inflow_yuan", "unit": "yuan"}
  },
  "capability": "SUPPORTED | UNAVAILABLE | UNKNOWN"
}
```

The probe result is not production data. A successful probe only authorizes a
future collector PR.

## Required Collector Architecture

Future collector flow:

```text
Eastmoney/a-stock-data endpoint
        |
        v
Source Adapter
        |
        v
EastmoneyStockFundFlowNormalizer
        |
        v
stock_fund_flow_snapshot
```

The collector may also persist raw HTTP payloads into the existing raw snapshot
mechanism, but it must not write ReviewDocument, Capital Intelligence, or UI
artifacts.

## Forbidden Paths

```text
eastmoney_fund_flow.main_net_inflow
  -> institution_attention
```

```text
stock_fund_flow_snapshot.large_net_inflow_yuan
  -> short_term_attack_style
```

```text
stock_fund_flow_snapshot
  -> ReviewDocument.capital.institution
```

```text
stock_fund_flow_snapshot
  -> ReviewDocument.capital.hot_money
```

```text
analyst report truth label
  -> stock_fund_flow_snapshot
```

## PR4.2.31c-2 Collector Entry Criteria

PR4.2.31c-2 collector work may start only after a live capability probe answers:

1. Which endpoint provides stock daily fund flow?
2. Which fields correspond to net, super-large, large, medium, and small order
   flow?
3. What units are returned?
4. Is the frequency daily or intraday?
5. Which statistical window does the endpoint represent?
5. Is the response stable enough to write replayable snapshots?

PR4.2.31c-2 scope must remain collector-only:

- allowed: source client, source adapter, normalizer reuse, raw snapshot write,
  `stock_fund_flow_snapshot` write, tests
- forbidden: ReviewDocument, UI, institution/hot-money producers, analyst truth
  labels, fallback estimates
