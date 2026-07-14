# PR4.2.34 — Investment Direction Layer

**Version:** v2.0
**Date:** 2026-07-14
**Status:** Design Approved — PR4.2.34a Ready
**Changes in v2.0:**
- Four-layer architecture: Market State → Direction → Theme/Event → Stock → Fund Evidence
- Direction roles: PRIMARY_DRIVER / SUPPORTING / OPTIONAL
- Double-counting guard: theme_direction_allocation_daily table
- S1: 70% Direction Flow + 30% Theme Momentum (not full replacement)
- 20 core directions for Phase 1
- Phase split: 34a (Foundation) → 34b (Replay Validation) → 35 (Institution upgrade)
- Three guard rules

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

Four-layer frozen structure:

```
                    Market State
                         │
                         ▼
              Investment Direction Layer
                 (资金投资方向 — 投资认知)
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
          Theme Layer            Event Layer
          (市场标签)             (催化事件)
              │                     │
              └──────────┬──────────┘
                         ▼
                       Stock
                         │
                         ▼
               Fund Evidence Layer
```

A direction can form from Themes (e.g. AI高速互联 ← PCB+铜连接+MPO) OR from Events (e.g. "英伟达Rubin发布" → AI服务器+液冷+高速连接+HBM). Direction is an investment cognition layer, not a simple theme aggregator.

Data flow:

```
stock_fund_flow_daily
        │
        ▼
theme_capital_flow_daily  (existing, unchanged)
        │
        ├── direction_theme_binding (weighted)
        └── theme_direction_allocation_daily (double-counting guard)
                │
                ▼
direction_capital_flow_daily  ← NEW
        │
        ▼
InstitutionStyleProducer
  S1 = Direction Flow (70%) + Theme Momentum (30%)
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
    role            TEXT NOT NULL DEFAULT 'SUPPORTING',  -- PRIMARY_DRIVER | SUPPORTING | OPTIONAL
    confidence      NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
    source          TEXT NOT NULL DEFAULT 'manual',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (direction_key, subject_key)
);
```

**Example bindings:**

| direction_key | subject_key | weight | relationship |
|--------------|-------------|--------|-------------|
| AI_HIGH_SPEED_INTERCONNECT | 9018144 | 0.30 | PRIMARY_DRIVER |
| AI_HIGH_SPEED_INTERCONNECT | 9023001 | 0.25 | PRIMARY_DRIVER |
| AI_HIGH_SPEED_INTERCONNECT | 9034501 | 0.20 | SUPPORTING |
| AI_HIGH_SPEED_INTERCONNECT | 9045601 | 0.15 | OPTIONAL |
| AI_COMPUTE_INFRA | 9014001 | 0.35 | PRIMARY_DRIVER |
| AI_COMPUTE_INFRA | 9015778 | 0.30 | PRIMARY_DRIVER |
| AI_COMPUTE_INFRA | 9056701 | 0.20 | SUPPORTING |

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

### 3.4 `theme_direction_allocation_daily` (Double-Counting Guard)

A theme can belong to multiple directions. When theme X has 100亿 flow and is bound to 3 directions at weights 0.3/0.4/0.3, the same 100亿 must not be triple-counted.

```sql
CREATE TABLE IF NOT EXISTS theme_direction_allocation_daily (
    trade_date          DATE NOT NULL,
    subject_key         TEXT NOT NULL,
    direction_key       TEXT NOT NULL,
    allocated_amount_yuan NUMERIC(24, 2),
    allocation_weight   NUMERIC(5, 4) NOT NULL,
    source_flow_yuan    NUMERIC(24, 2),  -- original theme flow for audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (trade_date, subject_key, direction_key)
);
```

**Constraint C10 (Theme Conservation):**
```
SUM(allocated_amount per theme across directions) ≤ source_flow_yuan × 1.001
```
A theme's flow allocated across directions must not exceed its total flow.

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

Direction does NOT fully replace Theme in S1. It complements:

```
S1 Capital Flow Score = Direction Flow × 0.70 + Theme Momentum × 0.30

Direction Flow (70%):
  Captures broad industrial capital trends. Aggregated from direction_capital_flow_daily.
  "Is capital flowing into AI infrastructure as a sector?"

Theme Momentum (30%):
  Captures sub-theme explosive signals. Individual theme breakout that might be diluted
  in direction aggregation. "Is PCB suddenly surging within AI高速互联?"
```

Producer formula unchanged (35/30/25/10). Only S1 input grain enriched with direction context.

---

## 6. Phase 1 — 20 Core Directions

Start with 20 analyst-verified directions. Expand after replay validation.

| # | direction_key | direction_name | Key Themes |
|---|--------------|----------------|-----------|
| 1 | AI_COMPUTE_INFRA | AI算力基础设施 | 国产算力, 服务器, 液冷, 存储芯片, HBM |
| 2 | AI_HIGH_SPEED_INTERCONNECT | AI高速互联 | PCB, 高速铜连接, MPO, 光模块, 覆铜板, 电子布 |
| 3 | ADVANCED_SEMICONDUCTOR_MFG | 先进半导体制造 | 半导体设备, 半导体硅片, 光刻胶 |
| 4 | SEMICONDUCTOR_MATERIALS | 半导体材料 | 电子特气, 靶材, 碳化硅, 氟化工 |
| 5 | AI_STORAGE_CHAIN | AI存储产业链 | 存储芯片, 存储模组, HBM |
| 6 | OPTICAL_COMMUNICATION | 光通信产业链 | CPO, 光模块, 光纤, MPO |
| 7 | DOMESTIC_COMPUTE | 国产算力链 | 国产服务器, 华为昇腾, 华为智算 |
| 8 | ROBOTICS_AUTOMATION | 人形机器人 | 人形机器人, 工业自动化, 伺服电机 |
| 9 | COMMERCIAL_SPACE | 商业航天 | 卫星互联网, 商业航天, 火箭 |
| 10 | NEW_ENERGY_TECH | 新能源新技术 | 固态电池, 钙钛矿, 算电协同 |
| 11 | POWER_INFRA | 电力基础设施 | 电力运营, 特高压, 智能电网 |
| 12 | DEFENSE_MILITARY | 国防军工 | 军工电子, 军用材料 |
| 13 | PHARMA_HEALTHCARE | 医药健康 | 创新药, 医疗器械 |
| 14 | CONSUMER_RETAIL | 消费零售 | 食品饮料, 新零售 |
| 15 | AUTO_SUPPLY_CHAIN | 汽车产业链 | 智能驾驶, 汽车电子, 一体化压铸 |
| 16 | MATERIAL_CHEMICAL | 材料化工 | 磷化工, 氟化工, 稀土永磁 |
| 17 | AI_APPLICATION | AI应用 | AI agent, 物理AI, AI+ |
| 18 | DISPLAY_OPTOELECTRONICS | 光电显示 | MiniLED, MicroLED, 光学 |
| 19 | LOW_ALTITUDE_ECONOMY | 低空经济 | 无人机, eVTOL |
| 20 | CROSS_BORDER_TRADE | 跨境贸易 | 跨境电商, 物流, 一带一路 |

---

## 7. Replay Alignment

Direction names are closer to analyst vocabulary than individual theme names:

| Analyst Report | Maps To Direction | Current Theme Match |
|---------------|-------------------|-------------------|
| "PCB产业链" | AI_HIGH_SPEED_INTERCONNECT | ❌ string miss on "PCB印制电路板" |
| "AI硬件" | AI_COMPUTE_INFRA | ❌ no match |
| "光通信" | AI_HIGH_SPEED_INTERCONNECT | ✅ partial |
| "半导体设备" | ADVANCED_SEMICONDUCTOR_MFG | ✅ partial |

Direction-level replay should improve overlap from 3.5→4+ by consolidating fragmented themes.

---

## 8. Frontend Direction Panel Upgrade

Your existing frontend "方向组合面板" should become a core page. Recommended information architecture:

```
Directions (Primary View)          Themes (Secondary View)
─────────────────────────          ─────────────────────
1. AI高速互联  65亿 ↑              展开→ PCB (20亿)
   包含: PCB,铜连接,MPO                 覆铜板 (10亿)
   生命周期: FERMENTATION                高速铜连接 (15亿)
   龙头: 沪电股份                        MPO (12亿)
```

The panel already has the right mental model. The missing piece is backend data from `direction_capital_flow_daily`.

---

## 9. Implementation Phases

### PR4.2.34a — Direction Foundation

- `investment_direction` + `direction_theme_binding` + `theme_direction_allocation_daily` tables
- 20 manual directions curated from analyst reports
- `DirectionCapitalAggregator` (deterministic weighted sum, C10 conservation)
- Contracts: C10 Theme Conservation, C11 No Direction Override

**Forbidden:** InstitutionStyleProducer changes, UI integration

### PR4.2.34b — Direction Replay Validation

- Map analyst baselines to direction keys
- Run replay: system directions vs analyst directions
- Verify overlap improvement (expect 3.5→4.0+)
- Identify direction granularity issues

**Forbidden:** Producer changes until replay validates

### PR4.2.35 — Institution Style Upgrade

- S1: Direction Flow 70% + Theme Momentum 30%
- Re-run replay with upgraded S1
- Compare with pre-direction baseline

### Future — AI-Assisted + M7 Learning

- LLM proposes direction candidates (review-gated)
- M7 learns theme grouping patterns from analyst reports

---

## 10. Guard Rules (Frozen)

```
Guard 1: ❌ direction → replace/obsolete theme
         (they co-exist at different abstraction levels)
Guard 2: ❌ same theme flow double-allocated across directions
         (C10: allocation ≤ source × 1.001)
Guard 3: ❌ direction → hot_money_style
         (direction is institution concept, hot money is per-theme attack)

Also forbidden:
❌ direction weights sum > 1.0 per theme
❌ AI auto-create directions without review
❌ direction_capital_flow → UI without InstitutionStyleProducer
```

---

## 11. Priority Justification

This PR should come **before** Hot Money Style because:

1. Institution Style quality is limited by theme fragmentation
2. Replay overlap (3.5/5) is partially unfair — system sees fragments, analyst sees directions
3. Frontend already has the direction panel, waiting for backend data
4. Hot Money Style works at theme level (涨停扩散 is inherently theme-granular), not blocked by this layer
