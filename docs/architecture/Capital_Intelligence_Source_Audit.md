# PR4.2.30 Capital Intelligence Source Audit

Status: Audit Only  
Frozen Date: 2026-07-13  
Scope: define semantics, source ownership, and future producer contracts for
Capital Intelligence. No production code, UI, ReviewDocument schema, or
fallback behavior is changed in this PR.

## 1. Current Boundary

`PR4.2.28 Active Capital Recovery` is complete and frozen.

```yaml
active_capital:
  value_yi: 2664.84
  method: board_pool_zt_zb_v1
  quality: PARTIAL
  components:
    - ZT
    - ZB
  missing:
    - board_pool.yzt.amount_yi
  calibration:
    future_owner: M7 Analyst Feedback Calibration
```

The difference between production `2664.84` and analyst truth `2707` is a
calibration target, not a reason to modify the fact producer.

Capital Intelligence is a separate interpretation layer:

```text
Market Fact Layer
  -> active_capital

Capital Evidence Layer
  -> fund_flow_snapshot
  -> dragon_tiger_snapshot
  -> theme_flow_snapshot

Capital Intelligence Layer
  -> institution_style
  -> hot_money_style
  -> capital_rotation

Capital Calibration Layer
  -> analyst_feedback
```

These layers must not be merged.

## 2. Capital Data Layer Model

Capital Intelligence must be built as a layered system, not as a direct
conversion from one data source into a UI label.

```text
                         Capital Intelligence
                                  |
          -------------------------------------------------
          |                                               |
  Capital Evidence Layer                         Intelligence Layer
          |                                               |
  observable / vendor-defined facts              analyst-style judgement
          |
  --------------------------------
  |              |               |
fund flow     dragon tiger      theme flow
```

### 2.1 Capital Evidence Layer

The Evidence Layer stores observable or vendor-defined facts. These fields can
be replayed, audited, and compared. They must not be presented as final
institution/hot-money conclusions.

Examples:

```json
{
  "stock_code": "002747",
  "net_inflow": 12345,
  "super_large_order_flow": 5000,
  "large_order_flow": 3000,
  "medium_order_flow": -1000,
  "small_order_flow": -2000,
  "source": "eastmoney_fund_flow"
}
```

Semantics:

```text
large / super-large order flow
  -> order-size proxy
  -> not real institution identity
```

Dragon-tiger example:

```json
{
  "stock_code": "002747",
  "institution_buy": true,
  "seats": ["机构专用", "某某营业部"],
  "source": "dragon_tiger_snapshot"
}
```

Semantics:

```text
dragon tiger
  -> abnormal trading evidence
  -> not total institution capital
```

Theme-flow example:

```json
{
  "theme_name": "存储芯片",
  "net_inflow": 12345678,
  "rank": 3,
  "source": "theme_flow_snapshot"
}
```

Semantics:

```text
theme capital flow
  -> theme heat / flow evidence
  -> not main-force identity
```

### 2.2 Intelligence Layer

The Intelligence Layer produces analyst-style interpretation from multiple
evidence sources. It must carry evidence, confidence, and reason codes.

It is allowed to say:

```text
存储芯片 has institution_attention because:
  - theme stage is fermentation
  - theme strength is rising
  - theme flow has continued for multiple days
  - dragon-tiger evidence confirms participation
```

It is forbidden to say:

```text
main_net_inflow > 0
  -> institution_style
```

### 2.3 Calibration Layer

Analyst report values and labels belong to calibration:

```text
analyst report
  -> truth label
  -> model error
  -> future weight calibration
```

They must not be hardcoded into production evidence or producer outputs.

## 3. Field Definitions

| Field | Business meaning | Not meaning |
| --- | --- | --- |
| `capital.institution_style[]` | medium-term capital preference by industry/theme | dragon-tiger institution seat rows |
| `capital.hot_money_style[]` | short-term attack direction by theme/event | stock role labels or raw hot-money seats |
| `capital.evidence.dragon_tiger` | seat-level supporting evidence | the sole decision owner |
| `capital.active_amount` | short-term active capital fact | institution/hot-money style |
| `capital.evidence.fund_flow` | vendor-defined order-size flow evidence | real main-force identity |
| `capital.evidence.theme_flow` | theme-level flow/heat evidence | hot-money or institution label |

Avoid field names such as `main_force_money`. Prefer:

```text
fund_flow_evidence
large_order_flow
super_large_order_flow
retail_flow_proxy
net_inflow
```

These names make the proxy nature of the data explicit.

## 4. Data Source Capability Matrix

| Capability | Recommended source | Layer | Use | Priority | Restriction |
| --- | --- | --- | --- | --- | --- |
| individual stock fund flow | Eastmoney fund flow via a-stock-data adapter | Evidence | large/super-large/medium/small order-flow evidence | P0 | not real institution/retail identity |
| concept/theme fund flow | Eastmoney concept/theme fund flow via a-stock-data adapter | Evidence | theme flow / capital heat evidence | P0 | not direct hot-money or institution style |
| dragon tiger | official exchange / Eastmoney / a-stock-data adapter | Evidence | abnormal seat confirmation | P1 | enhancement only, not sole producer |
| limit-up pool | Eastmoney board pool | Evidence / Fact | short attack breadth and active capital | P0 | not institution identity |
| strong-stock structure | `strong_stock_watch_history` | Evidence | leader/sub-dragon/high-board structure | P0 | stock role is not participant identity |
| northbound | HKEX official preferred | Evidence | slow institutional proxy | P2 | not reliable as intraday style owner |
| margin financing / block trade | exchange / vendor sources | Evidence | slow auxiliary signal | P3 | not short-term attack owner |
| analyst report | internal analyst markdown / labels | Calibration | truth labels and weight tuning | M7 | never production fallback |

`a-stock-data` should be integrated only as an adapter source:

```text
a-stock-data
  -> Source Adapter
  -> Evidence Tables
  -> Capital Intelligence
```

Forbidden direct path:

```text
eastmoney_fund_flow
  -> institution_style
```

Required path:

```text
eastmoney_fund_flow
  -> stock_fund_flow_snapshot
  -> theme aggregation / evidence normalization
  -> institution_style evidence
```

## 5. Institution Style

### 3.1 Definition

`institution_style` describes medium-term capital preference for industry and
theme trends. It is closer to analyst sections such as "科技硬件",
"材料/服务器", and "存储/光通信/PCB", where themes are described as
"启动第1天", "调整第3天", or "资金回流".

It must answer:

- Which industry/theme directions are becoming preferred?
- What stage is each theme in?
- Is the direction sustained or only a one-day attack?
- What evidence supports the judgement?

It must not answer:

- Which seat bought which stock today?
- Which stock is 龙头/龙二/补涨?
- Which theme has the largest one-day raw inflow?

### 3.2 Candidate Sources

| Source | Owner role | Candidate fields | Restriction |
| --- | --- | --- | --- |
| `theme_cycle_judgement_v2` | lifecycle owner | stage, cycle day, divergence/start/fermentation/decay | lifecycle is not participant identity |
| `theme_strength_snapshot` | strength owner | strength score, rank, breadth, leader strength | strength is not institution identity |
| `subject_daily_feature` | theme behavior owner | breadth, turnover, leader quality, limit-up count | requires field-level proof before production |
| `theme_capital_flow` | theme money-flow evidence | inflow, return, continuity | evidence only; not active amount and not hot-money identity |
| `post_market_recap_snapshot.strong_hotspot_subjects` | confirmed theme evidence | market-recognized directions | evidence only, not a complete producer |
| `money_flow_enhanced` | stock money evidence | stock-level strength/concentration | `role_label` is stock role, not participant type |
| `stock_fund_flow_snapshot` | order-size flow evidence | net inflow, large/super-large order flow by stock | evidence only, not institution identity |
| `theme_flow_snapshot` | theme-flow evidence | theme-level net inflow and rank | evidence only, not final style |

### 3.3 Future Producer Contract

Candidate owner:

```text
ThemeCapitalIntelligenceProducer
```

Inputs:

```yaml
theme_cycle:
  source: theme_cycle_judgement_v2
theme_strength:
  source: theme_strength_snapshot
subject_daily_feature:
  source: subject_daily_feature
theme_capital_flow:
  source: theme_capital_flow
confirmed_hotspots:
  source: post_market_recap_snapshot.strong_hotspot_subjects
dragon_tiger_evidence:
  source: DragonTigerSnapshot
  role: evidence_only
fund_flow_evidence:
  source: stock_fund_flow_snapshot
  role: evidence_only
theme_flow_evidence:
  source: theme_flow_snapshot
  role: evidence_only
```

Output shape:

```json
{
  "theme_key": "9018144",
  "theme_name": "PCB印制电路板",
  "stage": "fermentation",
  "cycle_day": 1,
  "capital_signal": "资金回流",
  "confidence": 0.82,
  "reason": [
    "主题强度提升",
    "周期处于启动/发酵早期",
    "资金连续回流",
    "机构席位确认"
  ],
  "evidence": {
    "theme_strength": 85,
    "cycle": "fermentation",
    "sources": [
      "theme_strength_snapshot",
      "theme_cycle_judgement_v2",
      "theme_capital_flow"
    ]
  }
}
```

## 6. Hot-Money Style

### 4.1 Definition

`hot_money_style` describes short-term attack direction. It is closer to analyst
statements such as "商业航天 关注", "洪涝/水利 台风催化，观察", or
"光刻胶/材料 大面积启动第1天".

It must answer:

- Where is the short-term attack happening today?
- Which directions have limit-up spread or leader height?
- Which events are catalyzing the move?
- Is dragon-tiger evidence strengthening the signal?

It must not answer:

- Which theme has the largest active capital amount?
- Which stock has role label 龙头?
- Which seat category alone determines the theme direction?

### 4.2 Candidate Sources

| Source | Owner role | Candidate fields | Restriction |
| --- | --- | --- | --- |
| `post_market_recap_snapshot.strong_hotspot_subjects` | hotspot owner | confirmed hot themes, status text | names must pass identity guard |
| `limit_up.categories` | limit-up spread owner | theme category, count, stocks | source must stay recap/limit-up, not themes fallback |
| `strong_stock_watch_history` | strong-stock owner | leader, sub-dragon, height, role | stock role is not participant identity |
| structured event layer | event catalyst owner | policy/news/weather/event theme map | must be structured evidence, not free text fallback |
| `DragonTigerSnapshot` | seat evidence owner | seat participation and net buy evidence | evidence only; not sole decision owner |
| `stock_fund_flow_snapshot` | order-size flow evidence | large/super-large order participation | evidence only; not hot-money identity |

### 4.3 Future Producer Contract

Candidate owner:

```text
ShortTermCapitalProducer
```

Inputs:

```yaml
limit_up:
  source: limit_up.categories
strong_stock:
  source: strong_stock_watch_history
events:
  source: structured_event_layer
dragon_tiger_evidence:
  source: DragonTigerSnapshot
  role: evidence_only
fund_flow_evidence:
  source: stock_fund_flow_snapshot
  role: evidence_only
```

Output shape:

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
  "confidence": 0.78,
  "evidence": [
    "limit_up",
    "strong_stock",
    "dragon_tiger"
  ]
}
```

## 7. Source Ownership Matrix

| Target | Source owner | Allowed evidence | Forbidden path |
| --- | --- | --- | --- |
| `capital.institution_style[]` | `ThemeCapitalIntelligenceProducer` | theme cycle, theme strength, subject daily features, theme/theme fund flow, stock fund flow evidence, dragon-tiger evidence | `money_flow_enhanced.role_label -> institution_style` |
| `capital.hot_money_style[]` | `ShortTermCapitalProducer` | limit-up categories, strong stocks, events, stock fund flow evidence, dragon-tiger evidence | `theme_capital_flow -> hot_money_style` |
| `capital.evidence.dragon_tiger` | `DragonTigerSnapshot` | a-stock-data / normalized dragon-tiger source | dragon-tiger rows as sole style producer |
| `capital.active_amount` | `ActiveCapitalProducer` | BoardPoolSnapshot ZT/ZB/YZT amounts | theme capital flow, dragon tiger, analyst truth labels |
| `capital.evidence.fund_flow` | `FundFlowEvidenceAdapter` | Eastmoney / Sina fund-flow evidence | direct institution/hot-money conclusion |
| `capital.evidence.theme_flow` | `ThemeFlowEvidenceAdapter` | Eastmoney concept/theme flow, internal theme capital flow | active amount or final style label |

## 8. Target Architecture

```text
capital/
├── evidence/
│   ├── fund_flow_snapshot
│   ├── dragon_tiger_snapshot
│   └── theme_flow_snapshot
│
├── intelligence/
│   ├── institution_style
│   ├── hot_money_style
│   └── capital_rotation
│
└── calibration/
    └── analyst_feedback
```

Dragon-tiger data belongs to the evidence layer:

```text
a-stock-data adapter
  -> DragonTigerSnapshot
  -> Capital Evidence Layer
  -> institution_style / hot_money_style confidence adjustment
```

It must not become the only style producer.

## 9. Forbidden Paths

The following paths are explicitly forbidden:

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
  -> active_amount
```

```text
theme_capital_flow
  -> hot_money_style
```

```text
eastmoney_fund_flow.main_net_inflow > 0
  -> institution_style
```

```text
eastmoney_fund_flow.main_net_inflow > 0
  -> hot_money_style
```

```text
dragon_tiger rows missing
  -> infer from money_flow_enhanced / role_label / theme stage
```

```text
analyst_report.active_capital_yi
  -> production active_amount
```

## 10. Non-Goals

This PR does not:

- produce `institution_style[]`
- produce `hot_money_style[]`
- produce evidence tables
- change `ReviewDocument` schema
- change frontend rendering
- alter `ActiveCapitalProducer`
- ingest new dragon-tiger data
- ingest Eastmoney fund-flow data
- calibrate model weights against analyst reports

## 11. Next PRs

Suggested sequence:

```text
PR4.2.31 Capital Evidence Layer
  -> FundFlowEvidenceAdapter
  -> DragonTigerSnapshot adapter
  -> ThemeFlowEvidenceAdapter

PR4.2.32 InstitutionStyleProducer
  -> ThemeCapitalIntelligenceProducer only

PR4.2.33 HotMoneyStyleProducer
  -> ShortTermCapitalProducer only

M7 Analyst Feedback Calibration
  -> compare production outputs with analyst truth labels
  -> tune weights without hardcoding report values
```
