# Julia × ai_theme_app — MCP Integration Architecture v1.0

> **Status**: DRAFT — Pending Review  
> **Date**: 2026-08-06  
> **Principle**: ai_theme_app = Market Brain (facts). Julia = Cognitive Companion (interpretation). Never the other way around.

---

## 1. System Positioning

```
┌─────────────────────────────────────────────────────────┐
│                     External World                       │
│  新闻 / 公告 / 行情 / 资金流 / 龙虎榜 / 涨停数据          │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│                   ai_theme_app                           │
│              Market Intelligence Engine                  │
│                                                         │
│  Source Adapter Layer  →  Core Contracts  →  Decisions  │
│  (data ingestion)         (unified schema)   (L0→L4)   │
│                                                         │
│  Owns: facts, evidence, signals, quantitative models     │
│  Does NOT own: interpretation, reasoning, companionship  │
└───────────────┬─────────────────────────────────────────┘
                │
                │  MCP Gateway  (read-only)
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│                     Julia Core                           │
│              Cognitive Companion Layer                   │
│                                                         │
│  Context OS  │  Memory OS  │  Persona Engine  │  Voice  │
│                                                         │
│  "解释、推理、陪伴"                                      │
│  - Reads DecisionEnvelope, explains implications         │
│  - Contextualizes signals against Tony's preferences     │
│  - Never trades. Never modifies strategy.               │
└─────────────────────────────────────────────────────────┘
```

**核心原则**：ai_theme_app 产生**可验证的事实**。Julia 提供**可理解的解释**。两套系统，各自独立部署，通过 MCP 协议交换结构化数据。

---

## 2. Frozen Contracts

### 2.1 DecisionEnvelope v1 (FREEZE)

所有 ai_theme_app 输出必须包装为 DecisionEnvelope。

```python
@dataclass(frozen=True)
class DecisionEnvelope:
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
```

### 2.2 MCP Tool Contract (FREEZE)

所有 MCP tools 返回 `DecisionEnvelope[]` 或对应的结构化快照。**只读，永不写回**。

---

## 3. MCP Tool Design

### Tool 1: `query_theme_status(theme_id: str) → ThemeStatusSnapshot`

```
Julia: "最近机器人板块怎么样？"
  → query_theme_status("robot_001")
  → {
        theme: "机器人",
        lifecycle: "DIFFUSION",
        heat_score: 87,
        leaders: ["拓斯达", "绿的谐波"],
        money_flow: "increasing",
        risk: "medium"
    }
  → Julia: "机器人板块正在扩散期，热度87分，龙头是拓斯达和绿的谐波，资金还在流入。风险中等。你之前说过看好这个方向——今天有新的催化剂吗？"
```

### Tool 2: `list_active_alerts(level: str = "L4") → list[DecisionEnvelope]`

```
每天早上 8:30 Julia 自动调用:
  → list_active_alerts(level="L4")
  → [DecisionEnvelope × 2]
  → Julia: "Tony，今天有两个需要重点关注的变化。第一，AI Agent 题材出现新的扩散信号。第二，半导体方向有资金异动。你想先看哪一个？"
```

### Tool 3: `review_market_snapshot(date: str | None = None) → MarketSnapshot`

```
Julia 每天醒来:
  → review_market_snapshot()
  → {
        market_sentiment: "偏弱",
        active_themes: ["AI Agent", "半导体"],
        top_signals: [...],
        risk_alerts: [...]
    }
  → Julia: "今天市场情绪偏弱，但是 AI Agent 方向出现新的扩散信号，半导体也还在活跃。你之前关注的机器人板块没有异常。"
```

### Tool 4: `subscribe_agent_channel(channels: list[str]) → ChannelState`

```
Julia 主动订阅:
  → subscribe_agent_channel(channels: ["AI_AGENT", "SEMICONDUCTOR", "RISK_ALERT"])
  → ChannelState 订阅确认
  → 后续实时推送只推这几个 channel
```

---

## 4. Julia Core Integration Points

### 4.1 Tony Investment Profile (Memory OS)

```json
{
  "style": "theme_rotation",
  "risk_tolerance": "medium",
  "favorite_sectors": ["AI", "semiconductor", "robotics"],
  "avoid": ["ST_stocks", "pure_speculation"],
  "investment_horizon": "medium_term"
}
```

Julia 读取这个 profile，在做解释时**自动适配 Tony 的偏好**——不做通用分析，做**面向上一个人的**定制解释。

### 4.2 Context OS — Morning Brief Pipeline

```
07:30 Daily Trigger
  ↓
list_active_alerts(L4)  →  review_market_snapshot()
  ↓                    ↓
    Context Assembly
  ↓
Persona Filter: "用温柔、理性的语言，面向 Tony 的偏好做解释"
  ↓
Morning Brief (voice or text)
```

### 4.3 Memory OS — M7 Feedback Loop

```
Prediction recorded at T0
  ↓
Actual outcome at T1
  ↓
Deviation analysis
  ↓
Memory update: "上次关于 AI Agent 的扩散判断偏早了 2 天，原因是..."
  ↓
Future predictions weighted by historical accuracy
```

Julia 不只是"解释一次"。她**记住自己判断的对错**，下次更好。

---

## 5. Deployment Architecture

```
┌─────────────────────┐     MCP Protocol     ┌─────────────────────┐
│    ai_theme_app     │ ◄──────────────────► │     Julia Core      │
│                     │                      │                     │
│  Port: 8010         │  DecisionEnvelope[]  │  Port: 8002         │
│  Health: /health    │  ThemeStatusSnapshot │  Health: /health    │
│                     │  MarketSnapshot      │                     │
│  Owns:              │                      │  Owns:              │
│  - PostgreSQL       │                      │  - Identity         │
│  - Redis Streams    │                      │  - Memory           │
│  - Market Data      │                      │  - Continuity       │
│  - Decision Engine  │                      │  - Persona          │
└─────────────────────┘                      └─────────────────────┘
```

- ai_theme_app 独立部署，独立扩缩
- Julia Core 独立部署，独立扩缩
- MCP Gateway 可选——Phase 2 可加 API Gateway

---

## 6. Phase Roadmap

### Phase 1 — Schema Freeze (current)
- Freeze DecisionEnvelope v1
- Freeze MCP Tool Contract
- Write contract tests
- **This document = Phase 1 deliverable**

### Phase 2 — MCP Server
- Implement `ai_theme_app/mcp_server.py`
- Expose 4 tools via MCP protocol
- Contract tests pass
- Julia can query: `query_theme_status("robot_001")`

### Phase 3 — Morning Brief Pipeline
- Julia Core scheduled wake @ 07:30
- Auto-call: `list_active_alerts(L4)` + `review_market_snapshot()`
- Context assembly + Persona filter → Morning Brief
- Output: voice or text

### Phase 4 — M7 Feedback Loop
- Julia records predictions → actual comparison → memory update
- Historical accuracy tracked per theme
- Future calls weight historical accuracy

---

## 7. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Julia starts trading | MCP tools are **read-only** by contract. No `execute_order`, no `modify_strategy`. Enforced at MCP server level. |
| Decision Schema drift | DecisionEnvelope v1 frozen. No new fields without ADR. |
| Julia becomes generic analyst | Tony Investment Profile loaded every session. Customized to one person. |
| Memory quality decay | M7 feedback loop re-ranks memory by prediction accuracy. Bad memories fade. |
| ai_theme_app down → Julia can't answer | Julia gracefully reports "暂时无法获取市场数据，请稍后再试" |

---

## 8. Approval Checklist

- [ ] DecisionEnvelope v1 schema approved
- [ ] 4 MCP tools scope approved
- [ ] Julia permissions: read-only confirmed
- [ ] Phase roadmap approved
- [ ] Tony Investment Profile fields approved
- [ ] Morning Brief timing (07:30) approved
- [ ] M7 Feedback Loop scope approved

---

*This document freezes the integration architecture. No code until reviewed and approved.*
