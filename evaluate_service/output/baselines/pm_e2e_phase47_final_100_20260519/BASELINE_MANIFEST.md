# E2E Baseline: pm_e2e_phase47_final_100_20260519

## Date
2026-05-19

## Status
**PRODUCTION BASELINE** — all gates passed.

## Configuration
- write_db: stock_data
- read_db: stock_data_test
- theme_profile_version: v2 (draft, fallback_to_v1=true)
- llm_judge_mode: auto
- structured_concurrency: 2
- event_profile_llm: false
- stack: stream-only (no frontend_bff)

## Gate Results

| Gate | Value | Threshold | Status |
|------|-------|-----------|--------|
| theme_set_recall@5 | 0.72 | ≥0.65 | PASS |
| brief_stock_opportunity_count | 144 | ≥35 | PASS |
| A+B tier stock count | 74 | ≥12 | PASS |
| wrong_related_count | 0 | =0 | PASS |
| generic_only_related_count | 0 | =0 | PASS |
| dead_letter_count | 0 | =0 | PASS |
| terminal_distinct_event_count | 100 | ≥99 | PASS |
| numeric_theme_name_count | 0 | =0 | PASS |
| duplicate_decision_event_count | 0 | — | PASS |

## Files
- summary.md — evaluation summary
- accuracy_report.json — full accuracy metrics
- confusion_matrix.csv — per-case results
- sps_payload.json — brief snapshot payload
- db_trace_report.json — match engine trace
- run_result.json — full run output
- recall_regression_attribution_report.jsonl/csv — recall miss analysis
- opportunity_gap_report.csv — opportunity gap analysis
- opportunity_gap_summary.md — opportunity gap summary
