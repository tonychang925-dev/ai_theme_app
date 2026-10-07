# AI Theme App 架构与代码语义审计 R0（详细版）

审计模式：READ_ONLY

工程真源：`main` / `origin/main`，审计提交 `ddc9442e88c5bf6f5248bfb141e74472c48eb25a`

策略参考：`AI_THEME_APP_CANONICAL_INVESTMENT_STRATEGY_DEVELOPMENT_MODEL_v0.6.3_DRAFT.md` 的 L0–L12 语义，以及 Owner 提供的 v0.6.4 working-baseline 授权说明。当前可访问目录中未找到独立的 v0.6.4 文件；因此不把 v0.6.3 的 DRAFT 标题误写成已冻结规则。凡涉及未冻结 Owner Policy，按 `POLICY_UNFROZEN` / `UNAUTHORIZED_POLICY_FREEZE` 处理。

本文件只记录审计结果和纠正方向，不修改代码、数据库、schema、策略模型或生产配置。

## 1. 审计结论先行

当前系统不是“单一决策链”，而是以下几条并存链路：

```text
事实/对象生产
  ├─ 新链 M1–M7 / stock_processing_service
  ├─ 旧链 stock_service / database_service scripts
  └─ M8 Market Cognition sidecar

盘后 Job
  ├─ Layer C StrongStockTrackingUseCase
  ├─ Layer D1 读取既有 W2S pool
  ├─ Mainline discovery → review queue → lifecycle → MarketRegime
  ├─ 旧 PostMarketDecisionEngine（重新从 report_context 计算五层决策）
  ├─ PostMarketDecisionEngineV2（Layer C display assembler）
  └─ OneToTwoSetupPlanEngine
```

因此本轮总评为：

| 范围 | 结论 |
|---|---|
| 总体架构 | `SEMANTIC_DRIFT` |
| 新链分层与 Ports/Contracts | `PARTIAL`，存在 `WRONG_SCOPE` |
| L0–L12 策略链 | 只有局部链段符合，整体 `SEMANTIC_DRIFT` |
| 当前主风险 | 双决策链、report_context 回流、估算/默认值进入正式判断、竞价候选边界、未冻结政策被阈值化 |
| 是否发现策略模型自身无法回答的问题 | 有，登记为 `STRATEGY_MODEL_OPEN_QUESTION`，不由代码审计补规则 |

最重要的判断不是“某个模块有没有实现”，而是：同一字段/状态是否只有一个语义所有者、是否沿正确作用域流动、是否能在缺失时保持不可判定。

## 2. 目标架构基线（先于代码）

### 2.1 Overall Architecture v4.0

`docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md` 把 M1–M7 定义为事实与决策生产平面，M8 定义为只读认知编排层，M9 为后续自适应/学习层。M8 不拥有业务事实源，不重算 M1–M7，不写回事实，不阻塞旧复盘。

目标单向链为：

```text
M1–M7 Facts
  → MarketKnowledgeBundle
  → EvidenceSnapshot
  → ContextSnapshot
  → CognitionState
  → ThesisSnapshot
  → Consumer
```

快照必须不可变、版本化、可回放；运行状态可以更新，但必须事件化、可从 checkpoint + events 重建。缺失不得转成默认结论，每条判断必须有 EvidenceRef。

### 2.2 主线发现与生命周期

`mainline_discovery_architecture_design.md` 明确区分：

```text
Theme/Subject identity
  ≠ Mainline identity confirmation
  ≠ Mainline lifecycle
  ≠ Tradability
```

主线发现应从事件链、市场承认、前排/龙头、持续性等真实 FactContext 建候选；机器只能输出 `machine_fast_candidate` / `machine_slow_candidate` 等候选；必须经过 AnalystReviewQueue 和人工确认，才可进入统一生命周期。确认后只使用一个 UnifiedMainlineLifecycleEngine。市场环境另有自己的 broad / sentiment / mainline-environment 作用域。

设计文档特别禁止用 `report_context` 作为主线发现事实真源，也禁止用“单日热点”直接确认主线。

### 2.3 OneToTwo / Setup / Confirmation

`one_to_two_daily_review_architecture.md` 定义：

- Setup 只消费事实，不反向修改主线确认和 Layer A/B/C/D；
- 候选、硬门禁、技术门禁、评分、风险计划、执行确认分层；
- 空结果是合法结果；缺失必需字段要 fail-loud；可选字段缺失只能降级到 `pending/reject`；
- 竞价只输出 `auction_pass/watch/fail/risk` 等确认结果；盘中确认只能确认既有候选，不能创建新候选；
- Plan 不是 Buy，报告不能把 `focus/observe_only` 偷换成买入建议。

### 2.4 数据质量与回测

`data_status_spec.md`、`evidence_schema_v1.json` 与回测架构要求：

- `ok / partial / delayed / missing` 必须显式表达；
- missing 数据不得计入正式信号，不能静默补 0；
- `daily_open_proxy` 与 `real_auction` 必须分组，proxy 不得伪装成真实竞价；
- 回测必须按 `available_at` 防未来函数；
- 新链 UseCase 是回测唯一合法来源，旧链只允许兼容引用。

## 3. L0–L12 逐层审计矩阵

### L0 Evidence / Source

结论：`PARTIAL` + `SEMANTIC_DRIFT` + `UNAUTHORIZED_INFERENCE`

存在能力：

- M8 `MarketKnowledgeBundleBuilder` 从已有 recap/knowledge 组装 evidence，并计算 source coverage / quality envelope（`stock_processing_service/application/services/market_cognition/knowledge_evidence.py:81-145`）。
- `MainlineDiscoveryFactContextBuilder` 已按 read port 主动读取事件链、事件统计、周期证据、周期判断和资金事实，并在 diagnostics 中记录 missing/fallback（`stock_processing_service/application/services/mainline_discovery_fact_context_builder.py:61-90`）。
- auction confirmation 合约已经要求 missing → X，proxy → proxy level（`stock_processing_service/tests/contract/test_v2_2_auction_confirm_contract.py:134-205`）。

漂移证据：

- 盘后应用 Job 直接从 `_read_port._db` / `_db._db` 取 pool，并在 application 层执行 SQL（`build_post_market_recap_job.py:836-888, 1528-1548, 2260-2330`）。这违反架构文档中“Application 只编排、禁止 SQL、禁止触碰客户端细节”的冻结边界。
- M8 的 evidence adapter 本身不重算事实，但上游 `report_context` 仍混合了业务对象、fallback 和展示兼容字段；因此 EvidenceSnapshot 的“已计算事实”与旧 report payload 之间没有完全封闭的 producer contract。
- `build_post_market_recap_job.py:180-188` 的 `_d()` 把非法/缺失数值转成 `Decimal("0")`；这类归一化若进入正式判断，与“missing 不得成为默认结论”冲突。

判定：Evidence 能力存在，但事实生产、读取边界与缺失语义尚未收口。

### L1 Global Market Environment

结论：`SEMANTIC_DRIFT` + `WRONG_DATA` + `UNAUTHORIZED_INFERENCE`

存在能力：

- 新链有独立 MarketRegime / MarketEnvironment 相关模块，并在盘后链中生成 broad market、sentiment、mainline environment、trade mode、allow_trade 等字段。
- 旧链有 `MarketEnvironmentEngine`。

漂移证据：

- 旧 `MarketEnvironmentEngine` 明确从 `report_context.market` 读取数据（`post_market_decision/market_environment_engine.py:15-23`），不是从 v4.0 要求的版本化 EvidenceSnapshot / MarketContext 读取。
- 缺少 market score 时，空上下文默认 `score=0`，有部分上下文时又由涨停/跌停数推导 score（`:25-37`）；随后仍按阈值输出 `attack/normal/defense/wait` 和 `allow_trade`（`:39-104`）。这把估算/默认值推进了正式交易权限，属于 `UNAUTHORIZED_INFERENCE`，不是“保守处理”。
- 旧链 market mode 只有 `attack/normal/defense/wait`，而策略模型的 L1 语义是全市场大环境；`emotion_stage` 又直接取 relay/short-term sentiment，容易把 L3 周期语义重新混入 L1。

架构层面还存在双源：新链 MarketRegime 输出一组正式字段，旧 PostMarketDecisionEngine 又从 report_context 重新生成另一组 market environment。当前没有看到单一的 L1 owner 和冲突门禁。

### L2 Theme / Mainline Identity

结论：`PARTIAL` + `SEMANTIC_DRIFT` + `LEGACY_CONFLICT`

符合部分：

- 新链 MainlineDiscoveryEngine 文档和代码都明确：机器只出候选，不输出 confirmed；fast/slow 候选进入 human review（`mainline_discovery_engine.py:3-16, 189-214`）。
- Review service 的 `confirm_mainline` 才写入 `mainline_registry.identity_status=confirmed`（`mainline_review_service.py:41-72`）。
- `ActiveMainlineUniverseBuilder` 读取 confirmed registry，且区分存续主线与新发现（`active_mainline_universe_builder.py:40-90`）。

漂移/冲突：

- 旧 `MainlineJudgementService` 仅由事件链、涨停数、强势股数、龙头涨幅/涨停等统计计算 `is_main_theme` / tier（`stock_service/services/mainline_judgement_service.py:145-175`），这条 legacy judgement 与 registry-confirmed identity 并存。
- `ThemeDecisionEngine` 又把 `cycle.final_mainline_alive`、strength/fade score 直接转成 tier/decision，并从 stock facts 估算 market recognition（`post_market_decision/theme_decision_engine.py:26-68, 177-218`）。这使身份、周期、资金和交易决策重新在旧链中合并。
- 在 `BuildPostMarketRecapJob` 中，旧决策引擎在 `:800-808` 仍被正式执行并写入 recap；新 discovery/lifecycle/regime 链之后又执行 V2 assembler（`:1668-1715`）。这不是 shadow-only，而是两个结果都进入输出对象。

### L3 Mainline Lifecycle

结论：`PARTIAL` + `SEMANTIC_DRIFT` + `LEGACY_CONFLICT`

符合部分：

- 新链有 `MainlineStateTransitionService`，显式使用 previous snapshot，输出 from/to/transition（`mainline_state_transition_service.py:74-155`）。
- 生命周期测试验证 missing judgement → unknown / not alive，fade_confirmed → not trade alive，且 lifecycle 不直接输出 trading principle（`tests/test_mainline_lifecycle.py:38-148`）。

漂移证据：

- `ThemeCycleJudgementServiceV2` 仍以固定 threshold 从当日 evidence 计算多个 score，再通过 `previous_cycle_state` 只允许有限 repair 转移（`theme_cycle_judgement_service_v2.py:27-55, 247-270`）。它是“score → state”主导，而不是完整的 `previous state + transition evidence` 语义。previous state 不是所有状态转移的必要输入。
- `MainlineStateTransitionService` 的类注释写明 `final_mainline_alive = NOT fade_confirmed`，并把 `is_mainline = identity_confirmed AND final_mainline_alive`（`mainline_state_transition_service.py:55-94`）。这会把身份存续与周期退潮状态绑定成一个交易可用布尔量，虽然比纯 score 好，但仍不是 L2 identity 与 L3 lifecycle 的完全分离。
- 旧 chain 的 `final_mainline_alive`、`is_main_theme`、cycle state 与新 registry/lifecycle 同时存在，属于 `LEGACY_CONFLICT`。

### L4 Timing Resonance

结论：`MISSING`（正式的模型级 L1 × L3 共振实现）+ `UNAUTHORIZED_POLICY_FREEZE`

发现：

- 系统存在 market mode、cycle state、allow_trade、position_limit 等字段，但没有发现一个明确的 `TimingResonance = L1 × L3` 领域对象/契约，能够按模型要求区分 A/B/C/D/E 五类规则作用域。
- `ThemeDecisionEngine._decision_score` 把 mainline、market environment、leader、setup 按 0.35/0.30/0.20/0.15 加权（`theme_decision_engine.py:188-200`），这是一个旧链综合分，不是 L4 共振，也没有逐条引用 R2/R3/R4 或把 undefined 格子阻断。
- `TradingPrincipleEngine` 以 `market_mode == wait` 和是否存在 theme decision 直接决定 `allow_trade`（`trading_principle_engine.py:20-70`）。它把缺少正式共振语义压缩成 WAIT/allow，而模型明确要求 `BLOCKED_UNDEFINED` 与 `BLOCKED_POLICY_UNFROZEN` 不能写成普通 WAIT。

因此，任何当前固定的“某环境 + 某周期 → 可以做/不能做”组合，如果没有 canonical evidence 或 Owner policy，就应判为 `UNAUTHORIZED_POLICY_FREEZE`，而不是策略已实现。

### L5 Strong Stock / Role

结论：`PARTIAL` + `WRONG_SCOPE` + `LEGACY_CONFLICT`

存在能力：

- 新链 Layer C 有 `BuildStrongStockTrackingUseCase`；W2S candidate service 也有 role tags、support、prior7 等结构化输出。
- 主线生命周期设计有 LeaderCore/Role 输入；auction service 允许龙头、龙二、卡位、强趋势等角色。

漂移证据：

- 旧 `LeaderCoreEngine` 可以在 `strong_stock_reviews` 为空时直接回退到 `report_context.stock_facts`（`leader_core_engine.py:15-24`），再用 watch_score / support / main_net_inflow 重建 role 和 core_score（`:35-58`）。这不是消费已经确认的 `theme_leader_candidate` 或冻结角色事实，而是二次推断。
- `_role()` / capital score 等固定分段将 watch score/资金流映射成角色与行动；这类角色政策没有逐条回溯到 L5 角色定义和 evidence refs。
- `BuildPostMarketRecapJob._build_strong_hotspot_subjects()` 与 `_build_confirmed_mainline_hotspots()` 把强势股观察结果和 confirmed mainline 直接合并为 hotspot universe（`build_post_market_recap_job.py:2371-2431`），存在“主线宇宙/强势股宇宙/工作台热点宇宙”边界不清。

### L6 Strategy Router

结论：`SEMANTIC_DRIFT` + `UNAUTHORIZED_POLICY_FREEZE`

存在能力：

- `TradingPrincipleEngine` 输出 main strategy、allowed/forbidden actions、position limit；OneToTwo 也有 rule config/version。

漂移证据：

- 旧 router 只按 market mode 和 theme decision 选择“主线龙头优先 / 主线核心弱转强 / 空仓等待”，没有把 L1 × L3 × Role × Setup 的资格链作为显式 router input。
- `ThemeDecisionEngine` 的综合分权重与 `TradingPrincipleEngine` 的 mode mapping 是代码自定的政策；若这些不是 Owner 已冻结的政策，分类应为 `UNAUTHORIZED_POLICY_FREEZE`。
- 新旧两条 router 并存：旧 engine 的 `trading_principle` 写进 recap，新链 V2 又以 `allow_trade/trade_mode/position_limit` 生成 Layer C decision。没有单一 strategy router contract。

### L7 Setup

结论：`PARTIAL` + `LEGACY_CONFLICT`

符合部分：

- `OneToTwoSetupPlanEngine` 从 fact context → hard rule → score → risk plan 建立 Setup 计划；架构文档明确“Plan 不是 Buy”。
- `OneToTwoRuleEngine` 对 required missing fail/reject，对非主线、首板类型、一字板、晚封、低换手、无宽度等做门禁（`one_to_two_rule_engine.py:25-46` 起）。
- 回测架构规定 W2S 新链 UseCase 是唯一合法候选生成来源。

漂移证据：

- 盘后 Job 对 D1 的处理是读取既有 `weak_to_strong_candidate_pool`，并把 `pool_entry_type` 映射为 formal/observe（`build_post_market_recap_job.py:484-552`）；这符合“recap 不生成 D1”，但同时旧 W2S service 和旧 database scripts 仍作为其他入口存在，合法入口没有被工程上唯一化。
- `W2SCandidateService._weekly_midterm_gate()` 在 weekly data 不足时返回 passed=True（`w2s_candidate_service.py:215-234`）。这是明确的 fallback 进入候选资格，违反“估算/缺失不得参与正式判断”。若只是诊断候选，应显式 observe/pending，而不是 passed。
- W2S service 中 `formal_ok` / `observe_only_ok` 仍是固定阈值政策（`:521-537`），未证明这些阈值是 v0.6.4 已冻结 Owner Policy。

### L8 Expectation

结论：`MISSING` + `STRATEGY_MODEL_OPEN_QUESTION`

代码中存在“次日动作建议”“auction_confirm_only”“buy condition”等文本，但没有发现一个独立、冻结、带有效性条件与截止时间的 `Expectation` 对象，能够回答：

```text
明天应该看到什么？
在哪个时间窗验证？
何种观察结果证伪？
证伪后如何转入 L10/L11？
```

`LeaderCoreEngine._buy_condition()` 只是固定文案（`leader_core_engine.py:150-158`），不能替代 L8。模型本身也只给出“次日应该看到什么”的语义方向，没有冻结完整 schema、观察窗口与证伪协议。因此这里同时登记：

`STRATEGY_MODEL_OPEN_QUESTION`: L8 Expectation 的最小持久化契约、观察窗口、证伪事件、与 L9/L10 的状态转移尚未由 v0.6.4 明确。

代码不得自行补充“默认次日预期”或把 action advice 当作 expectation。

### L9 Confirmation

结论：`PARTIAL` + `SEMANTIC_DRIFT` + `WRONG_SCOPE`

符合部分：

- 竞价确认服务存在 hard reject、data_status、signal level、evidence schema 合约；missing/proxy/real auction 的测试边界明确。
- 新链 `BuildPreMarketBriefJob` 通过 candidate service → auction scorer → W2SConfirmService 形成确认链（`build_pre_market_brief_job.py:24-43, 66-72`）。

漂移证据：

- `database_service/scripts/build_pre_market_auction_signal.py:144-173` 在读取 W2S candidate 后直接写入 `mainline_alive=True`、`action_bias=watch_open`、`is_reversal_watch=True`；这是把候选输入硬编码成主线/反转上下文，属于 `WRONG_DATA` 与 `UNAUTHORIZED_INFERENCE`。
- 同一脚本仍直接通过 `PostgresDatabaseManager`/SQL 组织竞价信号，绕过新链的唯一入口与统一 snapshot/event contract。
- `AuctionSignalService.is_candidate_eligible()` 只检查 role/mainline_alive/action_bias（`auction_signal_service.py:55-69`）；如果上游字段是脚本硬编码的，竞价确认就不再是 `Market × Lifecycle × Role × Setup` 上下文中的确认，而是独立候选打分器。
- 架构测试正确区分了 proxy/real，但需要继续核实正式运行入口是否始终消费该 confirmation contract；当前存在旧脚本入口与新链入口并存。

### L10 Decision

结论：`SEMANTIC_DRIFT` + `LEGACY_CONFLICT`

存在能力：

- `OneToTwoSetupPlanDTO` 以及 W2S confirmation 输出了 observe/focus/approved/reject 等决策前状态。
- `PostMarketDecisionEngine` 输出 `trading_principle`，V2 输出 trade mode/allow trade/position limit。

漂移证据：

- 旧五引擎链的 flow 是 `MarketEnvironment → ThemeDecision → LeaderCore → NextDayWatchlist → TradingPrinciple`（`post_market_decision_engine.py:14-24, 37-87`），这相当于从 report_context 重新生成一套正式决策。
- `TradingPrincipleEngine` 把没有 theme decision 或 market wait 直接压成 `allow_trade=False` 和“空仓等待”（`trading_principle_engine.py:34-54`），没有区分 WAIT、BLOCKED_UNDEFINED、BLOCKED_POLICY_UNFROZEN。
- 当前 recap 同时保存旧 `trading_principle`、new MarketRegime/V2 decision、OneToTwo plan，未见一个决策冲突 resolver 或单一 DecisionSnapshot owner。

### L11 Position / Risk / Exit

结论：`PARTIAL` + `UNAUTHORIZED_POLICY_FREEZE`

符合部分：

- OneToTwo risk plan 有 trigger/invalidation/exit 字段，且架构文档要求 risk 在 decision 之后成为硬门禁。
- MarketRegime/TradingPrinciple 有 position_limit、no_trade 和 risk flags。

漂移证据：

- 旧 market mode 直接映射 1.0/0.5/0.3/0.0 position limit（`market_environment_engine.py:39-58`），旧 watchlist 又直接输出 `.3/.2/0` 一类建议；这些是代码固化的仓位政策，v0.6.3 Part 9 明确仍有若干仓位 Owner policy 未冻结。
- L11 所需的“角色 + 当前周期决定怎么拿；失效条件决定何时走”没有以状态化持仓管理对象实现。当前更多是文本化建议和计划字段，尚未证明能处理买入后角色升级/周期转移。

### L12 Review / Learning

结论：`PARTIAL` + `POLICY_UNFROZEN`

存在能力：

- M8 有 replay、validation dataset、eligibility、verdict 和 calibration 相关模块；架构上区分 Observation/Assessment/Narrative 与 eligible Hypothesis。
- 回测架构有 replay contract，要求 UseCase 调用链与 future-leak audit。

缺口/风险：

- `database_service/tests/integration/test_p2_phase0_decision_routing.py` 整体 skip，理由是 decision routing integration 尚未完成（该文件第 4 行）。因此不能把 unit contract 通过当成 L0–L12 全链路成立。
- 当前测试对 M8 对象契约覆盖较好，但尚未证明旧 decision chain、new regime、OneToTwo、auction confirmation、post-market snapshot、T+1 outcome 共享同一个 Decision/Expectation lineage。
- 回测架构已经规定 v0.x 收益验证停止、v1.0 只做 UseCase replay contract；任何仍从旧链直接验证收益或从静态字段复制 prior7 的入口应列入 legacy audit，而不能被当成新链学习闭环。

## 4. 重点假设的独立验证结果

| 审计假设 | 结果 | 分类 | 证据摘要 |
|---|---|---|---|
| L1 大盘环境与 L3 主线周期混成同一状态机 | 已验证存在混用，但不是唯一状态机 | `SEMANTIC_DRIFT` / `LEGACY_CONFLICT` | 旧 market engine 读 report_context 并取 relay sentiment；ThemeDecision 又用 cycle alive/score 直接进交易 tier；新 lifecycle 与旧 cycle 并存 |
| Mainline Identity 依赖 3 板龙头等后置证据 | 新 discovery 已避免直接确认，但 legacy judgement 仍使用 leader/limit-up 统计 | `PARTIAL` / `LEGACY_CONFLICT` | 新 discovery 明确 pending + human review；旧 MainlineJudgementService 用 leader_pct/leader_limit_up/strong count 生成 identity tier |
| Theme Lifecycle 是 score → state，不是 previous state + transition evidence | 仍存在 | `SEMANTIC_DRIFT` | V2 主要按固定 score threshold derive state；previous state 只参与 repair gate |
| 竞价做成独立选股/打分器 | 旧脚本路径存在 | `WRONG_SCOPE` / `WRONG_DATA` | 竞价脚本从 W2S pool 构造候选并硬写 mainline_alive/action_bias/reversal；AuctionSignalService 再独立打分 |
| OTO/W2S 脱离 Market × Lifecycle × Role 上下文 | 部分存在 | `SEMANTIC_DRIFT` | OneToTwo 有主线/生命周期门禁；但 W2S weekly data 缺失 bypass，旧候选池/竞价脚本有独立 fallback |
| 工作台 Theme Universe 漏掉短线核心股 | 不能仅凭代码下定论，但存在结构性风险 | `STRATEGY_MODEL_OPEN_QUESTION` + `PARTIAL` | 主线 universe 来自 confirmed registry；strong hotspot 另行 merge，二者不是同一 canonical short-term universe；需产品定义“真正短线核心股”的纳入契约 |
| 估算值/fallback 进入正式判断 | 已验证 | `UNAUTHORIZED_INFERENCE` | market score 缺失→0/limit-count proxy；weekly data insufficient→passed=True；非法数值→0 |
| 未冻结 Owner Policy 被代码写死 | 已验证多处 | `UNAUTHORIZED_POLICY_FREEZE` | mode→position_limit、综合分权重、W2S/role thresholds、默认 WAIT/allow mapping |

## 5. 架构门禁审计

| 门禁 | 结论 | 证据 |
|---|---|---|
| M8 不重算事实、不直查业务 DB | `WRONG_SCOPE` | M8 adapter 本身偏只读，但盘后 application job 直接取 DB pool/SQL；M8 与 report_context 边界不封闭 |
| M8 失败不阻塞旧复盘 | `PARTIAL` | 代码有部分异常降级，但盘后 Job 的 M8/主线/市场/旧决策步骤处于同一大型 Job，缺少可证明的独立 sidecar transaction boundary |
| Application 只编排 | `SEMANTIC_DRIFT` | `build_post_market_recap_job.py` 多处直接 SQL；`mainline_review_service.py:88-105` 也以 direct SQL 更新 review queue |
| Domain 只吃标准输入对象 | `PARTIAL` | 新链部分 domain 使用 DTO，但旧 decision engines 接收 `dict[str, Any]`/report_context |
| 单一对象层真源、页面/报告只读 snapshot | `PARTIAL` | snapshot DTO/ports 存在，但 report_context 仍作为二次计算输入，且旧/新 decision 字段同时写入 recap |
| 缺失不得默认结论 | `SEMANTIC_DRIFT` | `_d()`、market default zero、weekly insufficiency bypass |
| 人工确认前不得 confirmed_mainline | `COMPLIANT`（新链局部） | discovery engine 与 review service 语义正确；不能据此覆盖 legacy identity path |
| 竞价 proxy/real 分离 | `PARTIAL` | contract tests 合规；生产入口存在旧脚本硬编码与多入口，需运行链证明 |
| Replay 无未来函数 | `PARTIAL` | 回测文档和字段要求完整；当前报告未能证明所有旧入口均落实 available_at/tradable_at |

## 6. Correction Plan（只到纠正目标，不实施）

1. **先建立唯一语义 owner map**：为 L1、L2、L3、L4、L5、L6、L7、L9、L10、L11 各指定唯一 canonical object、producer、consumer；旧链输出只能标为 legacy projection 或 shadow。
2. **拆除双决策链的正式并行写入**：旧 `PostMarketDecisionEngine` 不能继续与新 MarketRegime/V2/OneToTwo 同时写正式 decision 字段；先做字段级冲突矩阵与只读对账，再决定兼容投影。
3. **收口事实读取边界**：把盘后 Job 的 `_db/_client/pool/SQL` 访问迁移目标定义为显式 ReadPort/Gateway 方法；本轮不实现，只登记为 architecture correction。
4. **将 L4 变成独立契约**：只实现已有 canonical R2/R3/R4 与已冻结 Owner policy；其余格子输出 `BLOCKED_UNDEFINED` 或 `BLOCKED_POLICY_UNFROZEN`，不能用旧综合分填满。
5. **禁止 fallback 进入正式资格**：market score 缺失、weekly data 不足、非法数值、daily proxy 等必须产生 quality/status 并降级为 observe/pending/X；不得转换为 0 分后继续判定。
6. **竞价改为 confirmation-only contract**：候选身份、主线、生命周期、角色、Setup 必须来自上游结构化对象；竞价脚本不能硬写 `mainline_alive=True` 等上下文；proxy 与 real 必须严格分组。
7. **建立 L8 Expectation 最小契约**：由策略 Owner 先定义 expectation 的字段、验证窗口、falsifier、过期规则，再由工程落地；代码不得自补。
8. **明确短线核心股 Universe**：如果工作台要展示“真正的短线核心股”，策略层必须先定义其与 confirmed mainline、strong watch、leader role、candidate pool 的关系；在此之前只能登记 open question。
9. **补充端到端 contract tests**：覆盖 L1×L3 作用域、identity-before-lifecycle、missing/proxy、no-trade 三态、旧链不得写正式 decision、M8 失败隔离、T+1 expectation/review lineage。

## 7. Open Questions（不得由代码审计代答）

1. L8 Expectation 的最小可持久化契约是什么？
2. “短线核心股”是否等同于 confirmed-mainline leader/front-row，还是允许未确认主线中的 early probe？
3. v0.6.4 对 L1×L3 36 个 `UNDEFINED` 格子的运行时输出是否统一采用 `BLOCKED_UNDEFINED`？
4. 未冻结的仓位政策、普通 RISK_OFF 下弱转强门槛、角色升级后的持仓管理，哪些已由 Owner 单独冻结？
5. 新链 MainlineDiscovery 与 legacy MainlineJudgement 的保留关系是 shadow、兼容投影还是淘汰？在没有 ADR 前不能由代码反推。

## 8. 审计边界与置信度

- 本报告基于 `main` 对象内容，未把当前 dirty worktree 的删除文件或未跟踪数据当作工程真源。
- 未执行数据库写入、代码修改、schema migration、生产操作或策略调整。
- `COMPLIANT` 只表示局部契约与目标架构一致，不表示整条 L0–L12 已通过。
- `STRATEGY_MODEL_OPEN_QUESTION` 只表示模型需要 Owner 补充定义，不允许工程以默认值、fallback 或阈值替代。
