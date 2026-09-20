# RD1-P2-I1F Real Integration Repair Evidence

## Candidate Scope

- Repair base: `0e6b599614842085e3f6cb505a0695ae5a80d1c3`
- Core context: `71919611416ad8c440f8a2d06995947181d846f4`
- Preflight evidence base: `32eb97dad2356b1631aacd98abc9da96b50d34de`
- Scope: Market-only repair of MKT-I1E-01, MKT-I1E-02, and the narrowly authorized `2026-05-15` persisted-state projection defect.

## MKT-I1E-01

The public contract still accepts canonical `YYYY-MM-DD`. `Phase1MarketStateReadRepository` now parses that string with `date.fromisoformat` and binds the resulting Python `date` to asyncpg. It does not select a latest date or use another source.

Focused type-sensitive repository evidence asserts the bound argument is a Python `date`, not a string. Real execution for `2026-07-10` returns:

```text
operation_status = SUCCESS
data_state = EMPTY
failures = ()
```

This closes the original `repository_protocol_failed` defect.

## MKT-I1E-02

`EventReadRequest` is contract version `0.3.1` and now accepts exactly one selector:

- canonical source-namespaced `item_id`; or
- legacy positive integer `event_id`.

Canonical `event:<news_event_id>:<subject_key>` performs an exact news-event/subject query. Canonical `event:jyhf_cdp:<staging_id>` performs an exact staging-identity query. Legacy IDs first check the news-event namespace, then JYHF CDP, without a top-N scan. Malformed selectors remain `CONTRACT_MISMATCH`; missing identities remain `OBJECT_NOT_FOUND`.

Real source-family roundtrips succeeded:

- JYHF CDP: `event:jyhf_cdp:166793`
- News event: `event:128787:9015778`

Both reads returned `SUCCESS/READY` with the exact resolve identity preserved.

## Narrow State Projection Repair

The frozen `2026-05-15` row remains bound to the exact requested date and is read once from `post_market_recap_snapshot`. The reader now normalizes only within that already-selected payload:

```text
payload.market_overview_review
payload.recap_doc.market_overview_review
```

If both review fields exist and conflict, projection fails closed. The public source reflects the physical selected path, and the row identity exposes the persisted non-empty `snapshot_version`. There is no second query, alternate table, latest-date selection, TDX read, board-pool read, `MarketMetricsService`, or synthetic reconstruction.

Real execution for frozen `2026-05-15` returns:

```text
operation_status = SUCCESS
data_state = READY
trade_date = 2026-05-15
source = post_market_recap_snapshot.payload.recap_doc.market_overview_review
failures = ()
```

Real execution for no-row `2026-07-10` still returns `SUCCESS/EMPTY`.

## Exact #124 Rerun

The exact #124 harness was run against the repaired Market code. All five capabilities passed:

```text
market.event.resolve        SUCCESS / READY
market.event.read           SUCCESS / READY
market.product.read         SUCCESS / READY
market.product.linkage.read SUCCESS / READY
market.state.read           SUCCESS / READY
```

Core execution and envelope semantic preservation passed for all five capabilities. The frozen state check confirms the exact `2026-05-15` date and row source identity. The linkage projection check confirms all narrow fields, excludes `detail_html`/`price`/`pct_chg`, and preserves `source_type`.

## Supplemental Diagnostic

A separately classified diagnostic reran the same #124 composition with exact state date `2026-07-10`, for which no snapshot row exists. It returned `SUCCESS/EMPTY` and the overall composition was `REAL_INTEGRATION_PASS`. This is supplemental isolation evidence only and is not claimed as the required exact #124 acceptance rerun.

## Truth Boundary

No fallback, mock primary evidence, synthetic success, schema change, Core change, Assistant change, merge, release, or deployment was used.
