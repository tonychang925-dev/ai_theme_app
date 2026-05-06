# Replay Matrix

| case_name | trade_date | stock_id | mode | ok | layers | assertions |
|---|---|---|---|---:|---|---|
| weike_2026_04_22 | 2026-04-22 | 600152.SH | ReplayMode.REUSE_ALL | false | evidence:reused, daily:reused, recap:reused | passed=False; missing_candidate_row; observe_rank=None/10 |

## weike_2026_04_22 Failed Assertions

- `layer_c.present_in_promoted_pool` expected `True` actual `False`
- `layer_d.candidate_level_in` expected `['formal', 'observe_only']` actual `None`
