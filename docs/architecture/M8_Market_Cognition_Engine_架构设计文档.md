# M8 Market Cognition Engine 架构设计文档

> 版本：v2.1 (v1.5 Core Contract Frozen + M2.5 MarketMetrics + Phase 4.2 Alignment + Phase 4.5 Workbench)
> 日期：2026-07-10 (v1.3: 07-04 / v1.4: 07-06 / v1.5: 07-06 / v2.0: 07-09 / v2.1: 07-10)
> 最新状态日期：2026-07-10
> 状态：**Core Contract Frozen**；**M2.5 MarketMetrics 已上线**；**Phase 4.2 对齐引擎已交付**；**Phase 4.5 工作台审查工作流已交付**
> 体系命名：M8 = Market World State Builder / M9 = Market World Intelligence Loop
> 实施基线：`tmp/plan/wbs_M8.phase1.5.md`（Phase 1.5 — Market World State Verification）
>
> **v1.4 变更**：New 7A-7G (Multi-Horizon Context, Cognition Graph, Theme/Trading Cognitive Card, Cycle Node Recognition, Divergence Quality, Node Transition Hypothesis)；New ADR M8-010, M8-011
> **v1.5 变更**：New 7C.6 (Dynamic Causal Chain)；New 7H (Historical Case Projection)；New 7I (Expectation Projection)；New 7J (Node Maturity Estimation)；New 7K (最终认知投影总链路)；New 7L (M9 Bridge — 6 个预留接口)；New 7M (从 Market Cognition 到 Market World Model)；New 7N (Phase 1.5 执行路线)；New ADR M8-012~M8-015, M9-BRIDGE-001~007
> **v1.5 Architecture Budget**：Stable Core 冻结 9 个核心对象（MarketSubject / MarketWorldModel / DailyMarketState / CognitionPipeline / CycleNode / DivergenceQuality / NodeMaturity / PolicyRegistry / FrozenHypothesisSource）；未来能力以 Adaptive Layer 消费者接入，不侵入 Stable Core
> **v2.1 变更**：Phase 4.2 对齐引擎（AnalystReferenceStore → AIAdapter → Comparator → TuringScore → Replay CLI → Dashboard）+ Phase 4.5 工作台审查工作流（Session状态机 + AI Draft + 审批API）
>
> 系统定位：AI Theme App 的市场世界模型——可推理、可验证、可演化
> 长期演进：M9 Market Intelligence System（Belief / Goal / Attention / Mental Simulation / Reflection / World Model Update）
> 分析师样本：[2026-07-02](https://bloom-rayon-9e1.notion.site/2026-07-02-3897bab0ee1d807fbe3ae9bacd4d2e20) / [2026-07-03](https://bloom-rayon-9e1.notion.site/2026-07-03-3937bab0ee1d81ca97b2df2898732f5b)
> 关联文档：
> - `docs/architecture/盘后复盘模块彻底重构设计文档.md`
> - `docs/architecture/Notion_盘后复盘发布系统_设计文档.md`
> - `docs/architecture/mainline_discovery_architecture_design.md`
> - `docs/architecture/weak_to_strong_strategy_design.md`
> - `docs/project_control/PRD.md`
> - `docs/project_control/ACCEPTANCE.md`
> - `docs/adrs/ADR_LIST.md`（ADR-M8-001~015, ADR-M9-BRIDGE-001~007）
> - `docs/project_control/reports/phase-M8.phase1-pilot-20260704.md`
> - `docs/project_control/wbs_M8.phase1.5.md`（Phase 1.5 实施基线）

> **首要架构原则**：M8 不是对现有盘后复盘系统的重写（Rewrite），而是建立在 Layer A/B/C/D、PostMarketDecisionV2 与 DailyReviewV2 之上的只读认知编排层（Cognitive Orchestration Layer）。
> **工程目标**：Build Cognition without Breaking Report。
> **冻结说明**：v1.5 为 M8 设计冻结最终版本。不再向本文追加新 Engine 或核心对象。Stable Core 9 个对象已冻结。后续新增能力（GraphReasoner / Belief / Attention / Goal / Simulation / MetaCognition / Learning）作为 Adaptive Layer 通过 DailyMarketState 接口消费，不侵入 MarketWorldModel。

---

# PART I — Current Baseline (Frozen)

> **阅读指引**：PART I（第 0–22 节）描述 M8 当前已冻结并正在实施的架构基线。
> PART I 的内容受 ADR 流程约束，修改前必须经过架构评审、回放和批准。
> 长期能力展望已移至 PART II（第 23–27 节），仅作为信息性参考，不代表当前开发承诺。

---

## 0. 文档目的

当前系统已经能稳定完成：

```text
数据采集
  -> Identity
  -> Cycle
  -> StrongStock
  -> Decision
  -> DailyReview V2
  -> Notion
```

但当前输出仍主要回答“今天发生了什么”，无法稳定回答成熟交易员每天真正关心的五个问题：

1. 昨天建立的市场假设，今天被确认还是证伪？
2. 新证据使我们对哪些方向更相信、对哪些方向降低信念？
3. 当前市场变化由什么关键变量驱动，而不是仅与哪些变量相关？
4. 如果关键变量没有发生，结果是否仍会出现？
5. 明天应观察哪些可证伪条件，并据此调整行动？

M8 的目标不是增加一套更复杂的报告模板，而是把系统从“每日独立生成报告”升级为“连续维护市场认知状态”。

本设计冻结以下主链：

```text
Evidence
  -> Reasoning
  -> Belief Update
  -> Hypothesis Validation / Revision
  -> Counterfactual Stress Test
  -> Market Narrative
  -> Decision
  -> Outcome Evaluation
  -> Case Library
  -> next trading day
```

Notion、盘前必读、M6、M7、W2S 和实时监控应通过 feature flag 渐进消费认知对象；迁移期继续保留并验证原有结构化输出，禁止一次性切断现有链路。

### 0.1 最新实施状态（2026-07-05）

本节是 v1.3 冻结设计的实施状态附录，不新增顶层 Engine，也不发布 v1.4。

| 范围 | 当前状态 | 已完成 | 未完成/门禁 |
|---|---|---|---|
| M8 Phase 0 | GA | Knowledge → Evidence → Context → Cognition → Thesis；Notion Dual Layer；真实快照 Replay；Decision Drift=0 | 默认 Consumer 迁移仍受 feature flag 控制 |
| M8.phase1-T01 | In Review | Validation Record、四类 Verdict、六种 Failure Type、source/reality hash 契约 | 等待阶段统一验收 |
| M8.phase1-T02 | In Review | append-only Dataset、duplicate skip、conflict reject、Manifest Integrity | 正式 Ground Truth Record 仍为 0 |
| ADR-M8-009 | Accepted | Observation/Assessment/Hypothesis 语义边界；Prediction Eligibility | 禁止 Narrative 进入 Calibration |
| M8.phase1-T03 | In Review | eligible Hypothesis source freeze、Eligibility Gate、approved Reviewer Verdict | 等待首个到期 Reality 与人工复核 |
| M8.phase1-T04 | Not Started | 指标契约已定义 | Binary Accuracy、Brier、ECE、Timing Offset 尚未实现 |
| M8.phase1-T05 | Not Started | 20 日退出条件已冻结 | 尚未开始连续 20 个真实交易日验证 |

当前真实试运行结论：

- 2026-07-01～2026-07-03 三日 Replay 均为 ready；
- EvidenceRef coverage 为 100%，Unsupported Claim 为 0，Decision Drift 为 0；
- 2026-07-03 eligible Hypothesis 已证明可冻结，deadline 由 Trade Calendar Producer 修正为 `2026-07-06`；
- 截至 2026-07-05，2026-07-06 Reality 尚未发生，因此不得提前生成 Reviewer Verdict 或 Ground Truth Record；
- Belief、Learning、Memory 继续延期，避免在没有 Ground Truth 时形成自我强化闭环。

当前实际链路：

```text
Layer A/B/C/D + DailyReviewV2
  -> MarketKnowledgeBundle
  -> MarketEvidenceSnapshot
  -> MarketContextSnapshot
  -> CognitionState
  -> MarketThesisSnapshot
       ├─ Observation ─────────────> Notion / Report only
       ├─ Assessment ──────────────> Notion / Report only
       └─ Hypothesis
            -> Eligibility Gate
            -> FrozenHypothesisSource (append-only)
            -> Today Reality
            -> Approved Reviewer Verdict
            -> MarketThesisValidationRecord
            -> Validation Dataset + Manifest
            -> Replay / Metrics
```

Phase 1 的正式定义已从：

```text
Yesterday Thesis -> Verification -> Outcome -> Replay
```

修订为：

```text
Yesterday Hypothesis
  -> Eligibility
  -> Frozen Source
  -> Reviewer Verdict
  -> Ground Truth
  -> Replay
```

### 0.2 当前 Phase 1 冻结契约

`FrozenHypothesisSource` 是内部审计投影，不是新的认知 Engine：

```python
@dataclass(frozen=True, slots=True)
class FrozenHypothesisSource:
    thesis_trade_date: str
    source_snapshot_id: str
    source_as_of: datetime
    source_knowledge_hash: str
    source_evidence_hash: str
    source_context_hash: str
    source_thesis_hash: str
    source_quality_status: str
    source_quality_score: float
    source_policy_version: str
    hypothesis: HypothesisState
```

Eligibility Gate 同时要求：

1. 输入类型必须是 `HypothesisState`，Observation/Assessment/ThesisStatement 直接拒绝；
2. status 为 `VALIDATING`；
3. statement、hypothesis_id、policy version 非空；
4. deadline 晚于 source trade date，且来自 Trade Calendar EvidenceRef；
5. `0 <= prediction_probability <= 1`；
6. expected observations、falsifiers、EvidenceRefs 非空；
7. source quality 非 `BLOCKED`，source hashes 为有效 SHA-256；
8. 验证时必须提供 approved Reviewer Verdict。

当前 `MarketThesisValidationRecord v1`：

```python
@dataclass(frozen=True, slots=True)
class MarketThesisValidationRecord:
    record_id: str
    schema_version: str
    thesis_trade_date: str
    verification_trade_date: str
    source_hypothesis_id: str
    source_hypothesis_as_of: datetime
    hypothesis_deadline: str
    reality_available_at: datetime
    verified_at: datetime

    source_knowledge_hash: str
    source_evidence_hash: str
    source_context_hash: str
    source_thesis_hash: str
    reality_evidence_hash: str

    prediction_probability: float
    source_quality_score: float
    source_policy_version: str

    label: VerificationLabel
    failure_type: VerificationFailureType | None
    verification_reason: str
    outcome: str
    evidence_refs: tuple[str, ...]
    record_hash: str
```

Verdict 固定为 `YES/NO/PARTIAL/UNVERIFIABLE`。Failure Type 一级分类继续冻结为六种：

```text
WRONG_DIRECTION
WRONG_TIMING
WRONG_THEME
INSUFFICIENT_EVIDENCE
UNEXPECTED_EVENT
MARKET_REGIME_SHIFT
```

不合格命题在 Dataset 写入前 reject，不通过新增 Failure Type 表达。由于正式 Dataset 仍为 0 条，本次 `confidence -> prediction_probability + source_quality_score` 是首条生产记录前的契约校正，不需要历史数据迁移。

---

## 1. 问题陈述

### 1.1 当前报告为什么“数据正确但没法看”

当前 Notion 报告按数据模块组织：

```text
交易结论
市场摘要
今日复盘要点
市场环境
涨停结构
主线状态
创新高
资金验证
次日计划
数据质量
```

这种结构有三个根本问题：

1. 同一结论被不同模块重复表达，例如“不交易”“情绪冰点”“仅观察”反复出现。
2. 题材只展示当日标签和数量，没有“昨日判断 -> 今日验证 -> 信念变化 -> 明日条件”。
3. 所有模块处于同一阅读层级，事实、解释、风险和行动混在一起，读者必须自行完成认知整合。

因此，清理空栏目、翻译英文状态、修正资金重复，只能提高数据卫生，不能解决报告可读性。

### 1.2 分析师复盘体现的真实认知对象

2026-07-02 分析师复盘包含两组稳定对象。

大盘层：

| 认知维度 | 分析师表达示例 | M8 对应对象 |
|---|---|---|
| 关键节点 | 分歧充分、分歧转修复、超跌反弹 | `MarketFSMState`、`MarketHypothesis.expected_observations` |
| 大盘概况 | 竞价量、流动性、涨跌家数、指数路径 | `MarketEvidence` |
| 题材强度 | 正负排名、科技赛道主跌 | `ThemeEvidence`、`ThemeLifecycle` |
| 大资金流向 | 机器人/黄金流入，芯片/通信流出 | `CapitalRotationGraph` |
| 情绪载体 | 高位加速杀跌，低位冲高回落 | `EmotionVector`、`LeaderEvolution` |
| 整体思路 | 老周期调整，低位轮动反弹 | `MarketNarrative`、`MarketBeliefState` |

题材层：

| 认知维度 | 分析师表达示例 | M8 对应对象 |
|---|---|---|
| 昨日思路 | 若先修复则冲高减仓；若先分歧则等待超跌反弹 | `MarketHypothesis` |
| 日内理解 | PCB 修复强，高位周期龙修复弱 | `HypothesisEvaluation` |
| 阶段研判 | 主升第三阶段第 12 天、分歧 D2 | `ThemeLifecycle` |
| 多空辨识度 | 周期龙、中军、前排、补跌股 | `ThemeRole`、`InfluenceGraph` |
| 交易者心态 | 持筹方信心崩溃、持币方回流信心不足 | `ParticipantBelief` |
| 指数共振 | 有共振、丧失共振、跷跷板效应 | `CrossMarketRelation` |
| 隔日思考 | 等待分歧、观察右侧确认、锚定韩国指数 | `ScenarioPath`、下一日假设 |

分析师不是在每天重新写一份静态报告，而是在维护一组可验证的市场观点。

### 1.3 核心架构差距

| 维度 | 当前系统 | M8 目标 |
|---|---|---|
| 时间 | 每日独立快照 | 跨日认知链 |
| 核心对象 | `recap_doc` 字典 | Evidence / Belief / Hypothesis / Decision 快照 |
| 市场状态 | 单标签 | FSM 状态与转移分布 |
| 题材理解 | 当日强弱与资金 | 身份、周期、角色、预期差、演化链 |
| 观点 | 无一等对象 | 可证伪的 `MarketHypothesis` |
| 信念 | 无连续状态 | prior -> posterior 的 `BeliefState` |
| 反事实 | 无 | 带干预假设和可信等级的反事实评估 |
| 历史经验 | 模式标签 | 完整 `MarketCase` |
| 叙事 | 模板或 LLM 拼接 | 从结构化认知编译的 `MarketNarrative` |
| 决策 | 单一 action | 条件化场景、触发器、失效条件 |
| 可解释性 | 字段来源分散 | EvidenceRef + TraceStep + PolicyVersion |

---

## 2. 设计目标与非目标

### 2.1 设计目标

1. 将“市场假设”提升为跨日持久化的一等领域对象。
2. 以显式先验、证据更新和后验置信度维护市场信念。
3. 将事实观察、推理判断、主观信念和交易决策严格分层。
4. 所有判断必须可追溯到结构化证据、计算策略和时间点。
5. 将分析师的“昨日 -> 今日 -> 明日”认知链固化为机器可验证契约。
6. 让报告首先呈现观点变化和关键条件，详细数据降级到证据附录。
7. 支持离线回放、无未来数据污染的评估与策略版本比较。

### 2.2 非目标

1. M8 不直接执行实盘交易。
2. M8 不用 LLM 替代行情、资金、事件和技术指标真源。
3. 第一阶段不宣称从相关性数据获得严格因果结论。
4. 第一阶段不建设 Tick 级全市场因果图。
5. 不一次性替换 A/B/C/D；M8 首先作为其上层认知与编排层。
6. 不允许在证据缺失时由模板或 LLM 补出事实。

---

## 3. 核心设计原则

### 3.1 Observation、Assessment、Hypothesis、信念与行动分离

```text
Evidence    = 市场实际观测及其 lineage
Observation = 对已经发生事实的结构化陈述
Assessment  = 对当前状态、风险或交易权限的判断
Reasoning   = 对观测的确定性或概率性解释
Belief      = 系统当前对某个命题的可信程度
Hypothesis  = 带未来期限、事前概率和可证伪条件的待验证命题
Decision    = 在风险与 Strategy 约束下选择的行动
```

Validation 与 Calibration 只消费 eligible Hypothesis。Observation、Assessment 和 Narrative 可以进入报告，但不得进入 Ground Truth Dataset。

质量与概率必须使用不同词汇：

```text
quality_score
  = 数据完整性、lineage、时效性和推理链可靠性

prediction_probability
  = 在 Hypothesis 冻结时，对未来事件发生概率的事前估计
```

`Narrative Confidence ≠ Prediction Probability`。禁止将 `quality_score`、LLM 语气强度或 Reviewer 事后评分复制为 `prediction_probability`。

禁止：

- 把“炸板率 18%”直接存为“市场很差”；
- 把“机器人弱”作为不可验证的假设；
- 把“Belief 82”当作客观市场事实；
- 把”如果龙头不炸板”写成已证实因果结论。

### 3.1.1 Semantic Contract（词汇边界契约）

以下表格是 M8 所有消费者的强制性语义边界。任何违反此边界的实现将被 Eligibility Gate 或 CI 契约测试拒绝。

| 对象 | 是否进入 Report/Notion | 是否进入 Validation | 是否进入 Ground Truth Dataset | 是否进入 Calibration (Brier/ECE) |
|---|---|---|---|---|
| Observation | ✅ | ❌ | ❌ | ❌ |
| Assessment | ✅ | ❌ | ❌ | ❌ |
| Narrative / ThesisStatement | ✅ | ❌ | ❌ | ❌ |
| Hypothesis（通过 Eligibility） | ✅ | ✅ | ✅ | ✅ |
| Reviewer Verdict | ✅ | ✅ | ✅ | ✅ |
| Ground Truth Record | — | — | ✅ | ✅ |

**Eligibility Gate 规则**（写入 Dataset 前的强制性门禁）：

```text
输入必须是 HypothesisState（Observation/Assessment/ThesisStatement 直接拒绝）
  AND hypothesis.status == “VALIDATING”
  AND hypothesis_id 非空 AND statement 非空
  AND deadline 来自 Trade Calendar Producer 且晚于 source trade date
  AND 0 <= prediction_probability <= 1
  AND expected_observations 非空
  AND falsifiers 非空
  AND EvidenceRefs 完整（含 Trade Calendar EvidenceRef）
  AND source quality != “BLOCKED”
  AND source hashes 为有效 SHA-256
  AND source_policy_version 非空
  AND Reviewer Verdict 显式存在（reviewer_id 在 approved_reviewer_ids 中）
  AND Reality available_at >= hypothesis deadline
```

**不合格处理**：不满足任一条件 → `HypothesisEligibilityError`。不合格命题在 Dataset 写入前拒绝，不产生 Validation Record，不新增 Failure Type。

### 3.2 时间一致性

每个输入与输出必须包含：

- `trade_date`
- `as_of`
- `available_at`
- `source_snapshot_id`
- `policy_version`

任何回测或回放只能读取 `available_at <= evaluation_as_of` 的数据。

### 3.3 证据必须可引用

不使用裸字符串 `supporting_evidence: list[str]` 作为最终契约。统一使用：

```python
class EvidenceRef:
    evidence_id: str
    evidence_type: str
    entity_type: str
    entity_id: str
    observed_at: datetime
    available_at: datetime
    source_table: str
    source_record_id: str
    snapshot_id: str
    value_digest: str
```

解释文本可以附加，但不能替代证据引用。

### 3.4 LLM 只做受约束解释

LLM 可以：

- 将结构化认知对象翻译为自然语言；
- 对冲突证据做摘要；
- 生成待审核的假设候选；
- 检索相似案例并解释差异。

LLM 不可以：

- 直接修改 Evidence；
- 绕过策略计算 Belief Score；
- 自动把假设标记为 CONFIRMED；
- 生成不存在的资金、价格、席位或事件事实；
- 用自然语言覆盖硬风险门禁。

---

## 4. 总体架构

```text
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: Market Evidence                                     │
│ Identity / Cycle / StrongStock / Decision / Capital / Event  │
│ DragonTiger / Technical / Auction / CrossMarket / Abnormal   │
│ Output: MarketEvidenceSnapshot                               │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 2: Market Reasoning                                    │
│ Market FSM / Theme Cognitive / Emotion / Leader Evolution    │
│ Influence / Capital Rotation / Expectation Gap               │
│ Output: MarketReasoningSnapshot                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 3: Belief & Hypothesis                                 │
│ Market Belief Engine                                         │
│ Hypothesis Engine                                            │
│ - prior -> evidence update -> posterior                      │
│ - validate / reject / revise / supersede                     │
│ Output: BeliefSnapshot + HypothesisSnapshot                  │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 4: Counterfactual & Scenario                           │
│ Counterfactual Engine / Scenario Engine / Risk Engine        │
│ Output: CounterfactualAssessment + ScenarioPath              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 5: Narrative & Decision                                │
│ Market Narrative Compiler / Action Engine                    │
│ Output: MarketNarrativeSnapshot + MarketDecisionSnapshot     │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 6: Learning Memory                                     │
│ Outcome Evaluator / Case Library / Calibration Metrics       │
│ Output: MarketCase + calibration reports                     │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Consumers                                                    │
│ PostMarket / PreMarket / M6 / M7 / W2S / Monitor / Notion    │
└──────────────────────────────────────────────────────────────┘
```

### 4.1 为什么保留 Reasoning，但用 Belief 替代 Meta Reasoner

Reasoning 描述市场对象的推理结果；Belief 描述系统对命题的当前确信程度。两者不是同一层。

原“Meta Reasoner”的冲突消解职责并不删除，而是收敛进 `MarketBeliefEngine`：

1. 收集不同 Engine 对同一命题的支持与反对证据；
2. 应用可靠性、时效性、独立性和硬门禁权重；
3. 更新 Belief posterior；
4. 保留冲突，而不是简单平均掉冲突；
5. 输出 Belief 变化原因和未解决矛盾。

---

## 5. 三类基础通用契约

### 5.1 ReasonedValue

```python
@dataclass(frozen=True, slots=True)
class ReasonedValue(Generic[T]):
    value: T
    confidence: float
    supporting_evidence: tuple[EvidenceRef, ...]
    counter_evidence: tuple[EvidenceRef, ...]
    reasoning_trace: tuple["TraceStep", ...]
    source_engine: str
    engine_version: str
    policy_version: str
    as_of: datetime
```

约束：

- `0 <= confidence <= 1`
- 无证据不得输出高置信判断；
- `reasoning_trace` 必须引用输入字段或 EvidenceRef；
- 不允许 `Any` 作为持久化边界的 `value` 类型。

### 5.2 TraceStep

```python
@dataclass(frozen=True, slots=True)
class TraceStep:
    step_no: int
    operation: str
    inputs: tuple[str, ...]
    output: str
    policy_rule_id: str | None
    evidence_refs: tuple[str, ...]
```

### 5.3 SnapshotEnvelope

```python
@dataclass(frozen=True, slots=True)
class SnapshotEnvelope(Generic[T]):
    snapshot_id: str
    schema_version: str
    trade_date: date
    as_of: datetime
    generated_at: datetime
    input_snapshot_ids: tuple[str, ...]
    policy_versions: dict[str, str]
    content_hash: str
    data_quality: "DataQualitySummary"
    payload: T
```

快照必须不可变；修正数据生成新版本，不覆盖历史版本。

---

## 6. Layer 1：MarketEvidenceSnapshot

### 6.1 契约

```python
@dataclass(frozen=True, slots=True)
class MarketEvidenceSnapshot:
    market: MarketEvidence
    themes: tuple[ThemeEvidence, ...]
    stocks: tuple[StockEvidence, ...]
    capital: CapitalEvidence
    events: tuple[EventEvidence, ...]
    cross_market: tuple[CrossMarketEvidence, ...]
    source_coverage: tuple[SourceCoverage, ...]
```

`raw_context` 不进入领域快照。原始 payload 只通过 `source_snapshot_id` 或对象存储引用保留，避免“纯事实层”退化为任意字典入口。

### 6.2 MarketEvidence

至少包含：

- 指数开高低收、涨跌幅、成交额；
- 竞价量、全市场成交额及环比；
- 上涨/下跌/涨停/跌停家数；
- 炸板率、连板高度、首板晋级率；
- 高位股与低位股表现差；
- 跨市场指数与关键商品表现；
- 数据完整性与时点。

### 6.3 ThemeEvidence

至少包含：

- 题材规范 ID 与名称；
- 涨停数、连板结构、上涨家数；
- 资金净流入/流出与 Top stocks；
- 机构/游资席位事实；
- 龙头、前排、中军的价格与量能观测；
- 事件及题材匹配证据；
- 与指数的相关性观测；
- D-5 至 Today 的时间序列。

---

## 7. Layer 2：MarketReasoningSnapshot

```python
@dataclass(frozen=True, slots=True)
class MarketReasoningSnapshot:
    market_fsm: MarketFSMState
    emotion_vector: EmotionVector
    expectation_gaps: tuple[ExpectationGap, ...]
    theme_identities: tuple[ThemeIdentity, ...]
    theme_lifecycles: tuple[ThemeLifecycle, ...]
    theme_roles: tuple[ThemeRole, ...]
    leader_evolutions: tuple[LeaderEvolution, ...]
    influence_graph: InfluenceGraph
    capital_rotation: CapitalRotationGraph
    cross_market_relations: tuple[CrossMarketRelation, ...]
```

### 7.1 Market FSM

FSM 描述市场所处环境，不直接给出买卖行动。

建议状态：

```text
CHAOS
INITIAL
FERMENTATION
ACCELERATION
CLIMAX
FIRST_DIVERGENCE
WEAK_TO_STRONG
SECOND_ACCELERATION
SECOND_DIVERGENCE
FADE
ICE_POINT
REBOUND
SECOND_WAVE
```

输出必须包含：

- 当前状态；
- 前一状态；
- 状态持续天数；
- 候选下一状态及概率；
- 支持/反对证据；
- 转移策略版本。

FSM 概率第一阶段应定义为“策略评分归一化后的相对权重”，不得直接宣称为统计学后验概率。只有经过历史校准后，才能对外称为概率。

### 7.2 Theme Cognitive

拆分为四个独立契约：

1. `ThemeIdentity`：题材名称、锚定方向、炒作风格；
2. `ThemeLifecycle`：周期、阶段、天数、日内状态；
3. `ThemeRole`：周期龙、中军、先锋、跟风、淘汰；
4. `ThemeReasoning`：昨日预期、今日实际、预期差、明日条件。

### 7.3 Emotion Vector

情绪不再是单一 `dead/strong` 标签：

```python
class EmotionVector:
    greed: ReasonedValue[float]
    fear: ReasonedValue[float]
    hesitation: ReasonedValue[float]
    fomo: ReasonedValue[float]
    market_confidence: ReasonedValue[float]
    primary_carriers: tuple[str, ...]
    weakened_carriers: tuple[str, ...]
    emerging_carriers: tuple[str, ...]
```

额外维护：

- `holder_mindset`：场内持筹方；
- `cash_holder_mindset`：场外持币方；
- `style_preference`：机构趋势、庄游、机游合力等；
- `attention_migration`：注意力从旧载体向新载体的迁移。

### 7.4 Influence Graph

Role 不是“涨停天数最多”的别名。影响力至少由以下分量构成：

```text
same_theme_follow_response
cross_theme_follow_response
capital_attention
emotion_carrier_strength
index_contribution
temporal_lead
```

第一阶段可用日级和可获得的分钟级数据构建近似图；若只有日级数据，必须标记 `resolution=daily_proxy`，不得声称识别了日内因果传播。

---

## 7A. Cognition Projections — 定位与设计原则

### 7A.1 为什么需要 Cognition Projections

当前 M8 Phase 1 已建立扎实的 Hypothesis Validation 链：

```text
Yesterday Hypothesis
  -> Eligibility
  -> Frozen Source
  -> Reviewer Verdict
  -> Ground Truth
  -> Replay
```

但 Hypothesis 生成前的市场认知过程仍然薄弱。分析师实际流程是：

```text
多天行情
  -> 外围市场
  -> 题材间强弱
  -> 板块内标的强弱
  -> 周期节点定位
  -> 交易节点判断
  -> 明日假设
```

M8 需要从 Hypothesis Validator 升级为 Hypothesis Generator — 生成的假设必须具备周期节点精度。

### 7A.2 设计约束

Cognition Projections 不是新 Engine，而是落在现有 Stable Core 内部的只读认知投影：

| 投影 | 宿主对象 | 说明 |
|---|---|---|
| Multi-Horizon Context | `MarketContextSnapshot` | 多周期维度扩展 |
| Market Cognition Graph | `MarketReasoningSnapshot` | 关系图扩展 |
| ThemeCognitiveCard + TradingCognitionCard | `CognitionState` | 题材/交易认知卡 |

核心约束：

1. 所有投影只消费 `versioned + as_of` 的 Evidence Snapshot，不直接读取业务数据库表
2. 每条判断必须携带 `EvidenceRef`，满足文档 19.2 节审计要求
3. 每日 append-only 快照，不覆盖历史版本
4. 严格遵守文档 3.1.1 节 Semantic Contract：Observation/Assessment 可入 Report，不可入 Validation/Dataset
5. 投影失败不阻塞旧复盘链

---

## 7B. Multi-Horizon Market Context

### 7B.1 定位

解决核心问题：**分析师不是只看一天。**

当前 `MarketEvidenceSnapshot` 已包含 D-5 至 Today 的时间序列（Section 6.3），但未结构化为多周期认知上下文。`MultiHorizonContext` 将每个题材/市场维度的 D1/D3/D5/D10/D20 状态显式化为结构化投影。

### 7B.2 契约

```python
@dataclass(frozen=True, slots=True)
class MultiHorizonContext:
    trade_date: date
    horizons: tuple[str, ...]  # "D1", "D3", "D5", "D10", "D20"
    
    market_windows: tuple[MarketWindowContext, ...]
    theme_windows: tuple[ThemeWindowContext, ...]
    stock_windows: tuple[StockWindowContext, ...]
    external_windows: tuple[ExternalMarketWindowContext, ...]
    earnings_windows: tuple[EarningsWindowContext, ...]
    
    as_of: datetime
    source_snapshot_ids: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class ThemeWindowContext:
    theme_id: str
    theme_name: str
    
    d1_state: str          # 今日是否修复/分歧/高潮
    d3_trend: str          # 连续三天是加速/分歧/修复
    d5_phase: str          # 是否进入阶段末端
    d10_cycle_position: str  # 是否处于大周期主升/调整
    d20_mainline_status: str  # 是否仍属于中期主线
    
    consecutive_days: int   # 当前节点持续天数
    phase_day: int          # 当前阶段第几天
    
    available_snapshot_ids: tuple[str, ...]  # 每个 horizon 可追溯到具体 snapshot
    evidence_refs: tuple[str, ...]
```

### 7B.3 示例

机器人：

```text
theme: 机器人
D1: 高潮 (CLIMAX)
D3: 连续增强 (连续3日走强)
D5: 一阶段第4天
D10: 新主线尝试确立
D20: 尚未进入大周期确认

来源 snapshots:
  D1 -> snapshot:2026-07-03
  D3 -> snapshot:2026-07-01, snapshot:2026-07-02, snapshot:2026-07-03
  D5 -> snapshot:2026-06-29..2026-07-03
  D10 -> snapshot:2026-06-24..2026-07-03
```

通信/CPO：

```text
theme: 通信/CPO
D1: 止跌 (DIVERGENCE_WEAKENING)
D3: 分歧减弱 (DIVERGENCE_D3)
D5: 主升后调整
D10: 高位科技退潮压力
D20: 仍是中期科技主线候选
```

### 7B.4 External Anchor Context

外围市场不应放在备注，而应结构化：

```python
@dataclass(frozen=True, slots=True)
class ExternalAnchorContext:
    anchor_id: str
    anchor_name: str          # 韩国股市 / SK Hynix / 美股半导体
    affected_themes: tuple[str, ...]
    affected_industry_chain: tuple[str, ...]
    not_directly_affected: tuple[str, ...]
    horizon: str              # D1 / D3 / D5
    direction: str            # bullish / bearish / neutral
    strength: float           # 0-1，对 A 股题材的实际传导强度
    evidence_refs: tuple[str, ...]
```

示例：

```text
anchor: 韩国股市
affected_themes: [存储芯片, HBM, 半导体设备]
not_directly_affected: [机器人, 商业航天]
direction: bearish
strength: 0.82
```

### 7B.5 Earnings Season Context

```python
@dataclass(frozen=True, slots=True)
class EarningsSeasonContext:
    theme_id: str
    stage: str                # 预热 / 披露 / 兑现 / 结束
    expected_beneficiaries: tuple[str, ...]
    risk_of_sell_the_news: float  # 0-1
    evidence_refs: tuple[str, ...]
```

---

## 7C. Market Cognition Graph

### 7C.1 定位

解决核心问题：**分析师不是孤立看题材，而是看关系。**

分析师在盘后复盘时维护的是一张关系网：韩国半导体传导至A股存储芯片、机器人从高位科技抽走资金、中报业绩支撑光模块趋势承接。`MarketCognitionGraph` 将这张关系网结构化为可查询、可审计的认知投影。

### 7C.2 与 M9 World Model 的边界

| 维度 | M8 Cognition Graph | M9 World Model |
|---|---|---|
| 时间尺度 | 当日 + 回溯窗口 | 跨周期、版本化 |
| 更新方式 | 每日重建 (append-only snapshot) | Proposal → Replay → Shadow → Approval |
| 关系来源 | 当日 Evidence 推导 | 长期校准的结构规则 |
| 可靠性 | `strength` 基于当前数据窗口 | `confidence` 基于历史校准 |
| 字段 | `graph_type = "daily_cognitive_projection"` | `world_model_version` |

### 7C.3 契约

```python
@dataclass(frozen=True, slots=True)
class MarketCognitionGraph:
    graph_id: str
    graph_type: str  # "daily_cognitive_projection"
    trade_date: date
    as_of: datetime
    
    nodes: tuple[CognitionNode, ...]
    edges: tuple[CognitionEdge, ...]
    
    world_model_version: str | None  # 如果 M9 已有 World Model，用作先验
    evidence_refs: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class CognitionNode:
    node_id: str
    node_type: str  # Market / Index / Theme / Stock / Leader /
                    # ExternalMarket / IndustryChain / Earnings /
                    # Commodity / CapitalStyle / EmotionCarrier
    entity_id: str
    entity_name: str
    properties: Mapping[str, Any]  # 迁移期允许，进入 Evidence 前转为类型化
    as_of: datetime


@dataclass(frozen=True, slots=True)
class CognitionEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    # resonates_with / competes_with / rotates_to / crowds_out /
    # anchors / leads / follows / constrains / supports / weakens /
    # external_anchor / capital_rotation / fundamental_support
    strength: float          # 0-1，基于当前窗口数据
    direction: str           # positive / negative / neutral
    reason: str              # 不超过 80 字的结构化原因
    evidence_refs: tuple[str, ...]
```

### 7C.4 示例

```text
edges:
  - source: 韩国股市
    target: 存储芯片
    relation: external_anchor
    strength: 0.82
    direction: negative
    reason: 韩国半导体走弱主要影响存储/HBM方向，不直接影响机器人和商业航天

  - source: 机器人
    target: 黄线(市场情绪载体)
    relation: resonates_with
    strength: 0.75
    direction: positive
    reason: 机器人日内强于白线，成为全市场情绪载体

  - source: 高位科技(通信/CPO/PCB)
    target: 机器人
    relation: capital_rotation
    strength: 0.68
    direction: positive
    reason: 高位科技补跌后资金寻找低位趋势承载，机器人承接流出资金

  - source: 中报业绩
    target: 光模块/CPO
    relation: fundamental_support
    strength: 0.71
    direction: positive
    reason: 业绩高增长细分开始披露，支撑机构趋势资金在调整中承接
```

### 7C.5 构建约束

- 边的关系类型必须是枚举值，不允许自由文本
- 每条边的 `strength` 必须有至少一个 `EvidenceRef` 支撑
- `world_model_version` 非空时，Graph 必须声明与 World Model 先验一致或冲突
- 分辨率标记：若只用日级数据推导关系，必须标记 `resolution=daily_proxy`

### 7C.6 Dynamic Causal Chain

Cognition Graph 不应只是静态关系图，而应支持因果链推演。分析师在复盘时维护的不是孤立关系，而是一条因果传导链：

```text
韩国半导体跌
  ↓ cause
HBM 板块承压
  ↓ cause
PCB 走弱
  ↓ cause (capital rotation)
资金流向机器人
  ↓ cause
机器人加强
  ↓ cause
黄线加强
  ↓ cause (but)
指数没有加强
  ↓ conclusion
赚钱效应局部化，跷跷板持续
```

**契约**：

```python
@dataclass(frozen=True, slots=True)
class CausalChain:
    chain_id: str
    chain_name: str
    trade_date: date
    
    steps: tuple[CausalStep, ...]
    # ordered list of cause → effect steps
    
    confidence: float         # 整条链的整体置信度
    alternative_chains: tuple[str, ...]  # 引用其他 chain_id（替代因果解释）
    policy_version: str

@dataclass(frozen=True, slots=True)
class CausalStep:
    step_no: int
    cause_node_id: str        # -> CognitionNode
    effect_node_id: str       # -> CognitionNode
    relation_type: str        # causes / strengthens / weakens / redirects / blocks
    
    mechanism: str            # 传导机制描述（不超过 100 字）
    strength: float           # 0-1，因果强度
    time_lag: str             # immediate / same_day / next_day / multi_day
    
    is_conjecture: bool       # 是否为推测（Phase 1 允许猜想，但必须标记）
    counterfactual_testable: bool  # 是否可通过反事实检验
    
    evidence_refs: tuple[str, ...]
```

**关键约束**：

- 因果链只连接 Graph 中已存在的节点
- `is_conjecture=True` 的步骤必须标记，且不能进入 Calibration Dataset
- 每条因果链必须至少有一条 alternative_chain（防止过度归因）
- `time_lag` 为 `next_day` 或 `multi_day` 的因果步骤，必须进入 Hypothesis（而非 Assessment）
- Phase 1 只允许 `immediate` 和 `same_day` 的因果链；跨日因果必须是 Hypothesis

CausalChain 与 CognitionEdge 的关系：
- `CognitionEdge` 描述节点之间的关联强度与方向（静态快照）
- `CausalChain` 描述关联的传导顺序与机制（动态推演）
- 一条 `CausalChain` 的每个步骤引用一条 `CognitionEdge`，但增加了顺序、时滞和机制描述

---

## 7D. Theme Cognitive Card

### 7D.1 定位

`ThemeCognitiveCard` 是分析师题材分析的结构化投影，直接对应分析师字段。它聚合多周期 Context、关系图和周期节点，形成每个题材的完整认知画像。

### 7D.2 分析师字段映射

| 分析师字段 | 系统字段 | 语义边界 (3.1.1节) |
|---|---|---|
| 炒作风格 | `style` | Assessment → Report only |
| 多头辨识度 | `leaders / followers` | Observation → Report only |
| 空头辨识度 | `bears` | Observation → Report only |
| 老龙头/题材锚定 | `old_leaders` | Observation → Report only |
| 与指数共振 | `index_resonance` | Assessment → Report only |
| 日内理解 | `intraday_interpretation` | Observation → Report only |
| 交易者心态(场内) | `holder_psychology` | Assessment → Report only |
| 交易者心态(场外) | `cash_holder_psychology` | Assessment → Report only |
| 阶段研判 | `cycle_node / stage / stage_day` | Assessment → Report only |
| 昨日思路 → 今日验证 | `yesterday_view → today_validation` | Hypothesis → Verdict → **Eligible for Dataset** |
| 隔日思考 | `tomorrow_watch` | ThesisStatement → Report only |
| 外围影响 | `external_relations` | Assessment → Report only |
| 中报影响 | `earnings_relations` | Assessment → Report only |

### 7D.3 契约

```python
@dataclass(frozen=True, slots=True)
class ThemeCognitiveCard:
    card_id: str
    theme_id: str
    theme_name: str
    trade_date: date
    as_of: datetime

    # ---- 风格与风格偏好 ----
    style: str                  # 机游合力 / 机构趋势 / 庄游合力 / 游资接力 / 量化套利
    style_confidence: float

    # ---- 周期与阶段 ----
    cycle_node: "CycleNodeRecognition"
    stage: str                  # 启动 / 发酵 / 加速 / 高潮 / 分歧 / 弱转强 / 退潮
    stage_day: int | None
    multi_horizon_ref: str      # -> MultiHorizonContext 的引用

    # ---- 角色识别 ----
    leaders: tuple[LeaderRole, ...]     # 周期龙、中军、先锋
    followers: tuple[StockRole, ...]     # 跟风、补涨
    bears: tuple[StockRole, ...]         # 空头辨识度
    old_leaders: tuple[StockRole, ...]   # 老龙头/题材锚定

    # ---- 共振与资金 ----
    index_resonance: str        # 有共振 / 无共振 / 跷跷板 / 中等偏强
    capital_recognition: str    # 机构认可 / 游资主导 / 混合 / 资金回避
    emotion_carrier_role: str   # 市场情绪载体 / 局部载体 / 无载体角色

    # ---- 日内与心理 ----
    intraday_interpretation: str
    holder_psychology: str      # 场内持筹方心态
    cash_holder_psychology: str # 场外持币方心态

    # ---- 跨题材与外部关系 ----
    cross_theme_relations: tuple[str, ...]   # 引用 CognitionEdge ID
    external_relations: tuple[str, ...]      # 引用 ExternalAnchorContext
    earnings_relations: tuple[str, ...]      # 引用 EarningsSeasonContext

    # ---- 时间线认知 ----
    yesterday_view: str | None
    today_validation: str | None
    tomorrow_watch: str

    # ---- 交易认知 ----
    trading_cognition: "TradingCognitionCard"

    # ---- 溯源 ----
    evidence_refs: tuple[str, ...]
    policy_version: str
```

### 7D.4 LeaderRole / StockRole

```python
@dataclass(frozen=True, slots=True)
class LeaderRole:
    stock_code: str
    stock_name: str
    role: str       # cycle_leader / sector_leader / capacity_core / front_row / pioneer
    stage: str      # 对应题材阶段的角色批次（一阶段/二阶段/...）
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StockRole:
    stock_code: str
    stock_name: str
    role: str       # follower / supplement / eliminated / bear / old_leader
    note: str
    evidence_refs: tuple[str, ...]
```

### 7D.5 示例

```text
ThemeCognitiveCard:
  theme_name: 机器人/减速器
  style: 机游合力、趋势风格为主
  stage: 启动后的强化阶段
  cycle_node: CLIMAX, node_day=4
  leaders:
    - 绿的谐波 (谐波减速器A股市占率25%, 有望供货特斯拉)
    - 埃斯顿 2B, 海晨股份 2B, 福莱新材 2B
    - 兆威机电, 雷赛智能 2B, 日盈电子 2B
  bears: 无
  index_resonance: 无(黄线强于白线)
  capital_recognition: 机构资金开始认可
  emotion_carrier_role: 市场情绪载体(机器人成为黄线共振方向)
  intraday_interpretation: 受宇树机器人IPO消息刺激发酵,
    资金从芯片/通信/玻璃基板流入机器人
  holder_psychology: 资金偏向科技赛道高低切
  cross_theme_relations:
    - capital_rotation from 高位科技(通信/CPO/PCB) strength=0.68
  external_relations: []
  yesterday_view: "机器人可能成为修复方向" → 得到验证
  tomorrow_watch: 关注是否继续获得资金确认;
    若继续加强则进入主线确认阶段
```

---

## 7E. Cycle Node Recognition & Divergence Quality

### 7E.1 Cycle Node Recognition

解决核心问题：**判断市场/题材/龙头现在处在哪个交易节点。**

这是 M8 生成 Hypothesis 的前提——只有知道当前节点，才能预测下一个节点迁移。

```python
@dataclass(frozen=True, slots=True)
class CycleNodeRecognition:
    recognition_id: str
    subject_type: str       # market / theme / leader
    subject_id: str
    trade_date: date

    # ---- 当前节点 ----
    current_node: str
    # CHAOS / INITIAL / FERMENTATION / ACCELERATION / CLIMAX /
    # FIRST_DIVERGENCE / DIVERGENCE_REPAIR / WEAK_TO_STRONG /
    # SECOND_ACCELERATION / SECOND_DIVERGENCE / FADE /
    # ICE_POINT / REBOUND / DIVERGENCE_WEAKENING / CYCLE_END
    previous_node: str | None
    node_day: int           # 当前节点持续天数
    consecutive_direction: str  # accelerating / diverging / repairing / fading / neutral

    # ---- 分歧状态 ----
    divergence_state: str   # healthy / forced / panic / insufficient / not_applicable
    repair_state: str       # confirmed / weak / failed / not_applicable
    climax_state: str       # accelerating / peaking / exhausting / not_applicable
    fade_state: str         # orderly / panic / acceleration / not_applicable

    # ---- 下一个节点预测 ----
    expected_next_nodes: tuple[ExpectedNodeTransition, ...]
    node_confidence: float  # 0-1，当前节点定位的置信度

    evidence_refs: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class ExpectedNodeTransition:
    target_node: str
    probability: float       # 0-1，事前估计
    required_conditions: tuple[str, ...]
    evidence_refs: tuple[str, ...]
```

示例：

```text
机器人:
  current_node: CLIMAX
  node_day: 4
  divergence_state: not_applicable (尚未分歧)
  expected_next_nodes:
    - target: FIRST_DIVERGENCE, probability: 0.65
      required: [板块不再继续一致加速, 前排核心分歧但不破位]
    - target: SECOND_ACCELERATION, probability: 0.20
    - target: FADE, probability: 0.15

通信/CPO:
  current_node: DIVERGENCE_WEAKENING
  node_day: 3
  divergence_state: healthy (缩量分歧, 核心未破位)
  expected_next_nodes:
    - target: DIVERGENCE_REPAIR, probability: 0.45
    - target: FADE, probability: 0.35
    - target: REBOUND, probability: 0.20
```

### 7E.2 Divergence Quality

分歧质量是分析师判断"能不能出手"的核心依据，应成为一等指标：

```python
@dataclass(frozen=True, slots=True)
class DivergenceQuality:
    quality_id: str
    subject_id: str
    trade_date: date

    quality_score: float         # 0-1
    volume_contraction: float    # 缩量程度 0-1 (1=极致缩量)
    core_intact: bool            # 核心/龙头是否守位
    rear_cleared: bool           # 后排风险是否释放
    capital_redirected: bool     # 资金是否有承接方向
    duration_sufficient: bool    # 分歧时间是否充分
    external_support: bool       # 外围是否支撑

    quality_label: str           # healthy / forced / panic / insufficient
    # healthy:      缩量有序，核心守位，后排释放，资金有承接 → left_side_allowed
    # forced:       受外力挤压，非内生分歧 → 等待确认
    # panic:        放量杀跌，核心破位，后排崩溃 → avoid
    # insufficient: 分歧时间不足，风险未释放 → wait

    evidence_refs: tuple[str, ...]
```

`DivergenceQuality` 直接决定 `TradingCognitionCard` 的 `left_side_allowed` 和 `right_side_allowed`：

```text
quality_label == "healthy"   → left_side_allowed = true (左侧可以试探)
quality_label == "panic"     → left_side_allowed = false, right_side_allowed = false (全面回避)
quality_label == "forced"    → left_side_allowed = false, right_side_allowed = true (只等右侧确认)
quality_label == "insufficient" → left_side_allowed = false, right_side_allowed = false (继续等待)
```

---

## 7F. Trading Cognition Card

### 7F.1 定位

`TradingCognitionCard` 回答交易员最核心的问题：**这个题材/标的现在能不能出手，以什么方式出手。**

它不绑定特定策略（那是 Strategy Layer 的职责），而是表达基于当前认知的交易节点判断。

### 7F.2 与 Strategy Layer 的关系

```
CycleNodeRecognition + DivergenceQuality
        ↓
TradingCognitionCard    ← 交易认知投影（不绑定特定策略）
        ↓
Strategy Eligibility    ← 策略适配（绑定 strategy_id + version，Section 38-41）
        ↓
Strategy Proposal
        ↓
Risk Gate → Decision
```

### 7F.3 契约

```python
@dataclass(frozen=True, slots=True)
class TradingCognitionCard:
    card_id: str
    subject_id: str
    subject_type: str         # theme / stock / leader
    trade_date: date

    # ---- 动作偏向 ----
    action_bias: str
    # wait / left_probe / right_confirm / hold_core / reduce / avoid

    left_side_allowed: bool
    right_side_allowed: bool

    # ---- 入场节点 ----
    next_entry_node: str | None
    # 例如: "龙头第一次良性分歧后修复" / "分歧充分后的超跌修复"
    required_divergence_quality: str | None

    confirmation_conditions: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]

    # ---- 状态快照 ----
    leader_divergence_status: str
    leader_repair_status: str
    divergence_quality_ref: str    # -> DivergenceQuality

    # ---- 风险与仓位 ----
    risk_level: str           # low / medium / high / extreme
    position_suggestion: str  # 建议仓位表述（非精确百分比）

    # ---- 溯源 ----
    source_cycle_node_ref: str     # -> CycleNodeRecognition
    evidence_refs: tuple[str, ...]
    policy_version: str
```

### 7F.4 示例

机器人：

```text
TradingCognitionCard:
  subject: 机器人/减速器
  action_bias: wait
  left_side_allowed: false
  right_side_allowed: false
  next_entry_node: 龙头第一次良性分歧后修复
  required_divergence_quality: 缩量分歧，核心不破位，后排释放风险
  confirmation_conditions:
    - 核心股弱转强
    - 板块资金回流
    - 黄线继续共振
  invalidation_conditions:
    - 龙头放量破位
    - 板块批量跌停
    - 后排先于核心崩溃
  risk_level: medium
  position_suggestion: 分歧后右侧确认再考虑轻仓试探
```

通信/CPO：

```text
TradingCognitionCard:
  subject: 通信/CPO
  action_bias: left_probe
  left_side_allowed: true
  right_side_allowed: false
  next_entry_node: 分歧充分后的超跌修复
  required_divergence_quality: 低开恐慌释放但周期龙不继续破位
  confirmation_conditions:
    - 韩国半导体继续支撑
    - 光模块/存储核心止跌
    - 中报业绩方向出现承接
  invalidation_conditions:
    - 韩国冲高回落
    - 高位科技继续放量杀跌
  risk_level: high
  position_suggestion: 左侧轻仓试探，严格止损
```

---

## 7H. Historical Case Projection

### 7H.1 定位

分析师最核心的能力之一是：**"这个行情，我以前见过。"**

当前 M8 的 Hypothesis 生成直接走 Evidence → Hypothesis，缺少历史类比环节。`HistoricalCaseProjection` 在 Hypothesis 生成前插入 Case-based Reasoning 层：

```text
当前行情
  ↓
检索历史相似场景
  ↓
对齐差异（指数环境、量能、情绪、资金、外部）
  ↓
参考历史路径与结果
  ↓
校准当前概率
  ↓
Hypothesis
```

### 7H.2 与现有 Case Library 的关系

文档 Section 13 已定义了 `MarketCase`（完整认知链归档）。`HistoricalCaseProjection` 是对 Case Library 的**在线检索投影**：

| 维度 | MarketCase (Section 13) | HistoricalCaseProjection |
|---|---|---|
| 目的 | 完整归档、离线回放 | 当前决策时的相似检索 |
| 查询时点 | 事后 | 当前 `as_of`，只访问 `available_at <= as_of` 的数据 |
| 输出 | 案例完整链 | Top-K 相似案例 + 差异分析 + 路径参考 |

### 7H.3 契约

```python
@dataclass(frozen=True, slots=True)
class HistoricalCaseProjection:
    projection_id: str
    trade_date: date
    as_of: datetime
    query_context_hash: str      # 当前 Context 的 hash（防止用未来数据检索）

    top_k_cases: tuple[SimilarCase, ...]
    # 按 similarity 降序，最多 K 个（建议 K ≤ 5）

    ensemble_conclusion: str     # 综合历史案例的结论
    ensemble_confidence: float   # 综合置信度（不能是 similarity 平均）

    evidence_refs: tuple[str, ...]
    policy_version: str
    retrieval_model_version: str

@dataclass(frozen=True, slots=True)
class SimilarCase:
    case_id: str                # -> MarketCase.case_id
    similarity: float           # 0-1，综合相似度
    similar_dimensions: tuple[str, ...]
    # market_fsm / emotion / theme_structure / leader_state /
    # capital_rotation / belief_trajectory / cycle_node / external_context
    different_dimensions: tuple[str, ...]
    # 相同维度的差异描述，如 "当前指数弱 vs 历史指数强"

    historical_path: tuple[str, ...]
    # 该案例后续的关键节点序列，如 ["CLIMAX_D4", "FIRST_DIVERGENCE_D1", "WEAK_TO_STRONG_D2"]

    historical_outcome: str     # 该案例的最终结果摘要
    success: bool | None        # 该案例的 Hypothesis 是否正确

    applicable_lessons: tuple[str, ...]
    invalid_transfer_risks: tuple[str, ...]
    # 为什么当前情况可能不适用该历史案例

    transfer_confidence: float  # 0-1，该案例可迁移到当前的可信度
    # 不是 similarity，而是扣除差异惩罚后的迁移可信度
```

### 7H.4 相似度计算维度

```text
retrieval_vector = [
    market_fsm_state,
    emotion_vector,
    theme_structure(leading_themes, theme_count, concentration),
    cycle_node_distribution,
    leader_state(leader_count, leader_strength),
    capital_rotation_direction,
    external_market_direction,
    volume_trend,
    index_position
]

# 关键约束：
# - 所有特征必须来自 available_at <= query_as_of 的数据
# - Outcome 标签绝对禁止进入检索向量
# - 检索结果必须记录查询时点的特征快照
```

### 7H.5 示例

```text
当前：机器人高潮 D4，指数缩量弱，黄线强于白线

Top-K:
  1. DeepSeek 2025-04
     similarity: 0.91
     similar: [高潮D4, 黄线共振, 机构认可, 消息催化]
     different: [当前指数弱 vs 历史指数强]
     historical_path: [CLIMAX_D4 → FIRST_DIVERGENCE_D1 → WEAK_TO_STRONG → SECOND_WAVE]
     transfer_confidence: 0.78
     applicable_lessons:
       - 高潮第4天不宜追高
       - 第一次分歧若缩量且核心不破位，是左侧观察节点
     invalid_transfer_risks:
       - 历史指数强支撑，当前指数弱势 → 上涨空间预计降低
       - 如果指数继续走弱可能压缩修复空间

  2. 机器人 2024-06
     similarity: 0.88
     ...

  3. AI Agent 2025-09
     similarity: 0.84
     ...

  4. 商业航天 2025-07
     similarity: 0.80
     different: [外围刺激 vs 内生催化]
     historical_path: [CLIMAX → FADE(直接A杀)]
     transfer_confidence: 0.62
     invalid_transfer_risks:
       - 历史是纯消息驱动，机器人有机构资金
       - 但如消息兑现后无增量，需要警惕
```

### 7H.6 关键约束

- **Outcome 隔离**：检索向量禁止使用未来 Outcome 标签。相似度基于"当时状态"，不是"事后结果"
- **差异维度强制输出**：不能只输出 `similarity=0.91`，必须输出不同维度
- **transfer_confidence ≠ similarity**：transfer_confidence 必须在 similarity 基础上扣除差异惩罚
- **高相似不可覆盖当前 Evidence**：即使检索到 `similarity=0.95` 的案例，当前 Evidence 仍优先
- **历史路径仅供参考**：`historical_path` 不直接进入 Calibration。仅当路径对应 Hypothesis 被验证后，该案例的 `success` 标记才能更新

---

## 7I. Expectation Projection

### 7I.1 定位

真正决定分析师水平的是**预期差（Expectation Gap）**，而不是事实本身。

> 机器人今天涨停 → 不是重点。
> 市场原本预期分歧，结果继续高潮 → 这才是重点。

`ExpectationProjection` 对每个关键维度维护 Consensus → Actual → Surprise 三元组，将预期差显式化为可审计的结构化对象。

### 7I.2 契约

```python
@dataclass(frozen=True, slots=True)
class ExpectationProjection:
    projection_id: str
    trade_date: date
    as_of: datetime

    items: tuple[ExpectationItem, ...]
    # 至少覆盖：market / theme / leader / external / earnings / volume

    aggregate_surprise: float    # -5 到 +5，全市场综合预期差
    surprise_direction: str      # positive / negative / mixed / neutral

    evidence_refs: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class ExpectationItem:
    item_id: str
    subject_type: str           # market / theme / stock / leader / external / volume / emotion
    subject_id: str
    subject_name: str

    consensus: str              # 市场共识预期（前一日或盘前形成）
    consensus_source: str       # prior_hypothesis / analyst_consensus / model_prior / market_pricing
    
    expected: str               # 系统预期（具体可观测的预期值）
    actual: str                 # 实际结果
    surprise: int               # -5 到 +5
    
    # -5: 严重负面预期差（预期强修复，实际加速杀跌）
    # -3: 明显负面预期差
    # -1: 轻微负面预期差
    #  0: 符合预期
    # +1: 轻微正面预期差
    # +3: 明显正面预期差
    # +5: 严重正面预期差（预期跌停，实际涨停）

    expectation_shift: str      # 预期如何被修正：reinforced / weakened / reversed / unchanged
    
    impact_on_hypothesis: str   # 该预期差对活跃 Hypothesis 的影响
    evidence_refs: tuple[str, ...]
```

### 7I.3 示例

```text
Expectation Items:
  
  1. 机器人/减速器:
     consensus: 高潮后即将分歧
     expected: 龙头走弱、板块内部分化
     actual: 继续高潮、兆威机电/雷赛智能晋级
     surprise: +2
     expectation_shift: reinforced
     # 连续超预期 → 市场对机器人的共识正在从"轮动反弹"转向"新主线确立"
     impact_on_hypothesis: 分歧预期推迟但不消除，
       高潮越久后续分歧可能越剧烈

  2. 韩国半导体/HBM:
     consensus: 韩国企稳→A股存储/HBM修复
     expected: HBM/存储小幅修复
     actual: 韩国继续大跌
     surprise: -3
     expectation_shift: reversed
     impact_on_hypothesis: 07-02 修复假设被外部冲击打断

  3. 市场量能:
     consensus: 量能维持
     expected: 成交额与昨日持平
     actual: 萎缩 7.77%
     surprise: -2
     expectation_shift: weakened
     impact_on_hypothesis: 缩量环境降低所有修复概率

  4. 中报业绩:
     consensus: 光模块业绩超预期支撑趋势
     expected: 中际旭创/新易盛业绩预告
     actual: 尚未披露
     surprise: 0
     expectation_shift: unchanged
```

### 7I.4 预期差的来源与消费

**Consensus 来源优先级**：
1. 昨日活跃 Hypothesis 的 expected_observations
2. `CycleNodeRecognition` 的 `expected_next_nodes` 中最高概率路径
3. `HistoricalCaseProjection` 中 Top-1 案例的 historical_path
4. 市场定价隐含预期（期货、期权、竞价）
5. LLM 提议的待审核预期（标记为 `consensus_source=llm_draft`）

**Surprise 的消费路径**：
- `surprise >= +2`：检查 Hypothesis 是否过于保守 → 可能触发 `REVISED`
- `surprise <= -3`：检查 Hypothesis 是否被外部冲击否定 → 可能触发 `REJECTED` (UNEXPECTED_EVENT)
- `surprise == 0`：预期被确认 → 增强对应 Hypothesis 的 posterior
- 大面积 `surprise != 0` 说明市场认知框架需要检讨（→ 触发 Meta Cognition）

### 7I.5 约束

- Consensus 必须在盘前冻结，不允许盘后用 Actual 反向修改 Consensus
- `consensus_source` 必须记录，`model_prior` 和 `llm_draft` 不可混用
- 预期差不直接进入 Calibration，但 `surprise` 值作为 Hypothesis 验证的辅助上下文
- 连续 N 天 `surprise >= 3` 或 `surprise <= -3` 触发 World Model 审视

---

## 7J. Node Maturity Estimation

### 7J.1 定位

`CycleNodeRecognition` (7E) 回答"现在在哪个节点"。`NodeMaturityEstimation` 回答**"距离下一节点还有多远"**。

这两个区别就是：

```text
CycleNodeRecognition:    CLIMAX
NodeMaturityEstimation:  CLIMAX, 成熟度 82%
                         Crowding 91%, Volume 83%, Emotion 95%
                         Leader Healthy
                         → FIRST_DIVERGENCE probability: 72%
                         → estimated arrival: 1-2 trading days
```

### 7J.2 契约

```python
@dataclass(frozen=True, slots=True)
class NodeMaturityEstimation:
    estimation_id: str
    subject_type: str         # market / theme / leader
    subject_id: str
    trade_date: date

    current_node: str         # 引用 CycleNodeRecognition
    node_day: int             # 当前节点持续天数

    # ---- 成熟度子维度 (0-100) ----
    maturity_score: float     # 0-100，综合成熟度
    crowding_score: float     # 拥挤度
    volume_score: float       # 量能健康度
    leader_score: float       # 龙头健康度
    emotion_score: float      # 情绪极端度
    time_score: float         # 时间充分度

    quality_label: str        # accelerating / peaking / exhausting / stalling

    # ---- 下一节点 ----
    next_node_probability: float  # 0-1，短期（1-2 日）内迁移到下一节点的概率
    estimated_arrival: str        # "1_day" / "2_days" / "3_5_days" / "1_week_plus"
    
    expected_next_nodes: tuple[NodeTransitionEstimate, ...]

    evidence_refs: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class NodeTransitionEstimate:
    target_node: str
    probability: float        # 0-1
    maturity_threshold: float # 0-100，触发该迁移需要的成熟度阈值
    key_indicators: tuple[str, ...]
    evidence_refs: tuple[str, ...]
```

### 7J.3 成熟度计算公式

```text
maturity_score = weighted_sum(
    crowding_score × 0.25,     # 拥挤度：参与资金是否饱和
    volume_score × 0.20,       # 量能：缩量/放量是否健康
    leader_score × 0.25,       # 龙头：龙头是否健康
    emotion_score × 0.15,      # 情绪：情绪是否极端
    time_score × 0.15          # 时间：当前节点是否"到时间了"
)

其中：
  crowding:  连板股占比、涨停集中度、同向资金集中度 → 越高越接近转折
  volume:    量价配合度、缩量程度 → 缩量极致 = 变盘前夜
  leader:    龙头是否加速、是否分歧 → 龙头状态是节点迁移的最佳领先指标
  emotion:   贪婪/恐惧/犹豫的极端程度 → 极端情绪预示转折
  time:      当前节点天数 vs 历史同节点平均天数 → 时间窗口
```

### 7J.4 示例

```text
机器人:
  current_node: CLIMAX
  node_day: 4
  maturity_score: 82
  crowding_score: 91     ← 高度拥挤，涨停集中度极高
  volume_score: 83        ← 放量但未失控
  leader_score: 95        ← 龙头健康，尚未分歧
  emotion_score: 95       ← 情绪极度亢奋
  time_score: 60          ← D4 在历史 CLIMAX 中处于中位
  quality_label: peaking  ← 高潮见顶中
  
  next_node_probability: 0.72
  estimated_arrival: 1-2_days
  expected_next_nodes:
    - target: FIRST_DIVERGENCE, probability: 0.72
      maturity_threshold: 88
      key_indicators: [龙头首次分歧, 后排亏钱效应出现]
    - target: SECOND_ACCELERATION, probability: 0.18
    - target: FADE, probability: 0.10

通信/CPO:
  current_node: DIVERGENCE_WEAKENING
  node_day: 3
  maturity_score: 65
  crowding_score: 35      ← 资金已大幅流出
  volume_score: 72        ← 缩量止跌
  leader_score: 55        ← 周期龙仍有破位风险
  emotion_score: 45       ← 恐慌释放中
  time_score: 70          ← D3 分歧接近充分
  
  quality_label: exhausting
  next_node_probability: 0.55
  estimated_arrival: 2_days
```

### 7J.5 与 DivergenceQuality 和 TradingCognitionCard 的关系

```text
NodeMaturityEstimation.maturity_score >= threshold
  AND
DivergenceQuality.quality_label == "healthy"
  → TradingCognitionCard.left_side_allowed = true

NodeMaturityEstimation.maturity_score >= threshold
  AND
DivergenceQuality.quality_label == "healthy"
  AND
LeaderEvidence.weak_to_strong_confirmed == true
  → TradingCognitionCard.right_side_allowed = true
```

---

## 7K. 最终认知投影总链路（v1.4 完整版）

### 7K.1 分析师的五个核心问题

分析师每天不是简单看盘，而是持续回答五个问题：

| # | 问题 | M8 对应投影 |
|---|---|---|
| 1 | **Where are we?** 市场现在处于什么阶段？ | Multi-Horizon Context + CycleNodeRecognition |
| 2 | **Have I seen this before?** 历史上有没有类似场景？ | HistoricalCaseProjection |
| 3 | **What surprised?** 市场预期差在哪里？ | ExpectationProjection |
| 4 | **How mature is this node?** 距离下一次转折还有多远？ | NodeMaturityEstimation |
| 5 | **What happens next?** 下一步最可能迁移到哪个节点？ | Node Transition Hypothesis |

### 7K.2 v1.4 完整链路

```text
Layer A/B/C/D + DailyReviewV2
        │
        ▼
MarketKnowledgeBundle
        │
        ▼
MarketEvidenceSnapshot
        │
        ├──────────────────────────────────────────┐
        ▼                                          ▼
Multi-Horizon MarketContext (7B)         Market Cognition Graph (7C)
  D1/D3/D5/D10/D20 windows                + Dynamic Causal Chains (7C.6)
  + ExternalAnchorContext
  + EarningsSeasonContext
        │                                          │
        └────────────┬─────────────────────────────┘
                     ▼
              ThemeCognitiveCards (7D)
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
  CycleNode       Expectation  Historical
  Recognition     Projection   Case
  (7E)            (7I)         Projection (7H)
        │            │            │
        ▼            │            │
  Divergence        │            │
  Quality (7E.2)    │            │
        │            │            │
        └────────────┼────────────┘
                     ▼
            Node Maturity
            Estimation (7J)
                     │
                     ▼
            Trading Cognition
            Cards (7F)
                     │
                     ▼
            Node Transition
            Hypothesis (9.7)
                     │
                     ▼
            MarketThesisSnapshot
                     │
                     ▼
            Validation Dataset
```

### 7K.3 从"市场指标"到"市场世界观"

这次升级的本质不是新增数据结构，而是系统认知方式的范式转换：

```text
旧：Indicator（指标）
  今天成交额多少？
  今天涨停多少只？
  今天机器人强不强？

新：World Model（世界观）
  机器人已经高潮第四天 → 成熟度 82%
  韩国半导体今天大跌 → 预期差 -3
  资金开始从 PCB 撤退 → 因果链：韩国 → HBM → PCB → 机器人
  中报开始进入兑现窗口 → 业绩锚定
  指数缩量、黄线强于白线 → 跷跷板效应
  →
  历史相似：DS 2025-04 (相似度 0.91)，但指数环境更弱
  →
  机器人今天不能追，等第一次分歧。
  如果分歧健康（缩量+核心不破位+后排释放），
  后天可能出现弱转强。
```

这正是**市场认知操作系统（Market Cognitive Operating System）**的雏形。

### 7K.4 不变量保证

1. Phase 0 (GA) 和 Phase 1 (Validation) 链路完整保留
2. 全部 Cognition Projections 落在 `MarketContextSnapshot` / `MarketReasoningSnapshot` / `CognitionState` 内部
3. 不新增顶层 Engine，不破坏现有分层架构
4. 所有投影 append-only，携带 `as_of` 和 `source_snapshot_ids`
5. Semantic Contract（文档 3.1.1）严格执行：Observation/Assessment → Report only；仅 eligible Hypothesis → Dataset

### 7K.5 分阶段实施路线

Step 0 — Schema Freeze（1-2 天）：
- 冻结以上全部 dataclass 定义
- 新增 ADR-M8-010（Cognition Projection 不是 Engine）
- 新增 ADR-M8-011（Node Transition Hypothesis）
- 新增 ADR-M8-012（Causal Chain 与 Cognition Graph 关系）
- 新增 ADR-M8-013（Historical Case 检索必须隔离 Outcome）
- 新增 ADR-M8-014（Expectation Consensus 盘前冻结、不可事后修改）
- 新增 ADR-M8-015（Node Maturity 不作为 Calibration 目标）
- 与现有 `MarketThesisValidationRecord` 做兼容性检查

Step 1 — Multi-Horizon Context（先做 D1/D3/D5/D10/D20）：
- 验收：每个核心题材输出阶段天数，识别连续分歧/修复/加速
- Replay hash 稳定，不改变 Decision

Step 2 — Cognition Graph + Causal Chain：
- 先输出静态关系图，再增量加入动态因果链
- 验收：每条边有 EvidenceRef，每条因果链有至少一条替代链

Step 3 — Cycle Node + Divergence Quality + Node Maturity：
- 先定位当前节点，再估计成熟度
- 验收：每个核心题材有节点定位和成熟度评分

Step 4 — Expectation Projection + Historical Case Projection：
- Expectation 的 Consensus 必须先于 Actual 冻结
- Historical Case 检索必须 Outcome 隔离
- 验收：预期差不事后修改，历史检索无未来数据泄漏

Step 5 — Theme Cognitive Card + Trading Cognitive Card：
- 聚合以上所有投影
- 先不参与决策，只进入 Notion shadow

Step 6 — Node Transition Hypothesis：
- 所有进入 Dataset 的命题必须是 Node Transition 类型
- Brier/ECE 只统计节点迁移命题

### 7K.6 新增关键 KPI

| KPI | 目的 |
|---|---|
| Hypothesis Generation Rate | 每日生成 ≥3 条可验证 Node Transition 命题 |
| Node Recognition Coverage | 核心题材 100% 有节点定位 |
| Node Maturity Accuracy | 成熟度评分与实际转折时间的相关性 |
| Transition Accuracy | 节点迁移方向判断正确率 |
| Divergence Quality Accuracy | 分歧质量判断正确率 |
| Left-side Hit Rate | 左侧先手节点有效性 |
| Right-side Hit Rate | 右侧确认节点有效性 |
| Expectation Surprise Calibration | Surprise 绝对值与后续市场波动的相关性 |
| Historical Transfer Precision | 历史案例迁移判断的正确率（transfer_confidence vs 实际结果） |
| Causal Chain Verification | 因果链被后续 Evidence 确认/否定的比例 |
| External Anchor Precision | 外围影响判断准确率 |
| Cross-theme Relation Accuracy | 轮动/竞争/共振判断准确率 |

---

## 7L. M9 Bridge — 预留接口（v1.5 Frozen, M9 Growth Path）

> **阅读指引**：本节是 v1.5 Core Contract 的冻结附录。以下六个 Projection 和三个升级方向**不属于当前 M8 实施范围**，而是为 M9 Market Intelligence System 预留的契约接口。
> 它们的 dataclass 定义、字段语义和与其他对象的关联在此冻结，确保未来 M9 在 M8 基础上自然生长，而非推倒重来。
> M9 启动前，每项必须通过独立 ADR、Replay 验证和真实交易日评估。

### 7L.1 优先级矩阵

| 优先级 | 接口 | 理由 |
|---|---|---|
| P0 (M9 首批) | **BeliefProjection** | Evidence → Hypothesis 之间缺失的信念层；M9 Meta Cognition 全部依赖它 |
| P0 (M9 首批) | **AttentionProjection** | 市场注意力迁移是轮动预测的最领先指标 |
| P1 | **CausalNetwork** | 线性因果链升级为 DAG，支撑 Graph Search 和 Counterfactual |
| P1 | **CaseTrajectory** | 历史案例从静态快照升级为序列演化 |
| P2 | **MaturityVelocity / Acceleration** | 节点成熟度的一阶/二阶导数 |
| P2 | **Multi-layer Expectation** | 不同参与者的预期层分离 |
| P3 | **M9 完整链路** | Belief → Goal → Attention → Hypothesis 全链 |

---

### 7L.2 BeliefProjection

#### 定位

当前架构中，Section 8 定义了 `BeliefState`，但它仍然是"盘后快照"，不是"连续维护的信念状态投影"。真正的大脑运行方式：

```text
Evidence 增强，但 Belief 没有变 → 为什么？
Evidence 一般，Belief 突然增强 → 因为历史案例或预期差？
多个 Evidence 指向同一方向，但 Belief 仍低 → 有什么冲突？
```

`BeliefProjection` 将 Belief 从"Snapshot 结果"升级为"可解释的状态迁移过程"。

#### 契约（预留）

```python
@dataclass(frozen=True, slots=True)
class BeliefProjection:
    projection_id: str
    trade_date: date
    as_of: datetime

    # ---- 信念快照 ----
    belief_snapshot_id: str          # -> BeliefState
    
    # ---- 信念变化归因 ----
    belief_score: float              # 0-100
    belief_direction: str            # strengthening / weakening / stable / volatile
    belief_delta: float              # vs 前一日
    belief_momentum: float           # 连续变化的速率
    
    # ---- 信念来源分解 ----
    evidence_contribution: float     # Evidence 更新对 belief 的贡献
    historical_contribution: float   # HistoricalCaseProjection 对 belief 的贡献
    expectation_contribution: float  # ExpectationProjection (surprise) 对 belief 的贡献
    graph_contribution: float        # CausalChain/Network 对 belief 的贡献
    prior_contribution: float        # 先验信念的惯性
    
    # ---- 冲突与不确定性 ----
    belief_conflicts: tuple[BeliefConflict, ...]
    uncertainty: float               # 信念的不确定性（不是 probability）
    divergence_among_sources: float  # 不同来源的分歧程度
    
    evidence_refs: tuple[str, ...]
    policy_version: str
```

#### 关键约束

- `belief_score` 不等于 `prediction_probability`。Belief 是主观确信度，probability 是事前事件概率
- `evidence_contribution + historical_contribution + expectation_contribution + graph_contribution + prior_contribution` 应大致解释 belief_delta
- 冲突大的 Belief 是高价值认知信号（→ Meta Cognition）
- BeliefProjection 本身不进入 Calibration；Calibration 只针对 Hypothesis

---

### 7L.3 AttentionProjection

#### 定位

不是 Transformer 的 Attention，而是**市场注意力分配**。分析师天天在看：

```text
机器人：所有人都在看（Attention 95）
PCB：没人看，但正在悄悄启动（Attention 15→32）
军工：开始有人关注（Attention 42→50）
消费：完全被忽略（Attention 5）
```

注意力迁移是题材轮动的最领先指标。当 Attention 还在机器人高位时，PCB 的 Attention 已经从 15 爬到 32 —— 这是轮动的前兆。

#### 契约（预留）

```python
@dataclass(frozen=True, slots=True)
class AttentionProjection:
    projection_id: str
    trade_date: date
    as_of: datetime

    items: tuple[ThemeAttention, ...]
    # 按 attention_score 降序排列
    
    attention_concentration: float  # Top-3 占比（0-1），越高说明注意力越集中
    attention_entropy: float        # 注意力分布熵，越高说明越分散
    attention_drift: tuple[AttentionDrift, ...]  # 本周注意力迁移事件
    
    evidence_refs: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class ThemeAttention:
    theme_id: str
    theme_name: str
    attention_score: float          # 0-100，综合注意力
    attention_delta: float          # vs 前一日
    attention_velocity: float       # 注意力变化速率（连续 N 日）
    
    # 注意力分项来源
    media_attention: float          # 媒体/舆情
    capital_attention: float        # 资金流向
    volume_attention: float         # 成交活跃度
    social_attention: float         # 社交/论坛讨论度
    institutional_attention: float  # 机构调研/评级
    
    # 注意力状态
    status: str                     # surging / stable / fading / ignored / awakening
    # awakening = 从低注意力开始持续上升（≤32但velocity>0 且连续上升）


@dataclass(frozen=True, slots=True)
class AttentionDrift:
    from_theme_id: str
    to_theme_id: str
    drift_strength: float           # 0-1
    started_at: date
    evidence_refs: tuple[str, ...]
```

#### 关键洞察

```text
Attention 状态转换的商业含义：

ignored (0-15)    → 无人区。低位埋伏机会。
awakening (15-35)  → 开始被注意到。这是最早的轮动信号。
surging (35-70)    → 加速关注。确认轮动方向。
peaking (70-100)   → 过度关注。反向信号。
fading (下降中)     → 注意力退潮。旧主线让位。
```

#### 约束

- Attention 不等同于 Belief。高 Attention + 低 Belief = 噪音；低 Attention + 高 Belief = 被忽视的机会
- Attention 不直接生成交易信号；它只是帮助系统分配认知资源
- M9 的 Attention Engine（Section 29）将消费这个投影来分配 LLM token / 深度推理 / 人工复核预算

---

### 7L.4 CausalNetwork（从 CausalChain 升级）

#### 定位

`CausalChain` (7C.6) 描述线性因果：A → B → C → D。但真实市场是网状因果：

```text
              韩国
           ↙      ↘
        HBM      AI服务器
         ↓           ↓
        PCB        CPO
          ↘       ↙
           机器人
```

这是 **Directed Acyclic Graph (DAG)**，不是 Chain。Chain 负责**解释**（向人类呈现因果故事），Network 负责**推理**（Graph Search、Counterfactual、What-if）。

#### 契约（预留）

```python
@dataclass(frozen=True, slots=True)
class CausalNetwork:
    network_id: str
    trade_date: date
    as_of: datetime

    nodes: tuple[CausalNode, ...]   # 引用 CognitionNode
    edges: tuple[CausalEdge, ...]   # 有向边，带因果强度和时滞
    
    # 网络分析
    root_causes: tuple[str, ...]    # 入度为0的节点（源头变量）
    terminal_effects: tuple[str, ...]  # 出度为0的节点（最终结果）
    critical_paths: tuple[CausalPath, ...]  # 最长/最强因果路径
    
    # Graph Search 能力
    downstream_effects: Callable[[str], tuple[str, ...]]
    # 给定一个节点，返回所有下游影响（BFS/DFS）
    upstream_causes: Callable[[str], tuple[str, ...]]
    # 给定一个节点，返回所有上游原因
    
    counterfactual_basis: tuple[InterventionNode, ...]
    # 预标注的关键干预节点（可做反事实实验的节点）
    
    evidence_refs: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True, slots=True)
class CausalPath:
    path_id: str
    steps: tuple[str, ...]          # 有序节点序列
    total_effect_strength: float    # 路径总效应（乘法叠加）
    bottleneck_nodes: tuple[str, ...]  # 路径上的关键瓶颈
    alternative: bool               # 是否为主要路径的替代路径
```

#### CausalChain vs CausalNetwork

| 维度 | CausalChain (7C.6) | CausalNetwork (7L.4) |
|---|---|---|
| 结构 | 线性链 | DAG |
| 用途 | 解释（向人呈现因果故事） | 推理（Graph Search, Counterfactual, What-if） |
| 复杂度 | O(n) | O(n²) |
| 实施阶段 | M8 Phase 2 | M9 Phase 2+ |
| 节点数 | ≤10 per chain | ≤100 per network |

---

### 7L.5 CaseTrajectory

#### 定位

`HistoricalCaseProjection` (7H) 将历史案例检索为静态 Top-K 快照。但真正的分析师不是回忆一个静态切片，而是回放整个演化过程：

```text
DS 案例不是 "DS 高潮 D4"
而是：
  DS 启动 → 发酵 D2 → 加速 D3 → 高潮 D4 → 第一次分歧 D1 →
  分歧修复 D1 → 弱转强 D2 → 二波加速 → 二波高潮 → 退潮
```

`CaseTrajectory` 将案例从 `Snapshot` 升级为 `Sequence`，为未来 Transformer / Sequence Matching 奠定基础。

#### 契约（预留）

```python
@dataclass(frozen=True, slots=True)
class CaseTrajectory:
    trajectory_id: str
    case_id: str                   # -> MarketCase.case_id
    trade_date_range: tuple[date, date]

    # ---- 状态序列 ----
    state_sequence: tuple[TrajectoryState, ...]
    # 每日的 market_fsm / emotion / theme_structure / cycle_node
    
    transition_sequence: tuple[NodeTransition, ...]
    # 每个节点迁移的时间点和特征
    
    belief_sequence: tuple[float, ...]
    # 每日的 belief_score（如果案例有对应 M8 数据）
    
    capital_sequence: tuple[CapitalSnapshot, ...]
    # 每日的资金流向快照
    
    # ---- 序列匹配 ----
    key_inflection_points: tuple[InflectionPoint, ...]
    # 关键转折点（趋势改变的位置）
    
    trajectory_signature: str      # 序列的压缩签名（用于快速粗筛）


@dataclass(frozen=True, slots=True)
class TrajectoryState:
    trade_date: date
    market_fsm: str
    emotion_vector: tuple[float, ...]   # [greed, fear, hesitation, fomo, confidence]
    theme_structure: str
    cycle_node: str
    volume_trend: str
    capital_rotation_direction: str


@dataclass(frozen=True, slots=True)
class InflectionPoint:
    inflection_id: str
    trade_date: date
    from_state: str
    to_state: str
    trigger_type: str              # divergence / repair / climax / external / earnings
    pre_inflection_signals: tuple[str, ...]  # 转折前的可观测信号
```

#### 未来能力

- **Trajectory Matching**：不是 "相似度 0.91"，而是 "当前前 4 天的演化轨迹与 DS 案例前 4 天高度重合，且都在 D4 出现分歧信号"
- **Inflection Point 识别**：训练模型识别"转折前信号"
- **Sequence Generation**：基于当前轨迹，生成可能的未来演化路径

---

### 7L.6 MaturityVelocity & MaturityAcceleration

#### 定位

`NodeMaturityEstimation` (7J) 输出静态成熟度：`maturity_score = 82`。但分析师真正看的是**成熟度的变化率**：

```text
成熟度 昨天 55 → 今天 82 → 快速成熟 → 危险（即将转折）
成熟度 昨天 80 → 今天 81 → 缓慢成熟 → 安全（仍有参与时间）
```

一阶导数（Velocity）告诉系统"节点在加速成熟还是减速"，二阶导数（Acceleration）告诉系统"成熟速度本身在加快还是放缓"。

#### 契约（预留）

```python
@dataclass(frozen=True, slots=True)
class MaturityDynamics:
    dynamics_id: str
    subject_id: str
    trade_date: date

    maturity_score: float          # 当前成熟度 (7J)
    
    # ---- 一阶导数：成熟度变化率 ----
    maturity_velocity: float       # dmaturity/dt (per trading day)
    velocity_direction: str        # accelerating / decelerating / steady
    velocity_smoothed: float       # N 日平滑后的速度
    
    # ---- 二阶导数：成熟度加速度 ----
    maturity_acceleration: float   # d²maturity/dt²
    acceleration_direction: str    # speeding_up / slowing_down / constant
    
    # ---- 转折预测 ----
    estimated_days_to_threshold: float | None
    # 如果 velocity > 0，预测多少天达到 maturity_threshold
    inflection_likelihood: float   # 0-1，短期内发生节点迁移的概率
    inflection_window: str         # "1_day" / "2_days" / "3_5_days" / "unknown"
    
    # ---- 历史对标 ----
    historical_velocity_profile: str  # 引用 CaseTrajectory 中的相似速度曲线
    
    evidence_refs: tuple[str, ...]
```

#### 示例

```text
机器人:
  maturity_score: 82
  maturity_velocity: +11.3/day    ← 快速成熟！危险信号
  maturity_acceleration: +2.1     ← 还在加速！
  velocity_direction: accelerating
  estimated_days_to_threshold: 0.7 → 明天就触发
  inflection_likelihood: 0.94

通信/CPO:
  maturity_score: 65
  maturity_velocity: +2.5/day     ← 缓慢成熟
  maturity_acceleration: -0.5     ← 减速中
  velocity_direction: decelerating
  estimated_days_to_threshold: 9.2 → 还有时间
  inflection_likelihood: 0.38
```

---

### 7L.7 Multi-layer Expectation

#### 定位

`ExpectationProjection` (7I) 只有一个 Consensus。但真实市场不同参与者持有不同预期：

```text
散户预期：机器人在涨，继续涨（momentum bias）
机构预期：机器人高潮后兑现，转向低位科技（rotation bias）
游资预期：高潮中只做核心，分歧即撤离（concentration bias）
宏观预期：韩国拖累半导体，科技整体承压（external bias）
```

`MultiLayerExpectation` 将共识拆解为参与层，分别追踪每层的预期和预期差，然后融合为综合 Consensus。

#### 契约（预留）

```python
@dataclass(frozen=True, slots=True)
class MultiLayerExpectation:
    projection_id: str
    trade_date: date
    as_of: datetime

    layers: tuple[ExpectationLayer, ...]
    
    consensus: str                 # 加权融合后的综合共识（→ ExpectationProjection.consensus）
    layer_divergence: float        # 各层之间的预期分歧程度（0-1）
    dominant_layer: str            # 当前主导预期的层级
    
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpectationLayer:
    layer_type: str                # retail / institution / hot_money / macro / model
    layer_weight: float            # 该层在当前市场状态下的影响力权重
    
    direction: str                 # bullish / bearish / neutral
    conviction: float              # 该层对自身预期的坚定程度（0-1）
    
    key_themes: tuple[str, ...]    # 该层关注的核心题材
    expected_action: str           # buy / hold / reduce / rotate / wait
    
    surprise_vs_actual: int        # -5 to +5，该层的预期差
    
    evidence_refs: tuple[str, ...]
```

#### 融合规则（预留）

```text
consensus = weighted_majority(layers, weights=[
    institution × 0.35,     # 机构资金体量最大
    hot_money × 0.25,       # 游资方向判断最敏锐
    macro × 0.20,           # 宏观提供大背景
    retail × 0.15,          # 散户情绪是反向指标
    model × 0.05            # 模型作为校准
])

layer_divergence 高 → 市场处于分歧状态 → volatility 升高
dominant_layer 切换 → 市场风格转变 → 新的交易逻辑确立
```

---

### 7L.8 M9 完整链路接口

#### v1.5 Frozen 链路 → M9 生长路径

```text
【v1.5 已冻结 — M8 Cognition Projections】
Evidence → Context → Graph → History → Expectation → Maturity → Trading Card → Hypothesis

                              ↓ (M9 预留接口)
                              
【M9 Phase 1 — Belief & Attention】
BeliefProjection ← 聚合全部 Cognition Projections 的信念状态
AttentionProjection ← 市场注意力分配与迁移

                              ↓

【M9 Phase 2 — Goal & Planning】
Goal Manager ← Belief + Attention → 今日最需要弄清楚什么
Attention Engine ← Goal → 有限认知资源的分配

                              ↓

【M9 Phase 3 — Meta Cognition】
Cognitive Trace → Self Reflection → Diary → Learning

                              ↓

【M9 Phase 4 — World Model Update】
CaseTrajectory + CausalNetwork + MaturityDynamics
  → World Model Update Proposal
  → Replay → Shadow → Approval
```

#### M9 完整链路（预留）

```text
World Model
        │
        ▼
Belief Projection ──────────────────────────┐
        │                                     │
        ▼                                     │
Goal Manager                                  │
        │                                     │
        ▼                                     │
Attention Projection                          │
        │                                     │
        ▼                                     │
Multi-Horizon Context                         │
        │                                     │
        ▼                                     │
Cognition Graph + Causal Network              │
        │                                     │
        ├── Historical Case Projection ───────┤
        │   + CaseTrajectory                  │
        │                                     │
        ├── Expectation Projection ───────────┤
        │   + Multi-layer Expectation         │
        │                                     │
        ├── Cycle Node Recognition ───────────┤
        │   + Maturity + Velocity/Accel       │
        │                                     │
        ▼                                     │
Trading Cognition Cards                       │
        │                                     │
        ▼                                     │
Node Transition Hypothesis                    │
        │                                     │
        ▼                                     │
Strategy Selector → Risk Gate → Decision      │
        │                                     │
        ▼                                     │
Outcome → Diary → Self Reflection ────────────┘
        │
        ▼
Case Library + CaseTrajectory
        │
        ▼
World Model Update Proposal
```

---

### 7L.9 新增 ADR（M9 Bridge）

16. **ADR-M9-BRIDGE-001**：BeliefProjection 是 Evidence 与 Hypothesis 之间的信念中间层。Belief score ≠ prediction probability。Belief 变化归因必须可分解（evidence / historical / expectation / graph / prior）。Belief 本身不进入 Calibration。

17. **ADR-M9-BRIDGE-002**：AttentionProjection 描述市场注意力分配而非系统注意力分配。Attention ≠ Belief。高 Attention + 低 Belief = 噪音；低 Attention + 高 Belief = 被忽视的机会。

18. **ADR-M9-BRIDGE-003**：CausalNetwork（DAG）是 CausalChain 的超集。Chain 负责解释，Network 负责推理。Network 必须在 Chain 验证稳定后才引入。

19. **ADR-M9-BRIDGE-004**：CaseTrajectory 将历史案例从静态 Snapshot 升级为时间序列。Trajectory 匹配特征禁止包含未来 Outcome。

20. **ADR-M9-BRIDGE-005**：MaturityVelocity 和 MaturityAcceleration 是 NodeMaturity 的一阶和二阶导数。它们不作为独立 Calibration 目标；Calibration 仍只针对 Node Transition Hypothesis。

21. **ADR-M9-BRIDGE-006**：Multi-layer Expectation 的共识融合规则必须版本化且可回放。各层权重不可硬编码为常数，必须随市场状态动态调整。

22. **ADR-M9-BRIDGE-007**：M9 在 M8 v1.5 Frozen Contract 基础上生长。M9 不得修改 M8 已冻结的 dataclass 字段语义。新增字段以 Optional 扩展或独立 Projection 形式添加。

---

## 7M. 最终定位：从 Market Cognition 到 Market World Model

### 7M.1 范式转变

v1.5 冻结时刻，系统完成的不仅仅是架构升级，而是定位的根本转变：

```text
旧范式：Market Cognition Engine
  = 一个分析行情的引擎
  = Engine 是主体，市场是客体

新范式：Market World Model
  = 维护一个可推理、可验证、可演化的市场世界
  = 世界是主体，引擎只是世界内部的运行机制
```

这个转变的本质是：

```text
以前：系统"分析市场"
  输入 → 处理 → 输出报告

现在：系统"维护一个市场世界"
  市场状态 → 题材 → 龙头 → 资金 → 外围 → 预期 →
  历史 → 因果 → 信念 → 注意力 → 目标 → 假设
  =
  一个完整的 Market World
```

LLM 以后不需要查询数据库。它直接**进入这个世界**，在世界内部进行推理：

```text
LLM: "机器人现在什么状态？"
World: "CLIMAX D4, 成熟度 82%, 拥挤度 91%"

LLM: "历史上类似情况怎么走的？"
World: "DS 2025-04, 相似度 0.91, 但当前指数更弱"

LLM: "市场预期是什么？"
World: "共识预期分歧, 实际继续高潮, Surprise +2"

LLM: "那应该怎么办？"
World: "不追高, 等第一次分歧。如果缩量+核心不破位, 分歧后弱转强概率 72%"
```

### 7M.2 世界的构成

```text
                    Market World
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   World State      World Laws       World Dynamics
   (状态)           (规律)           (演化)
        │                │                │
   - 市场FSM        - 因果网络       - 节点迁移
   - 题材周期       - 历史案例       - 成熟度变化
   - 龙头状态       - 外部锚定       - 注意力迁移
   - 资金分布       - 业绩周期       - 预期差演化
   - 情绪向量       - 关系图         - 信念更新
   - 预期层         - 因果链         - 目标漂移
```

### 7M.3 M9 认知闭环

M9 不应围绕单个模块命名，而应围绕一个完整的认知闭环：

```text
                    Market World
                         │
                         ▼
                    World State
                  (世界当前状态)
                         │
                         ▼
                    Belief Update
                (信念如何被证据改变)
                         │
                         ▼
                    Goal Selection
              (今天最需要弄清楚什么)
                         │
                         ▼
                  Attention Allocation
              (有限认知资源投向哪里)
                         │
                         ▼
                  Mental Simulation
            (在当前世界模型中推演未来)
                         │
                         ▼
                  Scenario Ranking
              (哪个路径最可能、赔率最高)
                         │
                         ▼
                    Hypothesis
              (可证伪的节点迁移命题)
                         │
                         ▼
                     Decision
              (策略 + 风险 + 仓位)
                         │
                         ▼
                     Outcome
                  (世界如何回应)
                         │
                         ▼
                    Reflection
            (系统对自身认知过程的审计)
                         │
                         ▼
                World Model Update
          (从错误中学习；Proposal→Replay→Shadow→Approval)
                         │
                         └────────→ 回到 Market World
```

### 7M.4 与 M8 v1.5 Frozen Contract 的关系

这个闭环与已冻结的 M8 v1.5 Contract 完全兼容：

| M9 步骤 | M8 v1.5 对应 |
|---|---|
| Market World | 全部 Cognition Projections (7A-7K) + M9 Bridge (7L) |
| World State | MarketEvidenceSnapshot + Multi-Horizon Context |
| Belief Update | BeliefState (Section 8) + BeliefProjection (7L.2) |
| Goal Selection | MarketGoal (Section 28) |
| Attention Allocation | AttentionProjection (7L.3) + AttentionEngine (Section 29) |
| Mental Simulation | CausalNetwork (7L.4) + Counterfactual (Section 10) |
| Scenario Ranking | ScenarioPath (Section 11) + ExpectedNodeTransition (7E) |
| Hypothesis | Node Transition Hypothesis (9.7) |
| Decision | Strategy → Risk Gate → Portfolio (Section 38-42) |
| Outcome | MarketThesisValidationRecord (0.2) |
| Reflection | Meta Cognition (Section 43) + MarketDiary (Section 31) |
| World Model Update | UpdateProposal → Replay → Shadow → Approval (Section 27.7) |

M9 不是在 M8 旁边堆叠新模块，而是将 M8 已冻结的认知对象**串成环**，赋予它们时序、目标和学习能力。

### 7M.5 命名的意义

```text
"Market Cognition Engine"
  → 暗示：这是一个分析工具
  → 边界：Engine 是一个模块

"Market World Model"
  → 暗示：这是一个世界
  → 边界：World 包含一切
  → 其中 Engine、Projection、Hypothesis、Validation
    都只是世界内部的运行机制

未来：
  LLM 不查数据库
  交易员不读报告
  系统不做分析

  他们直接进入这个世界
  在世界中感知、推理、假设、决策、反思、进化
```

### 7M.6 体系命名约定

```text
M8 = Market World State Builder
     构建并维护市场世界的当前状态
     Evidence → Context → Graph → Card → Node → Expectation →
     History → Maturity → Trading Cognition → Hypothesis → Validation

M9 = Market World Intelligence Loop
     让这个世界"活起来"
     World State → Belief → Goal → Attention → Simulation →
     Scenario → Hypothesis → Decision → Outcome → Reflection → Update
```

此后所有模块评审，不追问"报告好不好看"，只追问：

> 这个模块是否让 Market World 更准确、更可解释、更可验证、更能演化？

---

## 7N. Phase 1.5 — Node Transition Backtest

### 7N.1 执行纪律

v1.5 Core Contract Frozen 之后，所有新增实现必须服务于 Node Transition Hypothesis：

> 这个字段/投影/指标/脚本是否提高了节点定位、节点成熟度、分歧质量或节点迁移假设的质量？

否则延期到 M9。

### 7N.2 Step 1 — 最小闭环（不碰 M9）

```text
Multi-Horizon Context
  → Cycle Node Recognition
  → Divergence Quality
  → Node Maturity
  → Node Transition Hypothesis
```

### 7N.3 Step 2 — 历史回测（先验证认知，不验证收益）

| 验证项 | 问题 |
|---|---|
| Node Recognition | 系统能否正确识别高潮、分歧、修复、退潮？ |
| Node Maturity | 成熟度高时，是否真的更接近转折？ |
| Divergence Quality | 良性分歧是否更容易修复？ |
| Node Transition | 昨天预测的节点迁移，今天是否发生？ |
| Timing Offset | 节点是否提前/滞后 1～2 天？ |

### 7N.4 Step 3 — 交易认知验证（认知稳定后）

```text
left_probe / right_confirm / wait / avoid / reduce
→ 是否符合历史行情
```

### 7N.5 v1.5 冻结确认

```text
☑ Core Contract Frozen — v1.5 (FINAL)
☑ 22 ADR (M8-001~009 + M8-010~015 + M9-BRIDGE-001~007)
☑ 10 Cognition Projections (7A-7K)
☑ 6 M9 Bridge Interfaces (7L)
☑ 3 核心对象 (MarketSubject / MarketWorldModel / PolicyRegistry)
☑ M8/M9 体系命名 (7M.6)
☑ Architecture Budget — Stable Core 冻结 (0.1~0.3)
☑ Phase 1.5 实施基线 (7N + docs/project_control/wbs_M8.phase1.5.md)
☑ 不再扩架构 — 进入 Market World State Verification
```

---

## 8. Layer 3：Market Belief Engine

### 8.1 定位

Belief 是系统对一个明确命题的当前确信程度，而不是客观事实，也不是市场强弱分。

示例命题：

- “机器人将在未来两个交易日完成分歧修复。”
- “PCB 正在接替通信成为当前科技主线。”
- “科技赛道退潮只是局部龙头破坏，不是系统性风险。”

### 8.2 Belief 契约

```python
@dataclass(frozen=True, slots=True)
class BeliefState:
    belief_id: str
    proposition_key: str
    subject_type: str
    subject_id: str
    statement: str
    prior_score: float
    posterior_score: float
    delta: float
    confidence: float
    support_refs: tuple[EvidenceRef, ...]
    counter_refs: tuple[EvidenceRef, ...]
    unresolved_conflicts: tuple["BeliefConflict", ...]
    update_policy_version: str
    as_of: datetime
```

### 8.3 Belief 更新

第一阶段采用可解释加权更新：

```text
evidence_weight
  = source_reliability
  × freshness
  × independence
  × relevance
  × data_quality

belief_delta
  = Σ supporting_weight
  - Σ counter_weight
  - contradiction_penalty

posterior
  = clamp(prior + calibrated_delta, 0, 100)
```

禁止把多个 Engine 的 confidence 直接平均。相同底层数据派生出的多个判断不独立，必须通过 `evidence_lineage` 去重，避免重复计票。

### 8.4 Belief Collapse

`Belief Collapse` 不是任意阈值下穿，而是以下组合：

1. posterior 低于策略阈值；
2. 至少一个预定义 falsifier 被触发；
3. 关键支持证据失效；
4. 不存在同等强度的新支持证据；
5. 数据质量达到可判定标准。

Collapse 触发假设重评和风险动作，但仍不能绕过全局 Risk Engine。

---

## 9. Layer 3：Hypothesis Engine

### 9.1 定位

Hypothesis Engine 是 M8 的跨日主轴。

它负责：

1. 从当前认知状态中提出可验证命题；
2. 定义验证窗口、期望观测和证伪条件；
3. 在新证据到达时持续评估；
4. 记录确认、拒绝、过期和修订；
5. 将修订关系形成可追踪的假设谱系。

### 9.2 MarketHypothesis 契约

```python
@dataclass(frozen=True, slots=True)
class MarketHypothesis:
    hypothesis_id: str
    hypothesis_type: str
    subject_type: str
    subject_ids: tuple[str, ...]
    statement: str
    rationale: str

    created_at: datetime
    valid_from: datetime
    evaluation_deadline: datetime
    expires_at: datetime

    prior_probability: float
    current_probability: float
    prediction_probability: float
    source_quality_score: float

    expected_observations: tuple["ExpectedObservation", ...]
    falsification_conditions: tuple["FalsificationCondition", ...]
    invalidation_conditions: tuple["InvalidationCondition", ...]

    support_refs: tuple[EvidenceRef, ...]
    counter_refs: tuple[EvidenceRef, ...]

    status: str
    parent_hypothesis_id: str | None
    revision_no: int
    superseded_by: str | None

    policy_version: str
    created_by: str
```

字段语义：

- `prediction_probability` 必须在 Hypothesis 冻结时产生，Reviewer 不得事后修改；
- `source_quality_score` 独立表达 Evidence/Reasoning 质量，不是事件概率；
- `evaluation_deadline` 必须来自 Trade Calendar Producer，禁止使用 `trade_date + 1自然日`；
- 只有 statement、deadline、prediction probability、expected observations、falsifiers、EvidenceRefs、policy version 全部存在，且 source quality 非 BLOCKED，Hypothesis 才具备 Validation Eligibility。

### 9.3 状态机

```text
DRAFT
  -> CREATED
  -> VALIDATING
      -> CONFIRMED
      -> REJECTED
      -> INCONCLUSIVE
      -> EXPIRED
      -> REVISED -> 新 hypothesis
      -> SUPERSEDED
```

不建议使用单一 `FAILED`：

- `REJECTED`：证据触发明确证伪条件；
- `INCONCLUSIVE`：窗口结束但证据不足；
- `EXPIRED`：命题失去时效；
- `SUPERSEDED`：被更精确的新命题替代。

### 9.4 假设必须可证伪

错误示例：

> 机器人可能变强。

合格示例：

> 在未来两个交易日内，如果机器人板块先完成缩量分歧，且核心股不跌破 10 日线，则机器人应出现相对全市场更强的修复；若板块继续放量下跌且核心股集体破位，则该假设被拒绝。

### 9.5 假设生成来源

优先级：

1. 昨日有效假设的延续或修订；
2. FSM 允许的状态转移；
3. Expectation Gap 的显著偏差；
4. Capital Rotation 的新方向；
5. Leader/Emotion Carrier 的迁移；
6. Case Library 的差异化候选；
7. LLM 提议的待审核候选。

LLM 生成的假设默认 `DRAFT`，必须经过结构验证和证据门禁后才能进入 `CREATED`。

### 9.6 评估结果

```python
class HypothesisEvaluation:
    hypothesis_id: str
    evaluation_as_of: datetime
    observed_expectations: tuple[str, ...]
    missed_expectations: tuple[str, ...]
    triggered_falsifiers: tuple[str, ...]
    probability_before: float
    probability_after: float
    status_before: str
    status_after: str
    evidence_refs: tuple[EvidenceRef, ...]
    trace: tuple[TraceStep, ...]
```

### 9.7 Node Transition Hypothesis

Node Transition Hypothesis 是 M8 从 Hypothesis Validator 升级为 Hypothesis Generator 的核心机制。它将 Hypothesis 从"笼统市场命题"升级为"可验证的周期节点迁移预测"。

**定位**：

当前假设示例（笼统）：

> 主线修复后，交易权限才具备重新评估条件。

升级后（节点迁移）：

```json
{
  "hypothesis_type": "NODE_TRANSITION",
  "subject": "机器人/减速器",
  "current_node": "CLIMAX",
  "expected_transition": "FIRST_DIVERGENCE",
  "deadline": "2026-07-04",
  "prediction_probability": 0.65,
  "expected_observations": [
    "板块不再继续一致加速",
    "前排核心出现分歧但不破位",
    "后排释放亏钱效应",
    "成交额放大但未失控"
  ],
  "falsifiers": [
    "龙头直接放量破位",
    "板块批量跌停",
    "机器人继续无分歧高潮",
    "资金完全切换到其他主线"
  ],
  "trading_condition": {
    "left_side": "分歧充分但核心不死",
    "right_side": "分歧后核心弱转强"
  }
}
```

**Eligibility 兼容性**：

Node Transition Hypothesis 完全符合 ADR-M8-009 的 Eligibility Gate：

- `hypothesis_type` 必须是 `NODE_TRANSITION`
- `statement`：由 `current_node -> expected_transition` 自动编译，但保留人工可读覆盖
- `deadline`：来自 Trade Calendar Producer
- `prediction_probability`：冻结时的事前估计
- `expected_observations`：节点迁移应出现的关键观测
- `falsifiers`：否定该节点迁移的明确条件
- `trading_condition`：进入 ThesisStatement（Report only），不进 Dataset

**Failure Type 语义精度**：

节点迁移假设使 Failure Type 获得更高分辨率：

| Failure Type | 节点迁移语义 | 示例 |
|---|---|---|
| `WRONG_DIRECTION` | 节点迁移方向判断错误 | 预期 FIRST_DIVERGENCE，实际 SECOND_ACCELERATION |
| `WRONG_TIMING` | 节点到达时间判断错误 | 预期当日分歧，实际次日才分歧 |
| `INSUFFICIENT_EVIDENCE` | 分歧质量不足以判定节点迁移 | 缩量不足、核心未确认守位 |
| `UNEXPECTED_EVENT` | 外部冲击打乱节点节奏 | 韩国暴跌改变A股科技赛道节奏 |
| `WRONG_THEME` | 判断了错误的题材节点 | 该题材实际不在该周期位置 |
| `MARKET_REGIME_SHIFT` | 全市场环境切换 | 系统性风险改变所有节点预期 |

**生成来源优先级**（在 9.5 节基础上补充）：

1. 昨日活跃 Hypothesis 的节点迁移延续或修订
2. `CycleNodeRecognition` 的 `expected_next_nodes` 中 probability 最高的迁移路径
3. `DivergenceQuality` 达到 `healthy` 或 `forced` 水平的题材
4. FSM 允许的状态转移（Section 7.1）
5. `MarketCognitionGraph` 中检测到的 capital_rotation / external_anchor 变化
6. `TradingCognitionCard` 中 `action_bias != wait` 且 `left_side_allowed or right_side_allowed` 的标的
7. Case Library 的差异化候选
8. LLM 提议的待审核候选（默认 DRAFT）

**验收标准**：

- 每日至少生成 1～3 条 eligible Node Transition Hypothesis
- 所有 eligible 命题必须通过 Eligibility Gate
- 进入 Ground Truth Dataset 的命题类型必须包含 `NODE_TRANSITION`
- Brier Score / ECE / Timing Offset 只统计节点迁移命题
- 笼统市场命题（无 current_node / expected_transition）不得进入 Dataset

---

### 10.1 定位

Counterfactual Engine 回答：

> 如果关键条件没有发生，当前结果是否仍可能出现？

它用于检验市场故事是否过度归因于单一事件，并为假设准备替代解释。

### 10.2 反事实可信等级

由于市场数据大多是观察数据，必须区分：

| 等级 | 名称 | 含义 |
|---|---|---|
| CF-0 | Narrative Alternative | 仅提出替代解释，不做量化结论 |
| CF-1 | Sensitivity Test | 改变输入后重算模型，表示模型敏感度 |
| CF-2 | Matched Historical Estimate | 使用相似历史样本估算 |
| CF-3 | Causal Estimate | 有明确因果图、识别假设和稳健性验证 |

Phase 1/2 只允许输出 CF-0/CF-1。没有因果识别条件时，禁止使用“因为”“导致”的确定性措辞。

### 10.3 契约

```python
@dataclass(frozen=True, slots=True)
class CounterfactualAssessment:
    assessment_id: str
    target_hypothesis_id: str
    question: str
    intervention: str
    held_constant: tuple[str, ...]
    assumptions: tuple[str, ...]
    method: str
    credibility_level: str
    observed_outcome: str
    counterfactual_outcome: str
    outcome_delta: float | None
    confidence: float
    evidence_refs: tuple[EvidenceRef, ...]
    limitations: tuple[str, ...]
```

### 10.4 示例

问题：

> 如果机器人龙头没有炸板，PCB 是否仍会成为资金承接方向？

Phase 1 可执行：

1. 将“龙头炸板”特征替换为中性值；
2. 保持市场量能、PCB 资金流、PCB 前排强度不变；
3. 重算 Capital Rotation 与 Theme Belief；
4. 若 PCB Belief 仍显著上升，则说明“PCB 接棒”并不完全依赖机器人龙头炸板；
5. 输出 `CF-1 Sensitivity Test`，不宣称真实因果。

---

## 11. Layer 4：Scenario、Risk 与 Action

### 11.1 ScenarioPath

Scenario 不再每天凭空生成，而是由活跃 Hypothesis 派生：

```python
class ScenarioPath:
    scenario_id: str
    source_hypothesis_ids: tuple[str, ...]
    name: str
    probability_weight: float
    if_conditions: tuple[str, ...]
    expected_market_state: str
    expected_theme_changes: tuple[str, ...]
    confirmation_triggers: tuple[str, ...]
    invalidation_triggers: tuple[str, ...]
    recommended_action_ids: tuple[str, ...]
```

至少包含：

- Base：当前最高 Belief 路径；
- Bull：关键正向条件成立；
- Bear：关键假设被拒绝；
- Alternative：替代主线或风格切换。

### 11.2 Risk Engine

风险拥有硬优先级，不参与 Belief 加权平均：

```text
data_quality_block
global_no_trade_gate
liquidity_risk
sentiment_collapse
theme_fade_confirmed
stock_invalidation
position_limit
```

即使某主题 Belief 很高，全局 `no_trade` 仍可阻止开仓。

### 11.3 Action Engine

Action 必须引用：

- `hypothesis_id`
- `scenario_id`
- `belief_snapshot_id`
- `risk_assessment_id`
- 触发条件；
- 失效条件；
- 仓位上限；
- 有效时间。

---

## 12. Layer 5：Market Narrative

### 12.1 定位

Market Narrative 不是自由文本，而是可验证的结构化市场故事。

它回答：

```text
Yesterday: 我们原来相信什么？
Today: 哪些证据确认或拒绝了它？
Change: 信念发生了什么变化？
Now: 当前最可信的市场解释是什么？
Tomorrow: 哪些条件将确认或推翻下一步判断？
```

### 12.2 契约

```python
@dataclass(frozen=True, slots=True)
class MarketNarrative:
    narrative_id: str
    trade_date: date
    headline: str

    previous_beliefs: tuple["NarrativeBelief", ...]
    hypothesis_results: tuple["NarrativeHypothesisResult", ...]
    key_evidence_changes: tuple["EvidenceChange", ...]
    current_story: str
    alternative_story: str | None

    theme_chapters: tuple["ThemeNarrative", ...]
    tomorrow_scenarios: tuple[ScenarioPath, ...]
    action_summary: str
    risk_summary: str

    evidence_refs: tuple[EvidenceRef, ...]
    source_snapshot_ids: tuple[str, ...]
    compiler_version: str
```

### 12.3 Narrative Compiler

Narrative Compiler 是确定性的结构编排器：

1. 选择 Belief delta 最大的命题；
2. 选择已确认、已拒绝和新建立的核心假设；
3. 选择对决策有影响的证据变化；
4. 生成 story graph；
5. 由模板或 LLM Verbalizer 转为人话；
6. 对生成文本做数字、实体、证据引用校验。

LLM 不决定故事主轴，只负责表达。

### 12.4 目标 Notion 阅读结构

```text
# 盘后复盘

## 1. 今日认知结论
一句话故事
交易权限 / 风险 / 仓位

## 2. 昨日假设验证
假设 | 昨日概率 | 今日概率 | 结果 | 关键证据

## 3. 市场信念变化
命题 | Prior | Posterior | Delta | 原因

## 4. 当前市场故事
Yesterday -> Today -> Now
主故事 + 替代故事

## 5. 核心题材
每个题材只展示：
阶段/天数、角色、昨日预期、今日验证、信念变化、明日条件

## 6. 明日情景与行动
情景 | 概率权重 | 触发条件 | 行动 | 失效条件

## 7. 反事实检查
仅展示会改变决策的 1-3 个问题

## 8. 证据附录
涨停结构 / 资金 / 龙虎榜 / 新高 / 数据质量，默认折叠
```

当前“市场摘要、今日复盘要点、市场环境”三个重复章节合并为“今日认知结论 + 当前市场故事”。涨停、资金、新高不再是正文主轴，只作为假设与信念变化的证据。

---

## 13. Layer 6：Case Library

### 13.1 从 Pattern Memory 升级为完整案例

Pattern 只保存形态标签；Case 保存完整认知和结果链：

```text
Evidence
-> Reasoning
-> Belief
-> Hypothesis
-> Counterfactual
-> Decision
-> Outcome
-> Evaluation
```

### 13.2 MarketCase 契约

```python
@dataclass(frozen=True, slots=True)
class MarketCase:
    case_id: str
    start_date: date
    end_date: date
    case_type: str
    tags: tuple[str, ...]

    evidence_snapshot_ids: tuple[str, ...]
    reasoning_snapshot_ids: tuple[str, ...]
    belief_snapshot_ids: tuple[str, ...]
    hypothesis_ids: tuple[str, ...]
    decision_snapshot_ids: tuple[str, ...]

    outcome: CaseOutcome
    successful_hypotheses: tuple[str, ...]
    rejected_hypotheses: tuple[str, ...]
    key_turning_points: tuple[str, ...]
    lessons: tuple[str, ...]

    feature_vector_version: str
    case_schema_version: str
```

### 13.3 相似案例检索

相似度分解：

```text
market_fsm_similarity
emotion_similarity
theme_structure_similarity
leader_state_similarity
capital_rotation_similarity
belief_trajectory_similarity
hypothesis_path_similarity
```

返回的不只是 `similarity=91%`，还必须给出：

- 相似维度；
- 不相似维度；
- 该案例后续路径；
- 当前案例是否缺少关键条件；
- 是否存在结果泄漏风险。

### 13.4 防止未来数据污染

案例检索时，查询向量只能由查询时点之前的数据构成。Outcome 仅用于展示历史结果和离线评估，不得进入当前时点的输入向量。

---

## 14. 跨日运行流程

### 14.1 D-1 盘后

```text
构建 Evidence Snapshot
-> 计算 Reasoning Snapshot
-> 验证昨日 Hypotheses
-> 更新 Beliefs
-> 生成/修订 Hypotheses
-> 执行 Counterfactual sensitivity tests
-> 生成 Scenario + Decision
-> 编译 Market Narrative
-> 写入不可变快照
```

### 14.2 D 日盘前

```text
读取昨日 active hypotheses
-> 接入隔夜市场与竞价 Evidence
-> 更新短周期 Belief
-> 标记 hypothesis: still_valid / weakened / invalidated
-> 调整 Scenario 权重
-> 生成盘前行动卡
```

### 14.3 D 日盘中

只处理预先声明的触发条件：

```text
evidence event
-> hypothesis trigger evaluator
-> belief delta
-> risk gate
-> monitor alert
```

禁止盘中每个行情事件都重新生成完整市场故事。

### 14.4 D 日盘后结果评估

```text
Decision Outcome
-> Hypothesis calibration
-> Belief calibration
-> Scenario hit/miss
-> Case candidate
-> 人工复核后入 Case Library
```

---

## 15. 数据持久化设计

建议新增逻辑表：

| 表 | 主键 | 写入模式 | 说明 |
|---|---|---|---|
| `market_evidence_snapshot` | `snapshot_id` | append-only | 事实层 |
| `market_reasoning_snapshot` | `snapshot_id` | append-only | 推理层 |
| `market_belief_snapshot` | `snapshot_id` | append-only | 信念快照 |
| `market_hypothesis` | `hypothesis_id` | immutable base | 假设定义 |
| `market_hypothesis_evaluation` | `evaluation_id` | append-only | 每次验证结果 |
| `market_counterfactual_assessment` | `assessment_id` | append-only | 反事实评估 |
| `market_decision_snapshot` | `snapshot_id` | append-only | 决策层 |
| `market_narrative_snapshot` | `snapshot_id` | append-only | 消费读模型 |
| `market_case` | `case_id` | versioned | 案例元数据 |
| `market_case_snapshot_link` | composite | append-only | 案例与快照关系 |

### 15.1 Current Pointer

每类快照可维护独立 current pointer，但 pointer 只指向版本，不覆盖内容：

```text
trade_date
snapshot_type
current_snapshot_id
updated_at
```

### 15.2 幂等键

```text
snapshot:
  hash(trade_date + as_of + input_snapshot_ids + policy_versions)

hypothesis:
  hash(subject_ids + normalized_statement + valid_from + deadline + policy_version)

evaluation:
  hash(hypothesis_id + evaluation_as_of + evidence_snapshot_id)
```

---

## 16. Policy 外部化

配置目录建议：

```text
config/market_cognition/
  market_fsm_v1.yaml
  belief_update_v1.yaml
  hypothesis_templates_v1.yaml
  hypothesis_evaluation_v1.yaml
  counterfactual_v1.yaml
  narrative_selection_v1.yaml
  risk_gate_v1.yaml
```

规则配置必须：

- 有 JSON Schema 或 Pydantic 校验；
- 有版本号和生效日期；
- 不允许任意 Python 表达式；
- 修改后先 replay，再进入 shadow；
- 旧快照必须记录原 policy version。

---

## 17. API 与事件设计

### 17.1 查询 API

```text
GET /api/v2/market-cognition/evidence?date=&as_of=
GET /api/v2/market-cognition/reasoning?date=&as_of=
GET /api/v2/market-cognition/beliefs?date=&as_of=
GET /api/v2/market-cognition/hypotheses?date=&status=
GET /api/v2/market-cognition/scenarios?date=
GET /api/v2/market-cognition/narrative?date=
GET /api/v2/market-cognition/cases/similar?date=&top_k=
```

### 17.2 生成 API

```text
POST /api/v2/market-cognition/evidence/generate
POST /api/v2/market-cognition/reasoning/generate
POST /api/v2/market-cognition/hypotheses/evaluate
POST /api/v2/market-cognition/decision/generate
POST /api/v2/market-cognition/narrative/generate
```

生成 API 必须支持：

- `dry_run`
- `force_new_version`
- `input_snapshot_id`
- `policy_version`
- `idempotency_key`

### 17.3 领域事件

```text
MarketEvidenceBuilt
MarketReasoningBuilt
BeliefUpdated
HypothesisCreated
HypothesisConfirmed
HypothesisRejected
HypothesisRevised
BeliefCollapsed
ScenarioReweighted
MarketDecisionBuilt
MarketNarrativeBuilt
MarketCaseArchived
```

---

## 18. 与现有系统集成

### 18.1 输入映射

| M8 | 现有真源 |
|---|---|
| Market Evidence | MarketRegime、IndexTechnical、LimitUpMatrix |
| Theme Evidence | ThemeDecision、ThemeCapital、ThemeCycle |
| Stock Evidence | StrongStock、StockFacts、Abnormal |
| Capital Evidence | MoneyFlow、DragonTiger、SeatMoney |
| Event Evidence | EventDriverTracer、ThemeDriverEvents |
| Existing Decision | PostMarketDecisionV2、SetupPlan |
| Prior expectation | 前一交易日 Hypothesis/Scenario；迁移期读 Narrative |

### 18.2 增量式目标流程

```text
现有主链（保持）
Layer A/B/C/D
-> BuildPostMarketRecapJob
-> post_market_recap_snapshot
-> DailyReviewV2
-> 原 Notion Evidence Sections

新增旁路
post_market_recap_snapshot durable success event
-> BuildMarketCognitionJob
-> MarketEvidenceAdapter
-> MarketEvidenceSnapshot
-> Reasoning / Belief / Hypothesis / Strategy
-> MarketNarrativeSnapshot
-> DailyReviewV2 extension / future DailyReviewV3
-> Notion Cognitive Overview
```

### 18.3 兼容策略

迁移期：

- `DailyReview V2` 保持现有 API；
- 第一阶段单独持久化认知快照，不改 V2 必填字段；
- 第二阶段以可选 `extensions.market_cognition_v1` 增量挂载；
- Notion 采用“认知首页 + 原业务证据章节”的双层结构；
- 原八段式报告作为证据层与回滚路径继续存在；
- M6/M7/W2S 初期只读 M8 shadow 输出，不改变正式决策。

---

## 19. 可观测性与审计

### 19.1 必备指标

Evidence：

- source coverage；
- late/missing source count；
- duplicate evidence ratio；
- evidence lineage collision。

Belief：

- belief delta distribution；
- collapse count；
- unresolved conflict count；
- calibration error。

Hypothesis：

- created/confirmed/rejected/inconclusive/expired；
- confirmation latency；
- Brier Score；
- falsifier hit rate；
- revision depth。

Narrative：

- unsupported claim count；
- evidence citation coverage；
- duplicate conclusion count；
- human edit distance。

Case：

- retrieval precision；
- similarity dimension coverage；
- outcome leakage audit failures。

### 19.2 审计要求

任何对外结论应可回答：

1. 使用了哪个 Evidence Snapshot？
2. 哪个 Engine 和 Policy 生成？
3. Belief 从多少变化到多少？
4. 哪条假设被确认或拒绝？
5. 哪个风险门禁改变了行动？
6. LLM 是否参与，参与了哪一步？

---

## 20. 测试策略

### 20.1 契约测试

- Snapshot schema version；
- EvidenceRef 可解析；
- Hypothesis 状态转移合法；
- Belief 更新不重复计算同源证据；
- Decision 引用链完整；
- Narrative 每个核心命题有证据引用。

### 20.2 单元测试

- FSM transition policy；
- Belief update；
- Hypothesis falsifier；
- Counterfactual credibility guard；
- Risk hard gate；
- Narrative selection。

### 20.3 Replay

最小样本集：

1. 老周期退潮、低位轮动；
2. 分歧后修复；
3. 假修复后继续退潮；
4. 龙头破坏但板块未退潮；
5. 主线切换；
6. 无明确主线；
7. 数据缺失日；
8. 跨市场冲击日。

### 20.4 人工标注

准确率指标必须先冻结标注协议：

- 标注对象；
- 标注时点；
- 可见数据范围；
- 多分析师分歧处理；
- inter-rater agreement；
- gold set 版本。

在无标注集前，不得以“FSM 准确率 >75%”作为完成证明。

---

## 21. 验收指标

### 21.1 Phase 0 契约验收（已完成）

- 100% 核心判断包含 EvidenceRef；
- eligible Hypothesis 100% 有交易日 deadline、prediction probability、expected observations、falsifier 与 EvidenceRef；
- 不合法状态转移为 0；
- 未来数据泄漏为 0；
- Narrative unsupported claim 为 0。

### 21.2 Cognitive Validation 质量

| 指标 | 初始目标 |
|---|---|
| Eligibility false accept | 0 |
| Narrative/Observation/Assessment 进入 Calibration | 0 |
| Reviewer 事后修改 prediction probability | 0 |
| Hypothesis Binary Accuracy | 记录基线，不预设优秀值 |
| Hypothesis Brier Score | 首批人工样本后建立基线 |
| Hypothesis ECE | 样本量满足最低门槛后计算 |
| Timing Offset | 按交易日统计 0/1/2/... 日分布 |
| Falsifier 触发可解释率 | ≥95% |
| 核心假设人工一致率 | ≥75% |
| Narrative 证据引用覆盖 | 100% |
| 报告核心阅读区块 | ≤6 个 |
| 正文关键题材数 | ≤5 个 |

### 21.3 运行质量

- 同输入同策略版本结果 hash 一致；
- 单日盘后全链可分层重放；
- 任一层失败不会写入伪成功下游快照；
- 旧报告回滚不需要修改数据表；
- 连续 10 个交易日 shadow 无 P0 数据一致性问题。

### 21.4 Dataset Write Readiness Checklist

以下 Checklist 是向 Ground Truth Dataset 写入任何 Validation Record 的**唯一入口**。全部条件必须按顺序满足，缺一不可。

```text
□ 1. Hypothesis Frozen
     昨日收盘时 Hypothesis 已通过 Eligibility Gate 并 append-only 冻结
     来源：FrozenHypothesisSourceStore.append()

□ 2. Eligibility PASS
     HypothesisState 类型、VALIDATING 状态、statement、deadline、
     prediction_probability、expected_observations、falsifiers、
     EvidenceRefs（含 Trade Calendar）、source hashes、policy version
     全部通过 MarketThesisVerificationService.check_eligibility()

□ 3. Reality Available
     verification trade date >= hypothesis deadline
     且 TodayReality.available_at 早于 verified_at
     且 TodayReality.evidence_refs 非空

□ 4. Reviewer Approved
     ReviewerVerdict.reviewer_id 在 approved_reviewer_ids 中
     Reviewer 未修改 prediction_probability
     Verdict label 为 YES/NO/PARTIAL/UNVERIFIABLE
     NO/PARTIAL 必须携带 failure_type

□ 5. Manifest Ready
     Dataset 目录存在、schema 版本匹配
     Manifest 完整性校验就绪

□ 6. Integrity PASS
     record_hash 唯一且可重现
     无 duplicate（重复写入跳过）
     无 conflict（同 identity 不同内容拒绝）

     ↓
  [ Append Ground Truth Record ]
```

**反模式（禁止）**：

- ❌ 跳过任一 Checklist 项直接写入
- ❌ 用 Narrative confidence 替代 prediction_probability
- ❌ 用模型自动输出替代 Reviewer Verdict
- ❌ 在 Reality 未发生时提前生成 Record
- ❌ 用新版本代码重算昨日 Hypothesis 后覆盖 Frozen Source

---

## 22. 分阶段实施计划

> 状态说明：下方原 v1.3 Engine 路线保留为长期能力地图，不再作为当前执行顺序。当前执行以 `M8.phase0 GA -> M8.phase1 Cognitive Validation -> 20 Trading Days -> 再评估 Belief/Learning` 为准。

### 当前 Phase 0：Cognition Homepage（已完成）

交付：

1. `MarketKnowledgeBundle` 与 Evidence Adapter；
2. CLOSE Context、固定 Cognition Policy、Market Thesis；
3. Notion `legacy_only/cognition_shadow/dual_layer`；
4. 无副作用 Replay、canonical hash、Decision Drift 守卫；
5. 原 DailyReviewV2 与证据章节零破坏。

### 当前 Phase 1：Cognitive Validation（进行中）

目标：先建立可审计 Ground Truth，不实现 Belief/Learning。

```text
Frozen eligible Hypothesis
-> Today Reality
-> Approved Reviewer Verdict
-> Append-only Validation Record
-> Manifest Integrity
-> Replay
-> Binary / Brier / ECE / Timing Offset
```

退出条件：

- T01～T04 工程任务通过；
- 连续 20 个真实交易日完成 Hypothesis Validation；
- 未来数据泄漏为 0；
- Narrative calibration sample 为 0；
- Decision Drift 为 0；
- Belief/Learning 写入为 0。

### 当前 Phase 2：Belief/Learning 评估（延期）

只有当 Validation Dataset 已形成足够 Ground Truth、Reviewer 口径稳定且 Calibration 可解释后，才允许通过新 ADR 评估 Belief Update 与 Learning。不得因 T04 指标代码完成而自动进入 Phase 2。

---

# PART II — Future Roadmap (Informative)

> **阅读指引**：PART II（第 23–27 节）描述 M8 长期能力愿景和 M9 演进方向。
> 本节内容为信息性参考，不构成当前开发承诺。
> 所有 PART II 能力的启动必须先通过独立 ADR、回放验证和真实交易日评估。
> 当前执行顺序以 PART I 中 Phase 0/1 的门禁为准。

### v1.3 长期能力地图（保留）

### Phase 0：认知契约与可读报告切片（1-2 周）

目标：不等待完整 M8，先用现有真源生成可读的认知报告。

交付：

1. 冻结 EvidenceRef、BeliefState、MarketHypothesis、MarketNarrative 契约；
2. 建立昨日假设验证读模型；
3. Notion 改为“认知结论/假设验证/信念变化/核心题材/明日情景/证据附录”；
4. 原报告保留 feature flag 回滚；
5. 使用 7/2 分析师报告建立首个 gold sample。

门禁：

- 新报告不重复展示同一结论；
- 正文无内部状态码；
- 每个核心题材包含昨日、今日、明日；
- 无证据时显示“无法判定”，不补写结论。

### Phase 1：Evidence + FSM + Emotion（2-3 周）

交付：

- MarketEvidenceSnapshot；
- MarketFSMEngine；
- EmotionEngine；
- Policy 配置与 replay；
- 证据完整性监控。

### Phase 2：Belief + Hypothesis（2-3 周）

交付：

- MarketBeliefEngine；
- HypothesisEngine；
- 跨日状态与 evaluation；
- Brier/ECE 校准报告；
- 盘前假设增量更新。

### Phase 3：Theme Cognitive + Leader + Expectation（2-3 周）

交付：

- Theme 四契约；
- LeaderEvolution；
- InfluenceGraph daily/minute proxy；
- ExpectationGap；
- Participant mindset。

### Phase 4：Counterfactual + Scenario + Decision（2-3 周）

交付：

- CF-0/CF-1；
- ScenarioPath；
- Risk hard gates；
- Action 引用链；
- M6/M7/W2S shadow 接入。

### Phase 5：Case Library + 学习闭环（3-4 周）

交付：

- MarketCase；
- 相似案例检索；
- Outcome Evaluator；
- 防泄漏审计；
- 历史案例人工复核工具。

### Phase 6：消费者切换与生产门禁（2 周）

交付：

- PostMarket、PreMarket、Notion 切换；
- M6/M7/W2S 分批切换；
- 10 个交易日 shadow；
- 回滚演练与运行手册。

---

## 23. 风险与缓解

| 等级 | 风险 | 缓解 |
|---|---|---|
| P0 | Belief 对同源派生证据重复计票 | Evidence lineage 去重 |
| P0 | 回放读取未来数据 | `available_at` 强制门禁 |
| P0 | LLM 生成无依据市场故事 | Narrative Compiler 定主轴，Claim Validator 阻断 |
| P0 | Observation/Assessment 或 Narrative confidence 被写入 Calibration Dataset | ADR-M8-009 Eligibility Gate；仅冻结 Hypothesis 可写入 |
| P0 | 自然日 deadline 落在休市日 | deadline 只引用 Trade Calendar Producer |
| P0 | 风险门禁被 Belief 融合稀释 | Risk hard gate 独立优先 |
| P1 | 假设数量爆炸 | subject/type 配额、去重、deadline、supersede |
| P1 | 反事实被误解为因果 | CF-0~CF-3 可信等级与措辞门禁 |
| P1 | 权重过拟合 | shadow、walk-forward、policy version |
| P1 | Case 检索结果泄漏 | as-of feature vector 与 Outcome 隔离 |
| P2 | 架构过大导致长期无可见产出 | Phase 0 先交付认知报告切片 |

---

## 24. 建议 ADR

1. ADR-M8-001：Hypothesis 是跨日认知主轴，Scenario 必须引用 Hypothesis。
2. ADR-M8-002：Belief 是主观后验，不得与市场事实或强度分混用。
3. ADR-M8-003：Meta Reasoner 职责并入 Market Belief Engine，但 Risk hard gate 独立。
4. ADR-M8-004：Counterfactual 按 CF-0~CF-3 标注可信等级。
5. ADR-M8-005：Market Narrative 为结构化读模型，LLM 只做 verbalization。
6. ADR-M8-006：Pattern Memory 升级为 Case Library，并强制防未来数据泄漏。
7. ADR-M8-007：所有核心认知快照 append-only、可回放、带策略版本。
8. ADR-M8-008：Notion 正文以认知变化组织，原始事实降级到折叠证据附录。
9. ADR-M8-009：只有 Validation-Eligible Hypothesis 可以进入 Ground Truth Dataset；Narrative Confidence 不等于 Prediction Probability。
10. ADR-M8-010：Cognition Projection 不是新 Engine。Multi-Horizon Context、Market Cognition Graph、Theme/Trading Cognitive Card、Historical Case Projection、Expectation Projection、Node Maturity Estimation 是落在现有 Stable Core 内部的只读认知投影，不新增顶层模块，不破坏 Phase 0/Phase 1 链路。
11. ADR-M8-011：Hypothesis 升级为 Node Transition Hypothesis。所有进入 Ground Truth Dataset 的命题必须声明 `hypothesis_type = NODE_TRANSITION`，包含 `current_node` 和 `expected_transition`。笼统市场命题不得进入 Dataset。
12. ADR-M8-012：Causal Chain 与 Cognition Edge 的关系。CognitionEdge 描述静态关联强度，CausalChain 描述动态传导顺序与机制。每条 CausalChain 必须包含至少一条 alternative_chain。跨日因果（time_lag >= next_day）必须是 Hypothesis，不是 Assessment。
13. ADR-M8-013：Historical Case Retrieval 必须隔离 Outcome。检索向量禁止包含未来 Outcome 标签。transfer_confidence 必须在 similarity 基础上扣除差异惩罚。高相似案例不可覆盖当前 Evidence。
14. ADR-M8-014：Expectation Consensus 必须在盘前冻结。禁止盘后用 Actual 反向修改 Consensus。consensus_source 必须显式记录（prior_hypothesis / analyst_consensus / model_prior / llm_draft），不可混用。
15. ADR-M8-015：Node Maturity 不作为 Calibration 目标。NodeMaturityEstimation 是认知辅助，不是预测对象。Calibration 只针对 Node Transition Hypothesis，不对 maturity_score 计算 Brier/ECE。

---

## 25. 最终架构结论

M8 的核心不应是“更多 Engine”，而应是一个可持续修正的认知循环：

```text
观察事实
-> 形成解释
-> 更新信念
-> 验证旧假设
-> 修订或建立新假设
-> 检查替代解释
-> 形成条件化行动
-> 评估结果
-> 沉淀案例
```

FSM 描述市场，Belief 描述系统当前相信什么，Hypothesis 定义接下来要验证什么，Counterfactual 防止系统沉迷单一故事，Case Library 提供可回溯经验，Market Narrative 将全部认知压缩为交易员能快速理解的跨日故事。

这套闭环完成后，AI Theme App 才从“盘后报告生成器”升级为“持续维护、验证和修正市场观点的认知系统”。

---

## 26. M9 长期演进定位

### 26.1 为什么 M8 仍不是完整的智能系统

M8 已经解决：

```text
Evidence
-> Reasoning
-> Belief
-> Hypothesis
-> Counterfactual
-> Decision
-> Outcome
-> Case Library
```

这是一条完整的认知与决策闭环，但它仍隐含了五个尚未显式建模的问题：

1. 系统依据什么长期结构理解市场参与者、资金、指数、题材和股票之间的关系？
2. 面对海量市场信息，系统今天最重要的问题是什么？
3. 有限的推理、模型和人工复核资源应分配到哪里？
4. 假设在盘中如何随证据连续变化，而不是只保留日终结果？
5. 每日错误和认知变化如何沉淀为可审核的学习，而不是冷数据归档？

M9 不是在 M8 旁边继续堆叠 Engine，而是在 M8 外建立“长期模型 -> 当日目标 -> 注意力分配 -> 日内认知 -> 学习反馈”的控制循环。

```text
Market World Model
        │
        ▼
Goal Manager
        │
        ▼
Attention Engine
        │
        ▼
M8 Cognition Loop
Evidence -> Reasoning -> Belief -> Hypothesis -> Decision
        │
        ▼
Market Diary
        │
        ▼
Case Library
        │
        ▼
World Model Update Proposal
        │
        └──── replay / shadow / approval ────> New World Model Version
```

### 26.2 M8 与 M9 的边界

| 系统 | 时间尺度 | 核心职责 | 主要输出 |
|---|---|---|---|
| M8 Market Cognition Engine | 分钟到数日 | 理解当前市场、维护信念、验证假设、形成决策 | Cognition/Belief/Hypothesis/Decision Snapshot |
| M9 Market Intelligence System | 数周到跨周期 | 维护世界模型、设置目标、分配注意力、沉淀学习 | WorldModel/Goal/Attention/Diary/ModelUpdate |

M8 必须能独立工作；M9 只提供上层先验、资源调度和学习治理。M9 不得成为 M8 的单点强依赖。

---

## 27. Market World Model

### 27.1 定位

World Model 描述系统认为“市场通常如何运行”，包括参与者、对象、关系、状态转移和作用机制。

它不回答：

> 今天 PCB 是不是主线？

它回答：

> 在当前制度、流动性和风险偏好环境中，机构趋势资金通常如何选择容量方向？容量中军、情绪先锋和跟风股之间如何相互影响？什么证据表示主线正在切换？

因此：

```text
World Model = 结构与机制
Belief      = 在该结构下对当前状态/命题的后验判断
Hypothesis  = 对未来可观测结果的可证伪声明
```

### 27.2 与 Belief 的形式关系

World Model 定义：

```text
P(state_t | state_t-1, participants, capital, events, exogenous)
P(observation_t | state_t)
possible_relations
valid_transition_constraints
```

Belief 表示：

```text
P(current_state or proposition | observations_<=t, world_model_version)
```

Hypothesis 表示：

```text
在 world_model_version 和当前 belief 下，
未来窗口内应出现哪些观测；哪些观测将证伪该命题。
```

Belief 必须引用 `world_model_version`。同一证据在不同 World Model 下可能得到不同解释，这种差异必须可回放。

### 27.3 World Model 组成

```python
@dataclass(frozen=True, slots=True)
class MarketWorldModel:
    model_id: str
    version: str
    status: str
    valid_from: datetime
    valid_to: datetime | None

    ontology: "MarketOntology"
    participants: tuple["ParticipantModel", ...]
    structural_rules: tuple["StructuralRule", ...]
    capital_preferences: tuple["CapitalPreference", ...]
    rotation_mechanisms: tuple["RotationMechanism", ...]
    role_evolution_rules: tuple["RoleEvolutionRule", ...]
    emotion_rules: tuple["EmotionRule", ...]
    risk_rules: tuple["WorldRiskRule", ...]
    causal_graphs: tuple["CausalGraphSpec", ...]

    evidence_scope: tuple[str, ...]
    training_window: tuple[date, date] | None
    calibration_report_id: str
    policy_versions: dict[str, str]
    created_at: datetime
    approved_at: datetime | None
    approved_by: str | None
```

### 27.4 Market Ontology

Ontology 冻结对象及关系语义：

```text
Participant:
  institution
  hot_money
  retail
  quant
  policy_fund

Market Object:
  index
  style
  theme
  stock
  event
  capital_pool
  emotion_carrier

Relation:
  leads
  follows
  anchors
  substitutes
  competes_with
  resonates_with
  crowds_out
  transmits_risk_to
  attracts_capital_from
```

关系必须有：

- 有效时间；
- 适用市场状态；
- 方向；
- 强度；
- 证据；
- 可信等级；
- 版本。

### 27.5 Participant Model

```python
class ParticipantModel:
    participant_type: str
    preferred_styles: tuple[str, ...]
    preferred_market_cap_range: tuple[float, float] | None
    preferred_liquidity_range: tuple[float, float] | None
    holding_horizon: str
    typical_entry_signals: tuple[str, ...]
    typical_exit_signals: tuple[str, ...]
    reaction_to_volatility: str
    reaction_to_index_risk: str
    confidence: float
    evidence_refs: tuple[EvidenceRef, ...]
```

“机构喜欢趋势、游资偏好情绪”只能作为待校准的 Participant Rule，不能作为永久常识硬编码。

### 27.6 Structural Rule

```python
class StructuralRule:
    rule_id: str
    statement: str
    rule_type: str
    scope: str
    preconditions: tuple[str, ...]
    expected_effects: tuple[str, ...]
    exceptions: tuple[str, ...]
    confidence: float
    support_case_ids: tuple[str, ...]
    counter_case_ids: tuple[str, ...]
    status: str
    valid_from: datetime
    valid_to: datetime | None
```

状态建议：

```text
PROPOSED
-> BACKTESTED
-> SHADOW
-> ACTIVE
-> WEAKENED
-> RETIRED
```

### 27.7 World Model 不能直接自我修改

单个交易日只能产生 `WorldModelUpdateProposal`：

```python
class WorldModelUpdateProposal:
    proposal_id: str
    target_model_version: str
    change_type: str
    affected_rule_ids: tuple[str, ...]
    proposed_changes: tuple[str, ...]
    trigger_diary_ids: tuple[str, ...]
    support_case_ids: tuple[str, ...]
    counter_case_ids: tuple[str, ...]
    minimum_sample_requirement: int
    replay_plan_id: str
    status: str
```

更新流程：

```text
Diary / Case 发现认知偏差
-> PROPOSED
-> 历史样本回放
-> walk-forward 验证
-> shadow
-> 人工评审
-> 新 World Model Version
```

禁止：

- 单日错误自动修改长期规则；
- LLM 直接写 ACTIVE Rule；
- 用同一批样本提出并验证规则；
- 覆盖旧模型版本。

---

## 28. Market Goal Manager

### 28.1 定位

Goal 回答：

> 系统今天最需要弄清楚什么？

它不是收益目标，也不是“寻找可以买的股票”。它是一个有截止时间、证据要求和停止条件的认知目标。

示例：

- 验证 PCB 是否已从轮动题材升级为科技容量主线；
- 判断机器人是分歧修复失败，还是仅延迟修复；
- 确认科技赛道风险是否由局部龙头破坏扩散为系统性退潮。

### 28.2 Goal 契约

```python
@dataclass(frozen=True, slots=True)
class MarketGoal:
    goal_id: str
    goal_type: str
    priority: int
    question: str
    rationale: str

    target_entity_type: str
    target_entity_ids: tuple[str, ...]
    source_hypothesis_ids: tuple[str, ...]
    source_belief_ids: tuple[str, ...]

    required_evidence: tuple["EvidenceRequirement", ...]
    disconfirming_evidence: tuple["EvidenceRequirement", ...]
    success_criteria: tuple[str, ...]
    stop_conditions: tuple[str, ...]

    valid_from: datetime
    deadline: datetime
    status: str
    owner: str
    world_model_version: str
```

### 28.3 Goal 状态机

```text
PROPOSED
-> ACTIVE
-> SATISFIED
-> UNSATISFIED
-> BLOCKED
-> EXPIRED
-> CANCELLED
```

### 28.4 Goal 生成

候选来源：

1. 昨日未结束的高优先级 Hypothesis；
2. Belief delta 或 conflict 最大的命题；
3. 风险门禁要求验证的问题；
4. 盘前新增的外部冲击；
5. Attention Engine 发现的异常；
6. 人工指定。

优先级建议：

```text
priority_score
  = decision_impact
  × uncertainty
  × urgency
  × evidence_availability
  × risk_multiplier
```

### 28.5 防止 Goal 造成确认偏误

Goal 只聚焦推理，不过滤全市场事实感知。

每个 Goal 必须同时定义：

- `required_evidence`
- `disconfirming_evidence`
- `stop_conditions`

系统必须主动搜索反对证据；只收集支持证据的 Goal 无效。

---

## 29. Attention Engine

### 29.1 定位

Attention Engine 管理有限的：

- LLM token；
- 高成本模型调用；
- 分钟级图计算；
- 人工复核；
- 实时监控槽位；
- Notion 正文篇幅。

它不决定事实是否存在，也不删除低注意力对象。

### 29.2 双层注意力

```text
Broad Sensing:
  全市场低成本持续感知
  负责异常、风险和新主题召回

Focused Reasoning:
  对 Top-K 对象执行深度推理
  负责 Hypothesis、Counterfactual、Narrative
```

如果只分析固定 Top 5 且关闭全市场感知，系统会错过新主线和黑天鹅。

### 29.3 Attention 契约

```python
@dataclass(frozen=True, slots=True)
class AttentionAllocation:
    allocation_id: str
    as_of: datetime
    total_budget: float

    entity_type: str
    entity_id: str
    attention_score: float
    budget_allocated: float
    rank: int

    source_goal_ids: tuple[str, ...]
    source_hypothesis_ids: tuple[str, ...]
    urgency_reasons: tuple[str, ...]
    expected_information_gain: float
    decision_impact: float
    risk_interrupt: bool

    expires_at: datetime
    policy_version: str
```

### 29.4 Attention Score

```text
attention_score
  = expected_information_gain
  × decision_impact
  × uncertainty
  × time_urgency
  × anomaly_strength
  + risk_interrupt_bonus
  + exploration_bonus
```

### 29.5 预算策略

建议初始预算：

```text
60% exploitation:
  当前核心 Goal / active Hypothesis

20% risk reserve:
  全局风险、龙头破坏、流动性异常

15% exploration:
  新题材、新载体、异常资金

5% human override:
  人工指定
```

硬约束：

- 风险中断可抢占普通预算；
- 至少保留 exploration quota；
- 同一题材不得长期垄断全部预算；
- 低 Attention 不等于低 Belief；
- Attention 变化必须可解释。

### 29.6 Attention 与 LLM

LLM 默认只深入分析：

- Top 5 主题；
- Top 3 市场级 Goal；
- 高风险 interrupt；
- Belief 冲突最大的命题。

但确定性规则、异常检测和证据采集仍覆盖全市场。

---

## 30. Hypothesis Timeline

### 30.1 设计目标

Hypothesis 不是一条可原地修改的记录，而是一条事件流。

示例：

```text
09:20 CREATED     机器人修复，belief=82
09:35 EVIDENCE    竞价承接不足，belief=76
10:10 EVIDENCE    PCB 超预期吸金，belief=64
11:10 REVISED     机器人延迟修复，belief=51
13:30 REJECTED    核心股与板块均未修复，belief=28
14:00 CREATED     PCB 接替为机构容量方向，belief=67
```

### 30.2 Event Sourcing

```python
@dataclass(frozen=True, slots=True)
class HypothesisTimelineEvent:
    event_id: str
    hypothesis_id: str
    sequence_no: int
    event_type: str
    occurred_at: datetime
    available_at: datetime

    belief_before: float
    belief_after: float
    status_before: str
    status_after: str

    evidence_refs: tuple[EvidenceRef, ...]
    trigger_rule_ids: tuple[str, ...]
    reason: str
    actor: str
    idempotency_key: str
```

事件类型：

```text
CREATED
ACTIVATED
EVIDENCE_SUPPORTED
EVIDENCE_CONTRADICTED
BELIEF_INCREASED
BELIEF_DECREASED
REVISED
CONFIRMED
REJECTED
INCONCLUSIVE
EXPIRED
SUPERSEDED
```

### 30.3 快照与时间线

`MarketHypothesis` 保存定义；`HypothesisTimelineEvent` 保存变化；`HypothesisCurrentState` 是可重建投影。

```text
Hypothesis Definition
  + ordered Timeline Events
  -> Current State Projection
```

Current State 丢失时必须能通过事件流重建。

### 30.4 盘中更新策略

不是每个 Tick 都更新 Belief。只有以下事件触发：

- Goal required evidence 到达；
- falsifier 接近或触发；
- Attention Top-K 变化；
- 风险中断；
- 关键角色状态变化；
- 预定义时间检查点；
- 人工修订。

需要配置：

- debounce；
- minimum delta；
- maximum update frequency；
- out-of-order event handling。

---

## 31. Market Diary

### 31.1 定位

Report 面向阅读，Case 面向历史检索，Diary 面向学习。

Diary 记录：

1. 今日最大的认知变化；
2. 今日最重要的假设结果；
3. 今日最大的错误；
4. 哪条证据最早提示变化；
5. 系统为什么没有及时响应；
6. 哪条 World Model Rule 可能需要修订；
7. 明天需要延续的 Goal。

### 31.2 契约

```python
@dataclass(frozen=True, slots=True)
class MarketDiary:
    diary_id: str
    trade_date: date
    generated_at: datetime

    biggest_cognitive_change: str
    biggest_correct_call: str | None
    biggest_error: str | None
    earliest_valid_signal: str | None
    missed_signal: str | None
    response_gap: str | None

    belief_changes: tuple[str, ...]
    hypothesis_results: tuple[str, ...]
    attention_review: "AttentionReview"
    goal_review: "GoalReview"
    decision_outcomes: tuple[str, ...]

    lessons: tuple["LearningItem", ...]
    world_model_update_proposal_ids: tuple[str, ...]
    next_day_goal_candidates: tuple[str, ...]

    evidence_refs: tuple[EvidenceRef, ...]
    source_snapshot_ids: tuple[str, ...]
    status: str
    reviewed_by: str | None
```

### 31.3 Learning Item

```python
class LearningItem:
    learning_id: str
    category: str
    statement: str
    affected_rule_ids: tuple[str, ...]
    confidence: float
    support_case_ids: tuple[str, ...]
    counter_case_ids: tuple[str, ...]
    action: str
```

`action` 只允许：

```text
OBSERVE_MORE
CREATE_GOAL
PROPOSE_RULE_UPDATE
ADD_CASE_TAG
ADJUST_ATTENTION_POLICY
NO_CHANGE
```

Diary 不直接修改 World Model。

### 31.4 Diary 与 Case Library

Case 保存完整市场过程；Diary 保存系统对该过程的反思。

```text
Case:
  发生了什么，系统怎么判断，结果是什么

Diary:
  系统哪里判断对了，哪里错了，应该学什么
```

Case 检索时可以同时返回历史 Diary，但 Diary 的主观总结必须与事实快照分层展示。

---

## 32. M9 统一运行架构

### 32.1 日级主循环

```text
1. 读取 Active World Model Version
2. 读取昨日 Diary、未结束 Goal、Active Hypothesis
3. Goal Manager 生成 Today's Goals
4. Attention Engine 分配预算
5. M8 执行 Evidence -> Decision
6. Hypothesis Timeline 持续记录变化
7. 盘后生成 Narrative 与 Diary
8. Outcome Evaluator 评估 Goal/Hypothesis/Decision
9. Case Library 归档候选
10. 生成 World Model Update Proposal
```

### 32.2 盘中控制循环

```text
Broad Sensing
  -> Evidence Event
  -> Risk Interrupt?
       yes -> 抢占 Attention
       no  -> 是否命中 Goal/Hypothesis requirement?
  -> Focused Reasoning
  -> Belief Update
  -> Timeline Event
  -> Scenario / Decision Re-evaluation
  -> Alert or no-op
```

### 32.3 反馈学习循环

```text
Diary Lessons
  + Case Outcomes
  + Calibration Metrics
  -> Model Update Proposal
  -> Historical Replay
  -> Walk-forward
  -> Shadow
  -> Human Review
  -> New Model Version
```

### 32.4 失败隔离

| 故障 | 降级行为 |
|---|---|
| World Model 不可用 | 使用最近已批准版本 |
| Goal Manager 失败 | 延续昨日未完成 Goal + 风险 Goal |
| Attention Engine 失败 | 使用静态预算与 risk reserve |
| Hypothesis Timeline 写入失败 | 阻止 Current State 更新，进入补偿队列 |
| Diary 失败 | 不阻塞当日决策快照 |
| Case Library 失败 | 延迟归档，不影响 M8 |

---

## 33. M9 数据持久化与事件

### 33.1 建议新增表

| 表 | 写入模式 | 说明 |
|---|---|---|
| `market_world_model` | versioned | 模型元数据 |
| `market_world_model_rule` | versioned | 结构规则 |
| `world_model_update_proposal` | append-only | 更新提案 |
| `market_goal` | append-only + projection | 当日认知目标 |
| `market_attention_allocation` | append-only | 注意力预算 |
| `hypothesis_timeline_event` | append-only | 假设变化事件 |
| `hypothesis_current_state` | rebuildable projection | 当前状态 |
| `market_diary` | versioned | 日记 |
| `market_learning_item` | append-only | 学习项 |

### 33.2 领域事件

```text
WorldModelActivated
WorldModelRuleWeakened
WorldModelUpdateProposed
GoalActivated
GoalSatisfied
GoalExpired
AttentionAllocated
AttentionRebalanced
RiskAttentionInterrupted
HypothesisTimelineAdvanced
DiaryGenerated
DiaryReviewed
LearningItemCreated
```

### 33.3 审计链

任何盘中观点变化应能追溯：

```text
World Model Version
-> Goal
-> Attention Allocation
-> Evidence
-> Reasoning
-> Belief Delta
-> Hypothesis Timeline Event
-> Scenario
-> Decision
-> Outcome
-> Diary
-> Model Update Proposal
```

---

## 34. M9 实施路线

M9 不应阻塞 M8 的 Phase 0 可读报告交付。

### M9 Phase 0：契约与事件时间线（1-2 周）

交付：

- WorldModelRef；
- MarketGoal；
- AttentionAllocation；
- HypothesisTimelineEvent；
- MarketDiary；
- append-only 事件契约。

仅 shadow，不改变正式决策。

### M9 Phase 1：Goal + Attention（2 周）

交付：

- Goal Manager；
- Broad Sensing / Focused Reasoning 双层预算；
- Top-K + exploration + risk reserve；
- LLM 调用预算接入；
- Attention 可解释性面板。

验收：

- 全市场风险召回不低于无 Attention 基线；
- 深度推理成本显著下降；
- Top Goal 的 required/disconfirming evidence 均有覆盖。

### M9 Phase 2：Hypothesis Timeline（2 周）

交付：

- Timeline event store；
- current projection；
- 盘中关键事件触发；
- out-of-order、幂等与重建测试；
- 日内 Belief 曲线。

### M9 Phase 3：Diary + Learning（2 周）

交付：

- 日终 Diary；
- Goal/Attention/Hypothesis 复盘；
- Learning Item；
- Case 关联；
- 人工审核入口。

### M9 Phase 4：World Model v1（3-4 周）

交付：

- Market Ontology；
- Participant/Structural Rules；
- Model version；
- Update Proposal；
- replay、walk-forward、shadow、approval 流程。

### M9 Phase 5：闭环验收（至少 20 个交易日）

门禁：

- World Model 无未审批自动变更；
- Timeline 可完全重建；
- Goal 未造成显著风险召回下降；
- Attention 成本收益达到预设阈值；
- Diary Learning Item 有事实引用；
- 新模型相对旧模型在 out-of-sample 指标上改善；
- 可一键回滚到上一 World Model Version。

---

## 35. M9 风险矩阵

| 等级 | 风险 | 影响 | 缓解 |
|---|---|---|---|
| P0 | Goal 导致只寻找支持证据 | 系统性确认偏误 | 强制 disconfirming evidence |
| P0 | Attention 过滤低关注风险 | 黑天鹅与新主线漏检 | Broad Sensing + risk reserve + exploration |
| P0 | Diary 自动修改 World Model | 单日过拟合与模型漂移 | Proposal/replay/shadow/approval |
| P0 | Timeline 乱序或重复事件 | Belief 与状态不可重建 | sequence/idempotency/out-of-order policy |
| P1 | World Model 变成不可维护大字典 | 语义漂移 | Ontology + typed rule + version |
| P1 | 世界规则被当作永久真理 | 市场制度变化下失效 | validity window + weakened/retired |
| P1 | Attention Score 与 Belief 混用 | 资源优先级污染判断 | 独立契约与独立指标 |
| P1 | Diary 叙事后见之明 | 学习结果失真 | 记录当时 snapshot，隔离 outcome |
| P2 | M9 过早扩张拖慢 M8 | 无可见交付 | M9 shadow、M8 Phase 0 优先 |

---

## 36. M9 建议 ADR

1. ADR-M9-001：World Model 是版本化结构模型，Belief 必须引用模型版本。
2. ADR-M9-002：World Model 只能通过 Proposal、回放、shadow 和审批更新。
3. ADR-M9-003：Goal 必须同时定义支持证据、反对证据和停止条件。
4. ADR-M9-004：Attention 仅分配计算资源，不过滤全市场事实感知。
5. ADR-M9-005：Attention 必须保留 risk reserve 与 exploration quota。
6. ADR-M9-006：Hypothesis 采用事件溯源时间线，Current State 必须可重建。
7. ADR-M9-007：Diary 是学习读模型，不得直接修改规则或事实。
8. ADR-M9-008：World Model 更新必须执行无未来数据污染的 out-of-sample 验证。

---

## 37. M8/M9 最终结论

M8 解决“系统今天如何理解市场并形成行动”。

M9 解决“系统依据什么长期模型理解市场、今天把认知资源放在哪里、以及如何从错误中更新长期模型”。

最终主链为：

```text
World Model
-> Goal
-> Attention
-> Evidence
-> Reasoning
-> Belief
-> Hypothesis Timeline
-> Counterfactual
-> Decision
-> Diary
-> Case Library
-> World Model Update Proposal
```

其中最重要的治理边界是：

```text
Goal 不过滤事实
Attention 不等于 Belief
Belief 不等于 World Model
Diary 不直接改模型
单日经验不升级为长期规律
```

只有在这些边界成立时，系统的“持续学习”才不会退化为确认偏误、短期过拟合和自我强化叙事。

---

## 38. Strategy Layer：认知到行动的策略桥梁

### 38.1 为什么 Decision 不能替代 Strategy

Evidence、Reasoning、Belief 和 Hypothesis 描述的是“市场认知”。Strategy 描述的是“采用什么交易体系利用这种认知”。

同一份市场认知可以被不同交易体系解释为完全不同的行动：

| 共同认知 | 策略 | 可能行动 |
|---|---|---|
| 机器人 Belief=80，处于分歧 | 弱转强 | 等待转强确认，不提前追涨 |
| 机器人 Belief=80，处于分歧 | 左侧试错 | 在风险预算内分批试错 |
| 机器人 Belief=80，核心股最高板 | 龙头战法 | 只评估龙头，不交易跟风 |
| PCB Belief=60，机构容量增强 | 容量趋势 | 趋势确认后半路或回踩参与 |
| PCB Belief=60，题材轮动加快 | 轮动套利 | 只做短持有周期和明确止盈 |

因此，Decision 必须引用 Strategy，不能由 Belief 直接生成。

完整链路调整为：

```text
Market Cognition
  -> Strategy Eligibility
  -> Strategy Selection
  -> Strategy Proposal
  -> Risk Gate
  -> Portfolio Allocation
  -> Decision
  -> Execution Plan
```

### 38.2 Strategy Layer 的三类对象

```text
StrategyProfile:
  交易体系的稳定定义

StrategyContext:
  当前市场、题材、标的与账户环境

StrategyProposal:
  某个策略基于当前 Context 产生的候选行动
```

StrategyProfile 不应混入单日市场数据；StrategyProposal 不应修改 StrategyProfile。

---

## 39. StrategyProfile 数据契约

### 39.1 核心契约

```python
@dataclass(frozen=True, slots=True)
class StrategyProfile:
    strategy_id: str
    strategy_name: str
    strategy_family: str
    version: str
    status: str

    objective: str
    expected_holding_period: str
    expected_payoff_shape: str

    preferred_market_phases: tuple[str, ...]
    preferred_theme_stages: tuple[str, ...]
    preferred_roles: tuple[str, ...]
    preferred_styles: tuple[str, ...]

    eligibility_rules: tuple["StrategyRule", ...]
    entry_rules: tuple["StrategyRule", ...]
    confirmation_rules: tuple["StrategyRule", ...]
    position_model: "PositionModel"
    add_position_rules: tuple["StrategyRule", ...]
    reduce_position_rules: tuple["StrategyRule", ...]
    exit_rules: tuple["StrategyRule", ...]
    risk_rules: tuple["StrategyRule", ...]
    forbidden_conditions: tuple["StrategyRule", ...]

    required_evidence_types: tuple[str, ...]
    required_hypothesis_types: tuple[str, ...]
    minimum_belief: float | None
    maximum_uncertainty: float | None

    benchmark_id: str
    calibration_report_id: str
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime
    approved_at: datetime | None
    approved_by: str | None
```

### 39.2 Strategy 状态

```text
DRAFT
-> BACKTESTED
-> SHADOW
-> ACTIVE
-> PAUSED
-> RETIRED
```

只有 `ACTIVE` 策略可以产生正式 StrategyProposal。

### 39.3 StrategyRule

```python
@dataclass(frozen=True, slots=True)
class StrategyRule:
    rule_id: str
    rule_type: str
    expression: "TypedExpression"
    description: str
    severity: str
    evidence_requirements: tuple[str, ...]
    missing_data_behavior: str
    policy_version: str
```

策略规则必须使用受限 DSL 或类型化表达式，不允许配置任意 Python 代码。

`missing_data_behavior` 只允许：

```text
BLOCK
SKIP_RULE
DEGRADE_TO_OBSERVE
```

核心准入和风险规则缺数据时默认 `BLOCK`，不得默认为通过。

### 39.4 PositionModel

```python
class PositionModel:
    model_id: str
    max_strategy_exposure: float
    max_single_position: float
    initial_position: float
    add_position_steps: tuple[float, ...]
    confidence_multiplier: tuple[tuple[float, float], ...]
    liquidity_multiplier: tuple[tuple[float, float], ...]
    drawdown_reduction_rules: tuple[str, ...]
```

PositionModel 输出的是策略建议仓位，最终仓位仍由 Portfolio Allocator 和全局 Risk Gate 决定。

---

## 40. Strategy Catalog 与策略语义

### 40.1 首批策略族

| 策略族 | 核心机会 | 关键阶段 | 偏好角色 | 典型禁止条件 |
|---|---|---|---|---|
| 龙头战法 | 市场最高辨识度的持续溢价 | 发酵/加速/首次分歧 | 市场龙、周期龙 | 高位退潮确认、龙头地位丧失 |
| 弱转强 | 分歧后的超预期修复 | FIRST_DIVERGENCE -> WEAK_TO_STRONG | 前排、换手核心 | 一字、无板块合力、修复不及预期 |
| 容量趋势 | 机构主导的持续趋势 | 发酵/趋势主升/良性分歧 | 中军、容量核心 | 放量滞涨、机构持续流出、趋势破位 |
| 左侧试错 | 冰点或超跌后的赔率机会 | ICE_POINT/REBOUND 前段 | 抗跌核心、先手品种 | 风险未释放、无止损锚、流动性不足 |
| 高低切 | 高位风险释放后的低位新方向 | CLIMAX/FADE | 低位先锋、新载体 | 仅跟风旧周期、无增量资金 |
| 轮动套利 | 快速轮动中的短期价差 | 震荡/无主线 | 当日先锋、事件驱动 | 持续性要求过高、隔日流动性差 |

这些是独立 StrategyProfile，不是一个 `strategy_type` 字段的不同标签。

### 40.2 示例：弱转强策略

```yaml
strategy_id: weak_to_strong_v1
strategy_family: weak_to_strong
preferred_market_phases:
  - FIRST_DIVERGENCE
  - ICE_POINT
preferred_theme_stages:
  - divergence
preferred_roles:
  - cycle_leader
  - sector_leader
  - front_row
eligibility:
  - first_limit_up_confirmed
  - theme_has_breadth
  - liquidity_pass
confirmation:
  - auction_not_weaker_than_expected
  - intraday_turn_strong
forbidden:
  - one_word_board
  - global_no_trade
  - theme_fade_confirmed
```

### 40.3 示例：容量趋势策略

```yaml
strategy_id: capacity_trend_v1
strategy_family: capacity_trend
preferred_market_phases:
  - FERMENTATION
  - ACCELERATION
  - FIRST_DIVERGENCE
preferred_styles:
  - institution_trend
preferred_roles:
  - capacity_leader
eligibility:
  - liquidity_above_threshold
  - institution_capital_confirmed
  - trend_structure_intact
entry:
  - breakout_with_volume
  - controlled_pullback
forbidden:
  - trend_break
  - institution_outflow_persistent
  - crowding_risk_extreme
```

---

## 41. Strategy Selector 与多策略并行

### 41.1 Strategy Selector

Selector 回答：

> 当前认知环境下，哪些策略有资格运行，适配度是多少？

```python
@dataclass(frozen=True, slots=True)
class StrategyEligibility:
    strategy_id: str
    strategy_version: str
    eligible: bool
    suitability_score: float
    blocking_reasons: tuple[str, ...]
    supporting_reasons: tuple[str, ...]
    required_missing_evidence: tuple[str, ...]
    source_belief_ids: tuple[str, ...]
    source_hypothesis_ids: tuple[str, ...]
    evaluated_at: datetime
```

适配度建议：

```text
suitability
  = market_phase_fit
  × theme_stage_fit
  × role_fit
  × evidence_quality
  × liquidity_fit
  × strategy_recent_calibration
  - crowding_penalty
  - regime_mismatch_penalty
```

Suitability 只负责排序，不覆盖硬准入与禁止条件。

### 41.2 多策略不是互斥开关

同一标的可同时产生多个 StrategyProposal，例如：

```text
PCB 中军：
  capacity_trend: BUY_PULLBACK
  rotation_arbitrage: NO_ACTION
  weak_to_strong: INELIGIBLE
```

系统不得把多个策略意见简单平均。每个 Proposal 保持独立，交由 Risk Gate 与 Portfolio Allocator 做组合层裁决。

### 41.3 StrategyProposal

```python
@dataclass(frozen=True, slots=True)
class StrategyProposal:
    proposal_id: str
    strategy_id: str
    strategy_version: str

    target_type: str
    target_id: str
    action_type: str
    timing_type: str
    suggested_position: float
    expected_holding_period: str

    entry_conditions: tuple[str, ...]
    confirmation_conditions: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    exit_plan: tuple[str, ...]

    expected_return_range: tuple[float, float] | None
    expected_loss_range: tuple[float, float] | None
    payoff_ratio: float | None
    confidence: float

    source_goal_ids: tuple[str, ...]
    source_belief_ids: tuple[str, ...]
    source_hypothesis_ids: tuple[str, ...]
    source_scenario_ids: tuple[str, ...]
    evidence_refs: tuple[EvidenceRef, ...]

    valid_from: datetime
    expires_at: datetime
```

### 41.4 Decision 契约调整

最终 Decision 必须增加：

```python
class TradingDecision:
    decision_id: str
    selected_proposal_ids: tuple[str, ...]
    rejected_proposal_ids: tuple[str, ...]
    strategy_allocations: tuple["StrategyAllocation", ...]
    risk_assessment_id: str
    portfolio_snapshot_id: str
    final_actions: tuple["TradingAction", ...]
    arbitration_trace: tuple[TraceStep, ...]
```

Decision 不得在没有 `strategy_id/version` 的情况下输出可执行行动。

---

## 42. Risk Gate 与 Portfolio Allocator

### 42.1 为什么 Strategy 后不能直接接 Decision

策略只关心自身机会；组合层必须处理：

- 多策略争夺同一风险预算；
- 同一因子暴露重复；
- 多个标的属于同一主题；
- 全局 no-trade；
- 组合回撤；
- 流动性与成交冲击；
- 策略相关性。

因此：

```text
Strategy Proposals
-> Global Risk Gate
-> Cross-Strategy Conflict Resolver
-> Portfolio Allocator
-> Decision
```

### 42.2 Strategy Allocation

```python
class StrategyAllocation:
    strategy_id: str
    proposal_id: str
    requested_risk: float
    approved_risk: float
    requested_position: float
    approved_position: float
    constraint_reasons: tuple[str, ...]
```

### 42.3 冲突裁决优先级

```text
data integrity
> global risk
> account risk
> liquidity
> strategy forbidden conditions
> portfolio concentration
> proposal confidence
> strategy suitability
> expected payoff
```

Belief 高不能越过风险硬门。

---

## 43. Meta Cognition 控制面

### 43.1 定位

Diary 回答“今天发生了什么、系统判断结果如何”。

Meta Cognition 回答：

> 系统为什么这样思考？它的思考过程在哪一步产生了系统性偏差？

Meta Cognition 不是主链中的串行 Engine，而是横跨所有认知与决策阶段的审计控制面：

```text
┌──────────────── Meta Cognition Control Plane ────────────────┐
│ World Model / Goal / Attention / Reasoning / Belief          │
│ Hypothesis / Strategy / Risk / Decision / Memory Retrieval   │
└──────────────────────────────────────────────────────────────┘
```

它观察主链，但不在实时路径中随意改写主链状态。

### 43.2 Cognitive Trace

```python
@dataclass(frozen=True, slots=True)
class CognitiveTrace:
    trace_id: str
    trade_date: date
    as_of: datetime

    world_model_version: str
    active_goal_ids: tuple[str, ...]
    attention_allocation_id: str
    evidence_snapshot_id: str
    reasoning_snapshot_id: str
    belief_snapshot_id: str
    hypothesis_event_ids: tuple[str, ...]
    retrieved_episode_ids: tuple[str, ...]
    strategy_proposal_ids: tuple[str, ...]
    decision_id: str | None

    trace_steps: tuple[TraceStep, ...]
```

### 43.3 Self Reflection

```python
@dataclass(frozen=True, slots=True)
class SelfReflection:
    reflection_id: str
    trade_date: date
    cognitive_trace_id: str

    outcome_summary: str
    error_items: tuple["ReasoningError", ...]
    bias_items: tuple["CognitiveBias", ...]
    missed_signals: tuple["MissedSignal", ...]
    late_reactions: tuple["LateReaction", ...]

    correctly_used_evidence: tuple[str, ...]
    incorrectly_weighted_evidence: tuple[str, ...]
    missing_evidence_requirements: tuple[str, ...]

    strategy_review: tuple["StrategyReview", ...]
    proposed_learning_items: tuple[str, ...]
    confidence: float
    evidence_refs: tuple[EvidenceRef, ...]
    review_status: str
```

### 43.4 Reasoning Error 分类

```text
EVIDENCE_MISSING
EVIDENCE_STALE
EVIDENCE_DUPLICATED
EVIDENCE_MISWEIGHTED
CAUSAL_OVERCLAIM
WORLD_MODEL_MISMATCH
GOAL_MISPRIORITIZED
ATTENTION_BIAS
CONFIRMATION_BIAS
ANCHORING_BIAS
OVERCONFIDENCE
UNDERCONFIDENCE
HYPOTHESIS_TOO_VAGUE
FALSIFIER_IGNORED
MEMORY_MISRETRIEVAL
STRATEGY_REGIME_MISMATCH
RISK_GATE_TOO_LATE
LATE_REACTION
```

### 43.5 归因不能只靠 LLM 自我反思

Self Reflection 必须优先使用可计算反事实：

1. 若补入遗漏证据，Belief 是否改变？
2. 若移除被过度加权证据，Hypothesis 是否仍被拒绝？
3. 若 Attention 分配不同，关键信号是否能更早进入推理？
4. 若选择其他 Strategy，Decision Outcome 是否改善？
5. 相似 Episode 是否被错误召回或遗漏？

LLM 只能总结上述诊断，不得凭语言流畅度判定“为什么错”。

### 43.6 Meta Cognition 输出的动作

只允许产生提案：

```text
ADJUST_EVIDENCE_WEIGHT_PROPOSAL
ADD_EVIDENCE_REQUIREMENT
REVISE_GOAL_POLICY_PROPOSAL
REVISE_ATTENTION_POLICY_PROPOSAL
REVISE_HYPOTHESIS_TEMPLATE_PROPOSAL
PAUSE_STRATEGY_PROPOSAL
RECALIBRATE_STRATEGY_PROPOSAL
ADD_EPISODE_TAG
WORLD_MODEL_UPDATE_PROPOSAL
NO_CHANGE
```

任何提案仍需 replay/shadow/approval。

---

## 44. Episodic Memory

### 44.1 从 Case Library 到 Episode

Case Library 偏向结构化归档与离线比较；Episodic Memory 强调“在某个时点，系统看到什么、相信什么、做了什么、后来发生什么”。

Episode 必须保存当时的信息状态，而不是事后重写的完整真相。

```python
@dataclass(frozen=True, slots=True)
class MarketEpisode:
    episode_id: str
    episode_type: str
    start_at: datetime
    end_at: datetime

    world_model_version: str
    initial_context_snapshot_id: str
    goal_ids: tuple[str, ...]
    attention_timeline_ids: tuple[str, ...]
    evidence_snapshot_ids: tuple[str, ...]
    belief_snapshot_ids: tuple[str, ...]
    hypothesis_timeline_event_ids: tuple[str, ...]
    strategy_proposal_ids: tuple[str, ...]
    decision_ids: tuple[str, ...]

    outcome_snapshot_id: str
    diary_id: str
    reflection_id: str | None

    episode_summary: str
    turning_points: tuple[str, ...]
    tags: tuple[str, ...]
    retrieval_features_version: str
```

### 44.2 双过程认知架构

```text
Fast Path:
  当前 Context
  -> Episodic Retrieval
  -> 相似 Episode
  -> 候选解释 / 候选 Strategy

Slow Path:
  Evidence
  -> Reasoning
  -> Belief
  -> Hypothesis
  -> Counterfactual

Verification:
  Fast Path 建议
  vs Slow Path 当前证据
  -> 一致 / 冲突 / 拒绝
```

Episodic Recall 提高反应速度，但不能直接形成 Decision。

### 44.3 Retrieval Query

检索维度：

```text
world_model_regime
market_fsm
emotion_vector
theme_structure
capital_rotation
leader_state
belief_trajectory
hypothesis_transition
strategy_context
time_of_day
cross_market_context
```

返回：

```python
class EpisodeRetrievalResult:
    episode_id: str
    similarity: float
    similar_dimensions: tuple[str, ...]
    different_dimensions: tuple[str, ...]
    applicable_lessons: tuple[str, ...]
    invalid_transfer_risks: tuple[str, ...]
    historical_strategy_ids: tuple[str, ...]
    historical_outcome_summary: str
```

### 44.4 Memory Misretrieval

必须检测：

- 只因表面涨跌形态相似而召回；
- 忽略制度、流动性和市场风格差异；
- 结果标签泄漏进检索向量；
- 过度依赖最近案例；
- 相似度高但关键因果条件缺失。

高相似 Episode 不能覆盖当前 Evidence。

### 44.5 Memory Consolidation

并非每个交易日都是 Episode。入库条件：

- 出现关键认知转折；
- Hypothesis 被明确确认/拒绝；
- Strategy 产生代表性成功或失败；
- Meta Cognition 发现新错误类型；
- World Model Rule 获得重要支持或反证；
- 人工标记。

相似且低价值的日常记录可合并为 Episode Cluster。

---

## 45. Strategy、Meta Cognition 与 Memory 的统一架构

### 45.1 最终运行链

```text
Market World Model
        │
        ├──────────────┐
        ▼              │
Goal Manager           │
        ▼              │
Attention Engine       │
        ▼              │
Evidence               │
        ▼              │
Reasoning              │
        ▼              │
Belief                 │
        ▼              │
Hypothesis Timeline    │
        │              │
        ├── Episodic Recall ──┐
        ▼                     │
Counterfactual                │
        ▼                     │
Strategy Selector <───────────┘
        ▼
Strategy Proposals
        ▼
Risk Gate
        ▼
Portfolio Allocator
        ▼
Decision
        ▼
Execution / Outcome
        ▼
Market Diary
        ▼
Self Reflection
        ▼
Episodic Memory
        ▼
World Model / Strategy / Attention Update Proposals
```

Meta Cognition Control Plane 横跨整条链，持续记录 Cognitive Trace，并在盘后生成 Self Reflection。

### 45.2 对原 Decision Layer 的修订

原架构：

```text
Scenario Engine
-> Risk Engine
-> Action Engine
```

修订为：

```text
Scenario Engine
-> Strategy Selector
-> Strategy Proposal Engines
-> Global Risk Gate
-> Portfolio Allocator
-> Decision Composer
```

`Action Engine` 不再持有隐含交易体系。所有 entry/exit/position/forbidden 规则迁移到显式版本化 StrategyProfile。

---

## 46. Strategy Layer 数据持久化

| 表 | 写入模式 | 说明 |
|---|---|---|
| `strategy_profile` | versioned | 策略定义 |
| `strategy_rule` | versioned | 策略规则 |
| `strategy_calibration_report` | append-only | 回测与校准 |
| `strategy_eligibility_snapshot` | append-only | 当时适配结果 |
| `strategy_proposal` | append-only | 候选行动 |
| `strategy_allocation` | append-only | 组合批准结果 |
| `trading_decision` | append-only | 最终决策 |
| `cognitive_trace` | append-only | 认知链审计 |
| `self_reflection` | versioned | 元认知复盘 |
| `market_episode` | immutable/versioned | 情景记忆 |
| `episode_retrieval_log` | append-only | 召回审计 |

StrategyProfile 与历史 Decision 必须通过 `strategy_id + version` 关联，禁止策略规则更新后改变历史解释。

---

## 47. Strategy 与 Meta Cognition 测试门禁

### 47.1 Strategy Contract

- 每个正式 Decision 必须引用 StrategyProfile version；
- forbidden condition 命中时 Proposal 不得进入 Allocation；
- missing critical evidence 默认阻断；
- Risk Gate 可否决任何 Strategy；
- 同一输入和策略版本生成相同 Proposal hash；
- 多策略 Proposal 不得在 Selector 层被平均。

### 47.2 Strategy Evaluation

必须分别评估：

- eligibility precision；
- entry timing；
- exit discipline；
- payoff ratio；
- drawdown；
- turnover/cost；
- regime-specific performance；
- strategy correlation；
- calibration stability。

策略选择评估必须 walk-forward，禁止在同一窗口选择并证明最佳策略。

### 47.3 Meta Cognition

- Cognitive Trace 引用链完整率 100%；
- 自动错误分类必须有可计算证据；
- LLM-only reflection 不得进入正式 Learning Item；
- Bias 判定可被 replay；
- Policy Update Proposal 不得自动生效。

### 47.4 Episodic Memory

- Outcome 不进入 retrieval feature；
- 检索记录包含相似与差异维度；
- Fast Path 结果必须经过当前 Evidence 验证；
- 被误召回 Episode 可追踪；
- 删除索引后可从 Episode 真源重建。

---

## 48. 优先实施顺序修订

Strategy Engine 是当前 v1.2 后最高优先级，不应等待完整 World Model 或 Episodic Memory。

### Priority 0：Strategy Contract（1 周）

1. 冻结 StrategyProfile、StrategyEligibility、StrategyProposal；
2. 将现有弱转强/1进2规则映射为首个 StrategyProfile；
3. Decision 增加 `strategy_id/version/proposal_id`；
4. Risk Gate 与 Strategy 解耦；
5. 添加架构守卫测试。

### Priority 1：Weak-to-Strong Strategy Adapter（1-2 周）

1. 复用现有 W2S/OneToTwo 真源和规则；
2. 不改算法结果，只显式化准入、确认、禁止、仓位和退出规则；
3. 输出 StrategyProposal；
4. 与现有 Decision 做 shadow diff；
5. 保留旧链回滚。

### Priority 2：Capacity Trend Strategy（2 周）

1. 冻结容量趋势证据；
2. 定义中军/机构/成交额/趋势规则；
3. 进入 shadow，不与 W2S 共用隐含阈值；
4. 建立跨策略风险预算。

### Priority 3：Strategy Selector + Portfolio（2-3 周）

1. 多策略 eligibility；
2. suitability 排序；
3. Proposal 冲突裁决；
4. Portfolio Allocation；
5. 组合回放。

### Priority 4：Meta Cognition + Episodic Memory（后续）

先记录 Cognitive Trace，再做自动 Self Reflection；先建立 Episode 真源，再做向量召回。禁止反向顺序。

---

## 49. 新增风险矩阵

| 等级 | 风险 | 缓解 |
|---|---|---|
| P0 | Strategy 规则继续隐含在 Decision 中 | 强制 Decision 引用 Strategy version |
| P0 | 多策略建议被直接平均 | Proposal 独立 + Portfolio 裁决 |
| P0 | Strategy 绕过全局 no-trade | Risk Gate 独立且优先 |
| P0 | 同窗口选择和验证策略 | walk-forward/out-of-sample |
| P1 | Strategy 数量过快膨胀 | Catalog 准入与 ACTIVE 审批 |
| P1 | Suitability Score 被当作收益预测 | 明确仅为适配排序 |
| P1 | Meta Cognition 产生伪因果归因 | 计算诊断优先、LLM 只摘要 |
| P1 | Episode 召回替代当前推理 | Fast/Slow 双路径验证 |
| P1 | Outcome 泄漏进 Memory Retrieval | as-of 特征与 outcome 隔离 |
| P2 | 完整 M9 延迟当前报告改造 | Strategy P0 与 M8 报告并行推进 |

---

## 50. 新增 ADR

1. ADR-STRATEGY-001：Decision 必须引用 StrategyProfile 和 StrategyProposal。
2. ADR-STRATEGY-002：Strategy、Global Risk、Portfolio Allocation 三层职责分离。
3. ADR-STRATEGY-003：多策略 Proposal 独立保留，禁止简单平均。
4. ADR-STRATEGY-004：Strategy Rule 使用受限 DSL 并版本化。
5. ADR-STRATEGY-005：策略发布必须通过 replay、walk-forward 和 shadow。
6. ADR-META-001：Meta Cognition 是审计控制面，不直接改写在线认知状态。
7. ADR-META-002：Self Reflection 必须基于 Cognitive Trace 和可计算诊断。
8. ADR-MEMORY-001：Episodic Recall 是快速建议路径，不得绕过当前 Evidence 与 Risk。
9. ADR-MEMORY-002：Episode Retrieval 特征禁止包含未来 Outcome。

---

## 51. v1.2 最终结论

认知决定“怎么看市场”，策略决定“如何利用这种认知”，风险与组合决定“最终能做多少”。

因此，完整系统不再是：

```text
Belief -> Decision
```

而是：

```text
Belief
-> Hypothesis
-> Strategy Eligibility
-> Strategy Proposal
-> Risk Gate
-> Portfolio Allocation
-> Decision
```

Meta Cognition 负责审计系统为什么这样想、为什么判断错误；Episodic Memory 负责快速召回类似市场经历；二者都不能绕过当前证据和正式风险门禁。

当前最优实施顺序是：

```text
先显式化现有弱转强 Strategy
-> 再新增容量趋势 Strategy
-> 再建设多策略 Selector 与 Portfolio
-> 最后接入 Meta Cognition 和 Episodic Recall
```

这条路线能在不等待完整 M9 的情况下，先把 AI Theme App 从“统一决策输出”升级为“共享认知底座上的多策略交易平台”。

---

## 52. v1.3 架构连续性原则

### 52.1 核心裁决

M8/M9 采用增量演进，不采用替换式重构。

```text
Existing System = Fact & Decision Production Plane
M8              = Cognitive Orchestration Plane
M9              = Agent Control & Learning Plane
```

三者是叠加关系，不是新旧替代关系。

### 52.2 四条不可破坏原则

1. 现有 Layer A/B/C/D 继续作为事实与基础决策生产者，职责不变。
2. DailyReviewV2 不删除；认知能力先以可选扩展接入，保持旧消费者兼容。
3. M8 Domain 永远不拥有原始数据计算逻辑，只消费版本化 Evidence Snapshot。
4. Notion 采用双层结构：上层认知结论，下层保留现有业务章节作为证据。

### 52.3 附加约束

5. M8 失败不得使已成功的旧复盘变为失败。
6. M8 不直接读取业务数据库表；数据库访问只存在于既有生产者和 Adapter 的 Application/Infrastructure 边界。
7. Evidence Adapter 只做映射、标准化、校验和 lineage，不重新计算业务指标。
8. 新旧输出至少经过连续 shadow 对账后，消费者才能扩大 M8 使用范围。
9. 所有切换必须支持按消费者、按交易日和按功能单独回滚。

### 52.4 投资保护

保持不动的能力包括但不限于：

```text
MarketRegime
ThemeDecision
ThemeCycle
ThemeCapital
MainlineDiscovery
MainlineLifecycle
LimitUpMatrix
StrongStock
MoneyFlow
DragonTiger
Abnormal
PostMarketDecisionV2
OneToTwo / W2S
DailyReviewV2
Notion Publisher lifecycle
```

M8 只在这些结构化输出之上增加认知快照和认知读模型。

---

## 53. 三平面总体架构

### 53.1 Plane 1：Fact & Decision Production

现有 A/B/C/D 和派生模块保持所有权：

```text
Raw Data / Collection
        │
        ▼
Layer A: Identity
        │
        ▼
Layer B: Cycle / Mainline / Market Regime
        │
        ▼
Layer C: StrongStock / Role / Watch Pool
        │
        ▼
Layer D: Decision / W2S / Setup Plan
        │
        ├── Capital / DragonTiger / Event / Technical
        ▼
post_market_recap_snapshot
```

这一平面负责“算事实、算领域结果、写现有真源”。

### 53.2 Plane 2：Cognitive Orchestration

```text
MarketKnowledgeBundle
        │
        ▼
MarketEvidenceAdapter
        │
        ▼
MarketEvidenceSnapshot
        │
        ▼
Reasoning
-> Belief
-> Hypothesis Timeline
-> Scenario
-> Strategy Proposal
-> Narrative
```

这一平面负责“组织、解释、串联”，不反向写入 A/B/C/D 真源。

### 53.3 Plane 3：Agent Control & Learning

```text
Stable/Dynamic World Model
Goal Manager
Attention Engine
Meta Cognition
Market Diary
Self Reflection
Episodic Memory
Model Update Governance
```

这一平面负责“系统如何思考、关注什么、如何学习”。

### 53.4 横切平面

```text
Risk Gate
Policy Registry
Schema Registry
Feature Flags
Snapshot Lineage
Replay / Shadow / Calibration
Observability / Audit
```

横切能力不归属单一 M 模块。

---

## 54. MarketKnowledgeBundle：现有输出的稳定汇聚边界

### 54.1 为什么不让 DailyReviewV2 直接成为 M8 真源

DailyReviewV2 是面向页面的 ViewModel，字段可能因展示需求发生裁剪、排序和聚合。若 M8 直接依赖它：

- 页面字段调整会改变认知输入；
- diagnostics/fallback 可能被误当作事实；
- 前端兼容语义会污染 Domain；
- Evidence lineage 难以追溯到原生产者。

因此，在现有领域输出与两个下游投影之间增加只读汇聚 DTO：

```text
Existing Domain Outputs
        │
        ▼
MarketKnowledgeBundle
        ├── DailyReviewV2Builder
        └── MarketEvidenceAdapter
```

DailyReviewV2 和 MarketEvidenceSnapshot 是兄弟投影，不是上下游关系。

### 54.2 契约

```python
@dataclass(frozen=True, slots=True)
class MarketKnowledgeBundle:
    bundle_id: str
    trade_date: date
    as_of: datetime
    snapshot_version: str

    market_regime: Mapping[str, Any]
    market_overview: Mapping[str, Any]
    index_technical: tuple[Mapping[str, Any], ...]

    theme_decisions: tuple[Mapping[str, Any], ...]
    theme_cycles: tuple[Mapping[str, Any], ...]
    theme_capital: tuple[Mapping[str, Any], ...]
    limit_up_matrix: Mapping[str, Any]

    strong_stocks: tuple[Mapping[str, Any], ...]
    stock_capital: tuple[Mapping[str, Any], ...]
    abnormal_signals: tuple[Mapping[str, Any], ...]

    dragon_tiger: tuple[Mapping[str, Any], ...]
    money_flow: tuple[Mapping[str, Any], ...]
    driver_events: tuple[Mapping[str, Any], ...]

    post_market_decision: Mapping[str, Any]
    setup_plan: Mapping[str, Any]

    source_snapshot_ids: tuple[str, ...]
    producer_versions: Mapping[str, str]
    module_coverage: Mapping[str, Any]
```

`Mapping[str, Any]` 只允许用于迁移边界。进入 Evidence Snapshot 前必须转为类型化契约。

### 54.3 Bundle Builder 的职责

允许：

- 从已有 `recap_doc` 结构化字段组装；
- 校验必需模块；
- 记录 producer/version；
- 生成稳定 content hash；
- 保留 source snapshot 引用。

禁止：

- 重新计算炸板率；
- 重新判定题材周期；
- 重新合计资金；
- 重跑 StrongStock；
- 用文本 fallback 推导事实；
- 用 LLM 补齐缺失字段。

### 54.4 Schema 演进

新增 `RepairScore` 不会“自动”进入 M8。正确流程是：

```text
ThemeCycle producer 新增 versioned field
-> MarketKnowledgeBundle schema 增加 optional field
-> Evidence Adapter 显式映射
-> Evidence schema minor version
-> Cognition Engine 按 capability 检测消费
```

显式演进比动态透传更可维护。

---

## 55. MarketEvidenceAdapter 架构

### 55.1 Adapter 目录建议

```text
stock_processing_service/
  application/
    services/
      market_cognition/
        post_market_fact_bundle_builder.py
        market_evidence_snapshot_builder.py
        adapters/
          market_regime_evidence_adapter.py
          theme_decision_evidence_adapter.py
          theme_cycle_evidence_adapter.py
          theme_capital_evidence_adapter.py
          strong_stock_evidence_adapter.py
          decision_evidence_adapter.py
          dragon_tiger_evidence_adapter.py
          event_evidence_adapter.py
```

### 55.2 映射示例

```text
MarketRegimeReview
  -> MarketStateEvidence

ThemeDecisionReview
  -> ThemeDecisionEvidence

ThemeCycleJudgement
  -> ThemeLifecycleEvidence

ThemeCapitalReview
  -> ThemeCapitalEvidence

StrongStockReview
  -> StockRoleEvidence

PostMarketDecisionV2
  -> PriorDecisionEvidence
```

### 55.3 EvidenceRef 反向追溯

每条 Evidence 必须能回到：

```text
EvidenceRef
-> MarketKnowledgeBundle field path
-> recap snapshot version
-> producer module/version
-> source record/table
```

M8 的 Narrative 只引用 EvidenceRef，不复制并宣称拥有底层事实。

### 55.4 Adapter 测试

每个 Adapter 至少覆盖：

- 完整输入；
- 合法空输入；
- partial；
- schema version 不兼容；
- source lineage 缺失；
- 重复实体；
- 数值单位；
- 时间点与未来数据门禁。

---

## 56. 执行拓扑：旁路而非内嵌大爆炸

### 56.1 推荐拓扑

现有 `BuildPostMarketRecapJob` 已承担较多编排职责。首期不继续把全部 M8 步骤直接塞入该类。

```text
BuildPostMarketRecapJob
  -> durable save post_market_recap_snapshot
  -> emit PostMarketRecapSnapshotBuilt

PostMarketRecapSnapshotBuilt
  -> BuildMarketCognitionJob
       -> build MarketKnowledgeBundle
       -> build Evidence Snapshot
       -> build Cognition Snapshots
       -> build Narrative Snapshot
       -> persist cognition status
```

### 56.2 为什么采用 durable event

1. 旧复盘成功不依赖 M8 成功；
2. M8 可以独立重试；
3. 可用历史 snapshot 离线回放；
4. 可按日期启用 shadow；
5. 避免 `BuildPostMarketRecapJob` 继续膨胀；
6. 认知策略调整不触发 A/B/C/D 重算。

### 56.3 同步模式

当生产稳定后，可为需要“生成后立即发布认知报告”的入口增加 orchestrator：

```text
PostMarketWorkflowOrchestrator
  1. await recap success
  2. await cognition success or timeout
  3. compose DailyReview
  4. publish according to feature flag
```

这不改变两个 Job 的独立边界。

### 56.4 失败状态

| Recap | Cognition | 对外行为 |
|---|---|---|
| success | success | 双层报告 |
| success | pending | 原报告 + “认知生成中”状态 |
| success | failed | 原报告 + 折叠诊断，不阻断阅读 |
| failed | not_started | 原有失败语义 |
| success | stale | 原报告；不展示过期认知结论 |

---

## 57. DailyReview 兼容演进

### 57.1 Phase 0：独立快照

不修改 DailyReviewV2：

```text
GET /api/v2/daily-review-v2
GET /api/v2/market-cognition/narrative
```

前端/Notion 聚合层分别读取。

### 57.2 Phase 1：V2 可选扩展

```python
class DailyReviewV2Extensions(TypedDict, total=False):
    market_cognition_v1: "MarketCognitionView"


class PostMarketDailyReviewV2(TypedDict):
    # 原字段全部保持
    ...
    extensions: NotRequired[DailyReviewV2Extensions]
```

兼容约束：

- 不删除、不重命名原字段；
- 旧客户端忽略 `extensions`；
- cognition 不 ready 时字段可缺省；
- 不用空对象伪装 ready；
- `schema_version` 仍保持当前兼容约定。

### 57.3 Phase 2：DailyReviewV3 组合契约

只有当多个消费者需要统一 envelope 时才引入 V3：

```python
class PostMarketDailyReviewV3:
    schema_version: Literal["daily_review_v3"]
    trade_date: str
    source: SnapshotSource

    cognition: MarketCognitionView
    evidence_sections: DailyReviewV2EvidenceView
    decisions: DecisionView
    diagnostics: DailyReviewDiagnosticsV3

    compatibility: {
        "daily_review_v2_snapshot_id": str,
        "legacy_section_available": bool,
    }
```

V3 是组合层，不重新计算 V2 数据。

### 57.4 不立即创建 V3 的理由

- V2 已有大量契约测试；
- 当前最需要验证的是 cognition 价值，不是 API 改名；
- 新版本会扩大前后端迁移面；
- 可选 extension 足以支持 shadow 和灰度。

---

## 58. Notion 双层报告架构

### 58.1 阅读模型

```text
# 盘后复盘

Part A：市场认知（新增，默认展开）
  1. 今日最大认知变化
  2. 昨日假设验证
  3. Belief 变化
  4. 当前 Market Story
  5. 明日 Goal / Scenario / Strategy

Part B：市场证据（原逻辑延续）
  6. 市场环境
  7. 涨停结构
  8. 主线与题材
  9. 资金与龙虎榜
  10. 核心标的/次日计划

Part C：附录（默认折叠）
  11. 创新高与行业趋势
  12. 数据质量
  13. Evidence Trace
```

### 58.2 Narrative 是索引，不是真源替代

示例：

```text
认知结论：
PCB Belief 由 58 上升至 72，原因是机构容量资金与前排强度同时增强。

EvidenceRef:
  theme_capital:9018144:2026-07-02
  strong_stock:002384:2026-07-02
  dragon_tiger:002384:2026-07-02
```

Notion 可以通过 toggle 展开对应证据摘要。若未来支持深链接，则链接到证据区块或独立 Evidence 页面。

### 58.3 去重规则

保留旧章节不意味着重复全文：

- 认知层只写“变化、解释、条件”；
- 证据层只写“事实、数值、对象”；
- 相同结论不在多个章节复述；
- 详细风险列表只保留一处；
- 数据质量永远位于附录。

### 58.4 Render Mode

```text
legacy_only:
  只渲染原报告

cognition_shadow:
  认知内容仅写日志/预览，不发布

dual_layer:
  认知首页 + 原证据章节

cognition_primary:
  认知首页默认展开，证据章节默认折叠
```

首个生产目标是 `dual_layer`，不是 `cognition_primary`。

### 58.5 发布器职责保持

`NotionPostMarketRecapPublisher` 继续负责：

- report_id；
- 幂等查询；
- archive/recreate；
- 分批 append；
- page properties。

新增 `PostMarketCognitionReportRenderer` 或组合 Renderer 负责 Part A。原 Evidence Renderer 保留。

---

## 59. Stable World 与 Dynamic World

### 59.1 分层

```text
Market World Model
  ├── Stable World
  └── Dynamic World
```

### 59.2 Stable World

稳定层包括：

- A 股涨跌停制度；
- T+1；
- 交易日历；
- 板块和指数定义；
- 融资融券基础规则；
- 证券代码和市场归属；
- 交易时间与竞价阶段；
- 固定数据语义。

特征：

- 低频更新；
- 变更需要 schema/policy migration；
- 由监管或正式制度来源驱动；
- 不允许从 Diary 自动学习。

### 59.3 Dynamic World

动态层包括：

- 机构风格偏好；
- 游资风格；
- 量化行为代理；
- 市场容量偏好；
- 热点扩散机制；
- 题材轮动速度；
- 情绪载体迁移；
- 角色演化经验。

特征：

- 有 validity window；
- 有 confidence；
- 有 regime scope；
- 由 Case/Episode 和 calibration 更新；
- 必须经过 out-of-sample/shadow。

### 59.4 依赖方向

```text
Stable World
  -> constrains Dynamic World
  -> informs Belief/Hypothesis/Strategy
```

Dynamic World 不得覆盖 Stable World 的制度事实。

---

## 60. M1～M9 统一 Agent Architecture

### 60.1 编号治理说明

仓库历史文档中 `M1/M2/...` 同时被用于“模块编号”和“阶段里程碑”。v1.3 不擅自重命名既有阶段；正式实施前必须建立 `Capability Registry`，冻结每个 M 编号的唯一系统语义。

在本设计中先按能力平面表达：

```text
M1～M7：Existing Market Capability Plane
M8：Market Cognition Engine
M9：Market Intelligence / Agent Control & Learning
```

### 60.2 统一体系图

```text
┌──────────────────────────────────────────────────────────────┐
│ External Data / Collection                                   │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M1～M7 Existing Capability Plane                             │
│ Identity / Theme Match / Cycle / Mainline / StrongStock      │
│ Capital / Event / Risk / Prediction / Decision / W2S         │
│ Ownership: Fact Producers & Existing Decision Producers      │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
                    MarketKnowledgeBundle
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M8 Cognitive Orchestration                                   │
│ Evidence -> Reasoning -> Belief -> Hypothesis -> Scenario    │
│ -> Strategy Proposal -> Narrative                            │
│ Ownership: Interpretation & Cross-day Cognition              │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ M9 Agent Control & Learning                                  │
│ World Model / Goal / Attention / Meta Cognition              │
│ Diary / Self Reflection / Episodic Memory / Model Governance │
│ Ownership: Think Allocation & Learn                          │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Consumers                                                    │
│ DailyReview / Notion / PreMarket / M6 / M7 / W2S / Monitor   │
└──────────────────────────────────────────────────────────────┘
```

### 60.3 Consumer 不允许绕过所有权

- M8 不回写 A/B/C/D 事实；
- M9 不直接改 ACTIVE Strategy/World Model；
- Notion 不计算业务语义；
- M6/M7/W2S 不从 Narrative 反解析事实；
- Consumer 通过 snapshot ID 和 typed contract 读取。

---

## 61. 三类流：数据流、控制流、学习流

### 61.1 数据流

```text
Raw Data
-> Existing Producers
-> Existing Snapshots
-> MarketKnowledgeBundle
-> Evidence Snapshot
-> Cognition Snapshots
-> Narrative / Decision Views
-> Consumers
```

数据流单向；禁止从 Narrative 回填 Evidence。

### 61.2 控制流

```text
World Model
-> Goal
-> Attention Budget
-> Cognition Execution
-> Strategy Eligibility
-> Risk/Portfolio
-> Consumer Feature Flags
```

控制流只改变“运行什么、投入多少、采用哪个策略”，不改变历史事实。

### 61.3 学习流

```text
Outcome
-> Diary
-> Self Reflection
-> Episodic Memory
-> Update Proposal
-> Replay
-> Shadow
-> Approval
-> New Policy/Model Version
```

学习流不能直接反向写在线模型。

### 61.4 审计关联

三类流通过 ID 关联：

```text
source_snapshot_id
fact_bundle_id
evidence_snapshot_id
cognition_snapshot_id
goal_id
attention_allocation_id
hypothesis_id
strategy_proposal_id
decision_id
diary_id
episode_id
model_version
```

---

## 62. 渐进迁移阶段

### Phase C0：契约与守卫（1 周）

交付：

- `MarketKnowledgeBundle`；
- Evidence Adapter interface；
- Cognition status；
- feature flag；
- 架构守卫测试。

门禁：

- A/B/C/D 文件无行为变化；
- DailyReviewV2 JSON snapshot 无差异；
- 原 Notion renderer 测试全通过；
- M8 Domain 无 DB Gateway 依赖。

### Phase C1：只读 Evidence Shadow（1-2 周）

交付：

- 从历史 recap snapshot 构建 Evidence；
- Evidence lineage；
- coverage；
- replay。

门禁：

- 不写正式 Decision；
- 关键事实与 V2 一致；
- 单位/时间/实体映射错误为 0；
- Evidence 构建失败不影响旧报告。

### Phase C2：Cognition Shadow（2 周）

交付：

- Reasoning/Belief/Hypothesis/Narrative shadow；
- 分析师 7/2 gold sample；
- 新旧认知对比报告。

门禁：

- unsupported claim 为 0；
- 认知结论全部引用 EvidenceRef；
- 不改变 M6/M7/W2S 输入。

### Phase C3：Notion Dual Layer 灰度（1-2 周）

交付：

- Part A Cognition Renderer；
- Part B 原 Evidence Renderer；
- `dual_layer` flag；
- dry-run preview。

门禁：

- 原章节数据不减少；
- 正文重复结论显著下降；
- cognition 失败自动降级 legacy；
- 7/2、7/3 与至少 3 个历史日人工验收。

### Phase C4：DailyReviewV2 Extension（1 周）

交付：

- 可选 `extensions.market_cognition_v1`；
- API contract；
- frontend optional consumer。

门禁：

- 旧消费者无需修改；
- 无 cognition 时响应仍合法；
- schema contract 向后兼容。

### Phase C5：Strategy Proposal Shadow（2-3 周）

交付：

- Weak-to-Strong Strategy Adapter；
- StrategyProposal；
- 旧 Decision shadow diff。

门禁：

- 不改变正式交易结论；
- 策略规则可映射到现有设计；
- Risk Gate 结果一致。

### Phase C6：消费者渐进接入（至少 10 个交易日）

顺序建议：

```text
Notion
-> PostMarket UI
-> PreMarket
-> Monitor
-> M6/M7
-> W2S formal decision
```

每个消费者独立开关、独立对账、独立回滚。

---

## 63. Feature Flag 与回滚矩阵

### 63.1 Flags

```text
M8_EVIDENCE_SHADOW_ENABLED
M8_COGNITION_SHADOW_ENABLED
M8_NOTION_RENDER_MODE
M8_DAILY_REVIEW_EXTENSION_ENABLED
M8_STRATEGY_SHADOW_ENABLED
M8_CONSUMER_PREMARKET_ENABLED
M8_CONSUMER_M6_ENABLED
M8_CONSUMER_M7_ENABLED
M8_CONSUMER_W2S_ENABLED
```

### 63.2 回滚

| 故障 | 回滚 |
|---|---|
| Evidence Adapter 错误 | 关闭 Evidence shadow |
| Cognition 不稳定 | Notion 回到 `legacy_only` |
| Narrative 不可读 | 保留 Evidence Sections，关闭 Part A |
| V2 extension 兼容问题 | 关闭 extension flag |
| Strategy shadow 漂移 | 停止 proposal 消费，保留日志 |
| M9 控制层异常 | 使用静态默认 Goal/Attention 或绕过 |

回滚不删除新快照，只停止 current pointer 和消费者读取。

---

## 64. 连续性验收矩阵

| 验收项 | 基线 | M8 Shadow | Dual Layer | 失败判定 |
|---|---|---|---|---|
| Layer A/B/C/D 输出 | 当前 snapshot | 必须一致 | 必须一致 | 任一业务结果漂移 |
| DailyReviewV2 原字段 | 当前契约 | byte/semantic diff | 保持 | 删除/改名/语义变化 |
| Notion 原证据行 | 当前报告 | 不影响 | 不减少 | 核心证据缺失 |
| M8 Evidence | 无 | 与 MarketKnowledgeBundle 对齐 | 对齐 | 单位/实体/时点错误 |
| Narrative | 无 | preview | Part A | unsupported claim |
| Cognition 失败降级 | legacy | legacy | legacy | 阻断旧报告 |
| M6/M7/W2S | 当前输入 | 不读取 M8 | 默认仍不读取 | 隐式切换 |

### 64.1 必须保留的回归样本

- 旧周期退潮日；
- 主线修复日；
- 无龙虎榜日；
- 数据 partial 日；
- 无交易计划日；
- 多主线轮动日；
- 7/2 分析师复盘样本；
- 7/3 当前系统冲突样本。

---

## 65. v1.3 新增风险

| 等级 | 风险 | 影响 | 缓解 |
|---|---|---|---|
| P0 | M8 直接读取数据库形成第二真源 | 事实口径分裂 | 只允许 Evidence Adapter 消费 MarketKnowledgeBundle |
| P0 | DailyReviewV2 被当作 Domain 真源 | 展示变化污染认知 | V2/Evidence 兄弟投影 |
| P0 | M8 失败阻断旧复盘 | 生产可用性下降 | durable event + 独立 Job + legacy fallback |
| P0 | Narrative 替代原证据章节 | 可审计性下降 | Notion dual layer |
| P1 | BuildPostMarketRecapJob 继续膨胀 | 维护与故障域扩大 | 独立 BuildMarketCognitionJob |
| P1 | 新字段动态透传造成 schema 漂移 | Engine 行为不可控 | 显式 adapter + version |
| P1 | M1～M7 编号语义冲突 | 计划与模块混淆 | Capability Registry |
| P1 | 双层报告内容重复 | 阅读负担仍高 | cognition/evidence 去重规则 |
| P2 | 长期保留双轨增加成本 | 维护负担 | 分消费者迁移，不删除证据层 |

---

## 66. v1.3 新增 ADR

1. ADR-CONTINUITY-001：M8 定位为只读 Cognitive Orchestration Layer，不替代现有 Fact Producers。
2. ADR-CONTINUITY-002：MarketKnowledgeBundle 为 V2 与 Evidence 的共享汇聚边界。
3. ADR-CONTINUITY-003：DailyReviewV2 与 EvidenceSnapshot 是兄弟投影。
4. ADR-CONTINUITY-004：M8 首期由 durable recap event 触发独立 Job。
5. ADR-CONTINUITY-005：DailyReviewV2 只做可选 extension，V3 后置。
6. ADR-CONTINUITY-006：Notion 采用 Cognition Overview + Evidence Sections 双层结构。
7. ADR-CONTINUITY-007：M8 Engine 禁止直接访问业务数据库。
8. ADR-CONTINUITY-008：所有消费者必须按 feature flag 独立灰度和回滚。
9. ADR-WORLD-001：World Model 分为 Stable World 与 Dynamic World。
10. ADR-NAMING-001：建立 M1～M9 Capability Registry，消除模块/里程碑编号冲突。
11. ADR-M8-009：Observation/Assessment 仅用于报告；eligible Hypothesis 经冻结、人工裁决后才进入 Ground Truth Dataset。

---

## 67. v1.3 最终架构结论

M8/M9 的建设目标是：

```text
Build Cognition without Breaking Report
```

最终架构不是：

```text
删除旧复盘
-> 重写全部计算
-> 用 Narrative 替代数据
```

而是：

```text
保留现有 Fact/Decision Producers
-> 建立稳定 MarketKnowledgeBundle
-> 并行生成 Evidence 与 DailyReviewV2
-> 在 Evidence 上构建 Cognition
-> 用 Narrative 索引原证据
-> 通过 feature flag 渐进迁移消费者
```

工程上，M8 类似建立在现有计算平面之上的认知缓存与编排层：

- 下层算法升级时，通过 Adapter 和 schema version 吸收变化；
- 上层消费者获得统一认知，但仍能追溯原证据；
- M8 故障时，原 DailyReviewV2 和 Notion 证据报告继续工作；
- 新旧系统可长期 replay 和对账；
- 已有 A/B/C/D 投资全部保留。

这套连续性设计比一次性实现完整 World Model 更优先。只有先证明 M8 能在“不改变旧结果、不阻断旧链路、不隐藏旧证据”的条件下产生更高质量认知，后续 Strategy、Meta Cognition 和 M9 学习闭环才具备可靠工程基础。

---

# PART III — Current Implementation Status (v2.0 Baseline, 2026-07-09)

> **状态更新日期：2026-07-09**
> 本文档记录 M8 体系自 v1.5 Core Contract Frozen 以来的实际实现状态。

---

## 28. M2.5 — Canonical Market Metrics Service（市场统一事实层）

### 28.1 定位

全项目唯一负责行情统计、短线情绪、连板生态、资金流、换手、涨停归因基础指标的事实计算层。

```
Raw Data (JYHF/THS/Eastmoney/TDX)
          │
          ▼
MarketMetricsService (SINGLE canonical source)
          │
          ▼
MarketMetricsSnapshot
          │
   ┌──────┼────────┬──────────┐
   ▼      ▼        ▼          ▼
Diagnosis  Chart   Emotion   Narrative
```

### 28.2 核心结构

```python
MarketMetricsSnapshot (单日快照)
├── MarketBreadthMetrics    # 涨跌比/成交额
├── LimitUpMetrics v1.1     # 涨停/封板/炸板/板型分类/换手/资金
├── RelayEcologyMetrics v2  # 晋级率/昨涨停反馈/LimitUp Feedback Score
├── LeaderEvolutionMetrics  # 龙头识别/状态/健康分数 (8-state expectation)
├── LossEffectMetrics       # 跌停/大面/亏钱效应
├── LossAttributionMetrics  # 亏钱归因 (高位/龙头/板块)
├── HighPositionDeathMetrics # 高位死亡指数 (三维加权)
├── DeathPropagationMetrics v1 # 死亡传播指数
├── ActiveCapitalMetrics    # 活跃资金/占比
└── EmotionMomentumMetrics v3 # 情绪动能 (relay-based real ratios)
```

### 28.3 数据源: Eastmoney Board Pool (a-stock-data 打板层)

所有涨停/连板/炸板/跌停数据统一来自 Eastmoney push2ex API:

| 数据池 | API端点 | 关键字段 | 状态 |
|--------|---------|----------|------|
| 涨停池 (ZT) | `getTopicZTPool` | `lbc`(连板数), `zdp`(涨幅), `fund`(封单) | **已集成** |
| 炸板池 (ZB) | `getTopicZBPool` | `zbc`(炸板次数) | **已集成** |
| 跌停池 (DT) | `getTopicDTPool` | `lbc`(连续跌停) | **已集成** |
| 晋级率计算 | yesterday ZT JOIN today ZT | per-stock limit_days | **已集成** |

- 数据库: `eastmoney_board_pool_daily` (每日采集)
- 采集任务: `scripts/collect_eastmoney_board_pool.py`

### 28.3.1 全市场涨跌家数: TDX MarketBreadthProvider (Phase 4.5.6-P0)

全市场 A 股上涨/下跌家数来自 TDX/mootdx，**禁止从 subject_stock_daily_snapshot 临时聚合**（该表是题材映射表，非全市场行情事实表）。

| 数据源 | 端点 | 字段 | 状态 |
|--------|------|------|------|
| TDX security list | `mootdx.quotes.stocks(market=0\|1)` | 全市场 A 股代码 | **已集成** |
| TDX batch quotes | `mootdx.quotes.quotes(symbol=[...])` | price, last_close | **已集成** |

- Provider: `stock_processing_service/integrations/a_stock_data/tdx_market_breadth_provider.py`
- 规则: `price > last_close → up`, `price < last_close → down`
- 覆盖: 5404 只 A 股（SZ+SH，过滤非 A 股编码）
- 门禁: coverage < 0.95 → 返回 None，不进入正式指标
- 7/10 基准: up=3561 down=1609（对照 THS: 3772/1678）

### 28.4 关键指标验证 (vs 分析师)

| 指标 | 7/7 AI | 7/7 Analyst | 7/8 AI | 7/8 Analyst |
|------|--------|-------------|--------|-------------|
| 涨停数 | 33 | 33 ✓ | 47 | 46 ✓ |
| 最高板 | 6 | 5 | 7 | 7 ✓ |
| 炸板数 | 23 | — | 14 | — |
| 跌停数 | 30 | — | 41 | — |
| 活跃资金 | 903亿 | 897亿 ✓ | 738亿 | 739亿 ✓ |
| 1→2晋级率 | 5.4% | 5.1% ✓ | 21.4% | 21.0% ✓ |
| 2→3晋级率 | 0.0% | 0.0% ✓ | 33.3% | 33.0% ✓ |
| Phase | 恐慌/冰点 | PANIC ✓ | 混沌 | REPAIR_WATCH |

### 28.5 实现文件清单

```
stock_processing_service/application/services/market_metrics/
├── __init__.py
├── contracts.py           # 全部 Metrics dataclass (冻结)
├── service.py             # MarketMetricsService (单一入口)
├── registry.py            # Metric Registry + Quality + Dependency Graph
├── providers.py           # Protocol 接口定义
├── board_pool_provider.py # Eastmoney BoardPool 实现
├── leader_evolution.py    # 龙头演化引擎 (8-state expectation model)
├── narrative_engine.py    # 因果叙事引擎 (MarketStory + EvidenceNode)
├── market_memory.py       # 市场记忆引擎 (Fingerprint + TurningPoint)
├── calibration.py         # 校准学习闭环 (DriftEngine + WeightProposal)
├── validation.py          # 验证快照
└── replay_benchmark.py    # 回放基准测试 (100分制)

stock_processing_service/integrations/a_stock_data/clients/
└── eastmoney_board_client.py  # Eastmoney 打板层 HTTP 客户端

stock_processing_service/database/migrations/
└── create_eastmoney_board_pool.sql

stock_processing_service/scripts/
└── collect_eastmoney_board_pool.py  # 每日采集脚本
```

---

## 29. 前端 — 分析师工作台 (Analyst Workspace v2)

### 29.1 页面结构

```
┌─ 日期选择器 ──────────────────────────────────────┐
├─ [情绪与图表] [观察方向] ── 标签页 ──────────────────┤
│                                                    │
│ 情绪冰点 / ICE_POINT  -78 / 100                    │
│ 33涨停  903亿活跃资金  633/4482涨跌比               │
│ 5日趋势 (static trend.json, 即时加载)              │
│                                                    │
│ ┌─ 为什么 ───┬── 明日预测 ──┬── 今日交易 ───┐      │
│ │ ✓ 涨停33家 │  修复 40%    │ ✓ 允许        │      │
│ │ ✓ 炸板23家 │  持续 50%    │ ✗ 禁止        │      │
│ └────────────┴─────────────┴───────────────┘       │
│                                                    │
│ ▼ 分析师图表 Evidence Charts                       │
│   [大盘势能] [情绪动能]                             │
│   [活跃资金] [核心板块节律]                          │
│   (7张静态JSON图表, 即时加载)                       │
└────────────────────────────────────────────────────┘
```

### 29.2 数据加载策略

| 数据类型 | 来源 | 加载方式 |
|----------|------|----------|
| 情绪节点/评分 | `/api/emotion-{date}.json` | 静态 JSON (即时), API 后备 |
| 5日趋势 | `/api/analyst-charts/trend.json` | 静态 JSON (即时) |
| 7张图表 | `/api/analyst-charts/{date}.json` | 静态 JSON (自动加载) |
| 主题工作区 | `/api/v1/analyst-workspace/` | SPS API (不阻塞情绪页) |

- 不再依赖 SPS 服务器实时 API 调用
- 日历切换即时更新 (URL sync + 数据自动刷新)
- 标签页使用 CSS display:none 切换 (零 JSX 嵌套修改)

### 29.3 关键组件

```
frontend/src/components/analyst/
├── AnalystWorkspacePage.tsx   # 主页 (标签页 + 日期选择)
├── EmotionDashboard.tsx       # 情绪仪表盘 (顶部卡片 + 证据区)
├── ChartRenderer.tsx          # SVG 图表渲染器 (7种图表类型)
│   ├── AnalystBreadthChart    # 大盘势能 (评分仪表 + 指标网格)
│   ├── AnalystMomentumChart   # 情绪动能 (色区指针 + 因子表)
│   ├── AnalystCapitalChart    # 活跃资金 (比例柱 + 指标)
│   ├── AnalystRelayChart      # 核心板块节律 (阶梯图 + 晋级率)
│   ├── AnalystStyleTable      # 机构/游资方向 (状态矩阵)
│   └── AnalystLimitUpChart    # 涨停分类 (题材卡片)
└── TrendLineChart             # 多日折线图 (viewBox 响应式)
```

---

## 30. 技术债务与已知限制

| 问题 | 影响 | 优先级 |
|------|------|--------|
| Emotion Momentum 公式 | AI=-6.2 vs Analyst=-12, 需 per-stock returns 持久化表 | P1 |
| 7/7 最高板 dev=1 (6≠5) | 恒尚节能 6/30 EM 数据缺失 | P2 |
| Death Index 偶发 None | `_build_death_index` 返回 None bug | P2 |
| 7/8 Phase 混沌≠REPAIR_WATCH | 修复信号检测不足 | P1 |
| 活跃资金 25.6万亿总成交额 | recap total_amount 单位待校准 | P2 |
| DeathPropagation 缺少 capital_escape | 资金逃离预警字段未实现，已从 §28.2 降级为 v1 | P1 |
| SPS 服务器不稳定 | 前端已切换为静态 JSON 优先 | P0 (已缓解) |

---

## 31. 当前能力矩阵

```
L0 市场事实        ✅ (Eastmoney Board Pool, 统一数据源)
L1 指标治理        ✅ (Metric Registry + Quality + Dependency Graph)
L2 市场诊断        ✅ (10-phase ontology v2, Emotion v4.1)
L3 因果叙事        ✅ (Narrative Engine + Evidence Chain)
L4 市场记忆        ✅ (Market Memory + TurningPoint + Failure)
L5 认知校准        ✅ (Calibration Learning Loop + Drift Engine)
L6 外部环境        ⬜ (Phase 4, 未开始)
```

---

## 32. M8 实施状态（2026-07-10 更新）

### Phase 4.1 — Analyst Reference Ingestion ✅

| Phase | 描述 | 状态 |
|-------|------|------|
| Phase 4.1a | Core Metrics Parser | ✅ Done |
| Phase 4.1b | Full Reference Parser + Field Evidence + Quality | ✅ Done |
| Phase 4.1c | Parser Preflight Hardening (tolerance OR, ratio normalization) | ✅ Done |
| Phase 4.1d | Analyst Reference Store (JSONL + manifest) | ✅ Done (converged into Phase 4.2) |

### Phase 4.2 — AI↔Analyst Alignment Replay Engine ✅

| Phase | 描述 | 状态 | 交付物 |
|-------|------|------|--------|
| T01 | AnalystReferenceStore (JSONL + manifest v2) | ✅ | `analyst_reference/store.py` |
| T02 | AI Reference View Adapter (metrics_only + diagnosis) | ✅ | `analyst_alignment/ai_adapter.py` |
| T03 | Comparator (MetricDiff + SemanticDiff) | ✅ | `analyst_alignment/comparator.py` |
| T04 | Analyst Turing Score (m8_ats_v1, A-F grade) | ✅ | `analyst_alignment/turing_score.py` |
| T05 | Replay CLI (`run_analyst_alignment.py`) | ✅ | `scripts/run_analyst_alignment.py` |

### Phase 4.2.1–4.2.3 — Calibration + Hardening ✅

| Phase | 描述 | 关键交付 |
|-------|------|----------|
| 4.2.1 | Calibration Patch (PhaseOntology + RiskGate + LossEffect) | `phase_ontology.py` |
| 4.2.2a | StrategyIntentMatcher v1 (8 intent labels) | `strategy_intent.py` |
| 4.2.2b | ThemeAliasResolver v1 (30+ alias map) | `theme_alias.py` |
| 4.2.3 | CLI Hardening (safe chart reads, partial tracking, exit codes) | `run_analyst_alignment.py` v2 |

### Phase 4.3 — Larger Batch Replay ✅

| 指标 | 值 |
|------|-----|
| 回放窗口 | 2026-07-01 ~ 2026-07-09 (7 有效交易日) |
| Raw ATS | 0.700 |
| Fair ATS | 0.790 |
| Fair D/F | 14% |
| Gap 分类 | COUNTING_POLICY_GAP×5, FORWARD_VS_HINDSIGHT×1 |

### Phase 4.3.1 — Evaluation Fairness ✅

- EvaluationGapClassifier: FORWARD_VS_HINDSIGHT / DATA_SOURCE_GAP / COUNTING_POLICY_GAP / SEMANTIC_MAPPING_GAP / WEEKEND_TRANSITION
- Raw vs Fair ATS dual scoring in aggregate report

### Phase 4.4 — Calibration Dashboard ✅

- `calibration_dashboard.md`: 7-section dashboard (score summary, gap classification, daily trend, component trend, hints ranking, D/F drilldown, phase timeline)
- `calibration_action_plan.md`: auto-generated prioritized action plan from hints + gaps

### Phase 4.5 — Workbench Review Workflow ✅

| 组件 | 描述 |
|------|------|
| Session Store | 8-state lifecycle (NOT_STARTED → GENERATING → DRAFT_READY → IN_REVIEW → APPROVED → PUBLISHED → STALE/FAILED) |
| AI Draft Generator | `scripts/generate_analyst_workbench.py --date YYYY-MM-DD` |
| Workbench API | 5 endpoints: GET session, POST generate/save-review/approve/publish |
| Guards | APPROVED blocks regenerate, PUBLISHED blocks save-review, invalid transitions raise |

### 当前能力全景

```
L0 市场事实     ✅ Eastmoney Board Pool + 7 AI chart days
L1 指标治理     ✅ Metric Registry + Quality + Dependency Graph  
L2 市场诊断     ✅ 10-phase ontology v2 + PhaseOntology + RiskGate
L3 因果叙事     ✅ Narrative Engine + MarketStory
L4 市场记忆     ✅ Market Memory + TurningPoint + Failure
L5 认知校准     ✅ Calibration Learning Loop + Drift Engine
L6 对齐引擎     ✅ Analyst Alignment Replay (Raw/Fair ATS, dashboard)
L7 工作台工作流  ✅ Workbench Review (draft→review→approve→publish)
L8 外部环境     ⬜ Phase 4.x (未开始)
```

### 当前基线

```
M8 Analyst Alignment Replay v1
  Window: 2026-07-01 ~ 2026-07-09 (7 days)
  Raw ATS: 0.700  |  Fair ATS: 0.790
  Tests: 32 (workbench) + 91 (alignment) = 123 all-pass
  Tags: m8-phase-4.2-replay-v1 → m8-phase-4.5-workbench-review-v1
```

