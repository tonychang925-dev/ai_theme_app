# Current-Main Capability Contract v0.1

Status: OWNER FREEZE CANDIDATE  
Repository: `ai_theme_app`  
Canonical base: `95d2178d4bcffdd854c632fc28cb7904c55cf37c`  
Scope: read-only public capability contract  
Implementation: NOT AUTHORIZED BY THIS DOCUMENT

## 1. Purpose

Define the first stable, read-only capability boundary by which an external reasoning system such as Julia Core may consume Market Brain outputs without importing Market internal Python modules, accessing PostgreSQL directly, or consuming internal Redis decision streams.

This contract is derived from current-main DTOs, snapshots, readers, and REST behavior. It does not restore the historical `market_public_boundary` or `julia_domain_adapter` implementations.

## 2. Ownership and boundary

Market owns all computation, persistence, and internal mutation.

External consumers MUST NOT:

- import `stock_processing_service.application.*` or `stock_processing_service.domain.*` across repository boundaries;
- write Market durable state directly;
- access Market PostgreSQL tables directly;
- consume or mutate internal Redis decision streams;
- invoke `DecisionExecutor` or other internal pipeline executors;
- treat legacy `event_theme_map` as canonical event-subject authority.

External consumers MAY consume the read-only capabilities defined below through a future typed facade or transport adapter.

## 3. Common envelope

Every public capability response MUST expose the following envelope fields:

```json
{
  "capability": "market.<name>.read",
  "contract_version": "0.1",
  "as_of": "<ISO-8601 or YYYY-MM-DD>",
  "status": "ok | missing | partial | unavailable | invalid_request",
  "data": {},
  "provenance": {
    "source_authority": "<canonical authority>",
    "source_version": "<snapshot/schema/version when available>",
    "trace_id": null,
    "batch_id": null,
    "source_trace_id": null
  },
  "diagnostics": {}
}
```

Rules:

- `status=ok` requires a valid canonical source and usable data.
- `status=missing` means the canonical source was successfully queried but no record exists for the requested key/date.
- `status=partial` means the canonical source exists but one or more declared optional sections are unavailable; missing sections MUST be named in `diagnostics`.
- `status=unavailable` means the canonical source could not be queried or verified.
- `status=invalid_request` means request validation failed.
- Transport success MUST NOT convert source failure into `status=ok`.
- No fallback to a lower-authority source is permitted unless a future contract version explicitly names and orders such sources.

## 4. Capability: `market.snapshot.read`

Purpose: read a canonical synthesized Market snapshot by snapshot type and trade date.

Request:

```json
{
  "snapshot_type": "pre_market_brief | post_market_recap",
  "trade_date": "YYYY-MM-DD"
}
```

Response `data`:

```json
{
  "trade_date": "YYYY-MM-DD",
  "snapshot_type": "pre_market_brief | post_market_recap",
  "snapshot_version": "string",
  "payload": {},
  "generated_at": null,
  "finalized_at": null,
  "updated_at": null
}
```

Canonical authority:

- `pre_market_brief` -> pre-market brief snapshot store;
- `post_market_recap` -> post-market recap snapshot store.

Provenance:

- `snapshot_version` MUST be surfaced as `source_version`;
- `trace_id` / `batch_id` SHOULD be surfaced when present in the underlying snapshot DTO or row.

Not guaranteed in v0.1:

- any internal shape of `payload` beyond JSON object semantics;
- direct access to underlying write ports;
- reconstruction from non-canonical historical tables when snapshot is missing.

## 5. Capability: `market.event.read`

Purpose: read canonical Market event intelligence for a trading date, optionally filtered by subject or stock.

Request:

```json
{
  "trade_date": "YYYY-MM-DD",
  "session": "all | pre | intra | post",
  "item_type": "all | event | event_review | theme_move | new_theme | stock_move",
  "subject_key": null,
  "stock_id": null,
  "limit": 100
}
```

Response `data`:

```json
{
  "items": [],
  "count": 0,
  "trade_date": "YYYY-MM-DD",
  "session": "all",
  "item_type": "all"
}
```

Canonical authority:

- current `NewChainIntelFeedAdapter` read path;
- canonical event-subject mapping authority is `event_subject_map`;
- structured event authority is `news_event`;
- raw-news authority is `news_raw`.

Rules:

- legacy Phase1 read fallback is forbidden;
- `event_theme_map` MUST NOT be used as the canonical event-subject source;
- subject and stock filters are read filters only and MUST NOT mutate event mappings.

## 6. Capability: `market.subject.read`

Purpose: read a subject/theme context without granting the caller direct DB access.

Request:

```json
{
  "subject_key": "string",
  "trade_date": "YYYY-MM-DD"
}
```

Response `data` minimum contract:

```json
{
  "subject_key": "string",
  "subject_name": "string",
  "trade_date": "YYYY-MM-DD",
  "context": {},
  "event_summary": null,
  "event_stats": {},
  "stock_pool": [],
  "mainline": null
}
```

Canonical authority:

- subject context / subject registry read models;
- `event_subject_map + news_event` for canonical subject-event relations;
- subject-stock canonical read models for stock membership;
- mainline registry/state for mainline status.

Explicit v0.1 exclusion:

- the existing `/api/v1/theme/workspace/{subject_key}` implementation MUST NOT be treated as the public contract itself because it directly queries PostgreSQL staging tables and mixes presentation-oriented sections with authority-bearing data.

## 7. Capability: `market.metrics.read`

Purpose: read canonical market facts for one trading date.

Request:

```json
{
  "trade_date": "YYYY-MM-DD"
}
```

Response `data` minimum contract:

```json
{
  "trade_date": "YYYY-MM-DD",
  "breadth": {},
  "limitup": {},
  "emotion": {},
  "capital": {},
  "calibration": {
    "applied": false,
    "source": null,
    "fields": []
  }
}
```

Canonical authority:

- `MarketMetricsService` current-main canonical facts.

Rules:

- optional external board-pool enrichment is NOT part of the v0.1 authority contract;
- failure to fetch an optional external provider MUST NOT silently change canonical facts;
- public provenance MUST identify the source used for each major metric family when available.

## 8. Capability: `market.mainline.read`

Purpose: read confirmed mainline identity and lifecycle state.

Request:

```json
{
  "trade_date": "YYYY-MM-DD",
  "subject_keys": [],
  "active_only": true,
  "limit": 100
}
```

Response `data`:

```json
{
  "items": [
    {
      "subject_key": "string",
      "theme_name": "string",
      "identity_status": "string",
      "is_main_theme": true,
      "composite_score": 0.0,
      "final_cycle_state": "string",
      "final_mainline_alive": true,
      "mainline_strength_score": 0.0,
      "fade_watch": false,
      "fade_confirmed": false,
      "trigger_flags": []
    }
  ]
}
```

Canonical authority:

- mainline registry for confirmed identity;
- mainline daily state / lifecycle state for dated status.

Contract source models:

- `MainlineIdentityDTO`;
- `MainlineCycleDTO`.

Rules:

- do not infer active status from theme heat or UI ranking alone;
- do not reconstruct missing mainline state from narrative text.

## 9. Capability: `market.recap.read`

Purpose: read the canonical post-market analytical recap as a reasoning-ready Market artifact.

Request:

```json
{
  "trade_date": "YYYY-MM-DD"
}
```

Response `data`:

```json
{
  "trade_date": "YYYY-MM-DD",
  "snapshot_version": "string",
  "recap": {},
  "module_coverage": {},
  "diagnostics": {}
}
```

Canonical authority:

- post-market recap snapshot produced by the current post-market job pipeline.

Expected producer chain includes current-main runtime capabilities such as:

- market regime;
- active mainline universe;
- PostMarketDecisionV2;
- market cognition / evidence layers when present;
- analyst-workbench approved artifacts when the requested surface requires approval.

Rules:

- missing snapshot -> `status=missing`, never synthetic reconstruction;
- approval state MAY be surfaced but MUST NOT be fabricated from draft state;
- draft workbench artifacts are not equivalent to approved recap authority.

## 10. Failure contract

Public failures MUST be typed into one of:

```text
INVALID_REQUEST
SOURCE_MISSING
SOURCE_UNAVAILABLE
SOURCE_PARTIAL
CONTRACT_VIOLATION
UNSUPPORTED_CAPABILITY
```

Each failure MUST include:

```json
{
  "code": "SOURCE_MISSING",
  "message": "human-readable message",
  "retryable": false,
  "source_authority": "post_market_recap_snapshot",
  "details": {}
}
```

No public adapter may convert an exception, empty fallback, or unavailable source into a successful payload with invented values.

## 11. Provenance contract

At minimum, provenance SHOULD include when available:

- source authority name;
- snapshot/schema version;
- trade date / `as_of`;
- `trace_id`;
- `batch_id`;
- `source_trace_id`;
- source type / source channel for event intelligence;
- calibration source for market metrics.

Public consumers MUST treat provenance as metadata about the Market result, not as authority to mutate the source.

## 12. Explicitly not authorized in v0.1

This contract does NOT authorize:

- implementation of a new transport adapter;
- Julia Core integration;
- MCP exposure;
- HTTP route creation;
- database schema changes;
- direct write capabilities;
- event or decision execution capabilities;
- fallback or synthetic reconstruction;
- resurrection of historical `market_public_boundary` or `julia_domain_adapter` source.

## 13. Next gate

The next allowed step after Owner acceptance is a shadow-only implementation experiment that maps current-main read models into this contract without changing production routing or durable state.
