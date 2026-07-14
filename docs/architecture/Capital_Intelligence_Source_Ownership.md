# Capital Intelligence Source Ownership

**PR:** PR4.2.30 / PR4.2.31
**Status:** Frozen — Source Registry
**Frozen Date:** 2026-07-14
**Reference:** `Capital_Intelligence_Pipeline_Design.md` v2.0, `Capital_Intelligence_Source_Audit.md`

---

## 1. Ownership Registry

### 1.1 Stock Daily Order Size Flow

```yaml
owner: TushareMoneyflowAdapter
status: VERIFIED (probe: 2026-07-14)
table: stock_fund_flow_daily

primary:
  source: tushare.moneyflow
  version: v1
  verified_date: 2026-07-14
  frequency: DAILY
  unit_input: 万元
  unit_storage: 元
  buy_sell_direction: PRESERVED
  semantic:
    vendor_defined: order_size_flow
    not_owner_identity: true
  change_policy:
    require_audit: true

secondary:
  source: eastmoney.push2his
  status: CONNECTION_UNAVAILABLE
  buy_sell_direction: MISSING
  change_policy:
    require_audit: true

limited:
  source: sina.moneyflow_daily
  status: CAPABILITY_LIMITED
  available_buckets: [net, super_large]
  buy_sell_direction: MISSING
```

### 1.2 Theme Daily Fund Flow

```yaml
owner: ThemeCapitalAttributionEngine
status: DESIGN (implementation: PR4.2.32)
table: theme_fund_flow_daily

preferred:
  source: tushare.moneyflow_cnt_ths
  status: ACCESS_DENIED
  required_credits: 6000

primary (self-aggregated):
  source: stock_fund_flow_daily + stock_theme_map
  method: weighted_attribution
  rule: theme_flow = stock_flow × theme_weight
  constraint: SUM(theme_weight per stock) ≤ 1.0
```

### 1.3 Market Capital State

```yaml
owner: MarketCapitalStateProducer
status: DESIGN (implementation: PR4.2.31e)
table: market_capital_state_daily

inputs:
  - active_capital_yi (board_pool_zt_zb)
  - limit_up_count (MarketMetricsSnapshot)
  - limit_down_count (MarketMetricsSnapshot)
  - up_down_ratio (MarketMetricsSnapshot)
  - theme_rotation_speed (derived)

outputs:
  - capital_style: rotation_attack | defensive | risk_off
  - risk_preference_score: 0-100
```

### 1.4 Institution Style

```yaml
owner: InstitutionStyleProducer
status: DESIGN (implementation: PR4.2.33)

inputs:
  theme_fund_flow:
    source: theme_fund_flow_daily
    weight: 0.35
  theme_cycle:
    source: theme_cycle_judgement_v2
    weight: 0.30
  stock_structure:
    source: strong_stock_watch_history
    weight: 0.25
  dragon_tiger:
    source: seat_evidence
    weight: 0.10
    role: evidence_only

output: capital.institution_style[]
```

### 1.5 Hot Money Style

```yaml
owner: HotMoneyStyleProducer
status: DESIGN (implementation: PR4.2.34)

inputs:
  limit_up:
    source: limit_up.categories
    weight: 0.35
  relay:
    source: relay_ecology
    weight: 0.25
  strong_stock:
    source: strong_stock_watch_history
    weight: 0.25
  dragon_tiger:
    source: seat_evidence
    weight: 0.15
    role: evidence_only

output: capital.hot_money_style[]
```

### 1.6 AI Capital Explanation

```yaml
owner: CapitalExplanationProducer
status: DESIGN (implementation: PR4.2.35)

inputs:
  - institution_style[] output
  - hot_money_style[] output
  - market_capital_state output

output:
  capital.explanation.capital_story
  capital.explanation.risk_note
```

### 1.7 Active Capital (Existing)

```yaml
owner: ActiveCapitalProducer
status: COMPLETE (PR4.2.28)
source: board_pool_zt_zb
field: capital.active_amount
quality: PARTIAL (missing board_pool.yzt.amount_yi)
calibration: M7 Analyst Feedback (future)
```

### 1.8 Dragon Tiger Evidence

```yaml
owner: DragonTigerSnapshot
status: DEFERRED (Phase 4+)

role: evidence_only
usage:
  - institution_style confidence boost (10%)
  - hot_money_style confidence boost (15%)
forbidden:
  - sole producer of institution_style
  - sole producer of hot_money_style
  - blocking style output when unavailable
```

---

## 2. Source Ownership Matrix

| Target Field | Owner | Primary Source | Status | Forbidden Path |
|-------------|-------|---------------|--------|---------------|
| `capital.active_amount` | `ActiveCapitalProducer` | `board_pool_zt_zb` | ✅ COMPLETE | theme_capital_flow → active_amount |
| `capital.market_capital_state` | `MarketCapitalStateProducer` | MarketMetricsSnapshot | DESIGN | single metric → capital_style |
| `capital.institution_style[]` | `InstitutionStyleProducer` | 4-source weighted model | DESIGN | any single source → style |
| `capital.hot_money_style[]` | `HotMoneyStyleProducer` | 4-source weighted model | DESIGN | any single source → style |
| `capital.explanation` | `CapitalExplanationProducer` | institution + hot_money + state | DESIGN | template text without evidence |
| `capital.evidence.fund_flow` | `TushareMoneyflowAdapter` | Tushare `moneyflow` | ✅ VERIFIED | fund_flow → institution_style (direct) |
| `capital.evidence.theme_flow` | `ThemeCapitalAttributionEngine` | stock→theme weighted | DESIGN | simple SUM without attribution |
| `capital.evidence.dragon_tiger` | `DragonTigerSnapshot` | Tushare / a-stock-data | DEFERRED | seat rows as sole style producer |

---

## 3. Dragon Tiger Positioning

Dragon tiger data is **evidence enhancement only** — never the primary style producer.

```
DragonTigerSnapshot
  → capital.evidence.dragon_tiger    (事实存储)
  → InstitutionStyleProducer         (10% weight, confidence boost)
  → HotMoneyStyleProducer            (15% weight, confidence boost)

❌ DragonTigerSnapshot → institution_style (sole source)
❌ DragonTigerSnapshot → hot_money_style (sole source)
❌ Dragon tiger missing → infer from role_label / theme stage
❌ Dragon tiger missing → block all style output
```

---

## 4. Market Capital State Positioning

Market Capital State sits BETWEEN Evidence and Intelligence. It answers the environment question first, preventing style misattribution.

```
Same theme_fund_flow signal, different environments:

Market STRONG (risk_preference=72, capital_style=rotation_attack):
  theme_flow + persistence → institution_accumulation

Market WEAK (risk_preference=25, capital_style=defensive):
  theme_flow + persistence → capital_sheltering (not accumulation)
```

The same fund flow signal means different things in different market environments. Market Capital State provides this context.

---

## 5. Forbidden Paths (Frozen)

```
❌ Single source → capital intelligence
❌ net_amount > 0 → institution_attention
❌ net_amount > 0 → hot_money_style
❌ money_flow_enhanced.role_label → institution_style
❌ money_flow_enhanced.role_label → hot_money_style
❌ theme_capital_flow → hot_money_style
❌ theme_capital_flow → active_amount
❌ seat_money_summary → institution_style (sole)
❌ seat_money_summary → hot_money_style (sole)
❌ dragon_tiger missing → infer from role_label
❌ automatic source fallback (must be explicit registry)
❌ recomputing net_mf_amount from bucket data
❌ direct UI connection without Intelligence Layer
❌ stock flow SUM without theme_weight attribution
```

---

## 6. Change Policy

Any change to a source in this registry must:

1. Update the `verified_date` and `version` fields
2. Pass probe verification before status change
3. Not silently switch sources (explicit registry update required)
4. Not add automatic fallback paths

---

## 7. Migration Plan

```
1.  PR4.2.31e: Market Capital State Producer        ← Phase 0
2.  PR4.2.31f: Tushare Moneyflow Adapter            ← Phase 1 (P0, ready)
3.  PR4.2.32:  Theme Capital Attribution Engine      ← Phase 2
4.  PR4.2.33:  Theme Capital Lifecycle Adapter       ← Phase 2.5
5.  PR4.2.34:  Institution Style Producer            ← Phase 3
6.  PR4.2.35:  Hot Money Style Producer              ← Phase 4
7.  PR4.2.36:  AI Capital Explanation Producer       ← Phase 5
8.  PR4.2.37:  Frontend Connection                   ← Phase 6
9.  M7:        Analyst Feedback Calibration           ← Future
```

---

## 8. Non-Goals

- No frontend change in Phase 0-4
- No Assembler change
- No ContextFactory change
- No ReviewDocument schema change until Phase 5
- No inference from stock role to capital participant type
- No automatic source fallback
- No dragon tiger as sole style producer
