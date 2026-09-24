# HISTORICAL_COGNITION_FAILURE_FIXTURES_v1

## Authority

- `TASK_ID = POST-RD1-E1-E-HISTORICAL-COGNITION-ACCEPTANCE-P0`
- `START_HEAD = 97a8eb4257cdbde75ee632884c5bd1cbb6bc442c`
- Governing contract: `HISTORICAL_COGNITION_ACCEPTANCE_CONTRACT_v1.md`

These are contract-level negative fixtures. They define expected fail/degrade behavior; they do not implement a fault injector, fixture runner, replay runtime, connector, or production source.

## Typed-failure mapping rule

For every failure fixture, its condition, forbidden fallback, and STOP/exclusion/degradation requirement are frozen by this contract. An exact typed public failure mapping is frozen only when an existing Owner-frozen contract mechanically supports that type for the exact input path and the fixture report cites that mapping. Otherwise the exact typed public failure mapping is `DEFERRED / NOT_YET_FROZEN`; the acceptance report MUST NOT invent a new failure vocabulary or normalize the observed failure into an unsupported type.

## Failure matrix

| ID | Trigger / input corruption | Required failure/degradation behavior and typed-mapping status | Forbidden fallback | Ownership/provenance behavior | Julia review effect | Execution |
|---|---|---|---|---|---|---|
| HF-001 | Exact-date Market snapshot is contractually absent | Preserve `SUCCESS/EMPTY/None` and typed provenance; record missing Market evidence | Latest date, adjacent date, synthetic payload, or failure-to-empty rewrite | Market ownership and exact request identity preserved | Missing evidence visible; item `DEFERRED` or review `INCONCLUSIVE` only after Julia cognition | Continue only if remaining inputs satisfy review contract; otherwise STOP |
| HF-002 | Unapproved or noncanonical analyst snapshot/maturity is supplied | Exclude as canonical approved augmentation; retain as explicitly noncanonical input/claim where auditable | Promote draft/unapproved/tmp state to approved or published | Analyst owner preserved; no maturity binding invented | Julia may challenge/defer the claim as a claim, not approved truth | Continue with Market + external + StrategyKnowledge path |
| HF-003 | Corrupt Market snapshot/input blocks exact projection | Fail closed and STOP; no analytical payload. Exact typed public failure = `DEFERRED / NOT_YET_FROZEN` unless an existing frozen Market mapping mechanically applies and is cited | Parse around corruption, guess fields, synthesize partial success, or invent a public failure type | Failure identity and available input ownership preserved | No judgment based on corrupted evidence; missing evidence explicit | STOP when required Market evidence is unusable |
| HF-004 | Digest/content identity mismatch | Reject the mismatched binding and STOP; no silent recompute or acceptance. Exact typed public failure = `DEFERRED / NOT_YET_FROZEN` unless an existing frozen type is mechanically cited | Recompute identity silently, accept mismatch, or downgrade to warning | Original and expected identities remain separately recorded | Dependent items cannot be accepted/challenged without valid refs | STOP for affected review dependencies |
| HF-005 | Unsupported schema/contract version | Reject and STOP; no normalized payload or schema conversion. Exact typed public failure = `DEFERRED / NOT_YET_FROZEN` unless an existing frozen contract type is mechanically cited | Schema guessing, default conversion, best-effort interpretation, or new schema-failure vocabulary | Requested and observed versions preserved | No review from ungoverned semantics | STOP |
| HF-006 | Input is stale and staleness is mechanically knowable | Exclude at the historical-acceptance/cutoff layer; record explicit stale/missing dependency. This does not imply `market.analysis.read` emits a frozen `STALE` state | Use stale input, shift cutoff, select current version, or invent producer `STALE` semantics | Source owner and available time preserved | Missing/open question visible; no hindsight judgment | Continue only if cutoff-compliant inputs suffice; otherwise STOP or `INCONCLUSIVE` after cognition |
| HF-007 | Market provenance is explicitly incomplete | Continue only as evidence with frozen limitations; preserve `PROVENANCE_INCOMPLETE` and `UNKNOWN` origin where applicable | Manufacture field-level origin, release identity, governance, or completeness | Market ownership and all supplied refs preserved | Julia may accept/challenge/defer only with explicit limitation and refs | Continue unless a separate dependency requires complete provenance |
| HF-008 | External research partially fails | Preserve explicit partial-success/failure state and available refs | Fabricate completeness, relabel as Market evidence, or hide failed source | External owner/provenance preserved for every available and failed source | Available external evidence may inform review; gaps produce `DEFERRED`/open questions or review `INCONCLUSIVE` | Continue only if review contract remains satisfiable; otherwise STOP |

## Required assertions

Each executed failure fixture MUST report:

1. exact trigger and corrupted/malformed input identity;
2. observed failure/degradation state and its exact typed-public-failure mapping, or explicit `DEFERRED / NOT_YET_FROZEN`;
3. all preserved upstream ownership/provenance refs;
4. excluded or missing evidence;
5. Julia review effect, if review remains permissible;
6. whether execution stopped;
7. zero silent fallback, schema guessing, ownership mutation, authority promotion, Runtime-minted semantics, or hindsight leakage.

Expected failure is acceptance success only when the failure/degradation occurs exactly in the designed boundary. An unintended failure, unexpected success, or silent recovery is a gate failure.
