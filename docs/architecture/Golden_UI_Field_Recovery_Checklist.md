# Golden UI Field Recovery Checklist

**Frozen: 2026-07-12**
**Baseline commit: 1e4f42ae8**
**Rule: Fix ONE row per PR. No architecture changes, no refactoring, no "while we're at it".**

---

## Recovery Status Summary

| # | UI Area | Field | Status | Real Source | PR |
|---|---------|-------|--------|-------------|----|
| 1 | 大盘势能 | 12日涨停趋势折线 | ❌ | `MarketMetricsSnapshot.build_trend()` | 4.2.19 |
| 2 | 情绪动能 | 12日 emotion score 折线 | ❌ | `MarketMetricsSnapshot.build_trend()` | 4.2.19 |
| 3 | 资金驱动 | 12日 active amount 折线 | ❌ | `MarketMetricsSnapshot.build_trend()` | 4.2.19 |
| 4 | 核心节律 | 12日 relay 折线 | ❌ | `MarketMetricsSnapshot.build_trend()` | 4.2.19 |
| 5 | 机构资金审美方向 | 方向列表 | ❌ | `seat_money_summary.institution_buy_rows` | 4.2.20 |
| 6 | 游资情绪方向 | 方向列表 | ❌ | `seat_money_summary.hot_money_buy_rows` | 4.2.20 |
| 7 | 题材结构 | 9055378→名称映射 | ❌ | `ThemeIdentityRegistry` (subject_key→canonical_name) | 4.2.21 |
| 8 | 题材结构 | 垃圾文本过滤 | ❌ | `ThemeIdentityResolver` length guard | 4.2.21 |
| 9 | 强势股票池 | __independent__ 过滤 | ❌ | `StockIdentityResolver` | 4.2.21 |
| 10 | 涨停分类 | categories 列表 | ❌ | `post_market_recap_snapshot.strong_hotspot_subjects` | 4.2.22 |
| 11 | 明日计划 | scenario | ✅ | `PlanSnapshotProducer` → `draft_context.plan_state` | 4.2.14 |
| 12 | 明日计划 | allowed_actions | ✅ | `PlanSnapshotProducer` → `draft_context.plan_state` | 4.2.14 |
| 13 | 明日计划 | forbidden_actions | ✅ | `PlanSnapshotProducer` → `draft_context.plan_state` | 4.2.14 |
| 14 | 风险控制 | risk_level | ✅ | `EmotionReviewBuilder` → `emotion_review.risk_level` | 4.2.17 |
| 15 | 市场概览 | up_count/down_count | ✅ | `market_breadth` chart → `draft_context.market_state` | 4.2.18a |
| 16 | 市场概览 | limit_up_count | ✅ | `market_breadth` chart | — |
| 17 | 市场概览 | active_capital_yi | ✅ | `active_capital` chart | — |
| 18 | 情绪概览 | phase/score/confidence | ✅ | `emotion_review` | — |

---

## Row-by-Row Source Ownership

### Row 1-4: Historical Trend Lines (PR4.2.19)

**Current state:**
- `review_document.evidence.trend_series` has 1 data point per series (today only)
- Frontend renders empty charts because it expects multi-date arrays

**Root cause:**
`DraftContextBuilder._build_trend_data()` reads from single-day chart JSON.
`chart_engine.build_trend(snapshots[])` can generate multi-date series but is NOT called by DraftContextBuilder.

**Source contract:**
```
chart_engine.build_trend(snapshots: list[MarketMetricsSnapshot]) → dict
  returns: {breadth: [{date, up, down, limit_up, score}...],
             momentum: [{date, score, limit_up}...],
             capital: [{date, amount, limit_up}...],
             relay: [{date, max_height, promotion_1_to_2, feedback_score}...]}
```

**Fix:** DraftContextBuilder._build_trend_data() must call chart_engine.build_trend() with historical snapshots, not extract from single-day chart JSON.

**Forbidden:**
- ❌ No frontend changes
- ❌ No Assembler changes
- ❌ No ContextFactory changes
- ❌ No fallback to old emotion.json
- ❌ No hardcoded trend data

---

### Row 5-6: Institution/Hot Money Direction (PR4.2.20)

**Current state:**
- `capital.institution = []`, `capital.hot_money = []`
- `money_flow.role_label` values are "龙头", not "机构"/"游资"

**Root cause:**
`_capital_direction_from_flows()` filters by `role_label == "机构"` or `role_label == "游资"`.
Actual data has different role_label values.

**Source contract:**
The DB table `money_flow_enhanced` has columns:
- `institution_seat_count` — institution seat count from dragon tiger board
- `dragon_tiger_net_amount` — dragon tiger net amount
- `role_label` — stock role within theme (龙头/中军/补涨/etc., NOT institution/hot_money)

**Correct source for institution/hot_money direction:**
- `seat_money_summary.institution_buy_rows` — from recap snapshot
- `seat_money_summary.hot_money_buy_rows` — from recap snapshot
- OR: when recap is missing, this field SHOULD be empty (correct behavior)

**Fix options:**
A. Wait for recap to be generated (correct data source)
B. Aggregate institution/hot_money from `dragon_tiger` raw data (requires recap pipeline)

**Decision:** TBD after recap snapshot availability is resolved.

---

### Row 7-9: Theme/Stock Identity (PR4.2.21)

**Current state:**
- 9055378, 9018144, 9014001 → `final_value = None`
- 【驱动事件：7月9日连板复盘】... → junk text passes through
- 000566.SZ / 002396.SZ / 600793.SH → `__independent__` leaks into display

**Root cause:**
1. ThemeIdentityResolver correctly rejects numeric IDs but has no lookup mapping
2. No length/content guard on theme_name (junk text passes)
3. Stock rows with `__independent__` theme are not filtered

**Source contract:**
- `theme_cycle_judgement_v2` has `theme_name` column (may be numeric or junk)
- `mainline_identity_registry` may have canonical_name mapping
- OR a static/managed mapping table `subject_key → canonical_name`

**Fix for numeric IDs:** Need a lookup source. Options:
- Check if `mainline_identity_registry` table has canonical names
- Check if `cognition_cards` from previous approved snapshots have names
- Build a static `theme_identity_registry` table

**Fix for junk text:**
- `ThemeIdentityResolver` should reject `len(name) > 30`
- `ThemeIdentityResolver` should reject names containing `【` or `】`

**Fix for __independent__:**
- Stock rows with `theme_name == "__independent__"` → set `theme_name = None`

---

### Row 10: Limit-Up Categories (PR4.2.22)

**Current state:**
- `limit_up.categories = []`, quality = BLOCKED
- RecapCompletenessGuard correctly blocks approval

**Root cause:**
`post_market_recap_snapshot` for 2026-07-09 does not exist in DB.
`chart_engine._build_limitup()` depends on `recap.strong_hotspot_subjects`.

**Source contract:**
```
post_market_recap_snapshot.payload.recap_doc.strong_hotspot_subjects[]
  → chart_engine._build_limitup()
  → analyst-charts JSON (limitup_classification)
  → DraftContextBuilder._build_limit_up()
  → draft_context.limit_up
  → ContextFactory
  → ReviewDocument.limit_up.categories
```

**Fix:** Generate recap for 2026-07-09:
```
python scripts/build_post_market_recap.py --trade-date 2026-07-09
```
Then regenerate charts + workbench.

**No code changes needed.** Recap generation is the missing pipeline step.

---

## Already Recovered (Rows 11-18)

These fields are working in the current `review_document.json`:
- Plan (scenario, allowed, forbidden): PlanSnapshotProducer wired
- Risk (risk_level): EmotionReviewBuilder produces risk_flags
- Market (up/down/limit_up/active): chart data flows correctly
- Emotion (phase/score/confidence): emotion_review pipeline intact

---

## Recovery Order

```
PR4.2.19  TrendSnapshotProducer     ← First: most visible impact
PR4.2.20  Institution/HotMoney       ← Second
PR4.2.21  Theme/Stock Identity       ← Third
PR4.2.22  LimitUp Categories         ← Fourth (depends on recap generation)
```

Each PR must:
1. Restore exactly ONE row from the checklist
2. Include source ownership proof (which table/API/producer provides the data)
3. Pass Golden Replay for that specific field
4. NOT touch UI, Assembler, ContextFactory, or ReviewDocument schema
