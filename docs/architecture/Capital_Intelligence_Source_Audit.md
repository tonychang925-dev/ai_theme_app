# Capital Intelligence Source Audit

**PR:** PR4.2.30 / PR4.2.31
**Status:** Audit + Probe Verified
**Frozen Date:** 2026-07-14
**Scope:** Define semantics, source ownership, and producer contracts for Capital Intelligence. No production code, UI, ReviewDocument schema, or fallback behavior changes.

---

## 1. Layer Architecture

```
                         Capital Intelligence
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
   Evidence Layer          Market State Layer       Intelligence Layer
   (observable facts)      (环境判断)                (analyst-style judgement)
          │                       │                       │
   ┌──────┼──────┐         ┌──────┴──────┐         ┌─────┴─────┐
   │      │      │         │             │         │           │
fund flow 龙虎榜 theme   Risk Appetite  Style   Institution  HotMoney
          flow           攻击/防守/轮动  机构/游资    Style      Style
```

### 1.1 Evidence Layer

Stores observable or vendor-defined facts. Replayable, auditable, comparable.
Must NOT be presented as final institution/hot-money conclusions.

### 1.2 Market Capital State Layer (NEW)

Answers: "What is today's capital environment?" BEFORE asking "Which direction?"

```
Market Capital State:
  capital_style: rotation_attack | defensive | risk_off
  risk_preference_score: 0-100
  inputs: active_capital, limit_up_count, up_down_ratio, theme_rotation_speed
```

### 1.3 Intelligence Layer

Produces analyst-style interpretation from multiple evidence sources.
Must carry evidence refs, confidence, and reason codes.

---

## 2. Data Source Capability Matrix (Verified)

### 2.1 Stock Fund Flow

| Source | Capability | Frequency | Fields | Buy/Sell Direction | Status |
|--------|-----------|-----------|--------|-------------------|--------|
| **Tushare `moneyflow`** | 4档买卖量+额+净额 | DAILY | 20 fields | ✅ PRESERVED | **P0 VERIFIED** |
| Eastmoney `push2his` | 5档净额 only | DAILY | 5 net buckets | ❌ MISSING | CONNECTION_UNAVAILABLE |
| Sina `moneyflow_daily` | 2档净额 only | DAILY | net + super_large | ❌ MISSING | CAPABILITY_LIMITED |

**Probe results (2026-07-14):**
- Tushare `moneyflow`: 300223.SZ returned 20 fields, all expected fields present. Unit: 万元→元.
- Tushare `moneyflow_ths`: ACCESS_DENIED (requires 6000 credits)
- Tushare `moneyflow_cnt_ths`: ACCESS_DENIED (requires 6000 credits)
- Tushare `moneyflow_hsgt`: Transport OK, schema OK, **semantic quality SUSPICIOUS** (north_money=4007亿/day anomalous)
- Eastmoney `push2his`: RemoteProtocolError on current run; readback confirms prior successful collection
- Sina `moneyflow_daily`: HTTP 200, 20 rows, but only net + super_large (no large/medium/small split)

**Decision:** Tushare `moneyflow` is the primary stock fund flow source. Eastmoney and Sina are registered as alternatives for source availability comparison only — NO automatic fallback.

### 2.2 Theme Fund Flow

| Source | Capability | Frequency | Status |
|--------|-----------|-----------|--------|
| Tushare `moneyflow_cnt_ths` | 概念板块资金流 (净买/净卖/净额) | DAILY | ACCESS_DENIED (6000 credits) |
| Self-aggregated (stock→theme) | 个股聚合 | DAILY | **AVAILABLE** (requires attribution engine) |
| Eastmoney concept flow | 板块资金流 | DAILY | CONNECTION_UNAVAILABLE |

### 2.3 Other Capital Sources

| Capability | Source | Status | Notes |
|-----------|--------|--------|-------|
| Active capital | `board_pool_zt_zb` | ✅ COMPLETE | Current active_amount=2664.84 |
| Dragon tiger | Tushare / a-stock-data | DEFERRED | Phase 4+ |
| Northbound | Tushare `moneyflow_hsgt` + HKEX | SEMANTIC_AUDIT_REQUIRED | north_money magnitude anomalous |
| Limit-up pool | `limit_up.categories` | ✅ (recap-dependent) | Requires recap snapshot |
| Strong stock structure | `strong_stock_watch_history` | ✅ AVAILABLE | leader/sub-dragon/height |

---

## 3. Field Semantics

### 3.1 Order-Size Flow (NOT "主力资金")

```
Tushare moneyflow semantics:
  vendor_defined: order_size_flow
  not_owner_identity: true
  description: "成交单大小分类(小单/中单/大单/特大单)，非机构/游资/散户账户分类"
```

| Field | Business meaning | NOT meaning |
|-------|-----------------|-------------|
| `order_size_flow_amount_yuan` | L2-based net order-size flow | "主力资金净流入" |
| `buy_elg_amount_yuan` | 特大单主动买入金额 (>=100万/笔) | "机构买入" |
| `buy_lg_amount_yuan` | 大单主动买入金额 (20-100万/笔) | "游资买入" |
| `capital.institution_style[]` | Medium-term capital preference by industry/theme | Dragon-tiger institution seat rows |
| `capital.hot_money_style[]` | Short-term attack direction by theme/event | Stock role labels or raw hot-money seats |
| `capital.market_capital_state` | Today's capital environment judgement | Single-source capital conclusion |

### 3.2 Forbidden Field Names

```
❌ main_force_money
❌ institution_flow
❌ smart_money_net

✅ order_size_flow_amount
✅ fund_flow_evidence
✅ large_order_flow
✅ super_large_order_flow
```

---

## 4. Theme Capital Attribution (Critical)

### 4.1 The Double-Counting Problem

A single stock belongs to multiple themes. Direct SUM of stock flows by theme inflates totals:

```
中科曙光 belongs to: 国产算力, 液冷服务器, AI服务器, 华为产业链
fund_flow: +10亿

Naive aggregation:
  国产算力 +10, 液冷 +10, AI +10, 华为 +10 = 40亿 (WRONG)

Correct attribution:
  国产算力 × 0.5 + 液冷 × 0.3 + AI × 0.2 = 10亿 (weighted split)
```

### 4.2 Attribution Engine Contract

```yaml
ThemeCapitalAttributionEngine:
  inputs:
    - stock_fund_flow_daily
    - stock_theme_map (with theme_weight per stock)
  output:
    - theme_fund_flow_daily (weight-allocated)
  rule:
    theme_flow = stock_flow × theme_weight
    SUM(theme_weight for a stock) ≤ 1.0
```

---

## 5. Institution Style Producer Contract

### 5.1 Input Signals (Adjusted Weights)

| Signal | Weight | Source | Metric |
|--------|--------|--------|--------|
| Theme Fund Flow | **35%** | `theme_fund_flow_daily` | net_flow, persistence, acceleration |
| Industry Cycle Logic | **30%** | `theme_cycle_judgement_v2` | cycle stage (START/FERMENTATION bonus) |
| Strong Stock Structure | **25%** | `strong_stock_watch_history` | leader count, 中军 strength, trend stock ratio |
| Dragon Tiger Seats | **10%** | seat evidence | institution_seat_count, institution_buy_amount |

**Weight rationale:** Dragon tiger reduced from 20%→10% because: delayed data, sample bias, mixed with hot money behavior. True institution preference is closer to industry trends + sustained flow + core company structure.

### 5.2 Output Contract

```json
{
  "theme_key": "9018144",
  "theme_name": "国产算力",
  "score": 82,
  "reason": [
    "资金持续流入5日",
    "主题周期: FERMENTATION",
    "产业逻辑强化"
  ],
  "evidence_refs": ["fund_flow_5d", "cycle_judgement", "stock_structure"]
}
```

---

## 6. Hot Money Style Producer Contract

### 6.1 Input Signals

| Signal | Weight | Source | Metric |
|--------|--------|--------|--------|
| Limit-Up Diffusion | 35% | `limit_up.categories` | theme_limitup_count, board_height |
| Relay Ecology | 25% | relay snapshot | 1→2 rate, 2→3 rate, max height |
| Strong Stock Attack | 25% | `strong_stock_watch_history` | leader sealed, turnover, 封单 |
| Dragon Tiger Hot Money | 15% | seat evidence | hot_money_name presence, continuous_days |

### 6.2 Output Contract

```json
{
  "theme_key": "9015778",
  "theme_name": "存储芯片",
  "score": 88,
  "reason": [
    "涨停扩散: 5只",
    "连板晋级率: 22%",
    "事件催化: 存储涨价"
  ],
  "evidence_refs": ["limit_up_categories", "relay_ecology", "event_calendar"]
}
```

---

## 7. AI Explanation Layer

Capital Intelligence must include natural-language explanation:

```json
{
  "capital": {
    "explanation": {
      "capital_story": "过去5日资金持续流入存储芯片与国产算力，龙头股扩散至3家公司，当前处于启动阶段，机构资金偏好增强。",
      "risk_note": "连续上涨后，短线资金拥挤度升高，注意轮动风险。"
    }
  }
}
```

This leverages your existing AI analysis capability — transforming structured evidence into readable capital narrative.

---

## 8. Forbidden Paths

```
❌ net_amount > 0 → institution_attention
❌ net_amount > 0 → hot_money_style
❌ moneyflow_ths → ReviewDocument.capital.institution
❌ moneyflow_cnt_ths → ReviewDocument.capital.hot_money
❌ money_flow_enhanced.role_label → institution_style
❌ money_flow_enhanced.role_label → hot_money_style
❌ theme_capital_flow → hot_money_style
❌ theme_capital_flow → active_amount
❌ seat_money_summary → institution_style (sole source)
❌ seat_money_summary → hot_money_style (sole source)
❌ dragon_tiger missing → infer from role_label / theme stage
❌ automatic source fallback (must be explicit registry decision)
❌ recomputing net_mf_amount from bucket data
❌ direct UI connection without Intelligence Layer
```

---

## 9. Target Directory Structure

```
capital/
├── evidence/
│   ├── stock_fund_flow_daily        (Tushare moneyflow → DB)
│   ├── theme_fund_flow_daily        (attribution engine → DB)
│   └── dragon_tiger_snapshot        (future)
│
├── state/
│   └── market_capital_state_daily   (capital_style, risk_preference)
│
├── intelligence/
│   ├── institution_style_producer
│   ├── hot_money_style_producer
│   └── capital_explanation_producer
│
└── calibration/
    └── analyst_feedback             (M7)
```

---

## 10. Implementation Sequence

```
Phase 0:  Market Capital State         (PR4.2.31e)
Phase 1:  Tushare Moneyflow Adapter    (PR4.2.31f) — Stock Fund Flow Evidence
Phase 2:  Theme Attribution Engine     (PR4.2.32)  — weighted stock→theme
Phase 2.5: Theme Capital Lifecycle Adapter (PR4.2.33)  — adapt Theme Intelligence lifecycle
Phase 3:  Institution Style Producer   (PR4.2.34)  — multi-signal model
Phase 4:  Hot Money Style Producer     (PR4.2.35)  — multi-signal model
Phase 5:  AI Capital Explanation       (PR4.2.36)  — narrative generation
Phase 6:  Frontend Connection          (PR4.2.37)  — wire to ReviewDocument
```

---

## 11. Non-Goals

- No frontend change in Phase 0-4
- No Assembler change
- No ContextFactory change
- No ReviewDocument schema change until Phase 5
- No inference from stock role to capital participant type
- No automatic source fallback
