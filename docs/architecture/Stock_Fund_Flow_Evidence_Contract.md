# PR4.2.31a Stock Fund Flow Evidence Contract

Status: Contract + normalizer only  
Frozen Date: 2026-07-13

## Goal

Persist stock-level vendor-defined fund-flow facts as evidence.

This PR does not produce:

- `institution_attention`
- `short_term_attack_style`
- `institution_style`
- `hot_money_style`
- UI fields

## Source Semantics

Eastmoney fund-flow values such as net inflow, super-large order flow, large
order flow, medium order flow, and small order flow are order-size proxies.

They are not:

- real institution identity
- real retail identity
- hot-money seat identity
- analyst truth labels

## Evidence Table

Target table:

```text
stock_fund_flow_snapshot
```

Primary key:

```text
(trade_date, stock_code, source_name)
```

Fields:

```yaml
trade_date: date
stock_code: text
stock_name: text
net_inflow_yuan: numeric
super_large_net_inflow_yuan: numeric
large_net_inflow_yuan: numeric
medium_net_inflow_yuan: numeric
small_net_inflow_yuan: numeric
source_name: eastmoney_fund_flow
source_endpoint: eastmoney_stock_fund_flow
source_quality: VENDOR_DEFINED_ORDER_SIZE_FLOW
quality: OK | MISSING
diagnostics: jsonb
raw_json: jsonb
```

## Normalization

Allowed input aliases:

```yaml
stock_code:
  - stock_code
  - code
  - f12
  - secucode
stock_name:
  - stock_name
  - name
  - f14
  - secuname
net_inflow_yuan:
  - net_inflow
  - net_inflow_yuan
  - main_net_inflow
  - main_net_inflow_yuan
  - f62
super_large_net_inflow_yuan:
  - super_large_net_inflow
  - super_large_net_inflow_yuan
  - f66
large_net_inflow_yuan:
  - large_net_inflow
  - large_net_inflow_yuan
  - f72
medium_net_inflow_yuan:
  - medium_net_inflow
  - medium_net_inflow_yuan
  - f78
small_net_inflow_yuan:
  - small_net_inflow
  - small_net_inflow_yuan
  - f84
```

## Forbidden Paths

```text
stock_fund_flow_snapshot.net_inflow_yuan > 0
  -> institution_attention
```

```text
stock_fund_flow_snapshot.large_net_inflow_yuan > 0
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

## Next Step

After live endpoint capability is verified, add a collector that writes only to
`stock_fund_flow_snapshot`. Do not connect the table to Capital Intelligence in
the collector PR.

