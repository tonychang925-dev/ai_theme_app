# PR4.2.36 — Hot Money Style Producer

**Version:** v1.0
**Date:** 2026-07-14
**Status:** ✅ Implemented (PR4.2.36b) — See `Capital_Intelligence_v1_Freeze.md`

---

## 1. Source Audit Results

| Signal | Source | 7/09 Data | Status |
|--------|--------|-----------|--------|
| S1 Limit-up Expansion | `post_market_recap_snapshot.strong_hotspot_subjects` | 77 hotspot themes ✅ | READY |
| S2 Relay Structure | `strong_stock_watch_history` | 15 stocks, roles: sub_dragon/unknown | AVAILABLE |
| S3 Strong Stock Attack | `strong_stock_watch_history` + `theme_cycle_judgement_v2` | 15 strong stocks, 36 theme cycles | AVAILABLE |
| S4 Dragon Tiger | `dragon_tiger_object` | 3820 rows total | AVAILABLE |
| Event Catalyst | `event_theme_map`, `structured_intel_event` | Multiple tables exist | AVAILABLE |

### Recap hotspot fields (per entry):
```
source, stock_id, stock_name, theme_name, cycle_state, subject_key,
watch_score, watch_status, support_score, pool_entry_type
```

---

## 2. Difference from Institution Style

| Dimension | Institution Style | Hot Money Style |
|-----------|------------------|-----------------|
| Time horizon | 5-20 trading days | 1-3 trading days |
| Core question | Which industrial direction is capital accumulating? | Where is short-term attack happening today? |
| Primary signal | Direction capital flow persistence | Limit-up breadth expansion |
| Cycle usage | Stage bonus (FERMENTATION=85) | Stage detection (START vs CLIMAX) |
| Dragon tiger weight | 10% (confirmation) | 15% (stronger signal for hot money) |
| Output granularity | Direction | Theme (涨停扩散 is theme-level) |

**Critical rule:** Hot Money and Institution Style are completely separate models. Do NOT reuse weights, formulas, or output schemas between them.

---

## 3. Architecture

```
Market Emotion State
        │
        ├── Limit-Up Structure (涨停扩散)
        ├── Relay Ecology (连板晋级)
        ├── Strong Stock Pool (强势股)
        ├── Event Catalyst (事件驱动)
        └── Dragon Tiger Evidence (龙虎榜)
                │
                ▼
        HotMoneyStyleProducer
                │
                ▼
        hot_money_style_daily
                │
                ▼
        ReviewDocument.capital.hot_money_style[]
```

---

## 4. Four-Signal Model

### S1: Limit-Up Expansion (35%)

Measures short-term attack breadth and momentum. NOT just "how many limit-ups" — "is the attack spreading?"

```
attack_score = breadth_growth × 0.40 + spread_intensity × 0.35 + continuation_rate × 0.25

Where:
  breadth_growth = (today_limitup_count - avg_3day_count) / max(avg_3day_count, 1)
  spread_intensity = COUNT(DISTINCT themes with new limit-ups) / total_active_themes
  continuation_rate = today_continue_count / yesterday_limitup_count
```

### S2: Relay Structure (25%)

Measures board height quality and promotion chain health. Hot money cares deeply about relay ecology.

```
relay_score = promotion_quality × 0.50 + board_height_strength × 0.30 + feedback_health × 0.20

Where:
  promotion_quality = (1→2 rate × 0.5 + 2→3 rate × 0.3 + 3→4 rate × 0.2)
  board_height_strength = max_board_height / 10 (normalized)
  feedback_health = 1.0 - yesterday_big_loss_count / yesterday_limitup_count
```

### S3: Strong Stock Attack (25%)

Measures leader quality, sealing strength, and attack intensity.

```
attack_intensity = leader_sealed_rate × 0.40 + sub_dragon_quality × 0.30 + pool_depth × 0.30

Where:
  leader_sealed_rate = COUNT(role='龙头' AND sealed) / total_leaders
  sub_dragon_quality = COUNT(role='sub_dragon' AND positive) / total_sub_dragons
  pool_depth = COUNT(DISTINCT stocks with positive momentum) / total_strong_pool
```

### S4: Dragon Tiger Enhancement (15%)

Higher weight than Institution (15% vs 10%) because hot money behavior is more visible in dragon tiger data.

```
dt_enhancement = hot_money_presence × 0.60 + seat_continuity × 0.40

Where:
  hot_money_presence = COUNT(themes with known hot money seats) / total_active_themes
  seat_continuity = COUNT(seats appearing 2+ consecutive days) / total_seats
```

---

## 5. Output Schema

```sql
CREATE TABLE IF NOT EXISTS hot_money_style_daily (
    trade_date              DATE NOT NULL,
    subject_key             TEXT NOT NULL,        -- theme-level (hot money is per-theme)
    theme_name              TEXT NOT NULL DEFAULT '',

    -- Composite
    hot_money_score         NUMERIC(6, 2),
    confidence              NUMERIC(5, 4),

    -- Components
    attack_score            NUMERIC(6, 2),        -- S1: limit-up expansion
    relay_score             NUMERIC(6, 2),        -- S2: relay ecology
    intensity_score         NUMERIC(6, 2),        -- S3: strong stock attack
    dragon_tiger_score      NUMERIC(6, 2),        -- S4: DT enhancement

    -- Attack stage
    attack_stage            TEXT,                  -- FIRST_WAVE | CONTINUING | CLIMAX | RETREATING
    attack_day              INTEGER,              -- days since first detection

    -- Evidence
    evidence_quality        JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence                JSONB NOT NULL DEFAULT '{}'::jsonb,
    top_signals             TEXT[] NOT NULL DEFAULT '{}',

    -- Provenance
    model_version           TEXT NOT NULL DEFAULT 'hot_money_style_v1',
    source                  TEXT NOT NULL DEFAULT 'hot_money_style_producer',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trade_date, subject_key, model_version)
);
```

---

## 6. Attack Stage Detection

```
FIRST_WAVE:   day 1-2 of limit-up expansion, breadth growing
CONTINUING:   day 3-5, multiple stocks sealing, relay chain healthy
CLIMAX:        high board + maximum breadth + feedback turning negative
RETREATING:    breadth contracting, leaders breaking, promotion rates falling
```

---

## 7. Forbidden Paths (Frozen)

```
❌ institution_style formula → hot_money_style
❌ direction_capital_flow → hot_money_style
❌ theme_capital_flow → hot_money_style attack_score
❌ single signal → hot_money conclusion
❌ DT missing → infer from role_label
❌ hot_money_style → ReviewDocument (deferred to PR4.2.37)
```

---

## 8. Implementation Phases

### PR4.2.36a — Source Audit ✅ (this document)

### PR4.2.36b — Hot Money Producer

- `hot_money_style_daily` table
- `HotMoneyStyleProducer` with 4-signal model
- Contract tests: C1 attack detection, C2 separate from institution, C3 forbidden fields
- No UI, no ReviewDocument

### PR4.2.36c — Replay Validation

- Validate against analyst hot money mentions (商业航天, 机器人, 消费 etc.)
- Compare with institution style overlap (should be DIFFERENT rankings)

---

## 9. Institution vs Hot Money — Complete Separation

| Aspect | Institution | Hot Money |
|--------|------------|-----------|
| Input grain | Direction | Theme |
| Producer class | InstitutionStyleProducer | HotMoneyStyleProducer |
| Output table | institution_style_daily | hot_money_style_daily |
| S1 signal | Direction Flow (35%) | Limit-up Expansion (35%) |
| S2 signal | Industry Cycle (30%) | Relay Structure (25%) |
| S3 signal | Stock Structure (25%) | Strong Stock Attack (25%) |
| S4 signal | Dragon Tiger (10%) | Dragon Tiger (15%) |
| Time window | 5-20 days | 1-3 days |
| ReviewDocument field | capital.institution_style[] | capital.hot_money_style[] |
