# Replay Matrix

| case_name | trade_date | stock_id | mode | ok | reason | input_rank | promoted_rank | observe_rank | final_cycle_state | final_mainline_alive | layers | assertions |
|---|---|---|---|---:|---|---:|---:|---:|---|---:|---|---|
| liande_2026_04_15 | 2026-04-15 | 605060.SH | ReplayMode.FULL_REBUILD | false | observe_rank_gt_observe_top_n | None | 57 | None/286 | divergence | True | evidence:ok, daily:ok, recap:ok | passed=False |

## liande_2026_04_15 Failed Assertions

- `layer_d.present_in_observe_candidates` expected `True` actual `False`
