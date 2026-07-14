# Capital Intelligence v1.0 — Architecture Freeze

**Version:** v1.0 Frozen
**Date:** 2026-07-14
**Status:** All Producer contracts verified. Ready for M7 calibration.

---

## 1. System Architecture

```
                         Market State
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         Emotion          Direction         Event
         Engine            Layer           Catalyst
              │               │               │
              └───────────────┼───────────────┘
                              │
                    Theme Attribution
                              │
              ┌───────────────┴───────────────┐
              │                               │
       Institution Style                Hot Money Style
       (机构资金审美)                    (游资攻击情绪)
              │                               │
              └───────────────┬───────────────┘
                              │
                    Capital Intelligence
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         Consensus       Divergence      Narrative
         (共识方向)      (背离方向)      (资金叙事)
```

## 2. Data Flow (End-to-End)

```
Tushare moneyflow API
        │
        ▼
stock_fund_flow_daily                    ← PR4.2.31f
        │
        ├── subject_stock_map
        └── theme_cycle_judgement_v2
                │
                ▼
theme_capital_flow_daily                 ← PR4.2.32a
        │
        ├── direction_theme_binding
        └── theme_direction_allocation_daily
                │
                ▼
direction_capital_flow_daily             ← PR4.2.34a
        │
        ┌───────┴───────┐
        ▼               ▼
institution_style_    hot_money_style_
daily                 daily
(PR4.2.33a/35a)       (PR4.2.36b)
        │               │
        └───────┬───────┘
                │
                ▼
        ReviewDocument.capital
```

---

## 3. Frozen Source Ownership Registry

### 3.1 Stock Fund Flow
```yaml
owner: TushareMoneyflowAdapter
source: tushare.moneyflow
version: v1
verified_date: 2026-07-14
status: VERIFIED
table: stock_fund_flow_daily
semantic: order_size_flow, not_owner_identity
fallback_policy: forbidden
tests: 25/25
```

### 3.2 Theme Attribution
```yaml
owner: ThemeCapitalAttributionEngine
source: stock_fund_flow_daily + subject_stock_map
version: identity_registry_v1
status: VERIFIED
tables: [stock_theme_attribution_daily, theme_capital_flow_daily]
method: PRIMARY(0.60) + RELATED(0.40 split)
constraint: SUM(weight) ≤ 1.0 per stock (C1)
conservation: C10 theme, C12 capital closure (C8)
tests: 15/15
```

### 3.3 Investment Direction
```yaml
owner: DirectionCapitalAggregator
source: theme_capital_flow_daily + direction_theme_binding
version: bootstrap_v1
status: VERIFIED
tables: [direction_capital_flow_daily, theme_direction_allocation_daily]
directions: 20 (10 populated, 10 design targets)
constraint: C10 theme conservation, C12 capital closure
identity: theme_name resolution (not hardcoded subject_key)
tests: 13/13
```

### 3.4 Institution Style
```yaml
owner: InstitutionStyleProducer
version: v2 (Direction S1)
status: FROZEN
table: institution_style_daily
signals:
  S1: Direction Capital Flow (35%)
  S2: Industry Cycle (30%)
  S3: Stock Structure (25%)
  S4: Dragon Tiger (10%)
modifiers:
  - Market Regime (deferred to PR4.2.33b, currently 1.0)
  - Direction Quality Gate (capital_coverage + stock_coverage + identity)
  - Direction Confidence (0.5×capital + 0.3×stock + 0.2×identity)
cycle_vocabulary: [divergence, fade_watch, fade_confirmed, fermentation,
                   start, incubation, acceleration, climax, repair, decay]
forbidden: single-signal, net_amount→institution, DT as sole source
tests: 19/19
```

### 3.5 Hot Money Style
```yaml
owner: HotMoneyStyleProducer
version: v1
status: FROZEN
table: hot_money_style_daily
signals:
  S1: Limit-up Expansion (35%)
  S2: Relay Structure (25%)
  S3: Strong Stock Attack (25%)
  S4: Dragon Tiger (15%)
modifiers:
  - Event Modifier (×1.00-1.15, confidence boost only)
  - Emotion Modifier (×0.85-1.10, ICE_POINT=1.10)
output: institution_hot_relation field
forbidden: Institution formula reuse, shared weights, shared imports
tests: 10/10
```

---

## 4. Frozen Contract Registry (42 Total)

| Suite | Count | Last Verified |
|-------|-------|---------------|
| Tushare Moneyflow Evidence | 25 | 2026-07-14 |
| Theme Capital Attribution | 15 | 2026-07-14 |
| Investment Direction Layer | 13 | 2026-07-14 |
| Institution Style Producer | 19 | 2026-07-14 |
| Hot Money Style Producer | 10 | 2026-07-14 |
| Direction Coverage Audit | — | 2026-07-14 |
| Stock Identity Normalizer | — | 2026-07-14 |
| **Total** | **82** | |

---

## 5. Institution vs Hot Money — Complete Separation

| Dimension | Institution | Hot Money |
|-----------|------------|-----------|
| **Question** | Which industrial direction is capital accumulating? | Where is short-term attack happening today? |
| **Grain** | Direction (产业方向) | Theme (题材标签) |
| **Time window** | 5-20 trading days | 1-3 trading days |
| **S1 Signal** | Direction Capital Flow (35%) | Limit-up Expansion (35%) |
| **S2 Signal** | Industry Cycle (30%) | Relay Structure (25%) |
| **S3 Signal** | Stock Structure (25%) | Strong Stock Attack (25%) |
| **S4 Signal** | Dragon Tiger (10%) | Dragon Tiger (15%) |
| **DT missing** | Weight redistributed, dynamic penalty | Weight redistributed |
| **Modifiers** | Direction Quality Gate | Event + Emotion |
| **Output table** | institution_style_daily | hot_money_style_daily |
| **Module file** | institution_style_producer.py | hot_money_style_producer.py |
| **Shared code** | NONE | NONE |

---

## 6. Key Architecture Decisions (Frozen)

1. **Evidence before Intelligence** — Fund flow data is vendor-defined order-size evidence, never institution/hot-money identity
2. **Theme ≠ Direction** — Theme is market classification; Direction is investment cognition. They co-exist.
3. **PRIMARY/RELATED weights** — 0.60/0.40 split, not equal 1/N
4. **Single-signal forbidden** — No `net_amount > 0 → institution_style`
5. **Automatic fallback forbidden** — Source switching must be explicit registry decision
6. **Dragon Tiger is enhancement** — 10-15%, never sole style producer
7. **theme_name resolution** — Bootstrap uses theme names, not hardcoded internal keys
8. **Capital conservation** — Σ direction + unattributed = Σ theme (C10/C12)
9. **Direction quality gate** — Low coverage → confidence downgrade, not score manipulation
10. **Institution-Hot Money separation** — Different modules, weights, grains, time windows

---

## 7. Next Phase: Explainable Capital

### 7.1 Capital Narrative Engine

Converts structured scores into natural-language explanation:

```
Input:
  Institution: AI算力(score=73, FERMENTATION, flow↑4d)
  Hot Money: 商业航天(score=82, FIRST_WAVE, event=政策催化)

Output:
  "机构资金持续流入AI算力方向，已连续4日增强，处于产业发酵阶段。
   游资今日主要攻击商业航天，受政策催化影响，处于首波攻击阶段。"
```

### 7.2 Consensus & Divergence

```
Consensus (机构+游资共同认可):
  AI算力: Institution=73, HotMoney=65 → BOTH

Divergence (机构+游资方向背离):
  存储芯片: Institution=72, HotMoney=28 → INSTITUTION_ONLY
  商业航天: Institution=30, HotMoney=82 → HOT_MONEY_ONLY
```

### 7.3 M7 Calibration Targets

```
Before: calibrate single score
After:  calibrate separately —
  Institution Style vs analyst institution rankings
  Hot Money Style vs analyst hot money mentions
  Consensus stability vs report consistency
  Narrative accuracy vs analyst report text
```

---

## 8. Design Document Index

| PR | Document | Status |
|----|----------|--------|
| — | `Capital_Intelligence_Pipeline_Design.md` | v2.2 Frozen |
| — | `Capital_Intelligence_Source_Audit.md` | Verified |
| — | `Capital_Intelligence_Source_Ownership.md` | Frozen |
| 4.2.31f | `Tushare_Fund_Flow_Capability_Audit.md` | ✅ Implemented |
| 4.2.32a | `PR4.2.32_Theme_Capital_Attribution_Design.md` | v2.0, ✅ Implemented |
| 4.2.33a | `PR4.2.33_Institution_Style_Producer_Design.md` | v2.0, ✅ Implemented |
| 4.2.34a | `PR4.2.34_Investment_Direction_Layer_Design.md` | v2.0, ✅ Implemented |
| 4.2.36b | `PR4.2.36_Hot_Money_Style_Design.md` | v1.0, ✅ Implemented |
| — | `Golden_UI_Field_Recovery_Checklist.md` | 11/18 recovered |
| — | `Capital_Intelligence_v1_Freeze.md` | This document |

---

## 9. Stable Baseline for Production

This freeze establishes a **regressable, auditable, contract-verified** capital intelligence foundation. All 82 contract tests provide a safety net for future development.

The next phase — M7 Analyst Feedback Calibration — can now proceed with confidence that the underlying models are frozen and their source ownership is traceable.
