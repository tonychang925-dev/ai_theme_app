# Replay Matrix

| case_name | trade_date | stock_id | mode | ok | reason | input_rank | promoted_rank | observe_rank | final_cycle_state | final_mainline_alive | layers | assertions |
|---|---|---|---|---:|---|---:|---:|---:|---|---:|---|---|
| shenjian_2026_04_07 | 2026-04-07 | 002361.SZ | ReplayMode.REUSE_ALL | true | selected | None | None | 3/10 | divergence | True | evidence:reused, daily:reused, recap:reused | passed=True |
