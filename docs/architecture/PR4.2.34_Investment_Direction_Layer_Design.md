# PR4.2.34 — Investment Direction Layer

**Version:** v1.0
**Date:** 2026-07-14
**Status:** Design Proposal
**Priority:** Higher than Hot Money Style

---

## 1. Problem Statement

Analyst and system operate at different abstraction levels:

```
System (Theme/Subject Layer):        Analyst (Investment Direction Layer):
  PCB印制电路板                          AI高速互联产业链
  覆铜板                                    ├── PCB
  电子布                                    ├── 覆铜板
  高速铜连接                                ├── 电子布
  MPO                                       ├── 高速铜连接
  光模块                                    └── MPO/光模块

  存储芯片                                AI算力基础设施
  国产算力                                    ├── 国产算力
  液冷服务器                                  ├── 服务器
  HBM                                         ├── 液冷
  AIDC                                        ├── 存储芯片
                                              └── HBM

  光刻胶                                  先进半导体材料
  电子特气                                    ├── 光刻胶
  靶材                                        ├── 电子特气
  硅片                                        ├── 靶材
  碳化硅                                      └── 硅片
```

The analyst is NOT asking "which concept tag has the most money?" — they are asking **"which industrial direction is capital attacking?"**

This gap causes three concrete problems:

1. **Score dilution**: 60亿 in AI高速互联 shows as 20亿(PCB) + 15亿(铜连接) + 10亿(覆铜板) + ... — none individually rank top-5
2. **Unfair replay evaluation**: System says "PCB", analyst says "高速铜连接" — string match fails, but they're semantically close
3. **M7 contamination**: Model learns "analyst likes PCB" when analyst actually likes the broader direction

---

## 2. Architecture

Add one layer between Theme and Institution Style:

```
                         Market
                           │
                           ▼
              Investment Direction Layer  ← NEW
             (产业投资方向)
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          Theme A      Theme B      Theme C
              │            │            │
              ▼            ▼            ▼
                   Stocks
```

Data flow:

```
stock_fund_flow_daily
        │
        ▼
theme_capital_flow_daily  (existing, unchanged)
        │
        ▼
direction_capital_flow_daily  ← NEW
        │
        ▼
InstitutionStyleProducer  (S1 input changed: theme → direction)
```

---

## 3. Data Model

### 3.1 `investment_direction`

```sql
CREATE TABLE IF NOT EXISTS investment_direction (
    direction_key   TEXT PRIMARY KEY,    -- "AI_HIGH_SPEED_INTERCONNECT"
    direction_name  TEXT NOT NULL,       -- "AI高速互联"
    description     TEXT NOT NULL DEFAULT '',
    level           TEXT NOT NULL DEFAULT 'DIRECTION',  -- DIRECTION | MACRO_THEME
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3.2 `direction_theme_binding`

```sql
CREATE TABLE IF NOT EXISTS direction_theme_binding (
    direction_key   TEXT NOT NULL,
    subject_key     TEXT NOT NULL,
    theme_name      TEXT NOT NULL DEFAULT '',
    weight          NUMERIC(5, 4) NOT NULL,  -- 0.0000 ~ 1.0000
    relationship    TEXT NOT NULL DEFAULT 'MEMBER',  -- CORE | MEMBER | PERIPHERAL
    confidence      NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
    source          TEXT NOT NULL DEFAULT 'manual',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (direction_key, subject_key)
);
```

**Example bindings:**

| direction_key | subject_key | weight | relationship |
|--------------|-------------|--------|-------------|
| AI_HIGH_SPEED_INTERCONNECT | 9018144 | 0.30 | CORE |
| AI_HIGH_SPEED_INTERCONNECT | 9023001 | 0.25 | CORE |
| AI_HIGH_SPEED_INTERCONNECT | 9034501 | 0.20 | MEMBER |
| AI_COMPUTE_INFRA | 9014001 | 0.35 | CORE |
| AI_COMPUTE_INFRA | 9015778 | 0.30 | CORE |
| AI_COMPUTE_INFRA | 9045601 | 0.20 | MEMBER |

### 3.3 `direction_capital_flow_daily`

```sql
CREATE TABLE IF NOT EXISTS direction_capital_flow_daily (
    trade_date              DATE NOT NULL,
    direction_key           TEXT NOT NULL,
    direction_name          TEXT NOT NULL DEFAULT '',

    -- Weighted aggregation from theme flows
    net_flow_yuan           NUMERIC(24, 2),
    large_flow_yuan         NUMERIC(24, 2),

    -- Flow semantics
    flow_type               TEXT NOT NULL DEFAULT 'ATTRIBUTED_DIRECTION_FLOW',

    -- Composition
    theme_count             INTEGER NOT NULL DEFAULT 0,
    attributed_theme_count  INTEGER NOT NULL DEFAULT 0,
    flow_coverage_ratio     NUMERIC(5, 4) NOT NULL DEFAULT 0.0,

    -- Attribution
    attribution_method      TEXT NOT NULL DEFAULT 'direction_weighted',
    source                  TEXT NOT NULL DEFAULT 'direction_capital_aggregator',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, direction_key)
);
```

---

## 4. Direction Capital Aggregator

```
theme_capital_flow_daily
        +
direction_theme_binding
        │
        ▼
DirectionCapitalAggregator
  direction_flow = Σ(theme_flow × binding_weight)
        │
        ▼
direction_capital_flow_daily
```

**Constraint (same as theme attribution):**
```
SUM(binding_weight per theme across directions) ≤ 1.0
(A theme can belong to multiple directions, but weights must not double-count)
```

---

## 5. Institution Style Input Change

Current S1:
```
InstitutionStyleProducer
  S1: theme_capital_flow_daily  (35%)
```

After Direction Layer:
```
InstitutionStyleProducer
  S1: direction_capital_flow_daily  (35%)
```

The producer formula stays identical. Only the input grain changes: theme-level → direction-level. This means:
- "AI高速互联" with 60亿 aggregate flow now correctly ranks above individual sub-themes
- Flow persistence/acceleration/consistency computed at direction level (more stable)
- Coverage ratio now measures direction breadth, not individual theme narrowness

---

## 6. Replay Alignment

Direction names are closer to analyst vocabulary than individual theme names:

| Analyst Report | Maps To Direction | Current Theme Match |
|---------------|-------------------|-------------------|
| "PCB产业链" | AI_HIGH_SPEED_INTERCONNECT | ❌ string miss on "PCB印制电路板" |
| "AI硬件" | AI_COMPUTE_INFRA | ❌ no match |
| "光通信" | AI_HIGH_SPEED_INTERCONNECT | ✅ partial |
| "半导体设备" | ADVANCED_SEMICONDUCTOR | ✅ partial |

Direction-level replay should improve overlap from 3.5→4+ by consolidating fragmented themes.

---

## 7. Relationship to Frontend Direction Panel

Your existing frontend "方向组合面板" is the correct abstraction. The recommendation is:

```
Before:  Frontend Direction Panel (UI-only, no backend data)
After:   Frontend Direction Panel ← direction_capital_flow_daily (real data)
```

The panel already has the right mental model. The missing piece is the backend data layer.

---

## 8. Three-Phase Implementation

### Phase 1 — Manual Direction Mapping (PR4.2.34)

- `investment_direction` table with 20-50 analyst-verified directions
- `direction_theme_binding` manually curated (like subject_stock_map)
- `DirectionCapitalAggregator` (deterministic weighted sum)
- Replay aligned to direction-level

### Phase 2 — AI-Assisted Discovery (Future)

- LLM scans analyst reports for direction groupings
- Proposes `direction_candidate` entries
- Human review before promotion to production

### Phase 3 — M7 Learning (Future)

- From analyst reports, learn which themes are frequently grouped
- Auto-suggest direction refinements
- Calibrate binding weights

---

## 9. Forbidden Paths

```
❌ direction → replace theme (they co-exist, different abstraction levels)
❌ direction weights sum > 1.0 per theme
❌ AI auto-create directions without review
❌ direction_capital_flow → hot_money_style (direction is institution concept)
❌ direction → UI without InstitutionStyleProducer
```

---

## 10. Priority Justification

This PR should come **before** Hot Money Style because:

1. Institution Style quality is currently limited by theme fragmentation
2. Replay overlap (3.5/5) is partially unfair — system sees fragments, analyst sees directions
3. Frontend already has the direction panel, waiting for backend data
4. Hot Money Style works at theme level (涨停扩散 is inherently theme-granular), so it's not blocked by this layer
