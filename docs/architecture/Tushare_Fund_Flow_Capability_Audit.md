# PR4.2.31e Tushare Fund Flow Capability Audit

## Status

Audit/probe only. No collector, ReviewDocument, frontend, or Capital
Intelligence changes.

## Decision Summary

Tushare should be evaluated as the primary post-market fund-flow evidence source.
Eastmoney `push2/push2his` remains useful for intraday/realtime evidence, but
recent probe results show unstable live access from the current network.

The probe target is:

```yaml
script: stock_processing_service/scripts/probe_tushare_fund_flow_fields.py
production_write_allowed: false
network_note: "Run with VPN disabled / direct domestic route when testing Tushare."
```

## Candidate Interfaces

```yaml
moneyflow:
  source_endpoint: tushare.moneyflow
  role: stock_order_size_flow_native
  frequency: DAILY
  window: 1D

moneyflow_ths:
  source_endpoint: tushare.moneyflow_ths
  role: stock_order_size_flow_ths
  frequency: DAILY
  window: 1D
  priority: P0

moneyflow_cnt_ths:
  source_endpoint: tushare.moneyflow_cnt_ths
  role: concept_fund_flow_ths
  frequency: DAILY
  window: 1D
  priority: P0

moneyflow_hsgt:
  source_endpoint: tushare.moneyflow_hsgt
  role: cross_border_flow
  frequency: DAILY
  window: 1D
  priority: P1
```

## Source Ownership Proposal

```yaml
stock_fund_flow_snapshot:
  primary_post_market_source: tushare.moneyflow_ths
  secondary_native_source: tushare.moneyflow
  realtime_optional_source: eastmoney.push2his

theme_fund_flow_snapshot:
  primary_post_market_source: tushare.moneyflow_cnt_ths

cross_border_flow_snapshot:
  primary_post_market_source: tushare.moneyflow_hsgt
```

## Evidence Semantics

Tushare fund-flow rows are evidence. They are not direct participant identity.

```text
tushare.moneyflow_ths.net_amount > 0
  -> institution_attention
```

Forbidden.

```text
tushare.moneyflow_cnt_ths.net_amount > 0
  -> hot_money_style
```

Forbidden.

The correct path is:

```text
Tushare fund-flow
  -> Evidence Layer
  -> Theme Fund Flow Evidence
  -> Institution Attention / Short-Term Attack Producer
```

## Probe Command

```bash
.venv/bin/python stock_processing_service/scripts/probe_tushare_fund_flow_fields.py \
  --date 2026-07-09 \
  --ts-code 300223.SZ
```

If the environment does not export `TUSHARE_TOKEN`, pass `--token`.

## Acceptance

The probe must report each interface independently:

```yaml
capability: SUPPORTED | PARTIAL_SUPPORTED | UNKNOWN
row_count: int
response_fields: []
missing_expected_fields: []
production_write_allowed: false
```

No failed or partial interface may fabricate rows or write production tables.
