# AT-R3 Degradation + Provenance Notes

Status: AT-R3 implementation note. HTTP transport, MCP registration, Julia Core mapping, and unrelated market algorithm refactor remain out of scope.

## Preserved Integration Points

- `market.snapshot` still uses the lower-level `MarketContextExporter`-like `export(trade_date)` boundary.
- `market.alerts` still uses `session.json + snapshot.json + ApprovedSnapshotValidator + AnalystIntelligenceExporter`.
- The adapter still does not call legacy convenience wrappers that collapse failure into empty lists.

## Failure Matrix

| Case | Result |
|---|---|
| snapshot normal | `success + normal` |
| alerts normal | `success + normal` |
| legitimate zero alerts | `success + empty` only after approved snapshot validates |
| optional single source failure | `partial + normal/stale` with explicit failure |
| multiple source failures | `partial + normal/stale` with all failures preserved |
| required source missing | `unavailable + empty` with explicit failure |
| DB unavailable | `unavailable + empty`, `UPSTREAM_UNAVAILABLE` |
| Redis unavailable | explicit source failure with `dependency=redis` |
| upstream exception | `error + empty`, `INTERNAL_ERROR` |
| timeout | `unavailable + empty`, `UPSTREAM_TIMEOUT` |
| stale source | `data_state=stale`, source freshness stale |
| schema mismatch | `error + empty`, `SCHEMA_MISMATCH` |
| partial response | successful payload/source_records preserved, failed source_records retained |

## Source Provenance Model

Every source material record emitted by the adapter uses provider-native `SourceRecord`:

- `source_type`
- `source_name`
- `source_ref`
- `as_of`
- `observed_at`
- `freshness`
- `status`
- `provenance`
- optional `failure`

`SourceRecord` maps to future Julia C-12 Evidence. It is not Julia Evidence.

## Hard Invariants

- Provider/dependency exception never becomes `success + empty`.
- Partial source failure never erases successful payload/source material.
- `success + empty` means successful source execution positively established a legitimate zero-result condition.
- Top-level `status` is always interpreted before `data_state`.
