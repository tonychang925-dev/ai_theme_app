# Reconciliation Diff Explanation

- trade_date: 2026-04-07
- gate_passed: False
- old_count: 1
- new_count: 1
- missing_in_new: 0
- missing_in_old: 0
- changed: 1

## Category Counts

- threshold_diff: 1

## Top Diffs

- pk=2026-04-07|military_new_material|002361.SZ | reason=value_mismatch | reason_category=threshold_diff | diff_fields=candidate_score,decision

## Action Suggestion

- If gate_passed=false, classify each diff as input_missing/rule_diff/threshold_diff/order_diff/bug.
- For bug or unintended rule_diff, fix new chain before enabling BFF rollout flag.
