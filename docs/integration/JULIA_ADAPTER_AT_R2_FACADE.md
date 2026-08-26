# AT-R2 Domain Adapter Facade Notes

Status: AT-R2 implementation note. Transport, MCP, and broad degradation hardening remain out of scope.

## Selected Integration Points

### `market.snapshot`

Selected source boundary: injected `MarketContextExporter`-like object via `export(trade_date)`.

Reason:

- This is below the legacy MCP convenience wrapper.
- It already exposes explicit `status` and `missing_sources` concepts.
- It can preserve partial source failures before they are collapsed into a text response or fallback path.

Current AT-R2 behavior:

- no exporter configured -> `unavailable + empty` with explicit failure.
- exporter raises -> `error + empty` or timeout/unavailable with explicit failure.
- exporter returns `status=partial` plus `missing_sources` -> `partial + normal/stale` with source failures.
- exporter returns live/current object with no useful facts -> `success + empty` only after successful source execution.

### `market.alerts`

Selected source boundary: workbench `session.json` + `snapshot.json` + `ApprovedSnapshotValidator` + `AnalystIntelligenceExporter`.

Reason:

- This avoids `list_active_alerts()`, which AT-R0 proved collapses missing/invalid/exception states into `[]`.
- Missing source, invalid snapshot, JSON corruption, and exporter exception remain distinguishable from legitimate zero alerts.

Current AT-R2 behavior:

- missing session/snapshot -> `unavailable + empty`, explicit failure.
- invalid approved snapshot -> `unavailable + empty`, validation failure details.
- JSON/schema corruption -> `error + empty`, explicit failure.
- valid approved snapshot with no matching alerts -> `success + empty`.
- valid approved snapshot with matching alerts -> `success + normal`.

## Scope Audit

AT-R2 intentionally does not add:

- HTTP transport
- MCP registration
- Julia Core import
- Julia ToolResult/Evidence/Trace implementation
- Context OS behavior
- natural-language routing
- LLM operation selection
- trading/write behavior
- unrelated market algorithm refactor
- sibling-repository path dependency

## P0 Guardrail

No handler may emit `success + empty` unless successful source execution has been positively established.
