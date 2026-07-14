# Capital Intelligence Pipeline — Design & Implementation Plan

**Version:** v2.2 (Frozen)
**Date:** 2026-07-14
**Status:** Design Frozen — PR4.2.31f Ready
**Changes in v2.2:**
- Capital Lifecycle → Theme Capital Lifecycle Adapter (lifecycle originates from Theme Intelligence, not capital computation)

---

## Core Principle

```
资金数据 ≠ 资金判断

Data sources provide Evidence (事实证据)
AI models provide Intelligence (资金风格判断)
```

No single fund flow metric (e.g., `net_amount > 0`) shall ever be interpreted as "institution buying" or "hot money attack". The pipeline separates Evidence Layer from Intelligence Layer by design.

---

## 1. Overall Architecture

```
                     Multi-Source Fund Data
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   Tushare          东方财富           龙虎榜
   moneyflow        fund flow        Dragon Tiger
        │                │                │
        └────────────────┼────────────────┘
                         │
                Capital Evidence Layer
                         │
        ┌────────────────┼────────────────┐
        │                │                │
 Stock Fund Flow    Theme Fund Flow   Seat Evidence
 个股资金流          板块资金流          席位资金
        │                │                │
        └────────────────┼────────────────┘
                         │
               Market Capital State
              (市场资金环境判断)
                         │
        ┌────────────────┴────────────────┐
        │                                 │
   Risk Appetite                    Capital Style
   市场风险偏好                       资金风格
   (attack/defense/rotation)         (机构主导/游资主导/均衡)
                         │
                         │
        ┌────────────────┴────────────────┐
        │                                 │
  Institution Style                 Hot Money Style
  机构审美模型                        游资攻击模型
        │                                 │
        └────────────────┬────────────────┘
                         │
              Capital Intelligence Layer
                         │
              AI Explanation Layer
           (资金故事 / 风险提示)
                         │
                ReviewDocument.capital
                         │
                      Frontend
```

---

## 2. Target ReviewDocument Schema

```json
{
  "capital": {
    "active_amount": {
      "value": 2664.84,
      "unit": "yi",
      "source": "board_pool_zt_zb",
      "confidence": 0.85
    },

    "market_capital_state": {
      "capital_style": "rotation_attack",
      "risk_preference_score": 72,
      "active_capital_yi": 2664.84,
      "limit_up_count": 75,
      "limit_down_count": 25,
      "up_down_ratio": 1.47,
      "theme_rotation_speed": 0.35
    },

    "institution_style": [
      {
        "theme": "国产算力",
        "score": 82,
        "confidence": 0.76,
        "evidence_quality": {
          "fund_flow": "HIGH",
          "cycle": "HIGH",
          "dragon_tiger": "LOW"
        },
        "reason": [
          "资金持续流入5日",
          "主题周期: FERMENTATION",
          "产业逻辑强化"
        ],
        "evidence_refs": ["fund_flow_5d", "cycle_judgement", "industry_catalyst"]
      }
    ],

    "hot_money_style": [
      {
        "theme": "存储芯片",
        "score": 88,
        "confidence": 0.82,
        "evidence_quality": {
          "limit_up": "HIGH",
          "relay": "MEDIUM",
          "dragon_tiger": "LOW"
        },
        "reason": [
          "涨停扩散: 5只",
          "连板晋级率: 22%",
          "事件催化: 存储涨价"
        ],
        "evidence_refs": ["limit_up_categories", "relay_ecology", "event_calendar"]
      }
    ],

    "lifecycle": [
      {
        "theme": "存储芯片",
        "phase": "FERMENTATION",
        "days_since_start": 3,
        "signals": [
          "资金连续3日流入",
          "涨停扩散增加",
          "龙头未断板"
        ],
        "risk": "连续上涨后，短线资金拥挤度升高"
      }
    ],

    "explanation": {
      "capital_story": "过去5日资金持续流入存储芯片与国产算力，龙头股扩散至3家公司，当前处于启动阶段，机构资金偏好增强。",
      "risk_note": "连续上涨后，短线资金拥挤度升高，注意轮动风险。"
    },

    "evidence": {
      "fund_flow": [],
      "dragon_tiger": [],
      "northbound": []
    }
  }
}
```

---

## 3. Data Source Design

### 3.1 Layer 1: Stock Fund Flow (个股资金流)

**Question answered:** Which stocks have capital entering?

**Primary source:** Tushare `moneyflow`

| Status | Interface | Frequency | Unit Input | Unit Storage |
|--------|-----------|-----------|------------|--------------|
| VERIFIED | `moneyflow` | DAILY | 万元 (amount), 手 (vol) | 元 (amount), 手 (vol) |

**Semantic metadata (CRITICAL — must be stored with data):**

```json
{
  "semantic": {
    "vendor_defined": "order_size_flow",
    "not_owner_identity": true,
    "description": "成交单大小分类(小单/中单/大单/特大单)，非机构/游资/散户账户分类"
  }
}
```

Tushare `moneyflow` classifies trades by **order size**, NOT by investor identity. A large order does not mean "institution buying" — it means the order was above the size threshold. This distinction must be preserved throughout the pipeline.

**Field mapping:**

| Tushare Field | Meaning | Storage Field |
|---------------|---------|---------------|
| `buy_elg_amount` | 特大单买入金额 | `buy_elg_amount_yuan` |
| `sell_elg_amount` | 特大单卖出金额 | `sell_elg_amount_yuan` |
| `buy_lg_amount` | 大单买入金额 | `buy_lg_amount_yuan` |
| `sell_lg_amount` | 大单卖出金额 | `sell_lg_amount_yuan` |
| `buy_md_amount` | 中单买入金额 | `buy_md_amount_yuan` |
| `sell_md_amount` | 中单卖出金额 | `sell_md_amount_yuan` |
| `buy_sm_amount` | 小单买入金额 | `buy_sm_amount_yuan` |
| `sell_sm_amount` | 小单卖出金额 | `sell_sm_amount_yuan` |
| `net_mf_amount` | L2主力净流入 (不可自行重算) | `order_size_flow_amount_yuan` |
| `*_vol` | 各档成交量(手) | `*_vol_shou` |

**Field naming rationale:**

`net_amount_yuan` → `order_size_flow_amount_yuan`

The name `net_amount` implies "net capital flow" which invites misinterpretation as "smart money net buying". The name `order_size_flow_amount` explicitly ties the value to its actual source: order size classification, not investor identity classification.

**Unit conversion (CRITICAL — do NOT skip):**

```python
# Tushare amount fields are in 万元 (10k CNY)
# Storage unit is 元 (CNY)
amount_yuan = tushare_amount_wan * 10_000

# Tushare vol fields are in 手 (100 shares)
# Storage unit is 手 (shou) — keep as-is
vol_shou = tushare_vol
```

**Forbidden:** Do NOT recompute `net_amount` from bucket buys/sells. Tushare's `net_mf_amount` is L2-based and cannot be reproduced by summing bucket-level data.

**DB table: `stock_fund_flow_daily`**

```sql
CREATE TABLE stock_fund_flow_daily (
    trade_date      date,
    ts_code         varchar,
    -- extra-large (超大单, >=100万)
    buy_elg_amount_yuan   numeric,
    sell_elg_amount_yuan  numeric,
    buy_elg_vol_shou      numeric,
    sell_elg_vol_shou     numeric,
    -- large (大单, 20-100万)
    buy_lg_amount_yuan    numeric,
    sell_lg_amount_yuan   numeric,
    buy_lg_vol_shou       numeric,
    sell_lg_vol_shou      numeric,
    -- medium (中单, 5-20万)
    buy_md_amount_yuan    numeric,
    sell_md_amount_yuan   numeric,
    buy_md_vol_shou       numeric,
    sell_md_vol_shou      numeric,
    -- small (小单, <5万)
    buy_sm_amount_yuan    numeric,
    sell_sm_amount_yuan   numeric,
    buy_sm_vol_shou       numeric,
    sell_sm_vol_shou      numeric,
    -- net (L2-based, do not recalculate)
    net_amount_yuan       numeric,
    net_vol_shou          numeric,
    -- provenance
    source                varchar,
    created_at            timestamp
);
```

**Alternative sources (for source registry, NOT automatic fallback):**

| Source | Status | Fields |
|--------|--------|--------|
| Eastmoney `push2his` | CONNECTION_UNAVAILABLE | 5 net buckets (no buy/sell direction) |
| Sina `moneyflow` | CAPABILITY_LIMITED | net + super_large only (2 of 5 buckets) |

### 3.2 Layer 2: Theme Fund Flow (板块资金流)

**Question answered:** Which themes are capital flowing into?

**Data sources (priority order):**

| Priority | Source | Status | Detail |
|----------|--------|--------|--------|
| P0 | Tushare `moneyflow_cnt_ths` | ACCESS_DENIED | 同花顺概念板块资金流, needs 6000 credits |
| P1 | Self-aggregated from stock flow | AVAILABLE | Sum stock flows by theme mapping |
| P2 | Existing `theme_capital_flow` | AVAILABLE | Current evidence, keep as secondary |

**P1 aggregation formula:**

```
theme_net_flow  = SUM(stock_net_flow) FOR stocks IN theme
theme_large_flow_score = SUM(buy_lg + buy_elg - sell_lg - sell_elg) / SUM(turnover)
positive_stock_ratio  = COUNT(stock WHERE net > 0) / COUNT(all stocks in theme)
```

**DB table: `theme_fund_flow_daily`**

```sql
CREATE TABLE theme_fund_flow_daily (
    trade_date           date,
    subject_key          varchar,
    theme_name           varchar,
    stock_count          int,
    net_flow_yuan        numeric,
    large_flow_yuan      numeric,
    positive_stock_ratio numeric,
    limit_up_count       int,
    source               varchar,
    created_at           timestamp
);
```

---

## 4. Evidence Feature Engineering

### 4.1 Large Capital Intensity (大资金流入强度)

```
large_flow_score = (超大单净额 + 大单净额) / 成交额

Example:
  股票A: 超大单+2亿, 大单+3亿, 成交额20亿
  large_flow_score = 25% → 大资金参与明显
```

### 4.2 Flow Persistence (资金持续性)

```
flow_persistence = positive_days / total_days (rolling 5-day window)

Example:
  past 5 days: +3, +2, +1, -1, +4 (亿)
  flow_persistence = 4/5 = 0.80 → 资金持续流入
```

### 4.3 Flow Acceleration (资金加速度)

```
flow_acceleration = today_net_flow - avg_5day_net_flow

Positive → 资金突然加速进入 (potential catalyst)
Negative → 资金减速/撤离 (potential distribution)
```

---

## 5. Institution Style Intelligence Model

**Input:** NOT raw fund flow. Weighted multi-signal model.

### 5.1 Input Signals

| Signal | Weight | Source | Metric |
|--------|--------|--------|--------|
| Theme Fund Flow | **35%** | `theme_fund_flow_daily` | net_flow, persistence, acceleration |
| Industry Cycle Logic | **30%** | `theme_cycle_judgement_v2` | cycle stage (START/FERMENTATION bonus) |
| Strong Stock Structure | **25%** | `strong_stock_watch_history` | leader count, 中军 strength, trend stock ratio |
| Dragon Tiger Seats | **10%** | seat evidence | institution_seat_count, institution_buy_amount |

**Weight rationale (v2.0):** Dragon tiger reduced 20%→10%. True institution preference is closer to industry trends + sustained flow + core company structure. Dragon tiger has delayed data, sample bias, and mixed hot money behavior.

### 5.2 Formula

```
institution_score = 0.35 × theme_flow_score
                  + 0.30 × cycle_score
                  + 0.25 × stock_structure_score
                  + 0.10 × dragon_tiger_seat_score
```

### 5.3 Forbidden Interpretations

```
❌ net_amount > 0 → institution_attention
❌ moneyflow_ths → ReviewDocument.capital.institution (cross-layer violation)
❌ large_flow_score > threshold → institution_style (single-feature decision)
```

---

## 6. Hot Money Style Intelligence Model

Hot money is fundamentally different from institution flow — it focuses on short-term explosive momentum.

### 6.1 Input Signals

| Signal | Weight | Source | Metric |
|--------|--------|--------|--------|
| Limit-Up Diffusion | 35% | `limit_up.categories` | theme_limitup_count, board_height_distribution |
| Relay Ecology | 25% | relay snapshot | 1→2 promotion rate, 2→3 rate, max board height |
| Strong Stock Attack | 25% | `strong_stock_watch_history` | leader sealed, turnover rate,封单 |
| Dragon Tiger Hot Money | 15% | seat evidence | hot_money_name presence, continuous_days |

### 6.2 Formula

```
hot_money_score = 0.35 × limitup_score
                + 0.25 × relay_score
                + 0.25 × strong_stock_attack_score
                + 0.15 × dragon_tiger_hot_score
```

---

## 7. Dragon Tiger Re-Positioning

Dragon tiger data is **evidence enhancement**, not the primary capital direction source.

| Use | Weight | Detail |
|-----|--------|--------|
| Institution boost | 10% | institution seat buy activity (reduced: delayed, sample-biased) |
| Hot money boost | 15% | well-known hot money seat presence |

**Data sources (priority):**

1. Tushare dragon tiger API
2. a-stock-data encapsulated interface
3. Eastmoney datacenter (fallback)

---

## 8. Recommended Data Source Matrix

| Usage | Source | Status | Notes |
|-------|--------|--------|-------|
| Active capital | `board_pool_zt_zb` | ✅ COMPLETE | Current active_amount |
| Stock fund flow | Tushare `moneyflow` | ✅ VERIFIED | P0, ready for adapter |
| THS stock flow | Tushare `moneyflow_ths` | ACCESS_DENIED | Needs 6000 credits |
| Concept fund flow | Tushare `moneyflow_cnt_ths` | ACCESS_DENIED | Needs 6000 credits |
| Dragon tiger | Tushare / a-stock-data | DEFERRED | Phase 4+ |
| Northbound flow | Tushare + HKEX verify | SEMANTIC_AUDIT_REQUIRED | Data magnitude suspicious |
| Theme fund intelligence | Self-built model | CORE_IP | Competitive advantage |

---

## 9. Implementation Phases

### Phase 0 — Market Capital State (PR4.2.31e)

**Target:** Establish today's capital environment BEFORE direction judgement.

```
MarketMetricsSnapshot (active_capital, limit_up, limit_down, up_down_ratio)
        │
        ▼
MarketCapitalStateProducer
        │
        ▼
market_capital_state_daily table
  {capital_style: rotation_attack|defensive|risk_off, risk_preference_score: 0-100}
```

**Why Phase 0:** Same fund flow signal means different things in different environments. Strong market + fund flow = accumulation; weak market + fund flow = sheltering.

---

### Phase 1 — Stock Fund Flow Evidence (PR4.2.31f)

**Target:** Tushare Moneyflow Evidence Adapter

```
Tushare moneyflow API
        │
        ▼
TushareMoneyflowNormalizer  (万元→元, 手→手)
        │
        ▼
stock_fund_flow_daily table
        │
        ▼
Evidence Layer ONLY — no UI connection
```

**Deliverables:**
- `TushareMoneyflowNormalizer` class
- `stock_fund_flow_daily` DB table
- Field semantics: `order_size_flow_amount_yuan` (not `net_amount_yuan`)
- Metadata: `vendor_defined: order_size_flow, not_owner_identity: true`
- Unit tests: field mapping, unit conversion, net_mf_amount preservation
- Contract test: no net_amount recomputation from buckets

**Acceptance Contracts:**

| # | Contract | Assertion |
|---|----------|-----------|
| C1 | Unit conversion | `Tushare 54615.01 万元 → DB 546150100 元` |
| C2 | No recomputation | `net_amount != (buy_elg + buy_lg - sell_elg - sell_lg)` |
| C3 | No forbidden fields | Zero occurrences of: `institution`, `hot_money`, `smart_money`, `main_force` |
| C4 | Evidence replayable | Same `(trade_date, ts_code)` → same snapshot every time |
| C5 | Semantic metadata | Every row carries `semantic_type: order_size_flow, not_owner_identity: true` |
| C6 | Source provenance | Every row carries `source_name`, `source_version`, `collected_at`, `semantic_type`, `not_owner_identity` for M7 traceability |

**Forbidden in this PR:**
```
❌ theme aggregation
❌ institution_style
❌ hot_money_style
❌ ReviewDocument
❌ UI
❌ frontend
```

---

### Phase 2 — Theme Capital Attribution (PR4.2.32)

**Target:** Theme Capital Attribution Engine — weighted allocation to prevent double-counting.

```
stock_fund_flow_daily
        +
stock_theme_map + theme_weight
        │
        ▼
ThemeCapitalAttributionEngine
  rule: theme_flow = stock_flow × theme_weight
  constraint: SUM(theme_weight per stock) ≤ 1.0
        │
        ▼
theme_fund_flow_daily table
```

**Critical:** A-share stocks belong to multiple themes. Direct SUM inflates totals (1 stock × 5 themes = 5× overcount). The attribution engine applies `theme_weight` per stock-theme pair to ensure Σ(allocation) = actual flow.

---

### Phase 2.5 — Theme Capital Lifecycle Adapter (PR4.2.33)

**Target:** Adapt existing Theme Intelligence lifecycle data for Capital context. Lifecycle is NOT computed from fund flow — it originates from Theme Intelligence (theme_cycle_judgement_v2, theme_strength_snapshot, subject_daily_feature).

```
theme_cycle_judgement_v2 (existing)
        +
theme_strength_snapshot (existing)
        +
theme_fund_flow_daily (Phase 2)
        │
        ▼
ThemeCapitalLifecycleAdapter
  phase: START | FERMENTATION | CLIMAX | DIVERGENCE | FADE
  days_since_start: N
  signals: [资金连续流入, 涨停扩散, 龙头状态]
        │
        ▼
capital.lifecycle[]
```

**Name rationale:** "Capital Lifecycle Producer" implies lifecycle is derived from capital data. The actual lifecycle engine already exists in `theme_cycle_judgement_v2` — this adapter maps Theme Intelligence lifecycle into Capital context by overlaying fund flow evidence. It adapts, not produces.

---

### Phase 3 — Institution Style (PR4.2.34)

**Target:** InstitutionStyleProducer

```
theme_fund_flow_daily  (35%)
theme_cycle_judgement  (30%)
strong_stock_watch     (25%)
dragon_tiger seats     (10%)
        │
        ▼
InstitutionStyleProducer
        │
        ▼
capital.institution_style[]
```

---

### Phase 4 — Hot Money Style (PR4.2.35)

**Target:** HotMoneyStyleProducer

```
limit_up.categories    (35%)
relay_ecology          (25%)
strong_stock_watch     (25%)
dragon_tiger seats     (15%)
        │
        ▼
HotMoneyStyleProducer
        │
        ▼
capital.hot_money_style[]
```

---

### Phase 5 — AI Capital Explanation (PR4.2.36)

**Target:** Natural-language capital narrative from structured intelligence.

```
institution_style[] + hot_money_style[] + lifecycle[] + market_capital_state
        │
        ▼
CapitalExplanationProducer
        │
        ▼
capital.explanation {capital_story, risk_note}
```

Explanation is an independent model capability, not a frontend formatting concern.

---

### Phase 6 — Frontend Connection (PR4.2.37)

**Target:** Wire complete capital intelligence into ReviewDocument

```
capital.market_capital_state ──→  市场资金环境
capital.institution_style[]  ──→  机构资金审美方向
capital.hot_money_style[]    ──→  游资情绪方向
capital.lifecycle[]          ──→  资金生命周期
capital.explanation          ──→  AI 资金叙事 + 风险提示
```

---

## 10. Source Ownership Registry (Frozen)

```yaml
stock_daily_order_size_flow:
  primary:
    source: tushare.moneyflow
    owner_team: CapitalEvidenceTeam
    version: v1
    verified_date: 2026-07-14
    last_failure_reason: none
    status: VERIFIED
    frequency: DAILY
    unit_input: 万元
    unit_storage: 元
    buy_sell_direction: PRESERVED
    fallback_policy: forbidden
    semantic:
      vendor_defined: order_size_flow
      not_owner_identity: true
    change_policy:
      require_audit: true
  secondary:
    source: eastmoney.push2his
    owner_team: CapitalEvidenceTeam
    version: v1
    status: CONNECTION_UNAVAILABLE
    last_failure_reason: RemoteProtocolError
    buy_sell_direction: MISSING
    fallback_policy: forbidden
    change_policy:
      require_audit: true
  limited_fallback:
    source: sina.moneyflow_daily
    status: CAPABILITY_LIMITED
    available_buckets: [net, super_large]
    buy_sell_direction: MISSING

theme_daily_fund_flow:
  preferred:
    source: tushare.moneyflow_cnt_ths
    status: ACCESS_DENIED
    required_credits: 6000
  self_aggregated:
    source: stock_fund_flow_daily + stock_theme_map
    status: AVAILABLE

cross_border_flow:
  source: tushare.moneyflow_hsgt
  transport_capability: SUPPORTED
  schema_capability: SUPPORTED
  semantic_quality: SUSPICIOUS
  production_ready: false
```

---

## 11. Guard Rules

```
✅ ALLOWED:
  - Tushare moneyflow → stock_fund_flow_daily (evidence)
  - stock_fund_flow_daily → theme_fund_flow_daily (aggregation)
  - Multi-signal weighted model → institution_style/hot_money_style
  - Unit conversion with explicit formula documentation

❌ FORBIDDEN:
  - net_amount > 0 → "机构买入"
  - Single source → capital intelligence (must use multi-signal)
  - Automatic source fallback (must be explicit registry decision)
  - Direct UI connection without passing through Intelligence Layer
  - Recomputing net_mf_amount from bucket data
  - moneyflow_ths → ReviewDocument.capital.institution (wrong layer)
  - moneyflow_cnt_ths → ReviewDocument.capital.hot_money (wrong layer)
```
