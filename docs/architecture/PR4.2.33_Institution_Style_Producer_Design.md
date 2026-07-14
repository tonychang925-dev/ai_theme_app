# PR4.2.33 — Institution Style Producer

**Version:** v2.0
**Date:** 2026-07-14
**Status:** Design Frozen — PR4.2.33a Ready
**Depends on:** PR4.2.32a (theme_capital_flow_daily)
**Feeds into:** PR4.2.35 (AI Capital Explanation), PR4.2.37 (Frontend)
**Changes in v2.0:**
- S1: +flow_consistency (0.1), 4-factor breakdown
- S2: 7-stage granular table (START→DECAY), not 2-stage
- S3: leader_quality(0.4) + core_stock_strength(0.35) + breadth_depth(0.25)
- S4: +seat_quality_score (机构专用=1.0, 知名游资=0.8, 普通营业部=0.3)
- DT missing: dynamic confidence penalty based on other evidence quality
- Market Regime Modifier: multiplier layer (not 5th signal)
- C1 Component Explainability + C2 Score Stability contracts
- Output: component scores + evidence per row
- Split: PR4.2.33a (core multi-signal) + PR4.2.33b (regime modifier)

---

## 1. Problem Statement

Institution style answers: "Which industry/theme directions are becoming preferred by medium-term institutional capital?"

This is fundamentally different from hot money style (short-term attack momentum). Institution preference is closer to analyst report sections such as "科技硬件", "材料/服务器", "存储/光通信/PCB" with states like "启动第1天", "资金回流".

---

## 2. Architecture

```
theme_capital_flow_daily (PR4.2.32a)
        │
        ├── theme_cycle_judgement_v2 (existing)
        ├── theme_strength_snapshot (existing)
        ├── strong_stock_watch_history (existing)
        └── dragon_tiger seats (future, PR4.2.3x)
                │
                ▼
      InstitutionStyleProducer
                │
                ▼
      institution_style_daily
                │
                ▼
      PR4.2.35 AI Explanation
                │
                ▼
      PR4.2.37 Frontend
```

---

## 3. Input Signals & Weights

| # | Signal | Weight | Source | What it measures |
|---|--------|--------|--------|-----------------|
| S1 | Theme Fund Flow | **35%** | `theme_capital_flow_daily` | net_flow persistence, acceleration, large_flow ratio |
| S2 | Industry Cycle Logic | **30%** | `theme_cycle_judgement_v2` | cycle stage, days in stage, transition direction |
| S3 | Strong Stock Structure | **25%** | `strong_stock_watch_history` | leader count, 中军 strength, trend stock ratio, board depth |
| S4 | Dragon Tiger Seats | **10%** | seat evidence (future) | institution_seat_count, institution_buy_amount |

**Weight rationale:**
- Fund flow (35%): most direct evidence, but cannot stand alone
- Cycle (30%): same flow at START vs CLIMAX means completely different things
- Stock structure (25%): leaders + 中军 breadth = institutional conviction strength
- Dragon tiger (10%): delayed, sample-biased, mixed with hot money; enhancement only

---

## 4. Signal Detail

### S1: Theme Fund Flow Score (35%)

```
flow_score = normalize(
    flow_persistence  × 0.40
  + flow_acceleration × 0.30
  + large_flow_ratio  × 0.20
  + flow_consistency  × 0.10
)

Where:
  flow_persistence  = positive_days / 5 (rolling 5-day)
  flow_acceleration = (today_net - avg_5day_net) / max(abs(avg_5day_net), 1)
  large_flow_ratio  = large_flow_yuan / max(net_flow_yuan, 1) (big money proportion)
  flow_consistency  = 1.0 - std_dev(5d_flows) / max(avg_abs(5d_flows), 1)
                      (low variance = high consistency = institutional)

Why consistency matters:
  Series A: +10, -5, +8, -2, +15  → high variance → consistency ≈ 0.4
  Series B: +5, +6, +7, +8, +9    → low variance  → consistency ≈ 0.9
  Same total inflow. Series B is far more institutional.

Forbidden:
  ❌ today_net_flow > 0 → high flow_score (single-day inference)
  ❌ flow_score used alone without S2/S3/S4

Coverage penalty:
  if flow_coverage_ratio < 0.50:
      flow_score *= flow_coverage_ratio / 0.50  (downgrade low-coverage themes)
```

### S2: Industry Cycle Score (30%)

Institution capital follows a predictable lifecycle pattern. Same fund flow at different stages means completely different things. FERMENTATION is the highest-value signal because it represents "industry confirmed, institutions deploying" — not too early (speculative), not too late (distribution).

```
cycle_score = stage_bonus + transition_direction + days_in_stage_factor

Stage bonus (7-stage model):
  START:          0.65  (early signal, institutional scouts entering)
  INCUBATION:     0.75  (evidence building, more institutions watching)
  FERMENTATION:   0.85  (confirmation = strongest signal, institutions deploying)
  DIFFUSION:      0.80  (broadening participation, late-comers joining)
  PEAK:           0.45  (crowded trade risk, smart money begins exit)
  DISTRIBUTION:   0.20  (confirmed exit, only retail remaining)
  DECAY:          0.05  (abandoned, no institutional interest)

Transition direction:
  → FERMENTATION or → INCUBATION:   +0.10  (upgrading)
  → DIFFUSION:                      +0.05  (still positive)
  → PEAK or → DISTRIBUTION:         -0.12  (downgrading)
  → DECAY:                          -0.18  (collapsing)
  staying same:                      0.00
```

### S3: Strong Stock Structure Score (25%)

Institutions don't chase single 妖股 (speculative leaders). They look for leader + 中军 + breadth — a theme where quality stocks are moving together.

```
structure_score = leader_quality × 0.40 + core_stock_strength × 0.35 + breadth_depth × 0.25

Where:
  leader_quality     = COUNT(role='龙头' AND sealed AND trend_strength > 0) / max(leader_count, 1)
  core_stock_strength = COUNT(role='中军' AND trend_strength > 0) / max(core_count, 1)
                        (中军 = institutional favorites, steady accumulation)
  breadth_depth      = COUNT(stocks with positive trend) / max(stock_count, 1)
                        (broad participation = institutional conviction)
```

### S4: Dragon Tiger Score (10%)

Dragon tiger is confirmation, not decision. Seat quality matters more than raw count — a single 机构专用 seat means more than ten generic 营业部 seats.

```
dragon_tiger_score = seat_quality_weighted × 0.60 + institution_buy_intensity × 0.40

Where:
  seat_quality_weighted = SUM(seat_quality_score × institution_buy) / SUM(institution_buy)
  
  seat_quality_score:
    机构专用:    1.0  (dedicated institutional seat)
    知名游资:    0.8  (well-known hot money, mixed signal)
    普通营业部:  0.3  (retail/generic, low signal)

  institution_buy_intensity = SUM(institution_buy) / SUM(total_buy) for theme stocks

When dragon tiger data is missing (no recap):
  dragon_tiger_score = N/A
  → S4 weight (10%) redistributed: S1 +4%, S2 +3%, S3 +3%
  → Dynamic confidence penalty:
      if flow_confidence == HIGH AND cycle_confidence == HIGH:
          confidence *= 0.95  (only 5% penalty, core signals are strong)
      else:
          confidence *= 0.85  (15% penalty, missing confirmation when signals weak)
  → evidence_quality.dragon_tiger = "MISSING"
```

---

## 5. Composite Formula

```
Base Score = 0.35 × flow_score
           + 0.30 × cycle_score
           + 0.25 × structure_score
           + 0.10 × dragon_tiger_score

Final Score = Base Score × Market Regime Factor

confidence = base_confidence × coverage_factor × evidence_completeness

Where:
  base_confidence = 0.85 (model baseline)
  coverage_factor = min(1.0, flow_coverage_ratio / 0.70)
  evidence_completeness = 1.0 - (0.05 × missing_signal_count)
```

### 5.1 Market Regime Modifier

Same theme, same fund flow — different market environments, different meanings. This is a **multiplier layer**, NOT a 5th signal. It does not change component scores; it scales the final institution_score based on the broader market context.

```
Market Regime Factor:
  STRONG_TREND:    × 1.10  (bull market, institutional risk-on)
  NORMAL:          × 1.00  (baseline)
  WEAK/DEFENSIVE:  × 0.80  (bear market, institutions retreating regardless)
  CRISIS:          × 0.60  (capitulation, all styles suspended)

Source: Market Capital State (Phase 0)
```

This ensures that a FERMENTATION+high-flow theme scores 90 in a bull market but ~72 in a defensive market — which matches analyst behavior. During defense, institutions rotate to cash/bonds regardless of theme quality.

---

## 6. Output Table

```sql
CREATE TABLE IF NOT EXISTS institution_style_daily (
    trade_date              DATE NOT NULL,
    subject_key             TEXT NOT NULL,
    theme_name              TEXT NOT NULL DEFAULT '',

    -- Composite scores
    institution_score       NUMERIC(6, 2),        -- 0-100, after market regime modifier
    base_score              NUMERIC(6, 2),        -- 0-100, before regime modifier
    confidence              NUMERIC(5, 4),         -- 0.0000-1.0000
    market_regime_factor    NUMERIC(4, 3),         -- e.g. 1.100, 0.800

    -- Component scores (for M7 calibration — every score must be individually observable)
    flow_score              NUMERIC(6, 2),
    cycle_score             NUMERIC(6, 2),
    structure_score         NUMERIC(6, 2),
    dragon_tiger_score      NUMERIC(6, 2),

    -- Lifecycle context (from Phase 2.5)
    lifecycle_stage         TEXT,                  -- START/INCUBATION/FERMENTATION/DIFFUSION/PEAK/DISTRIBUTION/DECAY

    -- Evidence per signal (for AI explanation)
    evidence_quality        JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- {"flow": "HIGH", "cycle": "HIGH", "structure": "MEDIUM", "dragon_tiger": "MISSING"}

    -- Supporting evidence detail
    evidence                JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- {"top_flow_stocks": [...], "cycle_reason": "...", "structure_reason": "...", "seat_detail": [...]}

    -- Top reasons (for AI explanation)
    top_signals             TEXT[] NOT NULL DEFAULT '{}',

    -- Provenance
    model_version           TEXT NOT NULL DEFAULT 'institution_style_v1',
    source                  TEXT NOT NULL DEFAULT 'institution_style_producer',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, subject_key, model_version)
);
```

**Example row:**

```json
{
  "trade_date": "2026-07-09",
  "subject_key": "9015778",
  "theme_name": "存储芯片",
  "institution_score": 82.00,
  "confidence": 0.76,
  "flow_score": 78.00,
  "cycle_score": 85.00,
  "structure_score": 80.00,
  "dragon_tiger_score": null,
  "evidence_quality": {
    "fund_flow": "HIGH",
    "cycle": "HIGH",
    "structure": "MEDIUM",
    "dragon_tiger": "MISSING"
  },
  "top_signals": ["资金持续5日流入", "周期: FERMENTATION", "龙头封板扩散"]
}
```

---

## 7. Forbidden Paths

```
❌ theme_flow > 0 → institution_buying
❌ net_amount > 0 → institution_style
❌ single signal → style decision (must be 3+ signals with weights)
❌ dragon_tiger missing → infer from role_label / theme stage
❌ dragon_tiger missing → block all style output
❌ institution_style_daily → ReviewDocument (deferred to PR4.2.37)
❌ institution_style_daily → UI
❌ hardcoded threshold (e.g., score > 60 → institution_style)
```

---

## 8. When Dragon Tiger is Missing

Dragon tiger data is frequently unavailable (no recap for the date, or data delayed past 16:30). The producer must handle this gracefully:

```
If dragon_tiger_score is N/A:
  → Redistribute S4 weight: S1+4%, S2+3%, S3+3%
  → confidence *= 0.90 (10% penalty for missing evidence)
  → evidence_quality.dragon_tiger = "MISSING"
  → top_signals excludes dragon_tiger references

Do NOT:
  → infer from money_flow role_label
  → infer from theme stage
  → block style output entirely
```

---

## 9. Acceptance Contracts

| # | Contract | Assertion |
|---|----------|-----------|
| C1 | Component explainability | `institution_score` must be reproducible from `flow_score + cycle_score + structure_score + dragon_tiger_score` × `market_regime_factor`; no black-box score |
| C2 | Score stability | Same inputs → same `institution_score`, `confidence`, and all component scores (deterministic, no randomness) |
| C3 | Multi-signal mandatory | institution_score uses 3+ signals; single-signal input → FAIL |
| C4 | Dragon tiger optional | Missing DT → score redistributed, dynamic confidence penalty, NOT blocked |
| C5 | Evidence quality | Every output row has `evidence_quality` per signal + `evidence` detail |
| C6 | No forbidden inference | Zero occurrences of: `net_amount>0 → institution`, `main_force → style`, `single_day_flow → style` |
| C7 | Coverage-aware | Low flow_coverage_ratio → downgraded flow_score via coverage penalty |
| C8 | Stage bonus correct | 7-stage table verified: FERMENTATION=0.85, DECAY=0.05 |
| C9 | Market regime layer | `final_score = base_score × market_regime_factor` (multiplier, not 5th signal) |
| C10 | Component observable | Every component score individually readable for M7 calibration |

---

## 10. Implementation Split

### PR4.2.33a — Core Multi-Signal Producer

**Scope:** S1+S2+S3+S4 weighted formula + component traceability. No market regime modifier.

```
Deliverables:
  ✅ institution_style_daily DB migration
  ✅ InstitutionStyleProducer: 4-signal weighted model
  ✅ Component scores: flow_score, cycle_score, structure_score, dragon_tiger_score
  ✅ DT-missing graceful degradation with dynamic confidence penalty
  ✅ evidence_quality + evidence per row
  ✅ 10 contract tests (C1-C10 except C9)

Forbidden:
  ❌ Market regime modifier (deferred to 4.2.33b)
  ❌ ReviewDocument, UI, AI Explanation
```

### PR4.2.33b — Market Regime Layer

**Scope:** Market Regime Modifier as multiplier layer.

```
Deliverables:
  ✅ Market Regime Factor from Market Capital State
  ✅ base_score → final_score = base_score × regime_factor
  ✅ regime_factor stored per row for auditability

Forbidden:
  ❌ Regime as 5th signal (must be multiplier, not additive)
  ❌ Regime changing component scores
```

---

## 11. Implementation Boundary (PR4.2.33a)

```
ALLOWED:
  ✅ Read theme_capital_flow_daily (PR4.2.32a)
  ✅ Read theme_cycle_judgement_v2, strong_stock_watch_history
  ✅ Write institution_style_daily
  ✅ 4-signal weighted formula with component traceability
  ✅ DT-missing graceful degradation (dynamic confidence penalty)
  ✅ evidence_quality + evidence per row

FORBIDDEN:
  ❌ Single signal → style
  ❌ DT missing → infer from role_label/theme_stage
  ❌ DT missing → block output
  ❌ Market regime modifier (deferred to 4.2.33b)
  ❌ Touch ReviewDocument, UI, AI Explanation
  ❌ Hardcoded thresholds
```
