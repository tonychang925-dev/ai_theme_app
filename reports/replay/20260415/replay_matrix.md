# Replay Matrix

| case_name | trade_date | stock_id | mode | ok | reason | input_rank | promoted_rank | observe_rank | final_cycle_state | final_mainline_alive | layers | assertions |
|---|---|---|---|---:|---|---:|---:|---:|---|---:|---|---|
| liande_2026_04_15 | 2026-04-15 | 605060.SH | ReplayMode.REUSE_ALL | false | not_in_input_pool | None | None | None/10 | divergence | False | evidence:reused, daily:reused, recap:reused | passed=False |

## liande_2026_04_15 Failed Assertions

- `layer_c.present_in_promoted_pool` expected `True` actual `False`
- `layer_d.present_in_observe_candidates` expected `True` actual `False`
- `layer_d.support_type` expected `prev_low_support` actual `None`
- `layer_d.candidate_level` expected `observe_only` actual `None`
