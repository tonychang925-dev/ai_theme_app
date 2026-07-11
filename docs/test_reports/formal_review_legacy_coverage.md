# Formal Review Legacy Coverage Matrix

## 1. Purpose

This report is the PR6 Legacy Removal gate.

It tracks whether legacy DailyReviewV2 fields are represented in the frozen Formal Review v1 model, moved to appendix/diagnostics, or safe to remove.

Current status: `INCOMPLETE`

PR6 must not start until this matrix is completed against real composed responses.

## 2. Gate Rules

| Gate | Requirement | Current |
|---|---|---|
| Coverage source | At least 5 approved snapshot formal compose responses | BLOCKED |
| Projection loss rate | Critical semantic loss = 0 | PENDING |
| Analyst override preservation | 100% | PENDING |
| Duplicate reduction | Measured and documented | PENDING |
| User reading confirmation | FormalReviewView accepted for real review workflow | PENDING |

## 3. Coverage Matrix

| Legacy Field | Formal Target | Policy | Status | Notes |
|---|---|---|---|---|
| `market_summary.risk_flags` | `formal_review.executive_summary.top_risks` | MERGE | PENDING | Verify with real compose samples |
| `market_overview_review.up_count` | `formal_review.market_state.facts.up_count` | KEEP | PENDING | FACT owner: MarketBreadth |
| `market_overview_review.down_count` | `formal_review.market_state.facts.down_count` | KEEP | PENDING | FACT owner: MarketBreadth |
| `market_overview_review.limit_up_total` | `formal_review.market_state.facts.limit_up_total` | KEEP | PENDING | FACT owner: LimitPool |
| `market_overview_review.limit_down_total` | `formal_review.market_state.facts.limit_down_total` | KEEP | PENDING | FACT owner: LimitPool |
| `theme_reviews[]` | `formal_review.theme_structure.themes[]` | MERGE | PENDING | Subject union, not base table only |
| `mainline_daily_states[]` | `formal_review.theme_structure.themes[].state_evolution` | MERGE | PENDING | Preserve lifecycle/fade/alive |
| `theme_driver_events[]` | `formal_review.theme_structure.themes[].drivers` | MERGE | PENDING | Preserve drivers |
| `strong_stock_reviews[]` | `formal_review.stock_structure.stocks[]` | MERGE | PENDING | Dedup by stock_code |
| `stock_capital_reviews[]` | `formal_review.capital_evidence.stocks[].capital.fact` | MERGE | PENDING | FACT only |
| `money_flow_reviews[]` | `formal_review.capital_evidence.stocks[].capital.assessment` | MERGE | PENDING | Assessment only |
| `dragon_tiger_reviews[]` | `formal_review.capital_evidence.stocks[].dragon_tiger` | FOLD | PENDING | Orphan rows into `orphan_seats` |
| `abnormal_reviews[]` | `formal_review.capital_evidence.stocks[].abnormal_signals` | FOLD | PENDING | Dedup by stock_code |
| `watchlist_reviews[]` | `formal_review.next_day_plan.watch_stocks[]` | MERGE | PENDING | Analyst final watch override wins |
| `post_market_setup_plan` | `formal_review.next_day_plan.watch_stocks[]` | MERGE | PENDING | one_to_two tag |
| `playbook_review` | `formal_review.next_day_plan` | MERGE | PENDING | PLAN priority |
| `workbench_data` | Removed | REMOVE | DONE | Duplicate blob removed |
| `confirmed_mainlines` | Removed | REMOVE | DONE | Legacy empty output removed |
| `pending_mainline_reviews` | Removed | REMOVE | DONE | Duplicate alias removed |

## 4. Metrics To Fill Before PR6

| Metric | Formula | Target | Current |
|---|---|---:|---:|
| Projection Loss Rate | critical missing semantics / critical semantics | 0 critical loss | PENDING |
| Analyst Override Preservation Rate | preserved overrides / approved overrides | 100% | PENDING |
| Duplicate Reduction Rate | removed duplicate fields / legacy duplicate fields | >50% | PENDING |
| Top-level Reduction | old top-level fields -> new top-level objects | 63 -> 5 | PENDING |

## 5. Current Conclusion

PR6 Legacy Removal is blocked.

This matrix is a tracking skeleton only. It must be completed with real approved snapshot compose responses before any legacy field or legacy UI component is removed.
