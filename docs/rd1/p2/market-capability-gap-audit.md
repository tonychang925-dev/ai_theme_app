# RD1-P2-I1 Market Capability Gap Audit

## Audit Scope

- **TASK_ID:** `RD1-P2-I1-MARKET-CAPABILITY-GAP-AUDIT`
- **MARKET_BASE_SHA:** `d183241dad266a50d9ad8b12d831734317edf7b7` (verified as local `main`)
- **CORE_CONTEXT_SHA:** `52cacb1e7e61acc5c48335303df2c51db9f8dd5c`
- **ASSISTANT_CONTEXT_SHA:** `1309b1d18a86346480d5196533d3245840d1ff24`
- **RESEARCH_CANDIDATE_CONTEXT:** commit `20968507ddef842bacb7b84a1b0da2cbed1b88ec`, present on the local Core research branch; it defines bounded `research.web.query` evidence. This audit treats it as context only and does not depend on merge.
- **Decision rule:** recommend a public capability only when the first real composite investment E2E cannot produce a defensible Julia judgment without it. Convenience, catalog completeness, or speculative future tools are not sufficient reasons.

## CURRENT_CAPABILITY_MATRIX

| Public capability | Current public request | Current public result semantics | Private implementation source | Coverage verdict |
|---|---|---|---|---|
| `market.event.resolve` | `{feed_date?: YYYY-MM-DD, stock_id?: string, limit: 1..200}` | Ordered internal event rows for the target feed date/stock; empty is a valid `EMPTY` result | `Phase1ReadRepository.fetch_intel_feed(..., item_type="event")` via `market_public/factory.py` | Covers discovery of internal same-day event catalysts. It does not provide an event-to-theme-to-stock expansion or broad market state. |
| `market.event.read` | `{event_id: positive integer}` | One event payload if present in the implementation's current 200-row event scan | `Phase1ReadRepository.fetch_intel_feed(item_type="event", limit=200)` | Covers detail retrieval for recently resolved events. It is not a historical archive reader. |
| `market.product.read` | `{subject_key: string}` | One theme/product object: identity, binding, summary/detail metadata, and aggregate `history_count`, `children_count`, `stock_count` | `Phase1ReadRepository.fetch_theme_detail` | Covers product identity and existence only. It intentionally does not return linked stocks, leader roles, historical rows, or market breadth. |

### Boundary Observations

- Core context registers exactly the three public Market capabilities above, plus candidate `research.web.query`; it does not define a substitute Market provider.
- The public Market envelope already carries operation status, data state, provenance, typed failures, and boundary identity. Every recommended capability should reuse this envelope rather than invent a second result protocol.
- Existing `market.product.read` semantics are frozen. Adding link rows to its payload would be a semantic expansion and is therefore not an option.

## REPRESENTATIVE_PRODUCT_SCENARIOS

### S1 — Theme/event catalyst analysis

**Question:** “今天固态电池事件中，哪些内部事件是可信催化剂，强度和语义是什么？”

- **Julia evidence need:** discover date-scoped internal events, then read the selected event's structured fields and provenance.
- **Current fit:** **YES** — `market.event.resolve` followed by `market.event.read`.
- **Missing shape:** none for this scenario.
- **Classification:** no new capability.
- **Private wiring:** already present through `MarketPublicFactory -> _LazyPhase1Repository -> Phase1ReadRepository.fetch_intel_feed`.
- **New DB/repository wiring:** no.

### S2 — Theme-to-stock linkage and leaders

**Question:** “这个固态电池主题下，哪些股票是核心成分、哪些是 leader overlay，关系依据和排序是什么？”

- **Julia evidence need:** expand one `subject_key` into a bounded list of stock identities with relation type, mapping scope, source, reason/confidence, ordering, and latest available display price/pct change.
- **Current fit:** **NO.** `market.product.read` returns only `stock_count`; it deliberately does not expose rows.
- **Exact missing data shape:** list of logical linkage rows containing `subject_key`, `theme_id`, `theme_name`, `stock_id`, `stock_name`, `relation_type_candidate`, `mapping_scope`, `source_type`, `reason`, `remark`, `confidence`, `top`, `sort`, `price`, `pct_chg`, and `stock_remark`. HTML detail should not be exposed.
- **E2E classification:** **BLOCKING.** Julia cannot distinguish a named theme from investable constituents/leaders, so a composite investment judgment would collapse into unsupported narrative.
- **Candidate capability:** `market.product.linkage.read`.
- **Logical request:** `{subject_key, mapping_scope: pool|leader_overlay|all, include_leaders: boolean, limit}`.
- **Logical result:** linkage rows in Market's canonical envelope; `READY`, `EMPTY`, object-not-found, and dependency failures must remain typed.
- **Private implementation source:** `Phase1ReadRepository.fetch_stocks_by_theme` already implements deduplication, leader priority, source priority, ordering, and bounded output.
- **New DB/repository wiring:** no new repository or migration; add a lazy proxy/adapter in the existing Market factory boundary.

### S3 — Current market state / breadth

**Question:** “今天这个催化是否发生在有利的大盘环境：涨跌家数、涨跌停和成交额如何？”

- **Julia evidence need:** one authoritative whole-market post-close snapshot containing up/down counts, up ratio, limit-up/down counts, turnover, source authority, and trade date.
- **Current fit:** **NO.** Event and theme capabilities contain no broad-market facts.
- **Exact missing data shape:** `{trade_date, breadth: {up_count, down_count, up_ratio, limit_up_count, limit_down_count, turnover_yi}, source}`.
- **E2E classification:** **BLOCKING.** An investment judgment that ignores whether the catalyst occurred in risk-on or risk-off breadth is materially incomplete and cannot be validated as a composite decision.
- **Candidate capability:** `market.state.read`.
- **Logical request:** `{trade_date?: YYYY-MM-DD}`; omitted date means latest available closed snapshot, never an invented live quote.
- **Logical result:** the minimal snapshot above in the canonical envelope. If only older data exists, return `STALE` with the authoritative date rather than relabeling it current.
- **Private implementation source:** `stock_processing_service/application/services/market_metrics/MarketMetricsService._get_async_with_conn` and its breadth builder; metric authority is documented in `market_metrics/registry.py`.
- **New DB/repository wiring:** **YES, repository wiring only.** The service is already Market-owned, but `MarketMetricsService` hard-codes its DSN and exposes sync `asyncio.run` wrappers, so it is not safely composable by the async `MarketPublicFactory`. Add an injectable async read adapter/pool; no schema or migration is required.

### S4 — Historical confirmation

**Question:** “该主题最近是否反复出现？历史热度、涨跌幅和关联事件时间线是什么？”

- **Julia evidence need:** bounded, source-typed historical rows for one subject, including rank/event date, description, heat, pct changes, event id where applicable, and source ref.
- **Current fit:** **NO.** `market.product.read` exposes only `history_count`; `market.event.resolve` resolves a feed date rather than returning a subject timeline.
- **Exact missing data shape:** timeline rows containing `subject_key`, `rank_date`, `description`, `heat`, `heat_name`, `pct_chg`, `his_pct_chg`, nullable `event_id`, `source_type`, and `source_ref`.
- **E2E classification:** **OPTIONAL for the first composite E2E, blocking only for a scenario explicitly requiring recurrence confirmation.** The first E2E should select a current catalyst so it can remain minimal and avoid conflating event history with causal backtest claims.
- **Candidate capability:** `market.product.history.read`.
- **Logical request:** `{subject_key, limit}`; use bounded limits and descending date order.
- **Logical result:** source-typed historical rows in the canonical envelope, with `EMPTY` when no timeline exists.
- **Private implementation source:** `Phase1ReadRepository.fetch_history`.
- **New DB/repository wiring:** no new repository or migration; extend the existing lazy adapter only if this optional capability is accepted.

### S5 — Market facts plus external Research evidence

**Question:** “结合内部市场事实和外部证据，这个机器人零部件主题是可持续主线还是孤立事件？哪些标的值得跟踪？”

- **Julia evidence need:** internal event catalyst, product identity, stock/leader linkage, broad-market state, and externally sourced evidence on demand durability or industry change; Julia must reconcile those planes and own the final judgment.
- **Current fit:** **PARTIAL.** Event/product facts and candidate `research.web.query` are available, but S2 linkage and S3 state are missing.
- **Missing shapes:** exactly the S2 linkage rows and S3 market-state snapshot.
- **E2E classification:** **BLOCKING because of S2 and S3**; no additional Research-shaped Market capability is justified.
- **Candidate capability:** no capability beyond S2/S3.
- **Private wiring:** Market sources above; Research candidate context supplies one bounded source-cited web query and explicitly prevents the research worker from making Julia's final judgment.
- **New DB/repository wiring:** only the repository wiring already identified by S3.

## BLOCKING_GAPS

1. **Product-to-stock linkage facts:** `market.product.read` exposes a count but no constituent/leader rows. Private read logic already exists.
2. **Whole-market state facts:** no public capability exposes breadth, limits, and turnover. Private canonical metric logic exists but is not injection-composable with `MarketPublicFactory`.

No blocking gap exists for internal event resolution, event detail, product identity, or external Research evidence within the stated first composite E2E.

## NON_BLOCKING_WISHLIST

- **Subject history timeline:** useful for recurrence questions and later confirmation, but intentionally deferred from the first E2E to avoid turning a current catalyst judgment into an unsupported causal/backtest claim.
- **Deep event archive read:** the current `market.event.read` scans a bounded recent event set. A direct repository lookup could improve old-event coverage, but the first E2E can constrain its selected event to the resolvable recent set.
- **Theme reverse lookup by stock:** `Phase1ReadRepository.fetch_themes_by_stock` exists, but no representative first-E2E scenario requires stock-to-theme expansion.
- **Market metric suite:** limit ecology, leader evolution, loss effect, and capital metrics should remain private until a concrete Julia scenario requires them.

## MINIMUM_RECOMMENDED_NEXT_CAPABILITIES

| Classification | Capability | Minimum semantics | Why minimal |
|---|---|---|---|
| BLOCKING | `market.product.linkage.read` | Bounded theme-to-stock rows with leader/core semantics, source, reason/confidence, and ordering | Reuses existing repository logic; answers S2/S5 without widening `market.product.read`. |
| BLOCKING | `market.state.read` | Latest-or-requested post-close whole-market breadth snapshot: up/down, ratio, limit counts, turnover, source/date | Exposes only the state facts used by S3/S5; keeps advanced metric suites private. |

**Recommended total:** two public capabilities. `market.product.history.read` is designed but deliberately not recommended for P2-I4.

## IMPLEMENTATION_ORDER

1. **Market state repository adapter:** introduce Market-owned async wiring around the existing canonical metric builder, with injectable database configuration, post-close date resolution, and explicit `STALE` behavior.
2. **Market linkage adapter:** expose bounded `fetch_stocks_by_theme` semantics through a new request/result contract and the existing lazy Phase1 adapter.
3. **Public contract/tests:** add the two capabilities to Market-owned contracts, provider validation, typed empty/not-found/dependency behavior, provenance, and Core registration binding tests.
4. **Composite E2E:** execute S5 with Market event/product/linkage/state plus Research external evidence; verify Julia—not Research—issues the revised hypothesis and final judgment.
5. **Deferred history:** revisit `market.product.history.read` only after the first E2E proves that current-catalyst judgment needs recurrence evidence.

This order resolves the repository-boundary risk first, then maximizes reuse of already-proven read logic.

## RISKS / DATA FRESHNESS / SOURCE AUTHORITY

- **Market state freshness:** the metric registry describes breadth as T+0 but medium-confidence and recap-derived; TDX is a fallback. P2-I4 must pin an accepted closed trade date and surface `source`/`trade_date`, never present stale data as current.
- **Linkage authority:** linkage rows come from candidate mappings with multiple source types. Preserve `source_type`, `mapping_scope`, `relation_type_candidate`, confidence, and the repository's deterministic deduplication; do not collapse them into a single editorial fact.
- **Historical semantics:** mixed rank/event sources are observations, not a causal return series. This is the main reason history is optional for the first E2E.
- **Research separation:** external findings must retain source URLs/refs and limitations. Market cannot absorb Research semantics, and Research cannot manufacture internal market facts.
- **Failure behavior:** both blocking capabilities must fail closed with typed Market failures. Empty linkage/state is evidence, not an exception; dependency loss is `UNAVAILABLE`, not synthetic data.
- **Configuration:** market state adapter must use `MARKET_DATABASE_URL`/`DATABASE_URL` precedence already established by `MarketPublicFactory`; the hard-coded metric DSN must not leak into public composition.
- **Schema:** no migration is needed. Repository wiring and public contracts are sufficient for both blocking recommendations.

## RECOMMENDATION_FOR_P2-I4

Authorize only **`market.product.linkage.read`** and **`market.state.read`** before composite E2E. They are the smallest Market-owned additions that let Julia distinguish a real theme's constituents/leaders, place the catalyst in whole-market context, combine those internal facts with external Research evidence, and retain final judgment ownership.

Do not implement product history, reverse stock lookup, the full metric suite, schema changes, or broad catalog APIs in P2-I4. Keep the E2E scenario current-date and post-close so those additions remain unnecessary.
