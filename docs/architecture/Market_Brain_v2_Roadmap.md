# Market Brain v2 — Roadmap

**Version:** v1.0
**Date:** 2026-07-14
**Prerequisite:** Capital Intelligence v1.0 Frozen

---

## 1. Phase Shift: Producer → Brain → Analyst → Decision

```
v1 (Completed):                    v2 (Next):
───────────────                    ─────────
Producer                            Brain
  ↓                                   ↓
Producer                            Analyst
  ↓                                   ↓
Producer                            Decision
  ↓                                   ↓
Producer                            M7 Learning
```

The Producer phase is complete. Five frozen producers with 82 contract tests provide a stable foundation. The next phase is not about adding more signals or adjusting weights — it's about building cognitive layers on top of verified evidence.

---

## 2. Market Brain v1 Architecture

```
                    Market Brain Snapshot
               (unified daily cognition state)
                            │
    ┌───────────┬───────────┼───────────┬───────────┐
    │           │           │           │           │
 Emotion     Capital     Event       Theme      Strategy
 Engine      Engine      Engine      Engine      Engine
    │           │           │           │           │
    └───────────┴───────────┼───────────┴───────────┘
                            │
                     AI Analyst
                   (narrative + decision)
                            │
                    ReviewDocument
                      (render only)
```

**Key architectural shift:** ReviewDocument no longer assembles data from multiple sources. It reads a single `MarketBrainSnapshot` — a unified daily cognition state. ReviewDocument becomes a render layer, not an assembly layer.

---

## 3. Market Brain Snapshot

```json
{
  "trade_date": "2026-07-09",

  "emotion": {
    "phase": "CHAOS",
    "score": 39,
    "confidence": 0.82
  },

  "capital": {
    "institution_style": [
      {"direction": "AI算力方向", "score": 73, "confidence": 0.72}
    ],
    "hot_money_style": [
      {"theme": "商业航天", "score": 82, "stage": "FIRST_WAVE"}
    ],
    "consensus": [
      {"direction": "AI算力方向", "institution": 73, "hot_money": 65}
    ],
    "divergence": [
      {"theme": "存储芯片", "institution": 72, "hot_money": 28}
    ]
  },

  "event": {
    "active_catalysts": [],
    "pending_catalysts": []
  },

  "theme": {
    "active_themes": 36,
    "new_themes": 3,
    "fading_themes": 5
  },

  "direction": {
    "top_directions": ["AI算力方向", "先进半导体"],
    "direction_flows": {}
  },

  "market_state": {
    "regime": "ROTATION",
    "risk_preference": 55
  },

  "risk": {
    "risk_level": "MEDIUM",
    "top_risks": []
  },

  "narrative": {
    "capital_story": "机构资金持续流入AI算力方向...",
    "risk_note": "连续上涨后注意轮动风险"
  }
}
```

---

## 4. Phase Breakdown

### Phase 1: Market Brain Snapshot (PR4.2.40)

**Goal:** Single unified daily cognition state. All engines write to one snapshot.

```
Deliverables:
  - MarketBrainSnapshot schema
  - SnapshotBuilder (reads from all 5 frozen producers)
  - ReviewDocument simplified to render-only
  - Contract: snapshot must be replayable (same inputs → same snapshot)

Forbidden:
  - New producers
  - Weight changes
  - Business logic in snapshot builder
```

### Phase 2: Consensus & Divergence Engine (PR4.2.41)

**Goal:** Cross-reference Institution and Hot Money to identify consensus and divergence.

```
Consensus:  Institution > 50 AND Hot Money > 50 → BOTH
Divergence: Institution > 60 AND Hot Money < 30 → INSTITUTION_ONLY
            Hot Money > 60 AND Institution < 30 → HOT_MONEY_ONLY

This is the highest-density information for analyst decision-making.
```

### Phase 3: Narrative Engine (PR4.2.42)

**Goal:** Convert structured scores into natural-language explanation.

```
Input:   MarketBrainSnapshot
Output:  capital_story (机构叙事) + risk_note (风险提示) + hot_money_story (游资叙事)

Method:  Template-driven with evidence references.
         NOT free-form LLM generation (hallucination risk).
         Every statement must be traceable to a specific evidence source.
```

### Phase 4: Strategy Engine (PR4.2.43)

**Goal:** Tomorrow's strategy from today's brain state.

```
Input:   MarketBrainSnapshot + historical context
Output:  tomorrow_scenario, watch_directions, risk_alerts

Method:  Rule-based from emotion + capital + event state.
         NOT LLM-generated trading advice.
```

### Phase 5: M7 Feedback Learning (PR4.2.50)

**Goal:** Automated weight calibration from analyst feedback.

```
Input:   Historical snapshots + analyst report baselines
Output:  Calibrated weights for Institution S1-S4 and Hot Money S1-S4

Method:  Compare system scores with analyst rankings.
         Gradient descent on weight space.
         Human-in-the-loop approval before weight changes take effect.

Forbidden:
  - Direct analyst score substitution
  - Overfitting to single analyst
  - Weight changes without audit trail
```

---

## 5. Key Principles for v2

1. **ReviewDocument = Render, not Assemble** — No more data assembly in the API layer
2. **MarketBrainSnapshot = Single source of truth** — One snapshot, all engines
3. **Narrative = Evidence-traceable** — Every sentence must reference a specific signal
4. **M7 = Calibrate, don't hardcode** — Weights learned from data, not set by intuition
5. **Producers frozen** — No new signals, no weight adjustments without M7 approval

---

## 6. Migration Path from v1

```
v1 (Current):                       v2 (Target):
────────────                        ──────────
5 independent producers             MarketBrainSnapshot
  ↓                                   ↓
API assembles ReviewDocument         ReviewDocument renders snapshot
  ↓                                   ↓
Frontend displays                   Frontend displays

Migration:
  Step 1: Build MarketBrainSnapshot as new layer (producers unchanged)
  Step 2: Switch ReviewDocument to read snapshot instead of assembling
  Step 3: Deprecate direct producer→ReviewDocument paths
```

---

## 7. What Does NOT Change

```
FROZEN:
  ✅ All 5 producers (Tushare, Attribution, Direction, Institution, Hot Money)
  ✅ All 82 contract tests
  ✅ Source Ownership Registry
  ✅ Architecture decisions (single-signal forbidden, DT enhancement only, etc.)
  ✅ Institution-Hot Money separation

NEW (built on top of frozen foundation):
  🆕 MarketBrainSnapshot
  🆕 Consensus & Divergence
  🆕 Narrative Engine
  🆕 M7 Feedback Learning
```
