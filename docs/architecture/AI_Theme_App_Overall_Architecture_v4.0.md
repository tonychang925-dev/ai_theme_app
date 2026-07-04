# AI Theme App Overall Architecture v4.0

> 版本：v4.0
> 日期：2026-07-04
> 状态：Architecture Baseline v4.0 — FROZEN
> 核心原则：Stable Core + Adaptive Layer + Incremental Evolution
> 实施原则：Build Cognition without Breaking Report
> 冻结规则：不发布 v4.1；后续结构变化只通过 ADR 提案、回放、Shadow 和批准进入，满足总体升级条件后再发布 v5。
> 关联文档：
> - `docs/architecture/M8_Market_Cognition_Engine_架构设计文档.md`
> - `docs/architecture/盘后复盘模块彻底重构设计文档.md`
> - `docs/architecture/Notion_盘后复盘发布系统_设计文档.md`
> - `docs/architecture/个人投资助理-项目架构设计-第一阶段.md`
> - `docs/architecture/个人投资助理-项目架构设计-第二阶段（题材匹配重构版）.md`
> - `docs/architecture/个人投资助理-项目架构设计-第三阶段.md`

---

## 0. 架构决议

AI Theme App 停止继续横向增加 Engine，进入架构收敛与工程验证阶段。

本版本做五项裁决：

1. M1～M7 保持现有事实生产、领域计算、预测和风险职责。
2. M8 固定为只读认知编排层，不拥有业务真源。
3. M9 固定为适应性控制与学习层，不进入 Phase 0/1 正式决策。
4. Snapshot 与 State 分离，审计历史不可变，当前状态可重建。
5. 报告采用“Market Thesis 首页 + 原证据章节”，不替换旧复盘。

所有 PR、ADR、迁移与弃用决策必须引用第 26 章 Architecture Principles；架构健康度按第 27 章 Architecture KPI 度量；后续演进遵循第 28 章 ADR-only Policy。

从本版本开始，架构演进优先级为：

```text
实现
> 回放
> 真实交易日验证
> 校准
> 再设计
```

---

## 1. 总体系统图

```text
┌──────────────────────────────────────────────────────────────┐
│ M1 Data Acquisition                                         │
│ 行情 / 竞价 / 新闻 / 龙虎榜 / 资金 / 技术 / 外部市场        │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M2 Knowledge                                                 │
│ 题材主数据 / 股票实体 / 产业链 / 别名 / 映射 / Ontology      │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M3 Event                                                     │
│ 事件标准化 / 去重 / 题材匹配 / 驱动证据 / 时效               │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M4 Theme                                                     │
│ Identity / Cycle / Mainline / ThemeDecision / ThemeCapital   │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M5 Stock                                                     │
│ StrongStock / Role / Leader / WatchPool / W2S / OneToTwo     │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M6 Prediction                                                │
│ 预期 / 场景 / 候选走势 / 结果评估                            │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M7 Risk                                                      │
│ MarketRegime / NoTrade / Liquidity / Exposure / Invalidation │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
                  Existing Fact & Decision Plane
                               │
                    MarketKnowledgeBundle
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
┌────────────────────────────┐     ┌────────────────────────────┐
│ Existing Report Projection │     │ M8 Cognition Stable Core   │
│ DailyReviewV2 / Old Notion │     │ Evidence / Context /       │
│                            │     │ Cognition State / Thesis   │
└────────────────────────────┘     └──────────────┬─────────────┘
                                                  ▼
                                   ┌────────────────────────────┐
                                   │ M9 Adaptive Intelligence   │
                                   │ World Model / Goal /       │
                                   │ Attention / Strategy /     │
                                   │ Learning                   │
                                   └──────────────┬─────────────┘
                                                  ▼
┌──────────────────────────────────────────────────────────────┐
│ Consumers                                                    │
│ PostMarket / PreMarket / W2S / Monitor / Dashboard / Notion   │
└──────────────────────────────────────────────────────────────┘
```

说明：

- M1～M7 是逻辑能力编号，不在本版本强制重命名现有代码目录。
- 仓库内历史里程碑也使用 M1/M2 等编号，实施前通过 Capability Registry 消除歧义。
- 数据流不要求严格串行；图中箭头表达依赖方向和所有权，不代表所有模块都在同一 Job 内运行。

---

## 2. 两层架构：Stable Core 与 Adaptive Layer

### 2.1 Stable Core

Stable Core 定义任何市场认知系统都必须具备、且不应频繁变化的语义。

```text
Evidence
Context
Cognition State
Hypothesis
Market Thesis
```

为了控制对象数量，Reasoning 与 Belief 不再都扩张成大型独立子系统：

- Reasoning 是更新 Cognition State 的可审计过程；
- Belief 是 Cognition State 内的核心状态；
- Hypothesis 是 Cognition State 内的跨日验证单元；
- Market Thesis 是面向消费者的不可变输出。

Stable Core 的变化条件：

- 现有契约无法表达真实交易日出现的关键问题；
- 至少有多个交易日或多个消费者证明缺口；
- 有 ADR、迁移方案和回放证据；
- 不因单一新指标而新增核心对象。

### 2.2 Adaptive Layer

Adaptive Layer 负责市场、策略和系统自身的变化：

```text
World Model
Goal
Attention
Strategy
Diary
Self Reflection
Episodic Memory
Learning
```

这些能力可以独立升级、关闭或降级，不改变 Stable Core 契约。

### 2.3 分层依赖

```text
Adaptive Layer
  -> 提供 prior / budget / policy / strategy
  -> 不修改 Evidence 历史

Stable Core
  -> 产出可审计 cognition/thesis
  -> 不依赖所有 Adaptive 能力在线可用
```

### 2.4 Phase 0/1 的实现范围

只实现：

```text
EvidenceSnapshot
MarketContext
CognitionState
HypothesisState
MarketThesisSnapshot
```

延期：

```text
自动 World Model 学习
动态 Goal Manager
动态 Attention Engine
多策略 Portfolio
自动 Self Reflection
向量化 Episodic Recall
Counterfactual 高等级因果推断
```

---

## 3. Snapshot 与 State 的严格区分

### 3.1 Snapshot

Snapshot 是某个时点的不可变记录：

```text
Immutable
Versioned
Content-addressed
Replayable
Auditable
```

主要 Snapshot：

- `MarketEvidenceSnapshot`
- `MarketContextSnapshot`
- `CognitionCheckpointSnapshot`
- `MarketThesisSnapshot`
- `DecisionSnapshot`

### 3.2 State

State 是系统当前工作状态：

```text
Current
Updatable through commands/events
Rebuildable
Not the audit source
```

主要 State：

- `BeliefState`
- `HypothesisState`
- `GoalState`（Adaptive）
- `AttentionState`（Adaptive）
- `StrategyRuntimeState`（Adaptive）

### 3.3 更新规则

State 不能被任意原地修改：

```text
Immutable Snapshot / Event
-> State Transition Function
-> New Current State
-> Optional Checkpoint Snapshot
```

所有 State 更新必须记录：

- before；
- event/command；
- evidence references；
- transition policy；
- after；
- occurred_at/available_at；
- idempotency key。

### 3.4 恢复模型

```text
Last Checkpoint
+ Events after checkpoint
-> Current State
```

Current State 表可以覆盖更新，但必须可由不可变事件与 checkpoint 重建。

---

## 4. M8 Stable Core 最小契约

### 4.1 MarketEvidenceSnapshot

职责：表达 M1～M7 已计算完成的结构化事实和领域结果。

```python
class MarketEvidenceSnapshot:
    snapshot_id: str
    trade_date: date
    as_of: datetime
    schema_version: str

    market: MarketEvidence
    themes: tuple[ThemeEvidence, ...]
    stocks: tuple[StockEvidence, ...]
    capital: CapitalEvidence
    events: tuple[EventEvidence, ...]
    existing_decisions: ExistingDecisionEvidence

    source_snapshot_ids: tuple[str, ...]
    module_coverage: tuple[SourceCoverage, ...]
```

约束：

- 不计算炸板率、周期、资金净额等已有业务指标；
- 只通过 Adapter 映射；
- 每个判断性字段引用原 producer；
- 缺失不转换成默认结论。

### 4.2 MarketContext

Context 不是新的事实层，也不是长期 World Model。它是当前认知窗口中，对“为什么这些证据现在重要”的结构化背景。

```python
class MarketContext:
    context_id: str
    context_version: int
    schema_version: str
    context_type: str
    as_of: datetime
    horizon: str
    previous_context_id: str | None
    supersedes_context_id: str | None

    prior_market_state: str
    active_transitions: tuple[str, ...]
    dominant_tensions: tuple[str, ...]
    failed_prior_hypotheses: tuple[str, ...]
    active_external_anchors: tuple[str, ...]
    capital_rotation_background: tuple[str, ...]
    unresolved_conflicts: tuple[str, ...]

    evidence_refs: tuple[EvidenceRef, ...]
    prior_state_refs: tuple[str, ...]
    world_model_version: str | None
```

例：

```text
机器人修复假设失败
+ 科技高位风险偏好下降
+ PCB 机构容量资金增强
+ 海外科技指数提供外部锚
= PCB 接力的重要上下文
```

Context 必须由 Evidence 与 Prior State 推导，并可独立审计。

`context_type` 第一阶段固定为：

```text
PRE_MARKET
AUCTION
MORNING
MIDDAY
CLOSE
```

同一交易日、同一 `context_type` 的修正必须增加 `context_version`，不得覆盖旧版本。`previous_context_id` 表达时间序列前驱，`supersedes_context_id` 表达同一时点的版本替代。

### 4.3 CognitionState

```python
class CognitionState:
    state_id: str
    as_of: datetime
    context_id: str

    beliefs: Mapping[str, BeliefState]
    hypotheses: Mapping[str, HypothesisState]
    active_scenarios: tuple[ScenarioState, ...]

    last_event_id: str
    policy_versions: Mapping[str, str]
```

它是 M8 唯一聚合状态，不再为每个推理维度新增顶层 Snapshot 类型。

### 4.4 BeliefState

```python
class BeliefState:
    proposition_key: str
    score: float
    confidence: float
    previous_score: float
    support_refs: tuple[EvidenceRef, ...]
    counter_refs: tuple[EvidenceRef, ...]
    updated_at: datetime
```

### 4.5 HypothesisState

```python
class HypothesisState:
    hypothesis_id: str
    statement: str
    status: str
    probability: float
    deadline: datetime
    expected_observations: tuple[str, ...]
    falsifiers: tuple[str, ...]
    timeline_head_event_id: str
```

### 4.6 MarketThesisSnapshot

`Market Narrative` 对外更名为 `Market Thesis`。

Thesis 是结构化研究结论，不是自由故事：

```python
class MarketThesisSnapshot:
    thesis_id: str
    trade_date: date
    as_of: datetime

    primary_thesis: ThesisStatement
    alternative_thesis: ThesisStatement | None
    key_belief_changes: tuple[BeliefChange, ...]
    hypothesis_results: tuple[HypothesisResult, ...]
    scenarios: tuple[ScenarioView, ...]
    strategy_views: tuple[StrategyView, ...]
    invalidation_conditions: tuple[str, ...]

    evidence_refs: tuple[EvidenceRef, ...]
    cognition_state_id: str
    schema_version: str
```

LLM 只负责将 Thesis 翻译成人话，不决定 Thesis。

---

## 5. Market Context Builder

### 5.1 输入

```text
Current Evidence Snapshot
Prior Cognition State
Prior Hypothesis Results
Stable World constraints
Optional Dynamic World version
External anchors
```

### 5.2 输出维度

- 市场当前阶段；
- 与昨日相比的关键变化；
- 失败/确认的旧假设；
- 当前主要矛盾；
- 资金从哪里向哪里移动；
- 核心情绪载体变化；
- 外部市场锚；
- 尚未解决的冲突。

### 5.3 Context 不拥有事实

Context 的每条背景描述都必须引用：

- EvidenceRef；
- prior hypothesis；
- prior belief；
- stable/dynamic world rule。

### 5.4 Context 生命周期

```text
PreMarket Context
-> Auction Context
-> Morning Context
-> Midday Context
-> Close Context
```

每次变化生成新 Snapshot；Current Context Pointer 指向最新版本。

Context 回放顺序：

```text
trade_date
-> context_type order
-> context_version
-> available_at
```

---

## 6. 从 Pipeline 到 Agent Loop

### 6.1 最小闭环

```text
Broad Evidence Sensing
        │
        ▼
Evidence Snapshot
        │
        ▼
Context Update
        │
        ▼
Cognition State Update
  Belief + Hypothesis
        │
        ▼
Goal / Attention Re-evaluation
        │
        ├── 无需更多证据 ──> Thesis / Strategy / Decision
        │
        └── 信息不足
                │
                ▼
        Targeted Evidence Request
                │
                └──────────────> Evidence Sensing
```

### 6.2 Loop 终止条件

循环必须有边界：

- Goal 已满足；
- Hypothesis 被确认或拒绝；
- deadline 到达；
- information gain 低于阈值；
- 预算耗尽；
- 风险门禁要求立即停止；
- 市场阶段结束。

### 6.3 Broad Sensing 与 Targeted Request

`Targeted Evidence Request` 不能修改基础采集真源，只能：

- 请求已有数据的更深分析；
- 提升某对象的采样/计算优先级；
- 触发允许的补充数据源；
- 请求人工复核。

Broad Sensing 始终保留，避免 Goal/Attention 造成盲区。

### 6.4 Phase 0 简化

Phase 0 不实现动态 Goal/Attention，只使用固定问题模板：

```text
昨日核心假设是否成立？
今日最大 Belief 变化是什么？
主线是否发生切换？
全局风险是否改变交易权限？
明日哪些条件会确认或推翻 Thesis？
```

---

## 7. M9 Adaptive Layer

### 7.1 Stable World 与 Dynamic World

```text
World Model
  ├── Stable World
  │     制度、交易规则、指数定义、市场结构
  └── Dynamic World
        参与者偏好、风格、轮动机制、角色经验
```

Stable World 低频人工/制度更新；Dynamic World 通过 proposal、replay、shadow 和批准更新。

### 7.2 Goal

定义系统当前最重要的问题。Goal 必须包含：

- question；
- priority；
- deadline；
- required evidence；
- disconfirming evidence；
- stop condition。

### 7.3 Attention

分配推理资源，不过滤事实：

```text
60% current goals
20% risk reserve
15% exploration
5% human override
```

### 7.4 Strategy

Strategy 是 Execution Policy：

```text
Belief × Scenario × Strategy
-> StrategyProposal
-> Risk Gate
-> Portfolio Allocation
-> Decision
```

Phase 0/1 只显式化现有弱转强策略，不建设完整多策略平台。

### 7.5 Diary 与 Learning

Diary 记录当日认知变化和结果；Self Reflection 诊断系统为什么错；二者只产生更新提案，不直接修改 Stable Core 或 World Model。

### 7.6 Episodic Memory

完整 Episode 保存：

```text
Context
Evidence
Belief Timeline
Hypothesis Timeline
Strategy
Decision
Outcome
Reflection
```

Phase 0/1 只保留结构化历史数据，不实现自动向量召回。

---

## 8. 数据流、控制流、学习流

### 8.1 数据流

```text
M1～M7 Facts
-> MarketKnowledgeBundle
-> EvidenceSnapshot
-> ContextSnapshot
-> CognitionState
-> ThesisSnapshot
-> Consumer
```

单向、可追溯、无反向事实写入。

### 8.2 控制流

```text
Stable/Dynamic World
-> Goal
-> Attention
-> Cognition Update Policy
-> Strategy
-> Risk
-> Decision
```

### 8.3 学习流

```text
Outcome
-> Diary
-> Reflection
-> Episode
-> Update Proposal
-> Replay
-> Shadow
-> Approval
-> New Adaptive Version
```

### 8.4 不允许的捷径

- Narrative/Thesis 反向生成 Evidence；
- Diary 自动修改 World Model；
- Episode Recall 直接生成正式 Decision；
- Attention 关闭 Broad Sensing；
- Strategy 绕过 Risk；
- M8 直接查询业务数据库并重新计算事实。

---

## 9. 现有复盘的延续架构

### 9.1 当前主链保持

```text
Layer A/B/C/D
-> BuildPostMarketRecapJob
-> post_market_recap_snapshot
-> DailyReviewV2
-> Existing Notion Sections
```

### 9.2 新增旁路

```text
PostMarketRecapSnapshotBuilt
-> BuildMarketCognitionJob
-> EvidenceSnapshot
-> Context
-> CognitionState
-> ThesisSnapshot
```

M8 失败不改变原快照状态。

### 9.3 DailyReview 兼容

短期：

```text
DailyReviewV2 原字段保持
+ optional extensions.market_cognition_v1
```

长期只有在多消费者确有需求时才引入 V3。

### 9.4 Notion 双层报告

```text
Part A Market Thesis
  今日 Thesis
  昨日假设验证
  Belief 变化
  Scenario / Strategy / Invalidation

Part B Existing Evidence
  市场环境
  题材
  涨停
  资金
  龙虎榜
  标的与计划

Part C Appendix
  新高
  数据质量
  Evidence Trace
```

Thesis 引用证据章节，不替代证据章节。

---

## 10. Phase 0：Cognition Homepage

### 10.1 目标

用现有数据生成一个比当前报告更接近分析师认知结构的首页，同时保证原报告完全可用。

### 10.2 范围

Phase 0 铁律：

> 任何新增对象、服务、状态或策略，如果不能直接提升 Notion 认知首页质量，一律进入 Architecture Backlog，不得进入 Phase 0。

实现：

- MarketKnowledgeBundle；
- MarketEvidenceAdapter；
- MarketContext Builder；
- 固定模板 Belief/Hypothesis 更新；
- Market Thesis；
- Notion 双层报告；
- feature flag；
- replay。

不实现：

- 自动 World Model 学习；
- 动态 Goal/Attention；
- Counterfactual 因果推断；
- 多策略选择；
- Self Reflection 自动诊断；
- Episodic Retrieval。

### 10.3 Thesis 首页内容

最多六个区块：

1. 今日核心 Thesis；
2. 昨日假设结果；
3. 最大 Belief 变化；
4. 主线/情绪载体变化；
5. 明日 Scenario 与失效条件；
6. 交易权限与当前策略。

### 10.4 验收

- 原 DailyReviewV2 字段零破坏；
- 原 Notion 核心证据零减少；
- M8 失败可自动回退原报告；
- Thesis 所有命题都有 EvidenceRef；
- 正文无重复模块摘要；
- 7/2、7/3 及至少 5 个历史交易日通过人工评审；
- 分析师能在首页回答“昨日判断对错、今日变化、明日条件”。

---

## 11. Phase 1：Stateful Cognition

### 11.1 目标

把日终 Snapshot 扩展为可跨日更新的 Belief/Hypothesis State。

### 11.2 范围

- Cognition event；
- BeliefState；
- HypothesisState；
- checkpoint/rebuild；
- premarket/close 两个 Context；
- 连续交易日 replay；
- calibration。

盘中 Timeline、动态 Goal/Attention 后置。

### 11.3 验收

- State 可从 checkpoint + events 重建；
- 同一事件幂等；
- 乱序事件有明确策略；
- 无未来数据污染；
- 连续 20 个交易日运行；
- Belief 变化可解释；
- Hypothesis 有 deadline/falsifier；
- 不改变正式 Decision。

---

## 12. 真实交易日驱动的演进机制

### 12.1 每日问题清单

每个交易日只记录：

1. Thesis 是否准确表达市场？
2. 哪条 Evidence 缺失或映射错误？
3. 哪个 Belief 更新不合理？
4. 哪个 Hypothesis 不可证伪或失效过晚？
5. 报告是否重复、过长或缺少行动条件？

### 12.2 变更准入

新增 Engine 或顶层对象必须同时满足：

- 现有 Core Contract 无法表达；
- 至少 3 个真实样本重复出现；
- 不是字段、规则或 Adapter 可以解决；
- 有单独生命周期；
- 有独立消费者；
- 有回滚方案；
- ADR 通过。

### 12.3 Architecture Budget

Phase 0/1 预算：

```text
核心持久化契约 <= 5
核心 Job 新增 <= 1
核心 Consumer 改造 = Notion only
正式策略新增 = 0
自动学习模块新增 = 0
```

超过预算必须重新评审。

---

## 13. Capability Registry

正式实施前建立：

```text
capability_id
logical_module
domain_owner
code_owners
business_criticality
input_contract
output_contract
source_of_truth
consumers
runtime
status
review_policy
deprecation_status
```

字段说明：

| 字段 | 语义 |
|---|---|
| `domain_owner` | 业务语义最终责任模块/团队，例如 M5 |
| `code_owners` | 需要参与代码评审的人员或团队 |
| `business_criticality` | P0/P1/P2，表示错误对业务主链的影响 |
| `review_policy` | 变更所需评审类型与批准数量 |
| `deprecation_status` | ACTIVE/DEPRECATED/SHADOW/MIGRATING/RETIRED |

示例：

```yaml
capability_id: strong_stock
logical_module: StrongStock
domain_owner: M5
code_owners:
  - stock-domain
  - risk-reviewer
business_criticality: P0
review_policy:
  required_reviews: 2
  required_roles:
    - Domain Owner
    - QA/Risk
```

治理规则：

- 影响 P0 capability 的 PR 必须由 Domain Owner 与 QA/Risk 评审；
- 影响 P1 capability 的 PR 至少需要 Domain Owner 评审；
- Source of Truth、输入/输出契约或 Risk Gate 的变更自动提升为 P0 review；
- CI 根据 changed files -> capability mapping 检查评审要求；
- 无 Domain Owner 的 P0/P1 capability 不得进入生产变更。

第一版至少登记：

- Data Acquisition；
- Knowledge；
- Event；
- Theme Identity/Cycle/Mainline；
- StrongStock/W2S；
- Prediction；
- Risk；
- DailyReview；
- Notion；
- M8 Cognition；
- M9 Adaptive。

Registry 解决“M1/M2 是模块还是里程碑”的命名冲突，不要求立即重命名代码。

---

## 14. Feature Flags 与失败隔离

```text
M8_EVIDENCE_SHADOW_ENABLED
M8_CONTEXT_SHADOW_ENABLED
M8_COGNITION_STATE_ENABLED
M8_NOTION_RENDER_MODE
M8_DAILY_REVIEW_EXTENSION_ENABLED
```

Render Mode：

```text
legacy_only
cognition_shadow
dual_layer
cognition_primary
```

Phase 0 最高只进入 `dual_layer`。

失败隔离：

| 故障 | 行为 |
|---|---|
| MarketKnowledgeBundle 失败 | 保留原报告 |
| Evidence 失败 | 保留原报告，记录 diagnostics |
| Context 失败 | 不生成 Thesis |
| Cognition 失败 | 保留原报告 |
| Thesis 失败 | 不发布空认知首页 |
| Notion Part A 失败 | 回退 Part B |

---

## 15. 架构门禁

### 15.1 稳定性

- M1～M7 输出不得因 M8 接入发生语义变化；
- M8 Domain 无数据库 Gateway；
- M8 不回写现有真源；
- old report path 始终可用；
- shadow 期间不改变正式 Decision。

### 15.2 契约

- Evidence/Context/Thesis 使用版本化 schema；
- State 更新事件化；
- 所有命题有 EvidenceRef；
- optional extension 向后兼容；
- Snapshot content hash 稳定。

### 15.3 内容

- Thesis 首页不超过六个区块；
- 核心题材不超过五个；
- 同一结论只出现一次；
- 数据事实位于证据层；
- 缺失信息显示无法判定。

### 15.4 学习

- Phase 0/1 不自动更新 World Model；
- Diary 不进入在线决策；
- Episode Outcome 不进入当前检索输入；
- 所有 Adaptive 更新必须 proposal + replay + approval。

---

## 16. 风险矩阵

| 等级 | 风险 | 缓解 |
|---|---|---|
| P0 | 架构对象继续膨胀 | Core <= 5 + Architecture Budget |
| P0 | M8 形成第二套事实计算 | Adapter only + no DB guard |
| P0 | State 原地修改无法审计 | event + checkpoint + rebuild |
| P0 | Context 变成无证据故事 | Context 每项强制 EvidenceRef |
| P0 | M8 阻断旧报告 | 独立 Job + legacy fallback |
| P1 | Stable/Adaptive 边界漂移 | Capability Registry + ADR |
| P1 | Agent Loop 无限循环 | deadline/budget/information gain |
| P1 | Thesis 替代证据 | 双层报告 |
| P1 | 过早实现 M9 | Phase 0/1 Deferred List |
| P2 | 双轨维护长期存在 | 按消费者灰度，不删除 Evidence |

---

## 17. 决策记录

1. Overall-ADR-001：M8 Core Contract 冻结为 Evidence、Context、Cognition State、Hypothesis、Thesis。
2. Overall-ADR-002：Reasoning 是过程，Belief/Hypothesis 合并在 CognitionState 生命周期内。
3. Overall-ADR-003：Snapshot 不可变，State 可更新但必须可重建。
4. Overall-ADR-004：Market Narrative 对外更名为 Market Thesis。
5. Overall-ADR-005：M9 全部能力归入 Adaptive Layer。
6. Overall-ADR-006：M8 采用 Agent Loop，但 Phase 0 使用固定问题模板。
7. Overall-ADR-007：Phase 0/1 禁止自动 World Model 更新。
8. Overall-ADR-008：M8 通过旁路 Job 接入，不扩张现有 recap Job。
9. Overall-ADR-009：Notion 采用 Thesis + Evidence 双层结构。
10. Overall-ADR-010：新增顶层对象必须满足真实样本与 Architecture Budget 门禁。

---

## 18. 下一步执行顺序

### Step 1：冻结与基线

- 冻结 M8 v1.3；
- 建立 Capability Registry；
- 固化 7/2、7/3 和历史样本；
- 保存当前 DailyReviewV2/Notion baseline。

### Step 2：Phase 0 Contract

- MarketKnowledgeBundle；
- EvidenceSnapshot；
- Context；
- CognitionState 最小结构；
- ThesisSnapshot；
- contract tests。

### Step 3：Shadow

- 只读历史 snapshot；
- 不改正式 Decision；
- 不发布 Part A；
- 输出 cognition preview。

### Step 4：Dual Layer

- Notion 增加 Thesis 首页；
- 原证据章节保留；
- 按日期灰度；
- 人工评审。

### Step 5：20 日验证

- 记录真实问题；
- 只修复重复出现的问题；
- 不新增 Adaptive Engine；
- 满足门禁后再进入 Phase 1。

---

## 19. 最终结论

AI Theme App 的下一阶段不是继续增加认知对象，而是证明最小认知闭环能够稳定运行。

稳定核心是：

```text
Evidence Snapshot
-> Market Context
-> Cognition State
-> Hypothesis
-> Market Thesis Snapshot
```

适应层是：

```text
World Model
Goal
Attention
Strategy
Diary
Reflection
Episodic Memory
Learning
```

前者现在实现，后者按真实问题逐步启用。

最终工程目标保持不变：

```text
Build Cognition without Breaking Report
```

先让“认知首页 + 原证据章节”在真实交易日中证明价值，再决定 M9 中哪些能力值得进入生产。到此为止，架构设计冻结，工作重心转向 Phase 0/1 实施、回放和校准。

---

## 20. MarketKnowledgeBundle 命名与边界

### 20.1 命名裁决

原候选名称 `PostMarketFactBundle` 正式废弃，统一使用：

```text
MarketKnowledgeBundle
```

原因：

- 行情价格、成交额属于 Fact；
- ThemeCycle、Mainline、StrongStock、MarketRegime 已经是领域 Knowledge；
- Bundle 同时包含事实和现有领域模块的确定性/规则性结论；
- 使用 Fact 命名会错误暗示所有字段都是原始观测。

### 20.2 数据链

```text
M1～M7 Facts & Domain Knowledge
        │
        ▼
MarketKnowledgeBundle
        ├── Existing DailyReviewV2 Projection
        └── MarketEvidenceAdapter
                │
                ▼
        MarketEvidenceSnapshot
```

### 20.3 契约

```python
class MarketKnowledgeBundle:
    bundle_id: str
    schema_version: str
    trade_date: date
    as_of: datetime

    facts: MarketFactKnowledge
    theme_knowledge: ThemeKnowledge
    stock_knowledge: StockKnowledge
    decision_knowledge: ExistingDecisionKnowledge
    risk_knowledge: RiskKnowledge

    source_snapshot_ids: tuple[str, ...]
    producer_versions: Mapping[str, str]
    module_coverage: Mapping[str, SourceCoverage]
    quality: QualityEnvelope
```

### 20.4 边界

`MarketKnowledgeBundleBuilder` 允许：

- 组装已有模块输出；
- 保留 producer 类型；
- 校验版本、时点、单位和实体；
- 记录 lineage；
- 计算 bundle content hash。

不允许：

- 重新计算 ThemeCycle；
- 重判 Mainline；
- 重算 StrongStock；
- 生成新交易结论；
- 将 LLM 文本升级为事实；
- 从旧报告文本反解析核心 Knowledge。

---

## 21. 全系统数据生命周期

### 21.1 生命周期总图

```text
┌───────────────┐
│ Raw Data      │  行情、新闻、资金、龙虎榜、竞价、外部市场
└───────┬───────┘
        ▼
┌───────────────┐
│ Knowledge     │  Identity、Cycle、Mainline、StrongStock、Risk
│ M1～M7        │
└───────┬───────┘
        ▼
┌───────────────────────┐
│ MarketKnowledgeBundle │  现有能力的版本化汇聚边界
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Evidence Snapshot     │  M8 可消费、不可变、可追溯
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Context Snapshot      │  PRE/AUCTION/MORNING/MIDDAY/CLOSE
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Cognition State       │  Belief / Hypothesis / Scenario
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Market Thesis         │  结构化认知结论
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Strategy / Decision   │  M7/M9 策略、风险、组合裁决
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Market Diary          │  当日认知变化与结果
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Episode               │  完整市场经历
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│ Archive               │  长期审计、回放、学习
└───────────────────────┘
```

### 21.2 生命周期属性

| 阶段 | 可变性 | 保留策略 | 真源 |
|---|---|---|---|
| Raw Data | append/correction | 按数据源策略 | M1 |
| Knowledge | versioned | 业务审计周期 | M2～M7 |
| Bundle | immutable | 与 recap 同周期 | Knowledge producers |
| Evidence Snapshot | immutable | 长期回放 | M8 Adapter |
| Context Snapshot | immutable/version chain | 长期回放 | Context Builder |
| Cognition State | mutable projection | checkpoint + events | M8 |
| Thesis | immutable | 报告审计周期 | M8 |
| Decision | immutable | 长期审计 | M7/Strategy |
| Diary | versioned | 长期学习 | M9 |
| Episode | immutable/versioned | 长期记忆 | M9 |
| Archive | immutable | 合规/成本策略 | Archive service |

### 21.3 归档不等于删除

Archive 后：

- current API 默认不加载；
- replay 可按 ID 恢复；
- lineage 不断裂；
- schema reader 保留；
- 删除必须遵循 Deprecation Policy 和数据保留政策。

---

## 22. 统一 Quality Envelope

### 22.1 设计目标

不为每层新增独立大型 Quality 对象，而使用一个可组合的通用契约：

```python
class QualityEnvelope:
    quality_score: float
    status: str
    completeness: float
    freshness: float
    consistency: float
    lineage_coverage: float
    uncertainty: float

    blocking_issues: tuple[QualityIssue, ...]
    warnings: tuple[QualityIssue, ...]
    source_quality_refs: tuple[str, ...]
    evaluated_at: datetime
    policy_version: str
```

`status`：

```text
READY
PARTIAL
DEGRADED
BLOCKED
STALE
```

### 22.2 各层 Quality

| 层 | 重点质量维度 |
|---|---|
| Knowledge Quality | producer readiness、schema、业务门禁 |
| Evidence Quality | completeness、freshness、lineage、entity match |
| Context Quality | evidence coverage、prior-state availability、conflict |
| Cognition Quality | belief calibration、hypothesis testability、state consistency |
| Thesis Quality | citation coverage、unsupported claim、conflict disclosure |
| Decision Quality | strategy/risk references、validity、executable conditions |

### 22.3 质量传播

下游质量不能高于关键上游质量：

```text
Evidence quality
  -> caps Context quality
  -> caps Cognition confidence
  -> caps Thesis confidence
  -> may block Decision
```

建议初始规则：

```text
context_quality
  <= min(required_evidence_quality, prior_state_quality)

belief_confidence
  <= context_quality

thesis_confidence
  <= min(context_quality, cognition_quality)
```

### 22.4 缺失数据示例

如果龙虎榜缺失：

```text
Evidence:
  dragon_tiger = unavailable
  status = PARTIAL

Context:
  capital_validation incomplete

Belief:
  不使用“机构与游资共振”作为支持证据
  confidence cap 下调

Thesis:
  明确“资金席位验证不足”
  禁止输出确定性共振结论
```

### 22.5 Block 与 Degrade

| 缺失 | 行为 |
|---|---|
| 核心行情缺失 | BLOCK cognition |
| 交易日历/时点错误 | BLOCK |
| 题材周期 partial | DEGRADE theme belief |
| 龙虎榜正常无数据 | 不降市场质量，标记 no-event |
| 龙虎榜采集失败 | DEGRADE capital thesis |
| 历史 CognitionState 缺失 | 允许 cold start，降低跨日 confidence |

### 22.6 Notion 展示

首页只展示影响结论的质量问题：

```text
Thesis Confidence: 62%
限制：龙虎榜采集失败，资金共振无法确认
```

内部完整 diagnostics 放在数据质量附录。

---

## 23. Deprecation Policy

### 23.1 生命周期

```text
ACTIVE
  -> DEPRECATED
  -> SHADOW
  -> MIGRATING
  -> RETIRED
  -> DELETED
```

不允许从 `ACTIVE` 直接进入 `DELETED`。

### 23.2 状态语义

| 状态 | 语义 |
|---|---|
| ACTIVE | 正式生产路径 |
| DEPRECATED | 宣布替代方案，不再新增消费者 |
| SHADOW | 新旧并行对账 |
| MIGRATING | 消费者分批迁移 |
| RETIRED | 无正式消费者，但保留读能力和回滚 |
| DELETED | 代码/表/配置完成删除 |

### 23.3 进入下一状态的门禁

DEPRECATED：

- ADR 说明原因和替代方案；
- Capability Registry 标记；
- 文档与代码 warning；
- 禁止新增消费者。

SHADOW：

- 新实现已存在；
- 新旧输出有 diff；
- 失败不影响旧路径。

MIGRATING：

- shadow 指标达标；
- 消费者清单完整；
- 每个消费者有 feature flag。

RETIRED：

- 正式消费者为 0；
- 至少完成一次回滚演练；
- 历史 reader 与 migration 保留；
- 监控证明无隐式读取。

DELETED：

- RETIRED 观察窗口完成；
- 数据保留策略通过；
- rollback window 关闭；
- CI/文档/Registry/告警同步清理；
- 删除 PR 完成 P0/P1 review。

### 23.4 建议观察窗口

| Criticality | RETIRED 前 shadow | DELETED 前观察 |
|---|---:|---:|
| P0 | ≥20 个真实交易日 | ≥20 个真实交易日 |
| P1 | ≥10 个真实交易日 | ≥10 个真实交易日 |
| P2 | ≥5 个真实交易日 | ≥5 个真实交易日 |

### 23.5 数据库对象

表或字段弃用额外要求：

- 先停止写入，再停止读取；
- 保留兼容 view；
- 记录最后读写时间；
- migration 可重放；
- 不使用破坏性 migration 作为第一步。

---

## 24. Architecture Baseline Freeze

### 24.1 冻结窗口

v4.0 设为 Architecture Baseline。

从 Phase 0 首个真实交易日开始，连续 20 个真实交易日内：

- 不接受新的顶层 Engine；
- 不接受新的顶层 Stable Core 对象；
- 不启动延期的 M9 能力；
- 不扩大 Phase 0 Consumer；
- 只允许 P0/P1 缺陷修复、契约澄清和质量门禁修复。

### 24.2 Architecture Backlog

所有新想法进入：

```text
idea_id
problem_statement
real_trade_date_evidence
affected_core_contract
frequency
severity
current_workaround
proposed_change
decision_status
```

状态：

```text
CAPTURED
NEEDS_EVIDENCE
REPEATED
REVIEW_CANDIDATE
ACCEPTED
REJECTED
DEFERRED
```

### 24.3 解冻条件

只有满足以下条件才召开下一轮架构评审：

1. 完成至少 20 个真实交易日；
2. Stable Core 无法表达的问题重复出现；
3. 问题不是 Adapter、字段、规则或质量策略可以解决；
4. 有 replay 样本和失败证据；
5. 变更收益高于迁移成本；
6. Architecture Budget 明确；
7. 有 ADR 与回滚方案。

### 24.4 Phase 0 Scope Gate

每个 Phase 0 PR 必须回答：

```text
它直接改善 Notion 认知首页的哪个区块？
它解决哪个已登记真实样本问题？
如果延期，Phase 0 是否仍可完成？
它是否引入新的顶层对象或运行依赖？
```

若无法明确回答第一题，任务自动转入 Architecture Backlog。

### 24.5 Baseline 变更级别

| 变更 | 是否允许 |
|---|---|
| 修复 Evidence 映射错误 | 允许 |
| 修复 Quality 传播错误 | 允许 |
| 调整 Thesis 文案模板 | 允许，需内容回归 |
| 增加新的核心对象 | 禁止 |
| 实现 Goal/Attention | 禁止 |
| 新增正式 Strategy | 禁止 |
| 自动 World Model 学习 | 禁止 |
| 引入 Episodic Retrieval | 禁止 |

---

## 25. v4.0 基线补充 ADR

1. Overall-ADR-011：`PostMarketFactBundle` 更名为 `MarketKnowledgeBundle`。
2. Overall-ADR-012：Capability Registry 强制包含 Domain Owner 与 Business Criticality。
3. Overall-ADR-013：P0 capability 变更必须完成 Domain Owner 与 QA/Risk Review。
4. Overall-ADR-014：MarketContext 使用 type + version + previous/supersedes 版本链。
5. Overall-ADR-015：所有核心层共享 QualityEnvelope，并向下游传播置信上限。
6. Overall-ADR-016：任何能力弃用必须经过 Deprecated/Shadow/Migrating/Retired/Delete。
7. Overall-ADR-017：v4.0 后冻结 20 个真实交易日的顶层架构变更。
8. Overall-ADR-018：不直接提升 Notion 首页质量的对象不得进入 Phase 0。

---

## 26. Architecture Principles

本章是 AI Theme App 的架构宪章。所有 PR、ADR、Phase Contract、迁移和弃用方案必须引用适用的 Principle ID，并说明符合性。

### ARCH-P01：Single Source of Truth

> 同一个业务事实或领域结论只能有一个权威 Producer。

规则：

- 每个事实、Knowledge 和 Decision 字段必须在 Capability Registry 中登记唯一 `source_of_truth`；
- Consumer 不得重新计算 Producer 已拥有的语义；
- 多来源数据必须先在拥有该语义的 Producer 内完成裁决；
- Cache、Projection、Snapshot 和 Report 不是新真源；
- M8/M9 不得反向成为 M1～M7 的事实真源。

违反示例：

- Notion Renderer 自行计算涨停数量；
- M8 根据文本重新判断 ThemeCycle；
- DailyReviewV2 与 ThemeCycle 表分别维护不同周期结论。

门禁：

```text
duplicate_producer_count = 0
unregistered_source_of_truth_count = 0
```

### ARCH-P02：Adapter over Rewrite

> 接入旧能力时优先增加 Adapter，不重写已经验证的业务逻辑。

规则：

- M8 通过 `MarketKnowledgeBundle -> EvidenceAdapter` 接入现有模块；
- Adapter 只做映射、校验、单位统一、版本兼容和 lineage；
- 若现有模块输出不足，先扩展原 Producer 契约；
- 只有原模块无法满足职责、且有真实缺陷证据时，才允许提出 Rewrite ADR；
- Rewrite 必须保留 shadow、迁移和回滚路径。

门禁：

```text
rewrite_without_adr_count = 0
adapter_contract_coverage >= phase target
```

### ARCH-P03：Evidence before Conclusion

> 任何 Thesis、Belief、Hypothesis、StrategyProposal 和 Decision 必须先有可追溯 Evidence。

规则：

- 每个核心命题至少引用一个有效 `EvidenceRef`；
- 反对证据必须与支持证据同等可见；
- 缺失关键 Evidence 时输出“无法判定”或降级；
- LLM 文本不能作为原始事实证据；
- Context 和 Thesis 不得包含无法追溯的数字、实体和因果陈述。

门禁：

```text
thesis_evidence_coverage = 100%
unsupported_claim_count = 0
orphan_evidence_ref_count = 0
```

### ARCH-P04：Stable Core First

> Stable Core 的稳定性优先于 Adaptive Layer 的能力扩展。

规则：

- Stable Core 固定为 Evidence、Context、CognitionState、Hypothesis、Thesis；
- Adaptive 能力通过接口提供 prior、policy、budget 或 proposal；
- Adaptive Layer 不得修改历史 Snapshot；
- Adaptive 不可用时，Stable Core 必须可降级运行；
- Phase 0/1 不实现延期的 M9 能力。

门禁：

```text
stable_core_object_count <= 5
adaptive_to_core_reverse_write_count = 0
```

### ARCH-P05：Shadow before Replace

> 任何替换、迁移和策略切换必须先并行 Shadow，再迁移消费者。

规则：

- 新旧输出必须在同一输入、同一交易日下对账；
- Shadow 期间新路径不得影响正式 Decision；
- 差异必须分类为 expected/unexpected；
- 每个 Consumer 独立开关、独立迁移、独立回滚；
- P0 能力满足最少真实交易日窗口后才能进入 MIGRATING。

门禁：

```text
replacement_without_shadow_count = 0
unexplained_p0_shadow_diff_count = 0
rollback_path_coverage = 100%
```

### ARCH-P06：Human Explainable

> 系统必须能说明它相信什么、为什么相信、什么会使它改变判断。

规则：

- Belief 展示 prior、posterior、delta、支持与反对证据；
- Hypothesis 有 expected observations、falsifiers 和 deadline；
- Thesis 有主命题、替代命题和失效条件；
- Strategy/Decision 引用 policy version 与 arbitration trace；
- 不以“模型判断”作为最终解释。

门禁：

```text
belief_explanation_coverage = 100%
hypothesis_falsifier_coverage = 100%
decision_trace_coverage = 100%
```

### ARCH-P07：Quality governs Confidence

> Confidence 由数据与推理质量约束，不由语言模型语气决定。

规则：

- Knowledge、Evidence、Context、Cognition、Thesis 共用 `QualityEnvelope`；
- 下游 confidence 不得超过关键上游质量上限；
- 数据缺失、过期、冲突和 lineage 缺口必须降低质量；
- LLM confidence 不能覆盖结构化 Quality；
- BLOCKED 质量不得输出可执行 Decision。

门禁：

```text
quality_propagation_compliance = 100%
llm_confidence_override_count = 0
blocked_quality_decision_count = 0
```

### ARCH-P08：Incremental Evolution

> Never Rewrite. Always Evolve.

规则：

- 新能力先进入 Architecture Backlog；
- 优先字段、规则、Adapter 和 Projection，再考虑新对象；
- 所有迁移遵循 feature flag、shadow、migration、deprecation；
- 基线冻结期不新增顶层概念；
- 结构变化只通过 ADR，不发布 v4.1；
- 只有满足 v5 触发条件才重写总体基线。

门禁：

```text
top_level_change_without_adr_count = 0
baseline_change_during_freeze_count = 0
```

### 26.1 Principle 冲突裁决

优先级：

```text
数据正确性与风险
> Single Source of Truth
> Evidence before Conclusion
> Stable Core First
> Shadow before Replace
> Human Explainable
> Adapter over Rewrite
> Incremental Evolution
```

例如：如果 Adapter 会延续已确认的 P0 错误，可以提出 Rewrite，但必须通过 ADR、Shadow 和回滚，不能以 ARCH-P02 为由保留错误。

### 26.2 PR Architecture Checklist

每个影响架构边界的 PR 必须回答：

```text
适用哪些 Principle ID？
是否新增或改变 Source of Truth？
是否可以使用 Adapter 而不是 Rewrite？
新增结论是否都有 EvidenceRef？
是否污染 Stable Core？
是否完成 Shadow 与回滚设计？
Confidence 是否受 Quality 约束？
是否违反 Baseline Freeze 或 Architecture Budget？
```

P0/P1 capability 的检查结果写入 PR evidence。

---

## 27. Architecture KPI

### 27.1 目标

Architecture KPI 用于衡量边界、复杂度、迁移和可解释性，不用于替代业务结果指标。

所有 KPI 必须：

- 有明确定义；
- 有自动化数据源；
- 有 Owner；
- 有统计周期；
- 有阈值和超限动作；
- 避免通过隐藏问题来优化数字。

### 27.2 核心 KPI

| KPI | 定义 | 目标/门槛 | 数据源 | 周期 | Owner |
|---|---|---:|---|---|---|
| Stable Core Object Count | Stable Core 顶层持久化对象数 | `<=5` | Schema Registry | 每月 | Chief Architect |
| Duplicate Producer Count | 同一语义登记多个正式 Producer 的数量 | `0` | Capability Registry | 每次 PR/每月 | Architecture |
| Unowned P0/P1 Capability | 无 Domain Owner 的高关键能力数 | `0` | Capability Registry | 每周 | Engineering Lead |
| Adapter Coverage | 已接入 M8 的目标 Knowledge Producer 中具备正式 Adapter 的比例 | Phase 0 `100%` | Adapter Registry | 每次发布 | M8 Owner |
| Evidence Lineage Coverage | EvidenceRef 可回溯至 Producer/Source 的比例 | `100%` | Evidence audit | 每日 | Data/QA |
| Thesis Evidence Coverage | Thesis 核心命题具备有效 EvidenceRef 的比例 | `100%` | Thesis validator | 每日 | M8/QA |
| Quality Propagation Compliance | 下游 confidence 未突破上游质量上限的比例 | `100%` | Quality audit | 每日 | Risk/QA |
| Replay Success Rate | 固定样本与滚动交易日回放成功率 | Gold `100%`；Rolling `>=98%` | Replay runner | 每日/每周 | QA |
| Unexplained Shadow Diff | 无预期说明的新旧 P0/P1 差异 | P0 `0` | Shadow diff | 每日 | Domain Owner |
| Rollback Drill Success | 规定时间内成功回到旧路径的比例 | `100%` | Release audit | 每月 | Release |
| Deprecated Capability Count | 当前 DEPRECATED 能力数量 | 观察趋势 | Registry | 每月 | Architecture |
| Retired Aging | RETIRED 超过观察窗口仍未处理的数量 | `0` | Registry | 每月 | Code Owner |
| Shadow Aging | 超过计划窗口仍停留 SHADOW 的能力数量 | `0` 或有豁免 | Registry | 每周 | Migration Owner |
| Baseline Change Count | 冻结窗口内顶层基线变更数 | `0` | ADR/Doc audit | 每周 | Chief Architect |
| Phase 0 Scope Leakage | 不直接改善 Notion 首页但进入 Phase 0 的任务数 | `0` | Task/PR mapping | 每周 | PM/Architect |

### 27.3 质量与内容 KPI

| KPI | 目标 |
|---|---:|
| Unsupported Thesis Claim | `0` |
| Belief Explanation Coverage | `100%` |
| Hypothesis Falsifier Coverage | `100%` |
| Internal Status Code in Notion | `0` |
| Duplicate Conclusion Blocks | `0` |
| Cognition Homepage Sections | `<=6` |
| Core Themes in Homepage | `<=5` |
| Legacy Evidence Regression | `0` |

### 27.4 KPI 状态

```text
GREEN:
  达标

AMBER:
  单周期超限，已有 Owner 和整改期限

RED:
  连续超限、P0 门禁失败或无 Owner
```

RED 状态处理：

- 停止扩大灰度；
- 不新增 Phase 0 scope；
- 创建 P0/P1 修复任务；
- 必要时切回 `legacy_only`；
- 在 Architecture Review 中记录。

### 27.5 Architecture Dashboard

建议生成：

```text
tmp/architecture_kpi_daily.json
tmp/architecture_kpi_monthly.json
docs/project_control/reports/architecture-kpi-YYYY-MM.md
```

Dashboard 最少包含：

- 当前值；
- 目标；
- 7/20 日趋势；
- Owner；
- 超限原因；
- 修复任务；
- 数据生成时间。

### 27.6 防止 KPI 游戏化

- Deprecated Count 高不代表坏，关键是是否有迁移 Owner 和期限；
- Adapter Count 高不代表好，重复/无消费者 Adapter 应清理；
- Replay Rate 不得通过删除失败样本提高；
- Quality Score 不得通过降低 required sources 提高；
- Core Object Count 不得通过把多个无关对象塞入 untyped dict 降低。

---

## 28. ADR-only Architecture Evolution Policy

### 28.1 基线文档政策

`AI_Theme_App_Overall_Architecture_v4.0.md` 自冻结日起：

允许直接修改：

- 拼写和链接勘误；
- 不改变语义的排版；
- KPI 实际值与报告链接；
- 已接受 ADR 的索引；
- 安全或 P0 事故要求的紧急说明。

禁止直接修改：

- 顶层模块；
- Stable Core 对象；
- Source of Truth；
- 数据流/控制流/学习流方向；
- Phase 0 scope；
- Architecture Principles；
- M1～M9 所有权。

上述结构变化必须先有 Accepted ADR。

### 28.2 ADR 必需内容

```text
ADR ID
Title
Status
Context
Problem
Affected Principles
Affected Capabilities / Owners / Criticality
Evidence from Real Trading Days
Decision
Alternatives
Compatibility
Migration
Shadow Plan
Replay Evidence
Quality Impact
Rollback
Deprecation Impact
Consequences
Approval
```

### 28.3 ADR 状态

```text
PROPOSED
-> REVIEWING
-> ACCEPTED
-> IMPLEMENTING
-> VERIFIED

PROPOSED/REVIEWING
-> REJECTED

ACCEPTED/VERIFIED
-> SUPERSEDED
```

只有 `ACCEPTED` ADR 可以进入实现；只有 `VERIFIED` ADR 可以作为下一个 Baseline 的已完成依据。

### 28.4 ADR 编号

建议：

```text
ADR-ARCH-###
ADR-DATA-###
ADR-M8-###
ADR-M9-###
ADR-STRATEGY-###
ADR-DEPRECATION-###
```

编号稳定，不因文档移动而变化。

### 28.5 不发布 v4.1

v4 冻结期间：

- 不发布 v4.1/v4.2；
- 小变化通过 ADR 叠加；
- Implementation Detail 进入专项设计文档；
- 每月只发布 KPI/ADR/验证报告；
- 基线正文保持稳定。

### 28.6 v5 触发条件

满足任一结构条件并通过 Architecture Review，才考虑 v5：

1. M1～M9 所有权发生重大调整；
2. Stable Core 需要新增、删除或合并顶层对象；
3. 数据流、控制流或学习流发生方向性改变；
4. 累积多个 VERIFIED 结构 ADR，旧基线已难以准确表达现状；
5. 20 个真实交易日证明 v4 Core 无法表达关键认知；
6. 主要消费者完成 M8/M9 迁移，需要重画总体架构；
7. 法规、市场制度或基础设施发生重大变化。

建议同时满足：

- 至少 20 个真实交易日证据；
- 相关 ADR 已 VERIFIED；
- 无开放 P0 架构缺陷；
- 有迁移和回滚预算；
- v5 草案经过 Domain Owner 联合评审。

---

## 29. Architecture Baseline v4.0 正式冻结声明

自本声明起：

```text
不新增顶层概念
不新增认知 Engine
不扩展 World Model
不提前实现 M9
不发布 v4.1
```

项目资源集中于：

```text
Phase 0 Contract
-> Evidence Shadow
-> Cognition Shadow
-> Notion Dual Layer
-> Phase 1 Stateful Cognition
-> 20 个真实交易日验证
```

下一阶段最高目标不是证明架构完整，而是证明：

> 这套最小认知体系能否在连续真实市场中，稳定地产生比当前复盘更清晰、更可解释、更有行动价值的 Market Thesis。

架构团队在冻结窗口内只接受：

- P0/P1 缺陷；
- Evidence/Quality/Replay 问题；
- 兼容与回滚问题；
- 已有 Principle 的执行偏差；
- Architecture KPI 超限整改。

其他想法全部进入 Architecture Backlog，等待真实交易数据决定其优先级。
