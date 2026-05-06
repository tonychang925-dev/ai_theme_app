# Replay Matrix

| case_name | trade_date | stock_id | mode | ok | reason | input_rank | promoted_rank | observe_rank | final_cycle_state | final_mainline_alive | layers | assertions |
|---|---|---|---|---:|---|---:|---:|---:|---|---:|---|---|
| weike_2026_04_23 | 2026-04-23 | 600152.SH | ReplayMode.REUSE_ALL | false | in_input_but_not_promoted | 55 | None | None/10 | divergence | True | evidence:reused, daily:reused, recap:reused | passed=False |

## weike_2026_04_23 Failed Assertions

- `layer_c.present_in_promoted_pool` expected `True` actual `False`
- `layer_d.allowed_outcomes` expected `[{'candidate_level': 'formal'}, {'candidate_level': 'observe_only'}, {'candidate_level': 'reject', 'reject_reason_contains': '末端跳水'}]` actual `{'candidate_level': 'reject', 'reject_reason': ''}`
