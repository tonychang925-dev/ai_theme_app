# Phase 1.5 — Market World State Verification

> 版本：v1.0
> 日期：2026-07-06
> 状态：Draft — 待实施
> 关联文档：`docs/architecture/M8_Market_Cognition_Engine_架构设计文档.md` (v1.5 Core Contract Frozen)
> 前置门禁：v1.5 Core Contract Frozen
> 定位：验证 Market World State 的真实性、完整性、可解释性和可预测性

---

## 0. 架构原则

> **Phase 1.5 的目标不是提升交易胜率，而是验证 Market World State 的真实性、完整性、可解释性和可预测性。Trading Cognition 只是该世界模型的一个下游消费者，而不是 Phase 1.5 的成功标准。**

核心约束：

1. 按认知流水线（Cognitive Pipeline）组织，不按模块拆分
2. **MarketSubject** 统一 Aggregate Root — Theme/Leader/Index/External/Macro 都是 Subject，Node/Context/Quality/Hypothesis 全部引用 Subject
3. **MarketWorldModel** 是 Pipeline 的拥有者 — Pipeline 负责"如何构建"，WorldModel 负责"维护世界状态"
4. **DailyMarketState** 是版本化 Aggregate — state_id/parent_state/policy_snapshot 支持 State Diff/Replay/Rollback
5. Node 输出统一对象，不输出裸字符串
6. FSM 外部化为 Policy YAML，不硬编码
7. 所有评分保存完整向量，不只保存最终标签
8. Hypothesis 是确定性编译（Compiler），不是 LLM 生成（Generator），有 Inference→Candidate→Eligibility→Frozen 中间阶段
9. Replay 是 Historical Simulation 的一个环节，Simulation 维护 Timeline
10. 全部 Policy 统一版本管理（Policy Registry）
11. Metrics 分四层：World → Recognition → Prediction → Trading
12. Trading Validation 有硬门禁，不是自动启动
13. DailyMarketState 预留 M9 接口：working_memory / belief_state / attention_state / goal_state (全部 Optional)

### 0.1 Architecture Budget — 核心对象冻结

**MarketSubject、MarketWorldModel、PolicyRegistry 是 Phase 1.5 最后三个新增核心对象。此后不再新增。**

```text
Stable Core (不再扩展):
  MarketSubject       — Aggregate Root
  MarketWorldModel    — World State 拥有者
  DailyMarketState    — 版本化 Aggregate
  CognitionPipeline   — 认知流水线
  CycleNode           — 周期节点
  DivergenceQuality   — 分歧质量
  NodeMaturity        — 节点成熟度
  PolicyRegistry      — 统一 Policy 版本管理
  FrozenHypothesisSource — 冻结假设

Adaptive Layer (未来消费者——通过接口消费 DailyMarketState):
  GraphReasoner     → 消费 State + Graph → 因果推理增强
  BeliefEngine      → 消费 State + History → 信念更新
  AttentionEngine   → 消费 State → 注意力分配
  GoalManager       → 消费 State + Belief → 目标选择
  MentalSimulation  → 消费 State + CausalNetwork → 推演
  MetaCognition     → 消费 State + Timeline → 认知审计
  LearningEngine    → 消费 State + Verdict → 世界模型更新

约束:
  - Adaptive Layer 不侵入 MarketWorldModel 的内部状态
  - Adaptive Layer 通过 DailyMarketState 接口只读消费
  - 新增能力优先作为 Adaptive Layer 消费者，不修改 Stable Core
  - MarketWorldModel 保持稳定、最小、不可变
```

### 0.2 Architecture Budget 边界规则

```text
✅ 允许:
   - 新增 Adaptive Layer 消费者（消费 DailyMarketState 接口）
   - 修改 Policy YAML（Policy 本身就是可演化的）
   - 新增 dataclass 字段（Optional，向后兼容）
   - 新增 Metrics 层

❌ 禁止:
   - 新增 Stable Core 顶层对象（Engine / Projection / Model）
   - 修改已有 dataclass 的必填字段语义
   - 在 MarketWorldModel 内部添加新 Engine
   - Adaptive Layer 直接写入 MarketWorldModel 内部状态
```

### 0.3 Phase 1.5 的核心命题

```text
不是: 继续丰富世界模型
而是: 验证世界模型是否正确

验证链:
  MarketWorldModel.update(day) → DailyMarketState
  HistoricalSimulation.simulate(start, end) → SimulationTimeline
  Metrics.verify(timeline) → World Quality / Recognition / Prediction
```

---

## 1. 总体架构：MarketWorldModel + CognitionPipeline

```text
┌──────────────────────────────────────────────────┐
│              MarketWorldModel                     │
│  (维护世界状态；Pipeline 的拥有者)                  │
│                                                   │
│  current_state: DailyMarketState                  │
│  history: tuple[DailyMarketState, ...]            │
│  policy_registry: PolicyRegistry                  │
│                                                   │
│  update(day)     → DailyMarketState              │
│  snapshot()      → DailyMarketState              │
│  rollback(state) → DailyMarketState              │
│  diff(s1, s2)    → StateDiff                     │
│  simulate(start, end) → SimulationTimeline       │
│                                                   │
│  ┌─────────────────────────────────────────┐     │
│  │         CognitionPipeline               │     │
│  │  (负责"如何构建"；不持有状态)             │     │
│  │                                         │     │
│  │  build_context(day)    → Context       │     │
│  │  recognize_cycle(day)  → CycleNode[]   │     │
│  │  evaluate_divergence() → Divergence[]  │     │
│  │  estimate_maturity()   → Maturity[]    │     │
│  │  compile_hypothesis()  → Hypothesis[]  │     │
│  │                                         │     │
│  │  run(day) → DailyMarketState           │     │
│  └─────────────────────────────────────────┘     │
│                                                   │
│  # M9 Bridge — Optional, 全部实现为 None          │
│  working_memory: None                             │
│  belief_state: None                               │
│  attention_state: None                            │
│  goal_state: None                                 │
└──────────────────────────────────────────────────┘
```

**职责边界**：

```text
MarketWorldModel (Owner):
  拥有世界状态
  管理状态历史链
  提供 Diff / Rollback / Snapshot
  统一 Policy 版本管理
  → 为 Belief/Attention/Goal/Mental Simulation 预留入口

CognitionPipeline (Builder):
  消费 Evidence Snapshot
  执行认知流程
  输出新的 World State
  → 不持有状态，纯函数式
```

---

## 2. 四阶段分解

### Phase A — World State Construction

```
Evidence → Context → Cycle → Quality → Maturity
```

### Phase B — Reasoning

```
Inference → Candidate → Eligibility → Frozen Hypothesis
```

### Phase C — Simulation

```
Timeline → Replay → Reality → Validation
```

### Phase D — Metrics

```
World → Recognition → Prediction → Trading
```

---

## 3. Phase A — World State Construction

### A.1 MarketWorldModel + MarketSubject + CognitionPipeline

```python
class MarketWorldModel:
    """World State 的拥有者。Pipeline 只负责构建，WorldModel 负责维护。"""

    def __init__(self, pipeline: CognitionPipeline, registry: PolicyRegistry):
        self.pipeline = pipeline
        self.registry = registry
        self.current_state: DailyMarketState | None = None
        self.history: tuple[DailyMarketState, ...] = ()

        # M9 Bridge — 全部 Optional, 当前为 None
        self.working_memory: None = None
        self.belief_state: None = None
        self.attention_state: None = None
        self.goal_state: None = None

    def update(self, trade_date: date) -> DailyMarketState:
        """Pipeline.run() → 更新 current_state → 追加 history。"""
        state = self.pipeline.run(trade_date)
        self.history += (state,)
        self.current_state = state
        return state

    def snapshot(self) -> DailyMarketState:
        """返回当前状态的不可变快照。"""
        return self.current_state

    def rollback(self, state_id: str) -> DailyMarketState:
        """回滚到指定 state_id。"""
        ...

    def diff(self, s1: DailyMarketState, s2: DailyMarketState) -> StateDiff:
        """两个 World State 之间的结构化差异。"""
        ...

    def simulate(self, start: date, end: date) -> SimulationTimeline:
        """Historical Simulation → 返回完整 Timeline。"""
        ...


class CognitionPipeline:
    """负责"如何构建"；不持有状态；纯函数式。"""

    def __init__(self, fsm: CycleFSM, registry: PolicyRegistry):
        self.fsm = fsm
        self.registry = registry

    def run(self, trade_date: date) -> DailyMarketState:
        ...
```

**MarketSubject — 统一 Aggregate Root**：

```python
@dataclass(frozen=True, slots=True)
class MarketSubject:
    """统一的 Aggregate Root。Theme/Leader/Index/External/Macro 都是 Subject。"""
    subject_id: str
    subject_type: str   # theme / leader / index / external / macro / sector / emotion_carrier
    name: str
    # 所有 Context / Node / Quality / Maturity / Hypothesis 都引用 subject_id
```

此后所有对象（CycleNode / DivergenceQuality / NodeMaturity / Hypothesis）引用 `subject_id`，不直接引用 `theme_id`。

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| A.1 | `MarketWorldModel` 骨架 — update/snapshot/rollback/diff/simulate | `domain/market_cognition/market_world_model.py` |
| A.2 | `CognitionPipeline` — run/build_context/recognize_cycle/... | `application/pipeline/cognition_pipeline.py` |
| A.3 | `MarketSubject` — 统一 Aggregate Root | `domain/market_cognition/market_subject.py` |
| A.4 | `DailyMarketState` — 版本化 Aggregate（见 A.2） | `domain/market_cognition/daily_market_state.py` |

**验收**：
- [ ] `world.update("2026-07-03")` 返回完整 `DailyMarketState`
- [ ] `world.history` 包含完整的 State Chain
- [ ] 所有 Cognition Projection 通过 `subject_id` 引用，不直接引用 `theme_id`

---

### A.2 DailyMarketState — 版本化 Aggregate

```python
@dataclass(frozen=True, slots=True)
class DailyMarketState:
    """不可变 World State 快照。版本化，支持 Diff / Replay / Rollback。"""
    state_id: str               # hash(trade_date + content_hash)
    trade_date: date
    version: int                # 单调递增
    parent_state: str | None    # 前一日的 state_id（State Chain）
    created_at: datetime
    policy_snapshot: PolicySnapshot  # 生成此 State 时的全部 Policy 版本

    # ---- World State 内容 ----
    subjects: tuple[MarketSubject, ...]
    contexts: MultiHorizonContext
    cycle_nodes: tuple[CycleNode, ...]
    divergence_qualities: tuple[DivergenceQuality, ...]
    maturity_estimates: tuple[NodeMaturity, ...]

    content_hash: str
    evidence_refs: tuple[str, ...]

    # ---- M9 Bridge — 全部 Optional，当前实现为 None ----
    working_memory: None = None
    belief_state: None = None
    attention_state: None = None
    goal_state: None = None


@dataclass(frozen=True, slots=True)
class StateDiff:
    """两个 World State 之间的结构化差异。"""
    from_state: str
    to_state: str
    
    subjects_added: tuple[str, ...]
    subjects_removed: tuple[str, ...]
    
    node_changes: tuple[NodeChange, ...]       # 节点迁移
    maturity_changes: tuple[MaturityChange, ...]  # 成熟度变化
    hypothesis_results: tuple[HypothesisVerdict, ...]
    
    summary: str  # 人类可读的差异摘要


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """生成此 State 时的全部 Policy 版本快照——确保 Replay 100% 可重现。"""
    cycle_fsm: str          # e.g. "cycle_fsm.v1"
    divergence: str          # e.g. "divergence_policy.v1"
    maturity: str            # e.g. "maturity_policy.v1"
    compiler: str            # e.g. "compiler_policy.v1"
    snapshot_at: datetime
```

**原则**：Node 不是字符串，是对象。FSM 不硬编码，是 Policy。

```python
@dataclass(frozen=True, slots=True)
class CycleNode:
    """周期节点——不是 enum，不是裸字符串。"""
    node_id: str
    subject_type: str           # market / theme / leader
    subject_id: str
    trade_date: date

    name: str                   # CLIMAX / FIRST_DIVERGENCE / ...
    stage: str                  # 启动 / 发酵 / 加速 / 高潮 / 分歧 / 退潮
    stage_day: int              # 当前阶段第几天
    consecutive_direction: str  # accelerating / diverging / repairing / fading

    maturity: float             # 0-100 — 来自 NodeMaturity
    confidence: float           # 0-1 — 节点定位的置信度

    transition_candidates: tuple[TransitionCandidate, ...]
    quality_label: str          # accelerating / peaking / exhausting / stalling

    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransitionCandidate:
    target_node: str
    probability: float          # 0-1
    required_conditions: tuple[str, ...]
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| A.3 | 全部 v1.5 dataclass 写入 domain 层，frozen + slots | `domain/market_cognition/projections/` |
| A.4 | `EvidenceRef` 校验工具 | `domain/market_cognition/shared/evidence_ref_validator.py` |
| A.5 | ADR-M8-016~018 写入 | `docs/adrs/` |

**验收**：
- [ ] 全部 dataclass `@dataclass(frozen=True, slots=True)`
- [ ] 每个有 `__post_init__` 校验
- [ ] `CycleNode.name` 不是裸字符串，是受 `CycleFSM` Policy 约束的对象

---

### A.3 Policy Registry — 统一版本管理

```python
@dataclass(frozen=True, slots=True)
class PolicyRegistry:
    """所有 Policy 的统一版本注册中心。"""
    
    policies: dict[str, str]   # policy_name → version
    # e.g. {"cycle_fsm": "v1", "divergence": "v1", "maturity": "v1", "compiler": "v1"}
    
    def snapshot(self) -> PolicySnapshot:
        """冻结当前所有 Policy 版本，写入 DailyMarketState。"""
        ...

    def resolve(self, policy_name: str) -> Policy:
        """按版本加载 Policy 配置。"""
        ...


@dataclass(frozen=True, slots=True)
class Policy(Generic[T]):
    """版本化 Policy 基类。"""
    name: str
    version: str
    config: T                    # 从 YAML 加载的类型化配置
    valid_from: date
    valid_to: date | None
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| A.15 | `PolicyRegistry` + `PolicySnapshot` | `domain/market_cognition/policy/policy_registry.py` |

**验收**：
- [ ] 所有 Policy 通过 Registry 统一加载
- [ ] `PolicySnapshot` 写入每个 `DailyMarketState`
- [ ] Policy 版本变更后，历史 Replay 使用当时的 PolicySnapshot

---

### A.4 FSM Policy 外部化

**原则**：FSM 是版本化 YAML，不是 hardcoded Enum。

```yaml
# config/market_cognition/cycle_fsm_v1.yaml
version: "cycle_fsm.v1"
valid_from: "2026-01-01"

states:
  CHAOS:
    allowed_transitions: [INITIAL, ICE_POINT]
  INITIAL:
    allowed_transitions: [FERMENTATION, CHAOS]
  FERMENTATION:
    allowed_transitions: [ACCELERATION, CHAOS, FIRST_DIVERGENCE]
  ACCELERATION:
    allowed_transitions: [CLIMAX, FIRST_DIVERGENCE]
  CLIMAX:
    allowed_transitions: [FIRST_DIVERGENCE, SECOND_ACCELERATION, FADE]
  FIRST_DIVERGENCE:
    allowed_transitions: [DIVERGENCE_REPAIR, DIVERGENCE_WEAKENING, FADE]
  DIVERGENCE_REPAIR:
    allowed_transitions: [WEAK_TO_STRONG, SECOND_ACCELERATION, FIRST_DIVERGENCE]
  WEAK_TO_STRONG:
    allowed_transitions: [SECOND_ACCELERATION, FIRST_DIVERGENCE, FADE]
  SECOND_ACCELERATION:
    allowed_transitions: [SECOND_DIVERGENCE, CLIMAX, FADE]
  SECOND_DIVERGENCE:
    allowed_transitions: [DIVERGENCE_REPAIR, FADE, REBOUND]
  DIVERGENCE_WEAKENING:
    allowed_transitions: [DIVERGENCE_REPAIR, FADE, REBOUND]
  FADE:
    allowed_transitions: [ICE_POINT, REBOUND, CYCLE_END]
  ICE_POINT:
    allowed_transitions: [REBOUND, INITIAL, CHAOS]
  REBOUND:
    allowed_transitions: [INITIAL, FADE, SECOND_WAVE]
  SECOND_WAVE:
    allowed_transitions: [ACCELERATION, FIRST_DIVERGENCE, FADE]
  CYCLE_END:
    allowed_transitions: [CHAOS, INITIAL]

# 未来新增节点示例（Phase 2+）：
# FALSE_BREAKOUT:
#   allowed_transitions: [FADE, FIRST_DIVERGENCE]
# FAILED_REPAIR:
#   allowed_transitions: [FADE, DIVERGENCE_WEAKENING]
# ACCELERATION_EXTENSION:
#   allowed_transitions: [CLIMAX, FIRST_DIVERGENCE]
```

```python
class CycleFSM:
    """从 YAML 加载的版本化 FSM。"""

    def __init__(self, policy_path: str):
        self.config = yaml.safe_load(open(policy_path))
        self.version = self.config["version"]

    def is_valid_transition(self, from_node: str, to_node: str) -> bool:
        return to_node in self.config["states"][from_node]["allowed_transitions"]

    def allowed_next(self, node: str) -> tuple[str, ...]:
        return tuple(self.config["states"][node]["allowed_transitions"])
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| A.6 | `cycle_fsm_v1.yaml` 配置文件 | `config/market_cognition/cycle_fsm_v1.yaml` |
| A.7 | `CycleFSM` 加载器 + 转移校验 | `domain/market_cognition/policy/cycle_fsm.py` |

**验收**：
- [ ] YAML 与代码完全解耦，新增节点不需要改代码
- [ ] CycleNode 创建时强制校验 `name` 在 FSM 中存在
- [ ] `TransitionCandidate.target_node` 强制校验在 `allowed_transitions` 中
- [ ] FSM policy_version 写入 `CycleNode.evidence_refs`

---

### A.5 Multi-Horizon Context Builder

```python
def build_context(self, trade_date: date) -> MultiHorizonContext:
    """D1/D3/D5/D10/D20 多周期上下文。"""
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| A.8 | `MultiHorizonContextBuilder` — 消费 D-20..D0 Evidence Snapshot | `pipeline/builders/multi_horizon_context_builder.py` |
| A.9 | `ExternalAnchorContextBuilder` — 韩国/美股/SOX 锚定 | `pipeline/builders/external_anchor_builder.py` |
| A.10 | `EarningsSeasonContextBuilder` — 业绩披露日历 | `pipeline/builders/earnings_season_builder.py` |

**验收**：
- [ ] 每个核心题材 D1/D3/D5/D10/D20 状态非空
- [ ] 连续分歧/修复/加速识别正确
- [ ] Replay hash 稳定

---

### A.6 Divergence Quality — 保存向量，不保存标签

**原则**：`healthy/forced/panic/insufficient` 是 Policy 推导的 Label。真正保存的是五个维度。规则一改，Label 可重算；向量丢失则无法补救。

```python
@dataclass(frozen=True, slots=True)
class DivergenceQuality:
    """分歧质量——保存完整向量，Label 由 Policy 推导。"""
    quality_id: str
    subject_id: str
    trade_date: date

    # 五个维度 — 永久保存
    volume_contraction: float    # 0-1 缩量程度
    leader_intact: float         # 0-1 核心守位度
    rear_cleared: float          # 0-1 后排风险释放度
    capital_redirected: float    # 0-1 资金承接度
    duration_sufficient: float   # 0-1 时间充分度

    # Label — 由 Policy 推导，可重算
    quality_label: str           # healthy / forced / panic / insufficient
    policy_version: str          # 推导此 label 的 Policy 版本

    evidence_refs: tuple[str, ...]
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| A.11 | `DivergenceQualityAnalyzer` — 五维度计算 + Policy 推导 Label | `pipeline/analyzers/divergence_quality_analyzer.py` |
| A.12 | `divergence_policy_v1.yaml` — healthy/forced/panic/insufficient 判定规则 | `config/market_cognition/divergence_policy_v1.yaml` |

**验收**：
- [ ] 五维度向量永久持久化，Label 可随 Policy 重算
- [ ] Policy 规则修改后，历史 Replay 可产出新旧两个 Label（对比）

---

### A.7 Node Maturity — 保存向量，不保存分数

**原则**：`maturity_score: 82` 不可解释。必须保存整个 Vector。

```python
@dataclass(frozen=True, slots=True)
class NodeMaturity:
    """节点成熟度——保存完整向量。"""
    maturity_id: str
    subject_id: str
    trade_date: date

    # 完整向量 — 永久保存
    overall: float              # 0-100 综合成熟度
    crowding: float             # 0-100 拥挤度
    volume: float               # 0-100 量能健康度
    leader: float               # 0-100 龙头健康度
    emotion: float              # 0-100 情绪极端度
    time: float                 # 0-100 时间充分度

    quality_label: str          # accelerating / peaking / exhausting / stalling
    policy_version: str

    estimated_days_to_threshold: float | None
    inflection_likelihood: float  # 0-1

    evidence_refs: tuple[str, ...]
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| A.13 | `NodeMaturityEstimator` — 五维度评分 | `pipeline/estimators/node_maturity_estimator.py` |
| A.14 | `maturity_policy_v1.yaml` — 维度权重配置 | `config/market_cognition/maturity_policy_v1.yaml` |

**验收**：
- [ ] 五维度完整持久化
- [ ] `overall` 可由 vector + policy weights 重新计算
- [ ] 权重配置变更后，历史 Replay 可产出新旧两个 overall

---

## 4. Phase B — Reasoning

### B.1 World State Transition Compiler

**原则**：不是 Generator（像 LLM），是 Compiler（确定性编译）。不是 "Node Transition" 而是 "World State Transition"——真正发生迁移的是整个 Market World，Node 只是其中一个 Observation。

**四阶段编译流水线**：

```text
Inference (推理)
  → Candidate (候选)
  → Eligibility (门禁)
  → Frozen (冻结)
```

```python
class WorldStateTransitionCompiler:
    """将当前 World State 确定性编译为 State Transition Hypothesis。"""

    def compile(
        self,
        current_state: DailyMarketState,
        previous_state: DailyMarketState | None,
    ) -> tuple[FrozenHypothesisSource, ...]:

        # Stage 1: Inference — 从 World State 提取所有可编译命题
        inferences = self._infer_transitions(current_state, previous_state)

        # Stage 2: Candidate — 筛选满足编译条件的候选
        candidates = self._filter_candidates(inferences)

        # Stage 3: Eligibility — 通过 Eligibility Gate
        eligible = [c for c in candidates if self.gate.check(c)]

        # Stage 4: Frozen — append-only 写入
        return tuple(self._freeze(c) for c in eligible)

    def _infer_transitions(self, current, previous) -> tuple[Inference, ...]:
        """从 State Diff + Node 变化 + Maturity 变化 中推理可能的 World Transition。"""
        ...

    def _filter_candidates(self, inferences) -> tuple[Candidate, ...]:
        """按 Compiler Policy 筛选：maturity≥50, divergence≠not_applicable, ..."""
        ...

    def _freeze(self, candidate) -> FrozenHypothesisSource:
        """append-only 写入 FrozenHypothesisSourceStore。"""
        ...
```

**Inference 阶段消费的输入**：

```text
State Diff (previous → current):
  - 哪些 Node 发生了迁移？
  - 哪些 Maturity 达到了阈值？
  - 哪些 Divergence Quality 触发了信号？

Cognition Graph:
  - CausalChain 是否预示连带迁移？
  - External Anchor 是否发生变化？

Expectation:
  - Surprise ≥ 2 的方向是否预示加速迁移？
  - Surprise ≤ -3 的方向是否预示外部冲击打断？

Historical Case:
  - Top-1 Case 的 historical_path 是否预测类似迁移？
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| B.1 | `WorldStateTransitionCompiler` — 四阶段确定性编译 | `pipeline/compilers/world_state_transition_compiler.py` |
| B.2 | `compiler_policy_v1.yaml` | `config/market_cognition/compiler_policy_v1.yaml` |
| B.3 | `EligibilityGate` 增强 — 强制 `hypothesis_type == NODE_TRANSITION` | `domain/market_cognition/gate/eligibility_gate.py` |
| B.4 | `FrozenHypothesisSourceStore.append()` | `domain/market_cognition/store/frozen_hypothesis_source_store.py` |

**验收**：
- [ ] `compile()` 是确定性函数：相同输入 → 相同 `record_hash`
- [ ] 四阶段各自独立可测试
- [ ] Stage 2 (Candidate) 为未来 Belief 介入预留接口
- [ ] 100% 通过 Eligibility Gate
- [ ] 每日 ≥ 1 条 eligible Hypothesis

---

## 5. Phase C — Historical Simulation

### C.1 设计原则

不是 Replay（历史播放），是 Simulation（历史模拟）。区别：

```text
Replay:
  重放已有结果

Simulation:
  Day1: Evidence → Pipeline.run(Day1) → DailyMarketState + Hypothesis
  Day2: Evidence → Pipeline.run(Day2) → DailyMarketState + Verdict(Day1) + Hypothesis
  Day3: ...
  
  每一步只知道"截至当时的信息"，不知道未来
```

### C.2 Simulation Engine + SimulationTimeline

```python
class HistoricalSimulation:
    """逐日推进，无未来数据污染。输出完整 Timeline。"""

    def __init__(self, world: MarketWorldModel):
        self.world = world

    def simulate(
        self, start_date: date, end_date: date
    ) -> SimulationTimeline:
        timeline = SimulationTimeline()
        for day in date_range(start_date, end_date):
            state = self.world.update(day)           # World State
            hypotheses = self.world.pipeline.compiler.compile(state, prev)  # Hypotheses
            verdicts = self._verify_previous_day(day, state)  # Verdicts
            
            timeline.append(SimulationDay(
                date=day,
                state=state,
                hypotheses=hypotheses,
                verdicts=verdicts,
            ))
        return timeline

    def _verify_previous_day(self, day, state) -> tuple[Verdict, ...]:
        """验证前一日的 Hypothesis：Reality vs Prediction。"""
        ...


@dataclass(frozen=True, slots=True)
class SimulationTimeline:
    """完整的模拟时间线——所有 Simulation 结果的统一容器。"""
    days: tuple[SimulationDay, ...]
    
    @property
    def states(self) -> tuple[DailyMarketState, ...]: ...
    @property
    def hypotheses(self) -> tuple[FrozenHypothesisSource, ...]: ...
    @property
    def verdicts(self) -> tuple[MarketThesisValidationRecord, ...]: ...
    @property
    def events(self) -> tuple[TimelineEvent, ...]: ...


@dataclass(frozen=True, slots=True)
class SimulationDay:
    date: date
    state: DailyMarketState
    hypotheses: tuple[FrozenHypothesisSource, ...]
    verdicts: tuple[MarketThesisValidationRecord, ...]
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| C.1 | `HistoricalSimulation` 引擎 + `SimulationTimeline` | `pipeline/simulation/historical_simulation.py` |
| C.2 | `available_at` 门禁守卫 | `pipeline/simulation/guard.py` |
| C.3 | 8 个代表性场景数据集 | `datasets/simulation_scenarios/` |
| C.4 | CLI 脚本：`simulate --start X --end Y` | `scripts/simulate_world_transition.py` |

**验收**：
- [ ] 8 个场景至少覆盖 5 个完整交易日链
- [ ] `Timeline.states` 形成完整 State Chain
- [ ] `available_at` 违规 = 0
- [ ] Simulation hash 100% 可重现

---

## 6. Phase D — Validation Metrics

### D.1 四层指标体系

```text
Level 0 — World Quality（世界质量）
  验证：Market World 本身是否完整、一致、可靠
  ├─ Evidence Coverage            所有必需 Evidence 源是否就绪
  ├─ Evidence Conflict            Evidence 之间是否有矛盾
  ├─ Context Completeness         每个 Subject 的 Context 是否完整
  ├─ State Consistency            State Chain 中是否有逻辑矛盾
  └─ Policy Consistency           Policy 版本是否一致

Level 1 — Recognition（认知准确度）
  验证：系统是否"看清了"市场
  ├─ Subject Coverage             核心 Subject 的节点定位覆盖率
  ├─ Node Accuracy                节点定位正确率
  └─ Divergence Accuracy          分歧质量判断正确率

Level 2 — Prediction（预测准确度）
  验证：系统是否"预测对了" World State Transition
  ├─ Transition Accuracy          expected_transition == actual
  ├─ Timing Offset Distribution   节点到达时间偏差
  ├─ Brier Score                  概率校准
  └─ ECE                          期望校准误差

Level 3 — Trading（交易有效性）
  验证：认知是否转化为有效交易信号
  ├─ Left Probe Hit Rate          左侧试探有效性
  ├─ Right Confirm Hit Rate       右侧确认有效性
  ├─ Avoid Correct Rate           回避正确率
  └─ Wait Correct Rate            等待正确率
```

### D.2 Trading Validation 门禁

```text
Level 0 (World Quality) 全部通过:
  ☐ Evidence Coverage ≥ 95%
  ☐ State Consistency 违规 = 0
  ☐ Policy Consistency 违规 = 0
        ↓
Level 1 (Recognition) 全部通过:
  ☐ Subject Coverage ≥ 80% (连续 5 个交易日)
  ☐ Node Accuracy ≥ 70%
  ☐ Divergence Accuracy ≥ 65%
        ↓
Level 2 (Prediction) 全部通过:
  ☐ Transition Accuracy ≥ 50%
  ☐ Timing Offset ≤ 2 天占比 ≥ 70%
  ☐ Brier/ECE 样本量 ≥ 20
        ↓
Level 3 (Trading) 方可启动:
  ☐ 不得在门禁未通过时执行
```

**交付物**：

| # | 子任务 | 输出 |
|---|---|---|
| D.1 | Level 0 — World Quality 指标 | `pipeline/metrics/world_quality_metrics.py` |
| D.2 | Level 1 — Recognition 指标 | `pipeline/metrics/recognition_metrics.py` |
| D.3 | Level 2 — Prediction 指标 | `pipeline/metrics/prediction_metrics.py` |
| D.4 | Level 3 — Trading 指标（受门禁控制） | `pipeline/metrics/trading_metrics.py` |
| D.5 | 四层 Dashboard JSON 输出 | `pipeline/metrics/dashboard.py` |
| D.6 | Phase 交付报告模板 | `docs/project_control/reports/phase-M8.phase1.5-YYYYMMDD.md` |

**验收**：
- [ ] 四层指标各自独立计算
- [ ] 门禁逻辑强制执行（L0→L1→L2→L3 逐级解锁）
- [ ] Dashboard JSON 可直接导入 Notion/Grafana

---

## 7. 最终交付物清单

| # | 文件 | 类型 |
|---|---|---|
| 1 | `domain/market_cognition/market_world_model.py` | Domain |
| 2 | `domain/market_cognition/market_subject.py` | Domain |
| 3 | `domain/market_cognition/daily_market_state.py` (+ StateDiff + PolicySnapshot) | Domain |
| 4 | `domain/market_cognition/projections/` (全部 dataclass) | Domain |
| 5 | `domain/market_cognition/policy/cycle_fsm.py` | Domain |
| 6 | `domain/market_cognition/policy/policy_registry.py` | Domain |
| 7 | `domain/market_cognition/gate/eligibility_gate.py` | Domain |
| 8 | `domain/market_cognition/store/frozen_hypothesis_source_store.py` | Domain |
| 9 | `application/pipeline/cognition_pipeline.py` | Application |
| 10 | `application/pipeline/builders/` (context builders) | Application |
| 11 | `application/pipeline/analyzers/` (quality, cycle) | Application |
| 12 | `application/pipeline/estimators/` (maturity) | Application |
| 13 | `application/pipeline/compilers/` (hypothesis, 4-stage) | Application |
| 14 | `application/pipeline/simulation/` (simulation + timeline) | Application |
| 15 | `application/pipeline/metrics/` (四层指标) | Application |
| 16 | `config/market_cognition/cycle_fsm_v1.yaml` | Config |
| 17 | `config/market_cognition/divergence_policy_v1.yaml` | Config |
| 18 | `config/market_cognition/maturity_policy_v1.yaml` | Config |
| 19 | `config/market_cognition/compiler_policy_v1.yaml` | Config |
| 20 | `scripts/simulate_world_transition.py` | Script |
| 21 | `datasets/simulation_scenarios/` (8 场景) | Data |
| 22 | `docs/adrs/ADR-M8-016~018.md` | Doc |
| 23 | `docs/project_control/reports/phase-M8.phase1.5-YYYYMMDD.md` | Doc |

---

## 8. 依赖关系图

```text
Phase A (World State Construction)
  A.1 Pipeline + DailyMarketState
   ├─ A.2 Schema Contract
   ├─ A.3 FSM Policy YAML
   ├─ A.4 Multi-Horizon Context
   ├─ A.5 Divergence Quality (Vector)
   └─ A.6 Node Maturity (Vector)
        │
        ▼
Phase B (Reasoning)
  B.1 Node Transition Compiler
        │
        ▼
Phase C (Simulation)
  C.1 Historical Simulation Engine
        │
        ▼
Phase D (Metrics)
  D.1 Level 1 — Recognition ──┐
  D.2 Level 2 — Prediction ──┤ (并行)
  D.3 Level 3 — Trading ─────┘ (门禁：L1+L2 通过)
```

---

## 9. 时间线

```text
Week 1-2: Phase A.1~A.4  — Pipeline 骨架 + Schema + FSM + Context
Week 3-4: Phase A.5~A.6  — Divergence Quality + Node Maturity
Week 5-6: Phase B         — Node Transition Compiler
Week 7-8: Phase C + D.1   — Simulation + Level 1 Metrics
Week 9-10: Phase D.2      — Level 2 Metrics
Week 11+: Phase D.3       — Level 3 Metrics（门禁：L1 + L2 通过）
```

---

## 10. 门禁矩阵

| 门禁 | 条件 | 通过后 |
|---|---|---|
| Phase C 启动 | Phase A + B 全部验收通过 | 开始 Simulation |
| Level 1 指标启动 | Phase C Simulation 样本 ≥ 20 条 | 开始计算 Recognition 指标 |
| Level 2 指标启动 | L0 World Quality 全部 ≥ 阈值 AND L1 Recognition 全部 ≥ 阈值 | 开始计算 Brier/ECE |
| Level 3 指标启动 | L2 Prediction 全部 ≥ 阈值 | 开始 Trading 验证 |
| Phase 1.5 正式交付 | L0+L1+L2 全部 ≥ 阈值，连续 20 个交易日 | 进入 M9 Phase 1 评估 |
