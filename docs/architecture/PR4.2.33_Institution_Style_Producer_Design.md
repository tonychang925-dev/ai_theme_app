# PR4.2.33 — Institution Style Producer

**Version:** v1.0
**Date:** 2026-07-14
**Status:** Design Frozen
**Depends on:** PR4.2.32a (theme_capital_flow_daily)
**Feeds into:** PR4.2.35 (AI Capital Explanation), PR4.2.37 (Frontend)

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
flow_score = normalize(flow_persistence × 0.4 + flow_acceleration × 0.35 + large_flow_ratio × 0.25)

Where:
  flow_persistence  = positive_days / 5 (rolling 5-day)
  flow_acceleration = (today_net - avg_5day_net) / avg_5day_net
  large_flow_ratio  = large_flow_yuan / net_flow_yuan (big money proportion)

Coverage penalty:
  if flow_coverage_ratio < 0.50:
      flow_score *= flow_coverage_ratio / 0.50  (downgrade low-coverage themes)
```

### S2: Industry Cycle Score (30%)

```
cycle_score = stage_bonus + transition_direction + days_in_stage_factor

Stage bonus (base):
  START:         0.60  (early entry = high institutional value)
  FERMENTATION:  0.85  (confirmation = strongest signal)
  ACCELERATION:  0.70  (momentum confirmed)
  CLIMAX:        0.40  (late stage = risk of distribution)
  DIVERGENCE:    0.25  (uncertainty)
  FADE:          0.10  (confirmed decline)
  REPAIR:        0.50  (potential recovery)

Transition direction:
  → FERMENTATION or → ACCELERATION: +0.10
  → DIVERGENCE or → FADE:           -0.15
  staying same:                      0.00
```

### S3: Strong Stock Structure Score (25%)

```
structure_score = leader_quality × 0.40 + middle_strength × 0.35 + board_depth × 0.25

Where:
  leader_quality  = COUNT(role='龙头' AND sealed) / max(leader_count, 1)
  middle_strength = COUNT(role='中军' AND trend_strength > 0) / max(total_stocks, 1)
  board_depth     = COUNT(DISTINCT board_height) / max_board_height (height distribution)
```

### S4: Dragon Tiger Score (10%)

```
dragon_tiger_score = institution_seat_presence × 0.60 + institution_buy_intensity × 0.40

Where:
  institution_seat_presence = COUNT(theme stocks with institution seats) / stock_count
  institution_buy_intensity = SUM(institution_buy) / SUM(total_buy) for theme stocks

When dragon tiger data is missing (no recap):
  dragon_tiger_score = N/A
  → S4 weight (10%) redistributed: S1 +4%, S2 +3%, S3 +3%
  → confidence DOWNGRADED (evidence_quality.dragon_tiger = "MISSING")
```

---

## 5. Composite Formula

```
institution_score = 0.35 × flow_score
                  + 0.30 × cycle_score
                  + 0.25 × structure_score
                  + 0.10 × dragon_tiger_score

confidence = base_confidence × coverage_factor × evidence_completeness

Where:
  base_confidence = 0.85 (model baseline)
  coverage_factor = min(1.0, flow_coverage_ratio / 0.70)
  evidence_completeness = 1.0 - (0.05 × missing_signal_count)
```

---

## 6. Output Table

```sql
CREATE TABLE IF NOT EXISTS institution_style_daily (
    trade_date              DATE NOT NULL,
    subject_key             TEXT NOT NULL,
    theme_name              TEXT NOT NULL DEFAULT '',

    -- Composite scores
    institution_score       NUMERIC(6, 2),        -- 0-100 weighted composite
    confidence              NUMERIC(5, 4),         -- 0.0000-1.0000

    -- Component scores (for M7 calibration)
    flow_score              NUMERIC(6, 2),
    cycle_score             NUMERIC(6, 2),
    structure_score         NUMERIC(6, 2),
    dragon_tiger_score      NUMERIC(6, 2),

    -- Evidence quality per signal
    evidence_quality        JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- {"fund_flow": "HIGH", "cycle": "HIGH", "structure": "MEDIUM", "dragon_tiger": "MISSING"}

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
| C1 | Multi-signal | institution_score uses 3+ signals; single-signal input → FAIL |
| C2 | Component traceable | flow_score, cycle_score, structure_score individually observable |
| C3 | Dragon tiger optional | Missing DT → score redistributed, confidence downgraded, NOT blocked |
| C4 | Evidence quality | Every output row has evidence_quality per signal |
| C5 | Idempotent | Same inputs → same scores (deterministic formula, no randomness) |
| C6 | No forbidden inference | Zero occurrences of: `net_amount>0 → institution`, `main_force → style` |
| C7 | Coverage-aware | Low flow_coverage_ratio → downgraded flow_score via coverage penalty |
| C8 | Cycle-stage bonus correct | START:0.60, FERMENTATION:0.85, CLIMAX:0.40, FADE:0.10 |

---

## 10. Implementation Boundary

```
ALLOWED:
  ✅ Read theme_capital_flow_daily (PR4.2.32a)
  ✅ Read theme_cycle_judgement_v2, strong_stock_watch_history
  ✅ Write institution_style_daily
  ✅ Multi-signal weighted formula
  ✅ Component score traceability
  ✅ DT-missing graceful degradation

FORBIDDEN:
  ❌ Single signal → style (C1)
  ❌ DT missing → infer from role_label/theme_stage
  ❌ DT missing → block output
  ❌ Touch ReviewDocument, UI
  ❌ Hardcoded thresholds
```
