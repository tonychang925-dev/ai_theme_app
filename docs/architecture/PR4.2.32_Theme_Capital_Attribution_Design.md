# PR4.2.32 — Theme Capital Attribution Engine

**Version:** v2.0
**Date:** 2026-07-14
**Status:** Design Frozen — PR4.2.32a Ready
**Depends on:** PR4.2.31f (stock_fund_flow_daily)
**Feeds into:** PR4.2.34 (Institution Style Producer)
**Changes in v2.0:**
- Level 1: PRIMARY/RELATED weighting (not just 1/N equal split)
- Added `attribution_version`, `flow_type`, `coverage_ratio` fields
- AI candidate_binding → separate staging table, not direct attribution
- C8 Attribution Conservation + C9 Coverage Transparency contracts
- Split into PR4.2.32a (foundation) + PR4.2.32b (AI enhancement)

---

## 1. Problem Statement

A single A-share stock belongs to multiple themes. Direct `SUM(stock_flow) GROUP BY theme` inflates capital totals:

```
中科曙光: net_flow = +10亿
  belongs to: 国产算力, 液冷服务器, AI服务器, 华为产业链

Naive SUM: 国产算力+10, 液冷+10, AI+10, 华为+10 = 40亿  ← WRONG
Weighted:   国产算力×0.5 + 液冷×0.3 + AI×0.2 = 10亿       ← CORRECT
```

The Attribution Engine applies per-stock-per-theme weights to ensure `SUM(allocation) = actual_flow`.

---

## 2. Architecture

```
stock_fund_flow_daily (PR4.2.31f)
        │
        ├── stock_theme_map (existing)
        ├── theme_cycle_judgement_v2 (existing)
        └── mainline_identity_registry (existing)
                │
                ▼
   Theme Capital Attribution Engine
                │
        ┌───────┴───────┐
        │               │
  stock_theme_       theme_capital_
  attribution_daily  flow_daily
        │               │
        └───────┬───────┘
                │
                ▼
        PR4.2.34 Institution Style Producer
```

---

## 3. Data Tables

### 3.1 `stock_theme_attribution_daily`

Per-stock-per-theme weight allocation for a single trading day.

```sql
CREATE TABLE IF NOT EXISTS stock_theme_attribution_daily (
    trade_date      DATE NOT NULL,
    stock_code      TEXT NOT NULL,      -- e.g. "300223.SZ"
    subject_key     TEXT NOT NULL,      -- theme key
    theme_name      TEXT NOT NULL DEFAULT '',

    weight              NUMERIC(5, 4) NOT NULL,  -- 0.0000 ~ 1.0000
    confidence          NUMERIC(5, 4) NOT NULL DEFAULT 1.0,

    method              TEXT NOT NULL,      -- "identity_registry" | "sector_map" | "ai_semantic"
    attribution_version TEXT NOT NULL DEFAULT 'v1',  -- e.g. "identity_registry_v1"
    source              TEXT NOT NULL,      -- which table/producer provided the binding

    diagnostics         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, stock_code, subject_key, method)
);

-- Constraint: no stock can exceed 100% allocation per method
-- Enforced at application level; DB check is advisory
```

**Example rows for 2026-07-09:**

| trade_date | stock_code | subject_key | weight | method | source |
|------------|-----------|-------------|--------|--------|--------|
| 2026-07-09 | 300223.SZ | 9015778 | 0.70 | identity_registry | mainline_identity_registry |
| 2026-07-09 | 300223.SZ | 9034567 | 0.30 | identity_registry | mainline_identity_registry |

### 3.2 `theme_capital_flow_daily`

Aggregated daily capital flow per theme — the output of the attribution engine.

```sql
CREATE TABLE IF NOT EXISTS theme_capital_flow_daily (
    trade_date              DATE NOT NULL,
    subject_key             TEXT NOT NULL,
    theme_name              TEXT NOT NULL DEFAULT '',

    -- Aggregated flows (weighted, in 元)
    net_flow_yuan           NUMERIC(24, 2),
    large_flow_yuan         NUMERIC(24, 2),

    -- Flow semantics (ATTRIBUTED_ORDER_FLOW, not THEME_MONEY_FLOW)
    flow_type               TEXT NOT NULL DEFAULT 'ATTRIBUTED_ORDER_FLOW',

    -- Stock composition + coverage
    stock_count             INTEGER NOT NULL DEFAULT 0,
    attributed_stock_count  INTEGER NOT NULL DEFAULT 0,
    positive_stock_count    INTEGER NOT NULL DEFAULT 0,
    flow_coverage_ratio     NUMERIC(5, 4) NOT NULL DEFAULT 0.0,

    -- Quality
    attribution_confidence  NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
    attribution_method      TEXT NOT NULL,
    attribution_version     TEXT NOT NULL DEFAULT 'v1',

    source                  TEXT NOT NULL DEFAULT 'theme_capital_attribution_engine',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, subject_key, attribution_method)
);
```

**Example row:**

```json
{
  "trade_date": "2026-07-09",
  "subject_key": "9015778",
  "theme_name": "存储芯片",
  "net_flow_yuan": 1860000000.00,
  "large_flow_yuan": 520000000.00,
  "stock_count": 12,
  "positive_stock_count": 8,
  "attribution_confidence": 0.86,
  "attribution_method": "weighted_identity_registry"
}
```

---

## 4. Weight Source Hierarchy

### Level 1: Identity Registry Binding (P0)

**Source:** `mainline_identity_registry` + `subject_stock_map`

**Method:** The system already knows which stocks belong to which themes through:
- `subject_stock_map` — stock→theme mapping with `role` field (PRIMARY/RELATED)
- `mainline_identity_registry` — canonical theme identity records
- `theme_cycle_judgement_v2` — per-theme lifecycle state

**Weight assignment (v2.0 — PRIMARY/RELATED):**

Equal-split was the v1.0 baseline. v2.0 uses the `role` field from `subject_stock_map`:

```
subject_stock_map entry:
  { stock: "603019.SH", subject_key: "国产算力", role: "PRIMARY" }
  { stock: "603019.SH", subject_key: "液冷服务器", role: "RELATED" }
  { stock: "603019.SH", subject_key: "AI服务器", role: "RELATED" }

Rule:
  PRIMARY themes get 0.60 base, split evenly among all PRIMARY
  RELATED themes split the remaining 0.40 evenly

Example: 1 PRIMARY + 2 RELATED
  国产算力 (PRIMARY):    0.60
  液冷服务器 (RELATED):  0.20
  AI服务器 (RELATED):    0.20

Fallback (no role field):
  weight = 1.0 / N  (equal split, v1.0 behavior)
```

**Confidence:** 0.90 (high — these are system-maintained bindings)

### Level 2: Sector/Industry Enhancement (P1)

**Source:** Stock sector classification data (申万/中信 industry, concept boards)

**Method:** When a stock belongs to a sector that maps to a theme, increase that theme's weight proportionally. This reflects that some themes are "closer" to the stock's core business than others.

**Weight adjustment:** Bootstrap Level 1 weights with sector proximity score:

```
adjusted_weight = base_weight × sector_proximity_score

sector_proximity_score:
  1.0 = stock's primary industry matches theme's core industry
  0.5 = stock's secondary concept overlaps
  0.2 = broad industry category match
```

**Confidence:** 0.70 (medium — sector mapping has noise)

### Level 3: AI Semantic (P2 — Candidate Only, Staged)

**Source:** LLM analysis of stock business description, announcements, event calendar

**Method:** LLM judges the strength of stock→theme relationship based on business description text.

**Critical constraint:** AI weights are **candidate only** and must pass through a staging table before entering the attribution engine. They must NOT override Level 1 or Level 2 weights.

```
AI output → stock_theme_candidate_binding (staging)
                │
                ↓
         human/rule review
                │
                ↓
         stock_theme_attribution_daily (production)
```

**Staging table:** `stock_theme_candidate_binding`

```sql
CREATE TABLE IF NOT EXISTS stock_theme_candidate_binding (
    trade_date      DATE NOT NULL,
    stock_code      TEXT NOT NULL,
    subject_key     TEXT NOT NULL,
    theme_name      TEXT NOT NULL DEFAULT '',
    candidate_weight NUMERIC(5, 4),
    confidence      NUMERIC(5, 4) NOT NULL DEFAULT 0.50,
    llm_model       TEXT,
    llm_prompt_hash TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, stock_code, subject_key)
);
```

**AI constraints (v2.0 — stricter):**
```
AI can:  insert into candidate_binding with confidence ≤ 0.60
AI can:  add bindings not present in Level 1/2
AI cannot: change Level 1 weight from 0.25 to 0.80
AI cannot: remove a Level 1 binding
AI cannot: insert directly into stock_theme_attribution_daily
AI cannot: assign confidence > 0.60
```

**Confidence:** 0.40–0.60 (LLM output needs verification). Without review, AI candidates are NOT used in aggregation.

---

## 5. Aggregation Formula

### 5.1 Net Flow

```
theme_net_flow = Σ (stock_net_flow × weight) for all stocks with weight > 0

Where:
  stock_net_flow = stock_fund_flow_daily.order_size_flow_amount_yuan
  weight         = stock_theme_attribution_daily.weight (best available method)
```

### 5.2 Large Flow

```
theme_large_flow = Σ ((buy_lg + buy_elg - sell_lg - sell_elg) × weight) for all stocks

Where:
  buy_lg/buy_elg/sell_lg/sell_elg from stock_fund_flow_daily
```

### 5.3 Attribution Confidence

```
attribution_confidence = AVG(stock_level_confidence × weight_coverage)

Where:
  weight_coverage = SUM(weight) / stock_count
  (penalty for stocks with missing theme bindings)
```

### 5.4 Positive Stock Ratio

```
positive_stock_ratio = positive_stock_count / stock_count

Where:
  positive_stock = stock_net_flow > 0
```

### 5.5 Coverage Ratio

```
flow_coverage_ratio = attributed_stock_count / stock_count

Where:
  attributed_stock_count = stocks with fund_flow data AND weight > 0
  stock_count = total stocks in the theme universe

Example: 存储芯片 has 20 stocks, 16 have fund flow data
  → coverage = 0.80

Low coverage → Institution Style must downgrade confidence (PR4.2.34).
```

---

## 6. Application-Level Constraint

```python
# Enforced at write time, not in DB
def validate_attribution(rows: list[dict], stock_code: str) -> bool:
    """SUM(weight) per stock per method must not exceed 1.0."""
    total = sum(r["weight"] for r in rows)
    return total <= 1.0 + 1e-6  # float tolerance
```

---

## 7. Forbidden Paths

```
❌ AI weights → override identity_registry weights
❌ theme_capital_flow_daily → institution_style (PR4.2.34's job)
❌ theme_capital_flow_daily → hot_money_style (PR4.2.35's job)
❌ theme_capital_flow_daily → ReviewDocument
❌ theme_capital_flow_daily → UI
❌ simple GROUP BY SUM without weight (the whole point of this PR)
❌ hardcoded weight table (must be derived from existing bindings)
```

---

## 8. Deliverables

| # | Artifact | Description |
|---|----------|-------------|
| 1 | `stock_theme_attribution_daily` SQL | DB migration |
| 2 | `theme_capital_flow_daily` SQL | DB migration |
| 3 | `ThemeCapitalAttributionEngine` | Core class: weight resolution + aggregation |
| 4 | `StockThemeWeightResolver` | Level 1→2→3 weight resolution |
| 5 | Contract tests | Weight sum ≤ 1.0; no Level 1 override; idempotent replay |
| 6 | CLI script | `scripts/run_theme_capital_attribution.py --date 2026-07-09` |

---

## 9. Acceptance Contracts

| # | Contract | Assertion |
|---|----------|-----------|
| C1 | Weight sum ≤ 1.0 | `SUM(weight) per stock per method ≤ 1.0` |
| C2 | Idempotent | Same inputs → same `theme_capital_flow_daily` rows |
| C3 | Level 1 priority | Level 1 weight cannot be overridden by Level 2/3 |
| C4 | AI bounded | AI-assigned weight must have confidence ≤ 0.60 |
| C5 | AI only additive | AI can add bindings, never modify existing weights |
| C6 | No forbidden fields | Zero occurrences of institution/hot_money/main_force |
| C7 | Attribution traceable | Every theme_flow row has `attribution_method` + `attribution_version` set |
| C8 | Attribution conservation | `ABS(SUM(theme_net_flow) - SUM(stock_net_flow)) < 1e-6 × SUM(stock_flow)` — money is neither created nor destroyed |
| C9 | Coverage transparency | Every theme_flow row must have `attributed_stock_count`, `stock_count`, `flow_coverage_ratio` populated |

---

## 10. Implementation Split

### PR4.2.32a — Attribution Foundation (Deterministic)

**Scope:** Level 1 only. No sector, no AI.

```
Deliverables:
  ✅ stock_theme_attribution_daily + theme_capital_flow_daily SQL
  ✅ StockThemeWeightResolver: Level 1 PRIMARY/RELATED weighting
  ✅ ThemeCapitalAttributionEngine: weighted aggregation
  ✅ 9 contract tests (C1-C9)
  ✅ CLI: scripts/run_theme_capital_attribution.py --date 2026-07-09

Forbidden:
  ❌ Level 2 (sector proximity)
  ❌ Level 3 (AI candidate)
  ❌ stock_theme_candidate_binding
```

### PR4.2.32b — Attribution Enhancement (Model-based)

**Scope:** Level 2 + Level 3. Requires PR4.2.32a complete.

```
Deliverables:
  ✅ Sector proximity bootstrap (Level 2)
  ✅ stock_theme_candidate_binding table + AI pipeline (Level 3)
  ✅ Candidate → attribution promotion workflow
  ✅ Attribution version tracking (differentiate v1 vs v2 vs v3)

Forbidden:
  ❌ AI direct write to attribution_daily
  ❌ AI confidence > 0.60
  ❌ AI override of Level 1 weights
```

### Rationale for Split

Level 1 is deterministic — identity_registry + PRIMARY/RELATED → weight. This produces reproducible, auditable results. Level 2/3 introduce model uncertainty. Separating them means:
- M7 can calibrate Level 1 weights independently from AI errors
- Attribution version `identity_registry_v1` is always replayable
- AI candidate errors don't pollute the foundation layer

---

## 11. Completed Data Chain

```
Tushare moneyflow (PR4.2.31f)
        │
        ▼
stock_fund_flow_daily
        │
        ├── subject_stock_map (PRIMARY/RELATED)
        ├── mainline_identity_registry
        └── theme_cycle_judgement_v2
                │
                ▼
   StockThemeWeightResolver (PR4.2.32a)
                │
        ┌───────┴───────┐
        │               │
  stock_theme_       theme_capital_
  attribution_daily  flow_daily
  (v1, with version) (ATTRIBUTED_ORDER_FLOW, with coverage)
        │               │
        └───────┬───────┘
                │
                ▼
   InstitutionStyleProducer (PR4.2.34)
   HotMoneyStyleProducer  (PR4.2.35)
                │
                ▼
        ReviewDocument.capital
                │
                ▼
            Frontend
```

---

## 12. Implementation Boundary (PR4.2.32a)

```
ALLOWED:
  ✅ Read stock_fund_flow_daily (PR4.2.31f output)
  ✅ Read subject_stock_map, mainline_identity_registry
  ✅ Write stock_theme_attribution_daily, theme_capital_flow_daily
  ✅ Level 1 PRIMARY/RELATED weighting
  ✅ attribution_version = 'identity_registry_v1'
  ✅ flow_type = 'ATTRIBUTED_ORDER_FLOW'

FORBIDDEN:
  ❌ Write institution_style
  ❌ Write hot_money_style
  ❌ Touch ReviewDocument
  ❌ Touch UI
  ❌ AI weights at all (deferred to 4.2.32b)
  ❌ Sector proximity (deferred to 4.2.32b)
  ❌ Hardcoded weight table
  ❌ simple GROUP BY SUM without weight
```
