# RD1 P1-I5 — Stock Quote Public Capability

## Source Audit

- Audited existing source: `public.stock_daily_snapshot`
- Authority gate: existing writes permit only `source_name LIKE 'tushare%'`
- Exact selector columns: `trade_date`, `stock_id`
- Required quote columns are already persisted:
  `stock_id`, `stock_name`, `trade_date`, `open_price`, `high_price`, `low_price`,
  `close_price`, `pre_close`, `pct_chg`, `volume`, and `amount`
- No external provider, Tushare network call, fallback chain, latest-date discovery, synthetic row, or missing-field synthesis was added.
- Real exact identifier audit: `600519.SH`
- Latest authoritative date available in the current backend: `2026-07-31`
- Raw sanitized audit log: `/private/tmp/rd1_stock_quote_source_audit.json`

## Public Contract

- Capability: `market.stock.quote.read`
- Contract version: `0.3.2`
- Request: `StockQuoteReadRequest(stock_id, trade_date)`
- Date format: exact `YYYY-MM-DD`
- Result carrier: existing `MarketResultEnvelope`
- No matching exact row: `SUCCESS / EMPTY`
- Dependency failure: existing typed `FAILURE / UNAVAILABLE`
- Invalid request/date: existing typed `MarketContractMismatch`

## Real Exact Read

Request:

```text
stock_id = 600519.SH
trade_date = 2026-07-31
```

Result:

- `operation_status = SUCCESS`
- `data_state = READY`
- `source_name = tushare`
- `stock_name = ""` was preserved as source truth and not synthesized
- Payload:
  - open `1330.0300`
  - high `1355.7200`
  - low `1325.7700`
  - close `1350.6000`
  - pre-close `1361.7600`
  - pct change `-0.8195`
  - volume `55127.5200`
  - amount `7373462.6050`
- Raw sanitized execution: `/private/tmp/rd1_stock_quote_public_real_read.json`

## Verification

```text
/opt/miniconda3/bin/python -m pytest \
  tests/test_market_stock_quote_public_capability.py \
  tests/test_market_public_boundary.py \
  tests/test_market_public_integration.py -q

59 passed in 0.35s
```

## PR410 Review Remediation

- Review `4070836453`: date authority is `date.fromisoformat()` followed by exact
  `date.isoformat()` round-trip equality. Malformed, noncanonical, year-zero,
  impossible-calendar, and non-ASCII-digit dates remain typed
  `MarketContractMismatch` outcomes with zero repository executions.
- Review `4070836464`: quote retrieval uses `source_name ILIKE 'tushare%'`,
  and preferred-source ordering uses `source_name ILIKE 'tushare'`, matching the
  persisted truth gate's case-insensitive semantics without broadening authority.
- Repeated real request `600519.SH` / `2026-07-31` returned
  `SUCCESS / READY` from persisted `stock_daily_snapshot` with source `tushare`.
