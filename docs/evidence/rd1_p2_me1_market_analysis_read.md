# RD1-P2-ME1 — Market Aggregate Evidence Capability

## Boundary

- Base: `d65225394184fe83124471f1a3e61a01a67bd2f3`
- Capability: `market.analysis.read`
- Contract version: `0.4.0`
- Request: `MarketAnalysisReadRequest(trade_date: YYYY-MM-DD)`
- Result carrier: `MarketResultEnvelope`
- Source read: exact-date `post_market_recap_snapshot`
- Projection chain: existing `MarketKnowledgeBundleBuilder` → existing `MarketEvidenceAdapter`
- Public adapter behavior: serialization/projection only; no Market-domain recalculation
- Date fallback: none
- Synthetic success: none

The provider reads one explicit trade date and returns `SUCCESS / EMPTY` when
that exact row is absent. Invalid requests return `FAILURE / NOT_APPLICABLE /
MarketContractMismatch`; dependency failures return `FAILURE / UNAVAILABLE`.

## Real Database Acceptance

### READY — `2026-05-15`

```text
operation_status = SUCCESS
data_state = READY
snapshot_identity = post_market_recap_snapshot:2026-05-15
snapshot_version = daily_review_generate.read_model_only.d410dc43
batch_id = 4c17bd269d4e
trace_id = 33648b2b0fe6
source_bundle_id = mkb:2026-05-15:f55cecd4b97d47bd
evidence_snapshot_id = mes:2026-05-15:c37e238c7649ab34
content_hash = c37e238c7649ab3411d0ea6a7e813ce40739720def8be6c305b7b25f7e03b3f1
evidence_count = 25
evidence_ref_count = 25
quality = partial / 0.4
```

Ready modules:

```text
engine_summary
market_regime_review
mainline_states
theme_reviews
```

Explicit missing modules:

```text
daily_recap_essentials
limit_up_theme_events
new_high_summary
seat_money_summary
watchlists
post_market_setup_plan
```

Returned evidence keys:

```text
decision.allow_trade
decision.trade_mode
decision.position_limit
decision.next_day_strategy
market.broad_market_regime
market.short_term_sentiment
market.mainline_environment
mainline.0.name
mainline.0.lifecycle
mainline.0.strong_stock_count
mainline.1.name
mainline.1.lifecycle
mainline.1.strong_stock_count
mainline.2.name
mainline.2.lifecycle
mainline.2.strong_stock_count
mainline.3.name
mainline.3.lifecycle
mainline.3.strong_stock_count
mainline.4.name
mainline.4.lifecycle
mainline.4.strong_stock_count
mainline.5.name
mainline.5.lifecycle
mainline.5.strong_stock_count
```

Provenance remained explicitly `PROVENANCE_INCOMPLETE`, with source refs for
the exact snapshot date, snapshot version, batch identity, and trace identity;
all 25 evidence refs and the public bundle/evidence identities were preserved.
No release identity was fabricated.

### EMPTY — `2026-07-10`

```text
operation_status = SUCCESS
data_state = EMPTY
payload = null
failures = []
```

The repository received only `2026-07-10`; no latest, previous-day, or
nearest-date lookup was performed.

## Review Maturity

The selected canonical recap contained no durable review/approval metadata.
The result therefore reports:

```json
{
  "available": false,
  "source_mode": "unavailable",
  "source": "not_bound",
  "reason": "review maturity is not present in the canonical recap payload"
}
```

No `analyst_reviewed`, `approved`, or `published` state was fabricated. ME-1
does not bind `tmp/analyst_workbench`, `SnapshotStore`, or Workbench session
state. Follow-up requirement:
`OPTIONAL_ME2_ANALYST_MATURITY_BINDING_REQUIRED`.

## Evidence Coverage Assessment

No Julia reasoning or investment judgment was executed.

- 今天市场处于什么阶段？ — `SUPPORTED_BY_CURRENT_EVIDENCE`;
  `market.broad_market_regime`, `market.short_term_sentiment`, and
  `market.mainline_environment` are returned with refs.
- 当前主线是什么，生命周期如何？ — `SUPPORTED_BY_CURRENT_EVIDENCE`;
  six `mainline.<index>.name` and `mainline.<index>.lifecycle` items are
  returned, with strong-stock counts where present.
- 分析师/Market复盘对下一交易日重点观察什么？ — `NOT_SUPPORTED` for the
  accepted `2026-05-15` source because `watchlists` and
  `post_market_setup_plan` are explicit missing modules. A later source may
  expose `calendar.next_trade_date`, but the current evidence adapter emits no
  watchlist/focus items. Missing public evidence fields are watchlist entries
  and next-day setup focus/reason.

Overall assessment: `PARTIALLY_SUPPORTED`; partial coverage is explicit and is
not converted into synthetic defaults.

## Verification

Focused public-boundary and regression suite:

```text
PYTHONPATH=. /opt/miniconda3/bin/pytest -q \
  tests/test_market_analysis_public_capability.py \
  tests/test_market_public_boundary.py \
  tests/test_market_public_integration.py \
  tests/test_market_stock_quote_public_capability.py

70 passed in 0.36s
```

Real database acceptance:

```text
PYTHONPATH=. MARKET_REAL_DB=1 /opt/miniconda3/bin/pytest -q \
  tests/test_market_public_real_integration_repair.py

4 passed in 2.58s
```

`git diff --check` passed. No `Julia_core` or `Julia-AI-Assistant` files were
changed.
