# AI_THEME_APP
# ARCHITECTURE RECONCILIATION AND DRIFT CORRECTION MODEL
# v0.1

状态：ARCHITECTURE DESIGN DRAFT / OWNER APPROVAL REQUIRED

模式：READ_ONLY DESIGN

本文件只定义目标架构、职责边界、模块处置和实施前门禁，不修改代码，不修改数据库，不冻结未批准的策略政策，不生成 implementation task。

## 1. 设计目的

本模型用于把当前并存的新链、旧链、M8 认知链和竞价/W2S 链重新收敛到 v0.6.4 L0–L12 投资决策语义。

纠偏原则：

1. 策略层先定义语义 owner，工程层不能用现有代码结构反推策略。
2. 一个语义只能有一个正式 truth owner；其他模块只能消费、投影、诊断或 shadow。
3. L1 大盘环境、L2 主线身份、L3 主线生命周期、L4 共振、L5 角色、L6 路由必须是不同对象，不共享一个混合状态机。
4. 缺失、估算、代理、fallback 不得进入正式判断；只能作为诊断输入或触发降级。
5. OTO/W2S/竞价不能创建上游身份、生命周期或正式主线事实。
6. 旧链退役采用 `KEEP → SHADOW → DEPRECATE → RETIRE`，不允许新旧结果同时作为正式 truth。

## 2. 目标运行链

```text
L0 Evidence / Source
  ↓
MarketEvidenceSnapshot
  ↓
L1 MarketRegimeSnapshot       ← 唯一大盘环境语义 owner
  ↓
L2 MainlineIdentitySnapshot   ← IdentityRegistry + human confirmation
  ↓
L3 MainlineLifecycleSnapshot  ← previous state + transition evidence
  ↓
L4 TimingResonanceSnapshot    ← L1 × L3 policy evaluation
  ↓
L5 RoleSnapshot               ← L2/L3 + stock evidence
  ↓
L6 StrategyRouteSnapshot      ← route contract / blocked contract
  ↓
L7 SetupPlanSnapshot          ← OTO / W2S / other setup
  ↓
L8 ExpectationSnapshot
  ↓
L9 ConfirmationSnapshot       ← auction / open / intraday
  ↓
L10 DecisionSnapshot
  ↓
L11 PositionRiskExitSnapshot
  ↓
L12 ReviewLearningSnapshot
```

M8 作为只读认知编排层消费上述 versioned snapshots：

```text
L0–L11 snapshots
  → Evidence / Context / Cognition / Thesis
  → Report / Replay / Validation
```

M8 不成为 L1–L11 的业务 truth owner，不重算业务事实，不反向写入 L1–L11。

## 3. L1–L6 唯一职责模型

### 3.1 L1 Global Market Environment

唯一正式 truth owner：`MarketRegimeEngine`

唯一正式对象：`MarketRegimeSnapshot`

输入：

- `MarketEvidenceSnapshot.market`
- 全市场 breadth、指数、涨跌停、炸板、连板高度、流动性、跨市场等事实
- `MarketEmotionVector` 作为市场范围的观测维度

输出：

- broad market regime：例如 `SUPPORTIVE / NEUTRAL / RISK_OFF / EXTREME_RISK`
- market-wide trade gate
- market-wide risk flags
- data quality / source status / evidence refs

L1 禁止：

- 使用单一题材的周期状态作为全市场 regime；
- 产生某个题材的 `mainline_alive`；
- 产生某个题材的 lifecycle；
- 直接产生个股 role、setup 或 buy decision；
- 把缺失 score 补成 0 后作为正式 regime。

### 3.2 L2 Theme / Mainline Identity

唯一正式 truth owner：`MainlineIdentityRegistry`，由 `MainlineReviewService` 写入；机器发现只能产生候选。

唯一正式对象：`MainlineIdentitySnapshot`

合法状态：

```text
candidate → pending_review → confirmed / rejected / expired
```

确认条件必须来自：

- 事件/逻辑证据；
- 多日市场承认；
- 题材联动/前排/资金/持续性证据；
- 人工确认记录。

L2 禁止：

- 以 3 板龙头作为身份确认的硬前提；
- 以单日涨停数或单一 score 直接确认；
- 由 lifecycle 的 fade/start 状态反推 identity；
- 由 OTO/W2S/竞价确认新建正式主线身份。

### 3.3 L3 Mainline Lifecycle

唯一正式 truth owner：`UnifiedMainlineLifecycleEngine`

唯一正式对象：`MainlineLifecycleSnapshot`

生命周期状态：

```text
EARLY / START
→ FERMENTATION
→ ACCELERATION
→ CLIMAX
→ DIVERGENCE
→ REPAIR
→ FADE_WATCH
→ FADE_CONFIRMED / ENDED
```

生命周期更新必须同时消费：

- previous lifecycle snapshot；
- 当前 transition evidence；
- leader/front-row/relay/board structure；
- event continuity；
- market acceptance；
- L2 identity context。

L3 禁止：

- 只用当日 score 直接覆盖 state；
- 用 `final_mainline_alive` 同时承担 identity、lifecycle 和 tradability 三种含义；
- 直接产生全市场 L1 regime；
- 直接产生买入决定。

### 3.4 L4 Timing Resonance

唯一正式 truth owner：`TimingResonanceEngine`

唯一正式对象：`TimingResonanceSnapshot`

L4 是策略政策评估层，不是事实生产层：

```text
L1 MarketRegimeSnapshot
      ×
L3 MainlineLifecycleSnapshot
      ×
approved resonance policy
      → resonance verdict
```

输出至少包括：

- `resonance_status`：`ALIGNED / PARTIAL / BLOCKED_UNDEFINED / BLOCKED_POLICY_UNFROZEN`
- 使用的 L1/L3 状态；
- 命中的规则编号；
- 未定义格/未冻结政策；
- evidence refs；
- 是否允许进入某类 Strategy Route。

L4 禁止：

- 用旧综合分替代共振；
- 为 36 个未定义格擅自填入交易规则；
- 把 `WAIT` 当作 `BLOCKED_UNDEFINED` 或 `BLOCKED_POLICY_UNFROZEN`；
- 直接创建候选或个股 signal。

### 3.5 L5 Strong Stock / Role

唯一正式 truth owner：`LeaderRoleEngine` / `RoleSnapshotBuilder`

唯一正式对象：`RoleSnapshot`

输入：

- L2 confirmed identity 或明确的 candidate context；
- L3 lifecycle；
- 个股事实、前排结构、资金、强势股基因、承接与相对强度。

输出角色：

```text
cycle_leader / sector_leader / capacity_core / front_row
follower / supplement / old_leader / eliminated
```

L5 必须消费 L2/L3，不能仅通过 `watch_score`、`main_net_inflow` 或固定分段推导 role。

L5 禁止：

- 把角色评分直接当成 Strategy Route；
- 用 report_context stock facts 重新生成未经溯源的角色；
- 把 role label 作为竞价模块自己硬编码的输入。

### 3.6 L6 Strategy Router

唯一正式 truth owner：`StrategyRouter`

唯一正式对象：`StrategyRouteSnapshot`

Router 合同：

```text
route(
  market_regime=L1,
  mainline_identity=L2,
  lifecycle=L3,
  resonance=L4,
  role=L5,
  approved_strategy_policy,
  data_quality
) -> StrategyRouteSnapshot
```

`StrategyRouteSnapshot` 必须包含：

- `route_status`：`ROUTED / WAIT / BLOCKED_UNDEFINED / BLOCKED_POLICY_UNFROZEN / REJECTED`
- `strategy_id`：如 `ONE_TO_TWO`、`WEAK_TO_STRONG`；
- 资格条件与否决条件；
- 允许的 Setup 类型；
- position/risk policy reference；
- evidence refs；
- policy version；
- 不得越权的 downstream contract。

Router 不负责：

- 重新判定 L1/L2/L3；
- 重新打个股角色分；
- 生成竞价信号；
- 生成买入动作；
- 将未冻结政策隐式转成默认策略。

## 4. OTO / W2S 消费合同

### 4.1 OneToTwo

OTO 只能消费：

```text
L1 MarketRegimeSnapshot
L2 MainlineIdentitySnapshot
L3 MainlineLifecycleSnapshot
L4 TimingResonanceSnapshot
L5 RoleSnapshot
L6 StrategyRouteSnapshot(strategy=ONE_TO_TWO)
L0 stock/board/auction facts
```

OTO 输出：

- Setup candidate；
- hard-gate result；
- focus / observe_only / pending_review / reject；
- expectation；
- auction/intraday confirmation request；
- risk plan。

OTO 不得：

- 新建 mainline identity；
- 改写 lifecycle；
- 把 `observe_only` 变成正式买入；
- 在 auction 中发现并直接创建正式候选；
- 用缺失/代理数据晋级 formal。

### 4.2 W2S

W2S 只能消费：

```text
L1 MarketRegimeSnapshot
L2 MainlineIdentitySnapshot
L3 MainlineLifecycleSnapshot
L4 TimingResonanceSnapshot
L5 RoleSnapshot
L6 StrategyRouteSnapshot(strategy=WEAK_TO_STRONG)
L0 weakness/support/auction facts
```

W2S 的正式资格要求：

- 上游 context 完整；
- 主线/周期/角色可解释；
- 缺失数据转 `pending/observe/X`，不能 bypass；
- proxy 数据单独分组；
- confirmation 只能确认既有 candidate。

weekly data、auction data、support data 不足时：

```text
正式候选：不得晋级
观察候选：允许，但必须标记 quality/status
诊断：记录缺失、fallback、proxy、estimate
```

## 5. MarketEmotion / CycleFSM / MarketRegime 处置

| 模块/概念 | v0.1 处置 | 新职责 |
|---|---|---|
| `MarketRegime` | `KEEP`，升级为 L1 唯一 owner | 只负责全市场环境与全局交易闸门 |
| `MarketEmotion` | `KEEP_BUT_REPURPOSE` | 作为 L1 的市场范围观测向量/证据，不作为题材 lifecycle |
| `CycleFSM` | `KEEP_BUT_REPURPOSE` | 只服务 L3，必须 previous state + transition evidence |
| `ThemeCycleJudgementServiceV2` | `SHADOW` | 作为旧/候选 lifecycle 计算器对账，不能写正式 lifecycle |
| `final_mainline_alive` | `DEPRECATE` | 拆成 identity_status、lifecycle_state、tradability_status 三个字段 |
| `is_main_theme` | `DEPRECATE` | 只保留 legacy projection，不作为正式 identity truth |
| 旧 `market_mode` | `SHADOW` | 与 L1 MarketRegimeSnapshot 对账，不能独立产出正式决策 |
| 旧 `emotion_stage` | `DEPRECATE` | 由 L1 market emotion 或 L3 lifecycle 明确归属 |

## 6. 旧 PostMarketDecision 退役模型

### 6.1 处置结论

| 模块 | 处置 |
|---|---|
| `PostMarketDecisionEngine` | `DEPRECATE → RETIRE` |
| `MarketEnvironmentEngine`（旧 post_market_decision 子模块） | `SHADOW → RETIRE`，由 L1 owner 替代 |
| `ThemeDecisionEngine` | `RETIRE`，不得继续合并 L2/L3/L5/L6 |
| `LeaderCoreEngine` | `KEEP_BUT_REPURPOSE`，改为 L5 role projection，不输出交易动作 |
| `NextDayWatchlistEngine` | `DEPRECATE`，由 L6 route + L7 setup plan 替代 |
| `TradingPrincipleEngine` | `RETIRE`，由 L6 Router + L10 Decision 替代 |
| `PostMarketDecisionEngineV2` | `KEEP_BUT_REPURPOSE`，仅作为 Layer C read-model assembler |
| `BuildPostMarketRecapJob` | `KEEP_BUT_REPURPOSE`，只保留 orchestration / snapshot publication |

### 6.2 退役顺序

```text
Phase A  字段/owner 对账：旧输出不再宣称正式 truth
   ↓
Phase B  Shadow：旧链与新链只读计算并记录差异
   ↓
Phase C  Cutover：正式消费者只读 L1–L6 canonical snapshots
   ↓
Phase D  Deprecate：旧 engine 入口告警、禁止新增调用
   ↓
Phase E  Retire：删除旧决策生成职责，保留必要历史投影读取
```

退役门禁：

- 连续 replay 日的字段级差异可解释；
- 无旧链字段作为下游正式输入；
- L1–L6 每个对象都有唯一 producer；
- no-trade / blocked / missing / proxy 语义对账通过；
- M8、OTO、W2S、竞价、报告均完成 consumer migration；
- 通过 ADR/ARB 批准后才可删除旧入口。

## 7. 当前模块处置总表

### 7.1 Keep

| 模块 | 保留理由 |
|---|---|
| `MarketKnowledgeBundle` / Evidence adapter | 作为 M8/M1–M7 facts 到 Evidence 的适配边界 |
| `MainlineDiscoveryFactContextBuilder` | 真实事实读取方向正确，不使用 report_context 作为 discovery truth |
| `MainlineDiscoveryEngine` | 机器候选与 confirmed 分离的语义正确 |
| `AnalystReviewQueueBuilder` | 人工确认前置的架构正确 |
| `MainlineReviewService` 的确认语义 | `confirm_mainline` 写 registry 的职责正确；底层写入方式需迁移到 port |
| `ActiveMainlineUniverseBuilder` | 作为已确认主线 universe 读取器保留 |
| `OneToTwoRuleEngine` | 硬门禁、缺失拒绝、Plan 非 Buy 方向正确 |
| auction confirmation data-status contracts | missing/proxy/real 分离方向正确 |
| M8 Evidence/Context/Cognition/Thesis contracts | 作为只读认知层基础保留 |

### 7.2 Keep but Repurpose

| 模块 | 纠偏后职责 |
|---|---|
| `MarketRegimeEngine` | 唯一 L1 owner，输入改为 EvidenceSnapshot，禁止 fallback 正式判定 |
| `MarketEmotion` | L1 observation vector，不再表示题材周期 |
| `UnifiedMainlineLifecycleEngine` | 唯一 L3 owner，补齐 previous + transition evidence |
| `LeaderCoreEngine` | L5 role projection，只输出 role/evidence，不输出 auction action |
| `PostMarketDecisionEngineV2` | Layer C read-model assembler，不做 decision |
| `BuildPostMarketRecapJob` | orchestration-only；不得直接 SQL，不得重算事实 |
| `BuildPreMarketBriefJob` | consumption/publishing orchestration，不生成上游 identity |
| `StrongStockTrackingUseCase` | L5 输入生产/观察池，不成为主线 truth owner |
| `W2SCandidateService` | 只消费 L1–L6 context；缺失转 observe/pending |
| `W2SConfirmService` | 只做 existing candidate confirmation |
| `AuctionSignalService` | 只做 L9 confirmation，不做 universe discovery |
| `MarketCognition` M8 | 只读消费 canonical snapshots，不从旧 report_context 反推正式事实 |

### 7.3 Shadow

| 模块 | Shadow 目的 |
|---|---|
| `ThemeCycleJudgementServiceV2` | 与 Unified Lifecycle 对账 state/transition 差异 |
| 旧 `MarketEnvironmentEngine` | 与 L1 MarketRegimeSnapshot 对账 |
| 旧 `PostMarketDecisionEngine` | 记录旧/新 decision drift，不写正式 decision |
| 旧 `market_mode` / `emotion_stage` | 观察字段映射与冲突 |
| legacy `MainlineJudgementService` | 与 registry-confirmed identity 对账 |
| 旧 W2S/auction script path | 验证新链 consumer 覆盖率与候选差异 |
| legacy watchlist | 对账遗漏/误纳入，不作为正式候选源 |

### 7.4 Deprecate

| 模块/字段 | 退役原因 |
|---|---|
| `final_mainline_alive` 作为统一布尔闸门 | 混合 identity/lifecycle/tradability 语义 |
| `is_main_theme` 作为正式身份 | 与人工确认 registry 冲突 |
| `report_context` 作为 decision input | 不是结构化 truth snapshot |
| 旧 `trading_principle` | 被 L6/L10 分层替代 |
| 旧 `NextDayWatchlistEngine` | 把 route、role、setup、position 混在 watchlist |
| 旧 direct SQL application access | 违反 Ports/Gateway 边界 |
| 默认 0 / weekly bypass / silent fallback | 使不确定性进入正式判断 |

### 7.5 Retire

| 模块/职责 | 退役条件 |
|---|---|
| 旧 `PostMarketDecisionEngine` 正式决策职责 | 新 L1–L6/L10 consumer 全部切换后 |
| `ThemeDecisionEngine` | L2/L3/L4/L5/L6 owner 完整后 |
| 旧 `MarketEnvironmentEngine` 正式产出 | L1 对账通过后 |
| 旧 `TradingPrincipleEngine` | L6 Router + L10 DecisionSnapshot 完整后 |
| 竞价脚本中的候选构造逻辑 | confirmation-only contract 覆盖后 |
| legacy direct pool/SQL access in application | ReadPort/Gateway coverage 完成后 |

### 7.6 Missing New Capability

| 缺失能力 | 必须先解决的问题 |
|---|---|
| `TimingResonanceEngine` | Owner 需确认 undefined/policy-unfrozen 的输出语义 |
| `StrategyRouter` | route contract、blocked contract、policy version |
| `ExpectationSnapshot` | 预期、观察窗口、falsifier、过期规则 |
| `DecisionSnapshot` 唯一 owner | 解决旧 decision/V2/OTO 输出冲突 |
| `TradabilityStatus` | 从 identity/lifecycle 中拆出可交易性 |
| `RoleSnapshot` canonical contract | 角色必须消费 L2/L3，不能 score-only |
| `Fallback/Estimate Quality Gate` | 统一禁止正式判断消费 estimate/proxy/missing |
| `Legacy Projection Boundary` | 明确 legacy 字段只能读，不得反向进入正式链 |
| `End-to-end lineage contract` | L0 → L12 → L12 review 的 source/policy/availability trace |
| `State transition evidence contract` | L3 和 L10 都需要 previous/current/transition evidence |

## 8. fallback / estimate 的唯一允许位置

### 8.1 允许

- diagnostics；
- source coverage；
- data quality envelope；
- shadow comparison；
- analyst review queue 的“待补证据”；
- observe-only / pending / X 降级结果；
- replay report 中的 proxy group。

### 8.2 禁止

- L1 正式 regime；
- L2 identity confirmation；
- L3 lifecycle transition；
- L4 resonance pass；
- L5 formal role；
- L6 route approval；
- OTO/W2S formal candidate；
- L9 formal A/B confirmation；
- L10 ENTER/ADD；
- L11 position sizing / risk release。

### 8.3 强制传播规则

```text
missing / estimate / proxy
  → quality/status/diagnostic
  → pending / observe_only / X / blocked
  → never formal pass
```

## 9. Owner 批准前的架构门禁

本模型在 Owner 批准前，不得发 implementation task。至少需要批准：

1. L1–L6 的唯一 owner 与对象名称；
2. `MarketEmotion` 属于 L1 observation，不属于 L3；
3. `CycleFSM` 只服务 L3，必须 previous + transition evidence；
4. L4 undefined/policy-unfrozen 的输出，不得降级为 WAIT；
5. OTO/W2S 的上游消费合同；
6. 旧 PostMarketDecision 的 shadow/cutover/retire 顺序；
7. `final_mainline_alive`、`is_main_theme`、`market_mode` 等 legacy 字段的 projection 期限；
8. L8 Expectation 的最小策略语义；
9. 仓位、普通 RISK_OFF、角色升级后的持仓管理等 Owner Policy；
10. 哪些 `STRATEGY_MODEL_OPEN_QUESTION` 进入策略层重新定义。

## 10. 下一阶段边界

只有在本模型获得 Owner/Architecture Review Board 批准后，才允许生成下一份文档：

```text
AI_THEME_APP_ARCHITECTURE_RECONCILIATION_IMPLEMENTATION_CONTRACT_v0.1
```

该 implementation contract 才能进一步拆分：

- ADR；
- schema/contract changes；
- shadow instrumentation；
- consumer migration；
- tests；
- deprecation gates；
- rollback plan。

在此之前，任何直接修 P0、调阈值、删除旧引擎或迁移 schema 的行为，都属于越过架构批准门。
