# RD1 Fixture E2E Research Chain Report

## 1. Exact repository SHAs

| Repository | Role | SHA | State |
|---|---|---|---|
| `ai_theme_app` | M1B | `52893734532cdcab54d382c94037263de3eeb194` | Local HEAD, remote-verified before F1 |
| `Julia_core` | C1 + C2 | `4253dd4011f11fef663a3919117ab54c29fecb7a` | Local HEAD |
| `Claude_client` | D1-F1 | `b8ae48a9972ba5bf2f0e4b1db5a1025e38e97e82` | Local HEAD |

The parent chain for C2 is `ac25125045f0997da69693e19581eebf544764cd` → `4253dd4011f11fef663a3919117ab54c29fecb7a`. The D1-F1 parent is `889173478514a605cf59e2ded9a6af65ed926684`.

## 2. Harness topology

The intended topology remains:

```text
fixture Market event
→ market.event.read envelope
→ M1B MarketEventResearchComposer
→ C1 CapabilityRequest
→ fixture CapabilityCall
→ D1 research.bridge.response.v1
→ D1-F1 projection
→ ProviderExecutionOutcome
→ C1 ResearchEvidenceNormalizer
→ C2 JuliaSession.form_preliminary_research_judgment
```

Implementation of the full committed harness stopped at the D1-F1 → C1 authority seam because the exact frozen contracts cannot satisfy the F1 happy-path PASS criterion.

## 3. No-live proof

No live network or live provider was invoked during this audit.

The deterministic cross-contract reproduction used:

- an in-process D1 fixture delegate;
- one fixture WebSearch result containing a URL;
- one fixture WebFetch result with deterministic raw/content digests;
- frozen epoch `123`;
- no process/network provider;
- no Claude;
- no DB;
- no external URL access.

Existing native D1 tests also use deterministic local fixtures and do not access the public network.

## 4. Happy-path fixture

A valid Market fixture and D1 action fixture were constructed in `/private/tmp` for diagnosis only:

- successful WebSearch candidate;
- successful WebFetch observation;
- valid raw-response SHA-256;
- valid content SHA-256;
- exact D1-F1 capability request/call identity injection;
- successful C1 request/call;
- `ProviderExecutionOutcome.status=SUCCESS`;
- exact D1-F1 `projectResearchBridgeResponse()` output passed unchanged to `ResearchEvidenceNormalizer`.

The result was:

```json
{
  "claim_count": 0,
  "source_kinds": ["web_fetch"],
  "binding_count": 1,
  "evidence_states": ["NOT_PROVEN"]
}
```

This is the exact frozen-contract result, not a synthetic or bypassed result.

## 5. Provenance chain

The following links are proven:

```text
Market event_id/source_trace_id
→ M1B deterministic projection_id
→ C1 CapabilityRequest ID
→ fixture CapabilityCall ID
→ D1-F1 injected request/call IDs
→ source_record_id
→ raw_response_ref
→ content_digest
→ C1 runtime provenance
```

The chain cannot continue to a `SOURCE_VERIFIED` C1 Evidence state under exact D1-F1 output because there is no semantic claim to bind.

D1-F1 also upgrades the search and fetched URL to the same deterministic `source_record_id`; the projected source record is `web_fetch`. The original response retains the search candidate before projection, but the provider structured output does not expose both as separate records.

## 6. Verification-state proof

### D1-F1 source truth

`Claude_client/research_bridge_projection.ts` fixes the provider semantic shape to:

```text
semantic_result.claims = []
unknowns = ["NO_MODEL_SYNTHESIS: ..."]
```

Source references:

- `ProviderStructuredOutput.semantic_result.claims`: line 47
- emitted `claims: []`: line 195
- `NO_MODEL_SYNTHESIS`: line 198

### C1 authority truth

`Julia_core/julia_core/research/normalizer.py` mints claim-level `SOURCE_VERIFIED` only inside the `if semantic.claims:` branch after all E3 checks. With no claims, it uses result-level `_result_state()`.

Source references:

- claim branch: lines 95-118
- no-claim branch: lines 119-135
- claim E3 completion returning `SOURCE_VERIFIED`: line 331
- no-claim result state: lines 333-345

For a successful available result:

- any WebSearch source ⇒ `REPORT_ONLY`;
- otherwise ⇒ `NOT_PROVEN`;
- never `SOURCE_VERIFIED`.

### C2 truth

C2 reads verification only from C1-minted `Evidence.integrity_metadata`; it does not create an alternate source-verified state. Therefore the exact D1-F1 → C1 → C2 path cannot yield `SOURCE_VERIFIED` support.

## 7. Failure/degradation matrix

The full F1-F18 harness was not committed because the canonical happy path is blocking. Existing focused suites independently prove:

- M1B Market success, partial, relation failure, NOT_FOUND, DB unavailable, schema mismatch, unknown field, missing field, and provenance continuity;
- C1 claim-level WebSearch `REPORT_ONLY`;
- C1 missing binding/digest/runtime identity failures as `NOT_PROVEN`;
- C1 blocked observation as `BLOCKED`;
- C2 malformed/unknown-reference rejection and preliminary-judgment limits;
- D1 blocked/private-network/ambiguous fetch behavior and retry/fallback zero semantics.

These do not substitute for the required integrated happy path.

## 8. Hostile-content case

No committed E2E hostile-content case was added because the happy path is blocked first.

Existing D1 tests already prove hostile search snippets cannot authorize a private-network fetch and fetched content remains untrusted. Existing C2 control material marks source observation as evidence only, with no instruction authority. A valid F1 harness must still traverse those cases end-to-end after the semantic seam is resolved.

## 9. C2 no-model-synthesis case

This case is the source of the blocker.

Exact D1-F1 no-model synthesis emits:

```text
claims = []
NO_MODEL_SYNTHESIS
```

Exact C1 can still mint result-level evidence and C2 may form a Julia-owned preliminary judgment, but that evidence is `REPORT_ONLY` when a search record remains or `NOT_PROVEN` for fetched-only material. It cannot be `SOURCE_VERIFIED` without a semantic claim.

## 10. Authority-boundary assertions

Proven:

- M1A does not own cognition;
- M1B does not execute a provider;
- D1-F1 does not emit `verification_state`;
- C1 normalizer is the sole verification-state mint;
- C2 reads but does not rewrite source verification;
- C2 owns preliminary judgment;
- the diagnostic reproduction did not bypass M1B, D1-F1 projection, or C1 normalization.

Blocking:

- there is no contract-legal semantic claim for C1 to bind the fetched observation to `SOURCE_VERIFIED`.

## 11. Test commands/results

M1B:

```text
/opt/miniconda3/bin/pytest -q \
  tests/market_research/test_m1b_market_event_composition.py

14 passed
```

C1, C2, and relevant capability/review regressions:

```text
/opt/miniconda3/bin/pytest -q \
  tests/research/test_c1_research_event_enrichment.py \
  tests/research/test_c2_preliminary_research_judgment.py \
  tests/capability/test_m0_acceptance.py \
  tests/review/test_review_invocation.py

78 passed
```

D1 native fixture projection regression:

```text
bun test tests/research_bridge.test.ts

6 pass, 0 fail
```

Deterministic cross-contract reproduction:

```text
bun run /private/tmp/f1_blocker_projection.ts \
  > /private/tmp/f1_blocker_projection.json
python3.13 /private/tmp/f1_blocker_normalize.py

claim_count=0
source_kinds=["web_fetch"]
binding_count=1
evidence_states=["NOT_PROVEN"]
```

The `/private/tmp` scripts are diagnostic only and are not committed.

## 12. Production files changed

None.

M1B, C1/C2, and D1-F1 production behavior are unchanged.

## 13. Test-only files changed

Committed:

- `RD1_FIXTURE_E2E_RESEARCH_CHAIN_REPORT.md`

Diagnostic-only outside the repository:

- `/private/tmp/f1_blocker_projection.ts`
- `/private/tmp/f1_blocker_normalize.py`
- `/private/tmp/f1_blocker_projection.json`

No fixture E2E test files were committed because doing so would require one of the forbidden shortcuts.

## 14. Not proven

- End-to-end `SOURCE_VERIFIED` path;
- integrated C2 `PreliminaryResearchJudgment` through the exact D1-F1 output;
- F1-F18 full fixture matrix;
- D1 search-candidate and fetched-record dual retention after projection;
- live behavior (explicitly out of scope).

## 15. Architecture deviations

None introduced.

Possible owner-level resolutions would each be an explicit architecture decision, not an F1 fixture fix:

1. Extend C1 result-level verification to treat a bound fetched observation as `SOURCE_VERIFIED` without a semantic claim.
2. Allow D1-F1 to emit a deterministic semantic claim referencing fetched content.
3. Introduce a new governed semantic-binding stage before C1.

Option 1 changes C1 authority semantics. Option 2 conflicts with D1-F1’s frozen no-model-synthesis contract. Option 3 adds a new production seam. F1 must not silently choose among them.

## 16. Final verdict

**FIXTURE_E2E = BLOCKING**

Blocking reason:

```text
D1-F1 exact projection emits zero semantic claims,
while exact C1 mints SOURCE_VERIFIED only for a claim
with a complete runtime content binding.
Therefore the mandated WebSearch+WebFetch happy path
cannot produce SOURCE_VERIFIED without bypassing or
changing a frozen production contract.
```
