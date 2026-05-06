# Replay Matrix

| case_name | trade_date | stock_id | mode | ok | layers | assertions |
|---|---|---|---|---:|---|---|
| weike_2026_04_23 | 2026-04-23 | 600152.SH | ReplayMode.REUSE_ALL | false | evidence:reused, daily:reused, recap:reused | passed=False; missing_candidate_row; observe_rank=None/10 |

## weike_2026_04_23 Failed Assertions

- `layer_c.present_in_promoted_pool` expected `True` actual `False`
- `layer_d.allowed_outcomes` expected `[{'candidate_level': 'formal'}, {'candidate_level': 'observe_only'}, {'candidate_level': 'reject', 'reject_reason_contains': '末端跳水'}]` actual `{'candidate_level': 'reject', 'reject_reason': ''}`
