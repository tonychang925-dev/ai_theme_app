# Legacy Layer C Output Report - 2026-04-15

## Source

- source_used: `strong_stock_watch_history`
- reason: `trade_date_before_latest_pool_trade_date`
- latest_pool_trade_date: `2026-05-06`

## Raw Output

- raw_row_count: `5840`
- stock_distinct_count: `365`
- subject_distinct_count: `207`
- duplicate_stock_count: `365`
- max_rows_per_stock: `16`

## Effective Output

- effective_stock_count: `365`
- effective_subject_count: `207`

## Distributions

- watch_status_counts: `{'active': 5840}`
- pool_entry_type_counts: `{'formal': 5840}`
- watch_source_tag_counts: `{'history_snapshot': 5840}`
- watch_score: `{'p50': '50.84', 'p75': '54.15', 'p90': '55.73', 'max': '70.50'}`
- watch_priority: `{'p50': '50.84', 'p75': '54.15', 'p90': '55.73', 'max': '70.50'}`

## Target

- stock_id: `605060.SH`
- raw_rows: `16`
- effective_selected: `True`
- selected_subject_key: `9028694`
- selected_theme_name: `9028694`
- watch_status: `active`
- pool_entry_type: `formal`
- watch_score: `55.73`
- watch_priority: `55.73`
- prior7_limitup_days: `2`
- prior7_strong_days: `2`
- recent_limit_up_count: `2`
- support_type: `prev_low_support`
- support_score: `78.00`
- rank_in_effective_c_pool: `38`
- legacy_raw_row_count: `16`

## Recap Consistency

- recap_available: `True`
- recap_layer_c_input_mode: `legacy_watch_pool`
- recap_legacy_watch_input_count: `365`
- recap_strong_watch_input_7d_count: `365`
- recap_candidate_count_all: `10`
- recap_candidate_count_observe: `2`
- recap_observe_candidates_count: `2`
- effective_equals_legacy_watch_input_count: `True`
- effective_equals_strong_watch_input_7d_count: `True`

## Effective Top Preview

| rank | stock_id | subject | type | status | priority | score | prior7_limitup | prior7_strong | support | support_score |
|---:|---|---|---|---|---:|---:|---:|---:|---|---:|
| 1 | 002364.SZ | 9011609 | formal | active | 70.50 | 70.50 | 4 | 4 | prev_low_support | 78.00 |
| 2 | 603950.SH | 9025720 | formal | active | 69.00 | 69.00 | 4 | 4 | gap_support | 88.00 |
| 3 | 002580.SZ | 9012747 | formal | active | 68.90 | 68.90 | 4 | 4 | prev_low_support | 78.00 |
| 4 | 002328.SZ | 9014198 | formal | active | 67.35 | 67.35 | 3 | 4 | prev_low_support | 78.00 |
| 5 | 000889.SZ | 9017846 | formal | active | 66.50 | 66.50 | 4 | 4 | prev_low_support | 78.00 |
| 6 | 603777.SH | 9016453 | formal | active | 64.30 | 64.30 | 3 | 3 | prev_low_support | 78.00 |
| 7 | 605287.SH | 9063773 | formal | active | 61.35 | 61.35 | 1 | 2 | prev_low_support | 78.00 |
| 8 | 301517.SZ | 9025765 | formal | active | 61.30 | 61.30 | 1 | 3 | prev_low_support | 78.00 |
| 9 | 301018.SZ | 9019474 | formal | active | 61.20 | 61.20 | 1 | 3 | prev_low_support | 78.00 |
| 10 | 603459.SH | 9018144 | formal | active | 60.15 | 60.15 | 2 | 2 | prev_low_support | 78.00 |
| 11 | 000506.SZ | 9010270 | formal | active | 60.15 | 60.15 | 1 | 2 | gap_support | 88.00 |
| 12 | 600743.SH | 9013718 | formal | active | 59.41 | 59.41 | 5 | 5 | prev_low_support | 78.00 |
| 13 | 301189.SZ | 9020715 | formal | active | 58.60 | 58.60 | 2 | 5 | prev_low_support | 78.00 |
| 14 | 603773.SH | 9015387 | formal | active | 58.60 | 58.60 | 2 | 4 | prev_low_support | 78.00 |
| 15 | 002824.SZ | 9014270 | formal | active | 58.60 | 58.60 | 2 | 3 | prev_low_support | 78.00 |
| 16 | 002051.SZ | 9010250 | formal | active | 58.60 | 58.60 | 2 | 3 | prev_low_support | 78.00 |
| 17 | 002124.SZ | 79 | formal | active | 58.60 | 58.60 | 2 | 3 | prev_low_support | 78.00 |
| 18 | 300561.SZ | 69 | formal | active | 58.60 | 58.60 | 2 | 2 | prev_low_support | 78.00 |
| 19 | 301055.SZ | 9016988 | formal | active | 58.60 | 58.60 | 2 | 2 | prev_low_support | 78.00 |
| 20 | 300857.SZ | 9013933 | formal | active | 58.60 | 58.60 | 2 | 2 | prev_low_support | 78.00 |
| 21 | 301310.SZ | 9012413 | formal | active | 58.35 | 58.35 | 1 | 4 | prev_low_support | 78.00 |
| 22 | 002636.SZ | 9050315 | formal | active | 58.35 | 58.35 | 1 | 2 | prev_low_support | 78.00 |
| 23 | 600482.SH | 9052162 | formal | active | 57.95 | 57.95 | 1 | 4 | prev_low_support | 78.00 |
| 24 | 002008.SZ | 9022064 | formal | active | 57.87 | 57.87 | 1 | 3 | prev_low_support | 78.00 |
| 25 | 002281.SZ | 9054580 | formal | active | 57.73 | 57.73 | 1 | 3 | prev_low_support | 78.00 |
| 26 | 300696.SZ | 9013314 | formal | active | 57.65 | 57.65 | 1 | 3 | prev_low_support | 78.00 |
| 27 | 301219.SZ | 9064170 | formal | active | 57.65 | 57.65 | 1 | 1 | prev_low_support | 78.00 |
| 28 | 002645.SZ | 9010367 | formal | active | 57.35 | 57.35 | 1 | 1 | prev_low_support | 78.00 |
| 29 | 600152.SH | 9014701 | formal | active | 57.00 | 57.00 | 2 | 2 | prev_low_support | 78.00 |
| 30 | 300480.SZ | 9011398 | formal | active | 56.85 | 56.85 | 1 | 2 | prev_low_support | 78.00 |

## Notes

- `raw_rows_contain_duplicate_stock_across_subjects`
