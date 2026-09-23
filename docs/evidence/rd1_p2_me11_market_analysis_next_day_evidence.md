# RD1-P2-ME1.1 — Next-Day Evidence Coverage Extension

## Boundary

- Task: `RD1-MARKET-ANALYSIS-EVIDENCE-COVERAGE-P0`
- Upstream ME-1 SHA: `edccd14d78c65d5aa8b90c54a9933919c9b08088`
- Upstream PR: #412
- Production change: `MarketEvidenceAdapter` only
- Public capability/request: unchanged `market.analysis.read` with exact
  `MarketAnalysisReadRequest(trade_date)`
- Domain behavior: deterministic projection of existing producer fields only
- Workbench binding: none
- Analyst maturity binding: none
- LLM/inference/ranking: none

## Real Source Audit

Inspected real exact-date source:

```text
trade_date = 2026-07-09
snapshot_version = daily_review_generate.full_truth_rebuild.fa111eb8
batch_id = 0750e71214c3
trace_id = 97b9a5d4cce7
```

The canonical producer shape contains 20 `watchlists.one_to_two.items` rows
and 20 `post_market_setup_plan.items` rows. Existing projected fields include:

```text
watchlists.one_to_two.items[index].stock_id
watchlists.one_to_two.items[index].stock_name
watchlists.one_to_two.items[index].subject_key
watchlists.one_to_two.items[index].summary
watchlists.one_to_two.items[index].watch_date
watchlists.one_to_two.items[index].decision
watchlists.one_to_two.items[index].setup_type

post_market_setup_plan.items[index].summary
post_market_setup_plan.items[index].technical_summary.reason
```

The audited source has no standalone `focus`, direct `reason`, or `rationale`
field on setup items. Those fields remain absent; no watchlist/focus/reason
value is generated or inferred.

## Public Evidence Result

For `2026-07-09`, `market.analysis.read` returns `SUCCESS / READY` with:

```text
source_bundle_id = mkb:2026-07-09:6696c603df3b75d6
evidence_snapshot_id = mes:2026-07-09:ccdbdbef4a76ef43
content_hash = ccdbdbef4a76ef43361a5506f92b0f3a820fb736aa9caaddffb238215111047a
total evidence items = 184
watchlist evidence items = 140
setup evidence items = 40
```

Representative first-row keys and values:

```text
calendar.next_trade_date = 2026-07-10
watchlist.0.stock_id = 600584.SH
watchlist.0.stock_name = 长电科技
watchlist.0.subject_key = 9015778
watchlist.0.summary = 低空经济 首板事实入池，明日仅观察1进2晋级确认。
watchlist.0.watch_date = 2026-07-10
watchlist.0.decision = observe_only
watchlist.0.setup_type = one_to_two
setup.0.summary = 低空经济 首板事实入池，明日仅观察1进2晋级确认。
setup.0.technical_reason = ma_not_bullish_alignment
```

Every added item preserves `ref_id`, `source_module`, exact `source_path`,
`source_snapshot_id`, and `observed_at`. Representative source paths:

```text
watchlists.one_to_two.items.0.stock_name
watchlists.one_to_two.items.0.summary
post_market_setup_plan.items.0.summary
post_market_setup_plan.items.0.technical_summary.reason
```

## Product-Question Coverage

No Julia reasoning or investment judgment was executed.

Q3 — Market/复盘对下一交易日重点观察什么？

- Assessment: `SUPPORTED_BY_CURRENT_EVIDENCE`
- Supporting keys: `calendar.next_trade_date`, 20 rows of
  `watchlist.<index>.stock_name`, `.summary`, `.watch_date`, `.decision`,
  and `.setup_type`
- Q4 source trace: every item carries its exact source path and `EvidenceRef`
  as shown above
- Remaining field-level gap: no standalone `setup.<index>.focus`; producer
  only exposes `summary.focus_count`, which is not projected as a focus value

Watchlist evidence is `PASS`. Setup focus evidence is `NOT_PRESENT`. Setup
reason evidence is `PARTIAL`: the producer-supported
`technical_summary.reason` is exposed, but no direct overall setup
`reason`/`rationale` field exists.

## Verification

Focused adapter, capability, boundary, and existing public regression:

```text
PYTHONPATH=. /opt/miniconda3/bin/pytest -q \
  stock_processing_service/tests/unit/test_m8_phase0_knowledge_evidence.py \
  stock_processing_service/tests/unit/test_m8_phase0_cognition.py \
  tests/test_market_analysis_public_capability.py \
  tests/test_market_public_boundary.py \
  tests/test_market_public_integration.py \
  tests/test_market_stock_quote_public_capability.py

79 passed in 0.46s
```

Real database acceptance:

```text
PYTHONPATH=. MARKET_REAL_DB=1 /opt/miniconda3/bin/pytest -q \
  tests/test_market_public_real_integration_repair.py

5 passed in 3.32s
```

The same source projects deterministically and retains the same evidence and
content hash on repeated adaptation. Missing producer fields stay absent.
