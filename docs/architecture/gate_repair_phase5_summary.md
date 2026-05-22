# Gate Repair Phase 5 Summary

## Baseline

Phase 5 closes the gate quality repair loop triggered by the pre-market mismatch:

- Source event: a Czech public-health item about an Ebola exposure observation.
- Wrong match: `9043458` `中国星际之门`.
- Baseline artifacts:
  - `tmp/e2e100_phase5_round3/e2e100_gate_attribution_report.md`
  - `tmp/e2e100_phase5_round3/e2e100_gate_attribution_detail.jsonl`
  - `theme_service/eval/gate_repair_phase5/e2e_delta_hard_negatives.jsonl`
  - `theme_service/eval/gate_repair_phase5/e2e_delta_positive_rank_cases.jsonl`

## Root Cause

The mismatch was not a scheduling or page rendering problem. Low-quality theme gates allowed public-news words to behave like hard anchors. Runtime profile materialization then amplified the issue when weak `must_terms` entered direct-hit alias evidence.

## Repair Chain

Phase 5 established a repeatable repair chain:

1. Upgrade `gate_quality_audit.py` to v1.2 and flag generic/no-anchor hard evidence.
2. Generate an active runtime profile source report so v2 accepted profiles and v1 fallback gates are audited by their real runtime role.
3. Add hard-negative regressions for obvious wrong matches and public-news false positives.
4. Add positive-rank regressions for specific themes that are vulnerable to broad-theme hijack.
5. Add broad-theme hijack protection based on gate evidence specificity.
6. Lock the active runtime to v2 accepted profiles with explicit v1 fallback and required v2 loading.

## Metrics

Controlled gate E2E100 improved from the Phase 4 baseline to the Phase 5 round3 baseline:

| Metric | Phase 4 | Phase 5 round3 |
| --- | ---: | ---: |
| `theme_set_recall@5` | `0.86` | `0.91` |
| `top1_accuracy` | `0.80` | `0.87` |
| `obvious_wrong_match_count` | `8` | `1` |
| `broad_theme_hijack_count` | `5` | `2` |
| `hard_negative_violation_count` | `0` | `0` |
| `public_news_false_positive_count` | `0` | `0` |
| `medical_public_health_false_positive_count` | `0` | `0` |

The round3 post-run delta also tightened `9062419` `广州商业航天` against non-Guangzhou Blue Arrow launch news and added a hard-negative regression for that case.

## Runtime Contract

Phase 5 results use the active runtime contract below:

```text
THEME_PROFILE_VERSION=v2
THEME_PROFILE_V2_STATUS=accepted_candidate
THEME_PROFILE_V2_FALLBACK_TO_V1=true
THEME_PROFILE_V2_REQUIRE_LOADED=true
PG_DATABASE=stock_data_test
DB_NAME=stock_data_test
READ_PG_DATABASE=stock_data_test
POSTGRES_DATABASE=stock_data_test
```

Pure v1 remains a legacy-risk mode and is not the active validation baseline.

## Deferred Watchlist

The remaining two round3 broad hijacks are treated as subject-label boundary cases, not public-news safety regressions:

- Rocket-heavy Zhuque launch and recovery text labeled as `卫星互联网`.
- Generic commercial-space regulator text labeled as `卫星互联网`.

`9057022` `英伟达MLCP` and `9022942` `苹果MR` stay on a Phase 6 watchlist. They came from over-review or neighbor-theme behavior in backtest attribution. They are not hard-negative violations and should only receive delta repair when later full structuring E2E or real pre-market data reproduces a concrete failure.
