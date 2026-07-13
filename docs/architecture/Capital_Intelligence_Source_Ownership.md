# Capital Intelligence Source Ownership

PR: PR4.2.20d Capital Intelligence Source Audit  
Status: Audit Only  
Frozen Date: 2026-07-13

## 1. Decision

`capital` must not mean only dragon-tiger seat statistics. In ReviewDocument,
Capital Intelligence means:

- market money activity
- institutional style preference by theme
- short-term hot-money attack direction
- evidence used to support the above

The previous narrow path:

```text
seat_money_summary
  -> institution_buy_rows / hot_money_buy_rows
  -> capital.institution / capital.hot_money
```

is valid only as a dragon-tiger evidence path. It is not sufficient to produce
analyst-style institution/hot-money direction.

## 2. Source Inventory

### 2.1 Market Active Capital

| Target field | Source owner | Current status |
| --- | --- | --- |
| `capital.active_amount` | `MarketMetricsSnapshot.capital.active_limitup_amount_yi` / active-capital chart | READY |
| `capital.turnover` | `MarketMetricsSnapshot.capital.total_turnover_yi` | candidate |
| `capital.money_activity_score` | `MarketMetricsSnapshot` or chart review score | candidate |

This layer is a market fact layer. It does not produce institution or hot-money
style by itself.

### 2.2 Institution Style Candidates

Institution style means medium-term capital preference by industry/theme. It is
closer to the analyst report sections such as "科技硬件", "材料/服务器",
"存储/光通信/PCB", with states like "启动第1天", "调整第3天", and
"资金回流".

| Candidate source | Role | Value | Restriction |
| --- | --- | --- | --- |
| `theme_cycle_judgement_v2` | theme lifecycle | phase, cycle day, divergence/start/recovery state | must not be converted directly into participant identity |
| `theme_strength_snapshot` | theme strength | score, rank, breadth, leader strength | strength is not institution identity |
| `subject_daily_feature` | daily theme behavior | limit-up count, breadth, leader behavior, turnover candidates | requires field-level ownership proof before production use |
| `theme_capital_flow` | theme-level money flow | capital return / inflow signal by theme | not hot-money identity by itself |
| `post_market_recap_snapshot.recap_doc.strong_hotspot_subjects` | confirmed hot theme list | market-recognized theme directions | evidence for style, not a complete producer |
| `money_flow_enhanced` | stock-level money evidence | stock money strength and concentration | `role_label` is stock role, not participant type |

Future owner:

```text
ThemeCapitalIntelligenceProducer
  inputs:
    - theme_cycle_judgement_v2
    - theme_strength_snapshot
    - subject_daily_feature
    - theme_capital_flow
    - strong_hotspot_subjects
  output:
    capital.institution_style[]
```

Candidate contract:

```json
{
  "theme_key": "9018144",
  "theme_name": "PCB印制电路板",
  "phase": "启动",
  "cycle_day": 1,
  "strength": 92,
  "capital_signal": "资金回流",
  "evidence": [
    "theme_strength_snapshot",
    "theme_capital_flow",
    "subject_daily_feature"
  ]
}
```

### 2.3 Hot-Money Style Candidates

Hot-money style means short-term attack direction. It is closer to analyst
statements such as "商业航天 关注", "洪涝/水利 台风催化，观察", and
"光刻胶/材料 大面积启动第1天".

| Candidate source | Role | Value | Restriction |
| --- | --- | --- | --- |
| `limit_up.categories` | limit-up theme spread | short-term attack breadth by theme | category names must be identity-resolved |
| `strong_stock_watch_history` | strong-stock pool | leader/sub-dragon/replenishment structure | stock role is not capital participant identity |
| event catalyst sources | event-driven pressure | commercial aerospace, flood/water, policy/news catalyst | must be structured event evidence |
| `DragonTigerSnapshot` | seat evidence | institution/hot-money seat confirmation | evidence only; not the sole style producer |

Future owner:

```text
ShortTermCapitalProducer
  inputs:
    - limit_up.categories
    - strong_stock_watch_history
    - structured event catalysts
    - DragonTigerSnapshot evidence
  output:
    capital.hot_money_style[]
```

Candidate contract:

```json
{
  "theme_key": "9019807",
  "theme_name": "商业航天",
  "state": "关注",
  "attack_strength": 85,
  "drivers": [
    "涨停扩散",
    "事件催化"
  ],
  "evidence": [
    "limit_up",
    "strong_stock",
    "dragon_tiger"
  ]
}
```

## 3. Dragon-Tiger Data Ownership

Tushare dragon-tiger data is unstable around 16:30. The future preferred path is:

```text
a-stock-data adapter
  -> DragonTigerSnapshot
  -> Capital Evidence Layer
  -> ReviewDocument.capital.evidence.dragon_tiger
```

The adapter owns raw acquisition. `DragonTigerSnapshot` owns normalization.
Capital Intelligence Producers may use it as supporting evidence, but must not
block all style output solely because dragon-tiger data is unavailable.

## 4. ReviewDocument Capital Contract Direction

Do not break the current schema in this audit PR. The target contract for a
future implementation is:

```json
{
  "capital": {
    "active_amount": 5058.28,
    "institution_style": [],
    "hot_money_style": [],
    "evidence": {
      "dragon_tiger": {},
      "theme_rotation": {}
    }
  }
}
```

Backward-compatible mapping may continue to expose `institution` and `hot_money`
only after their semantics are explicitly migrated to `institution_style` and
`hot_money_style`.

## 5. Seat Money Positioning

`seat_money_summary` remains useful, but its owner is evidence:

```text
seat_money_summary
  -> capital.evidence.dragon_tiger
```

It must not be treated as the sole source for:

- `capital.institution_style`
- `capital.hot_money_style`
- theme cycle state
- theme attack strength

If dragon-tiger data is missing, the output should preserve the diagnostic:

```json
{
  "seat_money_summary": {
    "institution_buy_rows": [],
    "hot_money_buy_rows": [],
    "diagnostics": {
      "source": "none"
    }
  }
}
```

## 6. Forbidden Paths

The following paths are forbidden for all future agents and tests:

```text
money_flow_enhanced.role_label == "龙头"
  -> institution_style
```

```text
money_flow_enhanced.role_label == "龙头"
  -> hot_money_style
```

```text
theme_capital_flow
  -> hot_money_style
```

```text
seat_money_summary
  -> institution_style
```

```text
seat_money_summary
  -> hot_money_style
```

```text
dragon_tiger missing
  -> infer from money_flow_enhanced / role_label / theme stage
```

## 7. Migration Plan

1. Keep current empty capital directions when only `seat_money_summary.source=none`
   exists.
2. Add `DragonTigerSnapshot` acquisition audit for `a-stock-data`.
3. Design `ThemeCapitalIntelligenceProducer` with field-level evidence.
4. Design `ShortTermCapitalProducer` with limit-up, strong-stock, catalyst, and
   dragon-tiger evidence.
5. Add ReviewDocument contract extension only after producer contracts are
   frozen.
6. Update UI after `institution_style[]` and `hot_money_style[]` are produced by
   approved sources.

## 8. Non-Goals

- No frontend change.
- No assembler change.
- No ContextFactory change.
- No ReviewDocument schema change.
- No inference from stock role to capital participant type.
- No replacement of dragon-tiger provider in this PR.
