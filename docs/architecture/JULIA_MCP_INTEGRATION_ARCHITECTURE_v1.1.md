# Julia × ai_theme_app — MCP Integration Architecture v1.1

> **Status**: FROZEN FOR REVIEW  
> **Date**: 2026-08-06  
> **Replaces**: v1.0  
> **Changes**: causal_chain + theme_context + explain_decision + Market Memory + M7提前 + Event Sourcing

---

## v1.0 → v1.1 变更摘要

| # | 变更 | 位置 | 原因 |
|---|------|------|------|
| 1 | DecisionEnvelope 增加 `causal_chain`、`theme_context`、`prediction_id` | Section 2 | Julia 需要回答"为什么"，不只是"发生了什么" |
| 2 | MCP Tool 增加 `explain_decision(decision_id)` | Section 3 | Julia 核心能力不是查询，是解释 |
| 3 | Memory OS 分拆为 User Memory + Market Memory | Section 4 | 用户偏好 vs 市场经验——两种不同治理周期的记忆 |
| 4 | M7 Feedback Loop 提升为长期学习引擎 | Section 5 | 没有反馈 = 聪明的评论员；有反馈 = 成长中的分析师 |
| 5 | Event Sourcing 层 | Section 6 | 复盘 Julia 为什么这么判断——可追溯、可审计 |

---

## 1. System Positioning (unchanged)

```
ai_theme_app = Market Brain (facts)
Julia Core = Cognitive Companion (interpretation)
Never the other way around.
```

**核心原则不变**：ai_theme_app 产生可验证的事实。Julia 提供可理解的解释。MCP 只读。

---

## 2. DecisionEnvelope v1.1 (FREEZE)

### 2.1 完整 Schema

```python
@dataclass(frozen=True)
class DecisionEnvelope:
    # ── v1.0 字段 (unchanged) ──
    id: str                          # UUID
    timestamp: str                   # ISO 8601
    source: str                      # "news" | "market" | "signal" | "alert"
    type: str                        # "event_news" | "theme_match" | "support_alert" | ...
    level: str                       # "noise" | "observation" | "watch" | "alert" | "decision"
    evidence: list[Evidence]         # Source-traceable evidence items
    confidence: float                # 0.0 - 1.0
    impact: str                      # "positive" | "negative" | "neutral" | "unknown"
    expiry: str | None               # ISO 8601, when this signal becomes stale
    payload: dict                    # Domain-specific structured data

    # ── v1.1 新增 ──
    causal_chain: list[CausalLink]   # "为什么这些证据相关？" — 因果推导链
    theme_context: ThemeContext | None  # 当前主题的生命周期位置
    prediction_id: str | None        # 关联 M7 预测记录
```

### 2.2 CausalLink

```python
@dataclass(frozen=True)
class CausalLink:
    cause: str                       # "OpenAI发布Agent能力"
    effect: str                      # "AI Agent产业关注度提升"
    market_response: str             # "相关概念股上涨"
    confidence: float                # 因果置信度
```

**为什么需要**：Julia 最终需要回答"为什么"，而不是"发生了什么"。`evidence: [新闻A, 资金B]` 列出事实，`causal_chain` 解释它们如何关联。

### 2.3 ThemeContext

```python
@dataclass(frozen=True)
class ThemeContext:
    theme_id: str                    # "9019807"
    lifecycle: str                   # "START" | "DIFFUSION" | "CONSOLIDATION" | "DECLINE"
    previous_state: str              # 上次观测的状态
    change: str                      # "heat increasing" | "heat decreasing" | "stable"
    first_signal_date: str           # 首次发现日期
    days_active: int                 # 已持续天数
```

**为什么需要**：Julia 无法从单次 DecisionEnvelope 知道这个主题是"刚出现"还是"已经高潮"还是"正在退潮"。

### 2.4 prediction_id

用于 M7 反馈闭环。每个 Decision 可关联一个预测记录：

```
prediction_id: "pred_20260805_001"
  ↓
market truth (实际市场结果)
  ↓
accuracy score
  ↓
Julia Memory update
```

---

## 3. MCP Tools — 5 Tools (v1.1)

### Tool 1: `query_theme_status(theme_id: str) → ThemeStatusSnapshot` (unchanged)

```
Julia: "最近机器人板块怎么样？"
  → query_theme_status("robot_001")
  → { theme, lifecycle, heat_score, leaders, money_flow, risk, causal_chain }
```

### Tool 2: `list_active_alerts(level: str = "L4") → list[DecisionEnvelope]` (unchanged)

```
08:30 daily: list_active_alerts(L4) → 2 DecisionEnvelopes
  → Julia: "今天有两个需要关注的..."
```

### Tool 3: `review_market_snapshot(date: str | None = None) → MarketSnapshot` (unchanged)

```
Daily: review_market_snapshot()
  → { sentiment, active_themes, top_signals, risk_alerts }
  → Morning Brief
```

### Tool 4: `subscribe_agent_channel(channels: list[str]) → ChannelState` (unchanged)

```
Julia subscribes: ["AI_AGENT", "SEMICONDUCTOR", "RISK_ALERT"]
  → 只推这些 channel 的更新
```

### Tool 5: `explain_decision(decision_id: str) → DecisionExplanation` (NEW)

```python
@dataclass(frozen=True)
class DecisionExplanation:
    decision_id: str
    summary: str                     # "AI机器人板块出现扩散信号"
    causal_chain: list[CausalLink]   # 为什么这么判断
    supporting_evidence: int         # 支持性证据数量
    opposing_evidence: int           # 反对性证据数量
    confidence: float
    risk_factors: list[str]          # "市场情绪偏弱", "成交未能放量"
    alternatives: list[str]          # 替代解释
```

**为什么需要**：Julia 最核心的能力不是查询——是**解释**。当 Tony 问"为什么今天看好机器人"时，Julia 调这个接口，拿到结构化解释，再用自己的语言组织回答。

---

## 4. Julia Memory OS — 双层记忆

### 4.1 User Memory (Tony Investment Profile)

```json
{
  "style": "theme_rotation",
  "risk_tolerance": "medium",
  "favorite_sectors": ["AI", "semiconductor", "robotics"],
  "avoid": ["ST_stocks", "pure_speculation"],
  "investment_horizon": "medium_term",
  "preferred_analysis_style": "因果链 + 风险提示",
  "notable_past_interests": ["AI Agent", "机器人", "LoRa"]
}
```

**治理周期**：缓慢变化，Tony 手动确认更新。

### 4.2 Market Memory (M7 Feedback Records)

```json
{
  "prediction_id": "pred_20260805_001",
  "theme": "AI Agent",
  "prediction": "扩散阶段",
  "confidence": 0.82,
  "actual_outcome": "扩散确认",
  "accuracy": 0.91,
  "lesson": "等待成交确认再判断——上次过早了2天",
  "timestamp": "2026-08-05"
}
```

**治理周期**：每个交易日后自动更新。Julia 不只在"分析一次"——她**记住自己判断的对错**。

**为什么这是护城河**：大多数金融 AI 每次分析都是"第一次"。Julia 有历史记忆——她知道"上次看 AI Agent 太早了，因为成交量没跟上"。

---

## 5. M7 Feedback Loop — 长期学习引擎

### 5.1 Pipeline

```
T0: Julia records prediction
  prediction_id = "pred_20260805_001"
  predicted: "AI Agent 扩散阶段, 置信度0.82"

T1: Market truth arrives
  actual: "扩散确认, 领涨股8家涨停"

T2: Deviation analysis
  accuracy_score = f(predicted, actual)
  gap_analysis: "为啥偏了2天? → 成交量放大晚于预期"

T3: Memory update
  Market Memory updated with lesson learned
  Future predictions re-weighted by historical accuracy

T4: Julia 下次解释自动带上下文
  "我记得上次看这个方向早了两天，原因是成交量没跟上...
   今天的成交量已经放出来了，所以这一次应该更确定。"
```

### 5.2 Historical Accuracy Tracker

```python
@dataclass
class AnalystTrackRecord:
    theme: str                       # 跟踪的主题
    total_predictions: int           # 总预测次数
    correct_predictions: int         # 判断正确的次数
    avg_accuracy: float              # 平均准确率
    best_prediction: str             # 最准的一次
    worst_prediction: str            # 最差的一次
    key_lessons: list[str]           # 核心教训
```

---

## 6. Event Sourcing Layer (NEW)

### 6.1 为什么需要

当前架构：

```
Market → ai_theme_app → DecisionEnvelope → Julia → 回答
```

但这条链在事后是**不可回溯的**。如果 Julia 三个月前给了某个建议，今天发现是错的——无法复盘"她当时为什么这么说"。

### 6.2 Event Store Schema

```python
@dataclass(frozen=True)
class JuliaJudgmentEvent:
    event_id: str                    # UUID
    timestamp: str                   # ISO 8601
    trigger: str                     # "morning_brief" | "tony_query" | "auto_alert"
    input_envelopes: list[str]       # 用到的 DecisionEnvelope IDs
    memory_context: list[str]        # 用到的 Market Memory refs
    persona_artifact_version: str    # 当时的 persona 版本
    response: str                    # Julia 当时的回答
    prediction_id: str | None        # 如果包含预测
```

### 6.3 复盘能力

```
三个月后：Tony 问 "为什么我上次在机器人上亏了？"

Event Sourcing → 回溯：
  1. 当时 Julia 用了哪些 DecisionEnvelope？
  2. 当时的 Market Memory 有什么经验？
  3. 当时的 confidence_score 是多少？
  4. 哪个环节出了问题——事实不准确？因果链断了？还是判断太乐观？

Julia 能从完整证据链里找到原因，而不是说"抱歉，我不记得了"。
```

---

## 7. Updated Phase Roadmap

| Phase | 内容 | 优先级 |
|-------|------|--------|
| **Phase 1.1** | Schema Freeze+ — DecisionEnvelope v1.1 (含 causal_chain、theme_context、prediction_id) | P0 |
| **Phase 2** | MCP Server — 5 tools + contract tests | P0 |
| **Phase 3** | Julia Morning Brief Pipeline | P1 |
| **Phase 4** | M7 Feedback Loop + Market Memory | P0 (提前) |
| **Phase 5** | Event Sourcing + Julia 复盘能力 | P1 |

---

## 8. Updated Architecture Diagram

```
                        Market World
                              │
                    ┌─────────┴─────────┐
                    │  ai_theme_app     │
                    │  Market Brain     │
                    │                   │
                    │  Source Adapters   │
                    │  Core Contracts   │
                    │  Decision Engine  │
                    │  Causal Graph     │
                    └────────┬──────────┘
                             │
                    ┌────────┴──────────┐
                    │  Event Store      │  ← NEW
                    │  (归因 + 复盘)     │
                    └────────┬──────────┘
                             │
                    ┌────────┴──────────┐
                    │  MCP Gateway      │
                    │  5 Tools (read-only) │
                    └────────┬──────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
    ┌─────────┴─────────┐         ┌─────────┴─────────┐
    │   Julia Core      │         │  Future Agents    │
    │                   │         │                   │
    │  Context OS       │         │  Trading Agent    │
    │  Memory OS ×2     │         │  Risk Agent       │
    │  Persona Engine   │         │  Research Agent   │
    │  Voice OS         │         │                   │
    │  M7 Feedback      │         │                   │
    └────────┬──────────┘         └───────────────────┘
             │
             ▼
           Tony
```

---

## 9. Approval Checklist

- [ ] DecisionEnvelope v1.1 schema (causal_chain + theme_context + prediction_id) approved
- [ ] 5 MCP tools scope approved (含 explain_decision)
- [ ] Julia permissions: read-only confirmed
- [ ] Memory OS 双层拆分 (User + Market) approved
- [ ] M7 Feedback Loop 提升为长期学习引擎 approved
- [ ] Event Sourcing layer approved
- [ ] Phase Roadmap (M7 提前) approved

---

*This document freezes v1.1 architecture. No code until reviewed and approved.*
