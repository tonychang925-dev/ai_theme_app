# Julia Domain Adapter Operation Catalog v1.0

## Required Operations

### `market.snapshot`

Purpose: return read-only market-domain facts and summary context from ai_theme_app.

Allowed arguments:

- `trade_date`: optional ISO date string.
- `freshness_policy`: optional provider-native object for stale classification.

Preferred internal sources after AT-R1:

- `MarketContextExporter`
- `DerivedContextReader`
- workbench approved snapshot facts only when source status is preserved

Expected payload shape is provider-native and may include:

- `market_state`
- `themes`
- `quality`
- `summary`

### `market.alerts`

Purpose: return high-importance provider-native market observations/claims.

Allowed arguments:

- `trade_date`: optional ISO date string.
- `min_attention_level`: optional `CRITICAL | HIGH | MEDIUM | LOW`, default `HIGH`.

Preferred internal sources after AT-R1:

- approved workbench snapshot
- `ApprovedSnapshotValidator`
- `AnalystIntelligenceExporter`

Important: the existing `list_active_alerts` function must not be used as-is because it collapses failures into `[]`.

## Optional Later Operations

Not required for v1:

- `market.theme.details`
- `market.symbol.context`

These require hard-coded path removal, source/freshness normalization, and diagnostics redaction first.
