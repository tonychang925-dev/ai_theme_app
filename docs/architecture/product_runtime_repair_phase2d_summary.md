# Product Runtime Repair Phase 2D Summary

## Background

Phase 2C verified that the live `direct_theme_name_hit` guard was loaded and effective in the running SPS process, but the live replay still produced wrong MATCH rows. The root cause was that those samples were no longer accepted through `direct_theme_name_hit`; they were accepted by the LLM path as `llm_accept_match`, bypassing the direct-hit guard.

Phase 2D therefore did not continue repairing more gates. The repair target was the runtime decision boundary: an LLM `accept_match` can no longer become a final MATCH unless it has sufficient hard evidence and passes value/boundary checks.

## Fix

Phase 2D added an LLM accept safety gate in `ThemeMatchEngine`:

- `llm_accept_match` now requires hard evidence before final MATCH.
- v1 fallback profiles are stricter: weak v1 LLM accepts are downgraded to `HUMAN_REVIEW`.
- generic-only evidence is downgraded to `HUMAN_REVIEW`.
- low-confidence LLM accept with insufficient hard evidence is downgraded to `HUMAN_REVIEW`.
- low-value events on v1 fallback LLM accept are downgraded to `HUMAN_REVIEW`.

New safety reason codes:

- `weak_v1_llm_accept_review`
- `llm_accept_without_hard_evidence`
- `llm_accept_generic_only_review`
- `low_conf_llm_accept_review`
- `low_value_event_match_blocked`

The Phase 2C live replay reporting was also extended with LLM accept safety metrics.

## Verification

Phase 2D live replay:

- `new_rows_after_guard=10`
- `new_match_count=3`
- `new_human_review_count=4`
- `llm_accept_blocked_count=4`
- `weak_v1_llm_accept_review_count=2`
- `llm_accept_without_hard_evidence_count=1`
- `low_value_event_match_blocked_count=1`
- `new_obvious_wrong_match_count=0`
- `low_value_major=0`
- `duplicate_primary=0`

Regression:

- Unit tests: `39 passed`
- Product hard negatives: `13/13`
- Product positive rank: `13/13`
- Direct-hit delta hard negatives: `5/5`
- Direct-hit delta positive rank: `5/5`
- Full hard negative active v2: `64/64`

Runtime:

- SPS `8090`, Web `8000`, and Frontend are screen-managed and online.
- `runtime_guard_smoke` passed.
- `status_new_chain_stack.sh` health checks passed.

## Conclusion

Phase 2D is closed. The system should not continue blindly repairing remaining direct-hit subjects. The correct next step is a Product Runtime Observation Window using real incremental pre-market data.

## Phase 2E Trigger Conditions

Enter Phase 2E only if real new data satisfies at least one condition:

- An obvious wrong MATCH appears.
- The same v1 fallback subject absorbs at least two unrelated events.
- `direct_theme_name_hit` becomes the main source of wrong matches again.
- `llm_accept_match` bypasses the safety gate and causes an obvious wrong match.
- A low-value event re-enters `major_events`.
- A true positive theme is over-blocked into `HUMAN_REVIEW` or `UNKNOWN`.

Until then, keep the runtime services online and generate the daily quality report after each real pre-market cycle.
