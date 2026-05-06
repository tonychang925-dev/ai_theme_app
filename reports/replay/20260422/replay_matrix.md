# Replay Matrix

| case_name | trade_date | stock_id | mode | ok | reason | input_rank | promoted_rank | observe_rank | final_cycle_state | final_mainline_alive | layers | assertions |
|---|---|---|---|---:|---|---:|---:|---:|---|---:|---|---|
| weike_2026_04_22 | 2026-04-22 | 600152.SH | ReplayMode.REUSE_ALL | false | in_input_but_not_promoted | 52 | None | None/10 | divergence | True | evidence:reused, daily:reused, recap:reused | passed=False |

## weike_2026_04_22 Failed Assertions

- `layer_c.present_in_promoted_pool` expected `True` actual `False`
- `layer_d.candidate_level_in` expected `['formal', 'observe_only']` actual `None`
