# R4-Prep Market Adapter Donor Isolation

Base: `08fc1a688c852a9894d6bcb77fb1e9cc14567045`
Donor: `067060d5e93478374981e6e4d12273f75c3ce0a6`
Branch: `glm-c/r4-prep-market-donor-isolation`

## Dependency disposition

| Donor dependency | Disposition | Reason |
|---|---|---|
| Adapter DTO/contract module | REQUIRED | Defines `AdapterRequest`, `DomainObservationEnvelope`, `SourceRecord`, and `SourceFailure`. |
| Adapter facade and operation registry | REQUIRED | Exact dispatch for `market.snapshot` and `market.alerts`. |
| Snapshot operation and provenance helper | REQUIRED | Thin exporter mapping and degradation semantics. |
| Alerts operation | REQUIRED | Approved workbench reading and claim filtering. |
| HTTP transport and configuration | REQUIRED | Exposes execute, health, and ready. |
| `MarketContextExporter` | REQUIRED_WITH_REBASE | Donor snapshot domain interface; absent at base, introduced outside adapter chain. |
| `DerivedContextReader` | REQUIRED_WITH_REBASE | Donor snapshot DB reader; absent at base, introduced outside adapter chain. Base contains its queried tables. |
| `ApprovedSnapshotValidator` | REQUIRED_WITH_REBASE | Donor alerts approval gate; absent at base. Base `ReviewSnapshot` supplies required fields. |
| `AnalystIntelligenceExporter` and contract | REQUIRED_WITH_REBASE | Donor alerts claim exporter; absent at base. |
| Standalone stdlib client | REQUIRED | Clean-base AT-R4 regression dependency. |
| Frozen JSON schema, fixture manifest, fixtures | REQUIRED | Contract and golden regression truth. |
| AT-R1/R2/R3/R4/R5/R7 tests | REQUIRED | Mandatory clean-base regression equivalents. |
| AT-R0/R2/R3/R4/R5/R6/R7 narrative documents | EXCLUDED | Historical reports are not runtime dependencies. |
| Donor mixed-lineage workbench/frontend/data changes | UNRELATED | Not required by the isolated adapter surface. |
| Optional theme/symbol future operations | EXCLUDED | Outside required v1 catalog. |

## Clean-base corrections

- Reject extra top-level `AdapterRequest` fields, matching frozen JSON Schema.
- Return HTTP 400 for invalid UTF-8 instead of an uncaught HTTP 500.
- Use the current Python executable for alternate-CWD regression rather than assuming `.venv/bin/python`.

## Regression scope

Clean-base equivalent coverage executes wire contract, snapshot facade, alerts facade, degradation/provenance, HTTP transport, fault matrix, deployment configuration, golden fixtures, extra-field rejection, and invalid-UTF-8 handling.

Latest result: **69 passed**.

This document is preparation evidence only and does not declare Market canonicalization.
