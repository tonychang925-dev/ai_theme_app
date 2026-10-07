# CANONICAL_AND_LEGACY_DECISION_PRODUCER_INVENTORY

> **任务**：AI_THEME_APP_DRIFT_CORRECTION_PREIMPLEMENTATION_INVENTORY_P0 · 清单 2/2
> **工程基准**：`main@ddc9442e88c5bf6f5248bfb141e74472c48eb25a`
> **策略基准**：v0.6.4 APPROVED WORKING BASELINE（未冻结）
> **配套文档**：`EXECUTABLE_RULE_AUTHORITY_INVENTORY.md`（规则编号如 L4-01、OTO-05 指向该清单）、`AI_THEME_APP_DRIFT_AUDIT_R1_INDEPENDENT_VERIFICATION.md`
> **方式**：只读，从入口往下追调用链（API 路由、任务注册表、容器装配、引用搜索）。没有运行任何代码，没有访问数据库。
> **整理**：Mira（Claude），2026-10-07

---

## 0. 读法

### 0.1 运行状态

| 标记 | 判定依据 |
|---|---|
| **LIVE** | 新链；从在线入口（API 路由、任务注册表、API 启动时的循环任务）能追到 |
| **LEGACY_LIVE** | 旧链；同样能从在线入口追到，而且输出仍被下游消费 |
| **SHADOW** | 与另一条链并行运行，输出只写诊断，不被任何下游消费 |
| **DIAGNOSTIC** | 只被脚本、回测、校验工具调用 |
| **DEAD_CODE** | 全仓库没有引用 |

**说明：本轮没有发现严格意义上的 SHADOW。** 新旧两条链的输出都被写进了复盘文档，而且都有下游消费者。这本身就是 R1 DR-001 说的问题：双写，而不是影子运行。

### 0.2 其他字段

- **展示**：前端或报告是否直接读取这个输出。
- **决策权威**：输出是否进入交易许可、候选或动作。
- **boundary_status**：
  - `COMPLIANT`：经 Port / Gateway 访问数据；
  - `DIRECT_DB_VIOLATION`：Application 或 Domain 层自己建连接、写 SQL；
  - `UNKNOWN`：本轮没有核实。

### 0.3 在线入口

| 入口 | 位置 |
|---|---|
| 任务注册表 | `application/services/collection_task_registry.py`，由前端“采集调试页”和 API 触发。例如 `recap.snapshot` → `PostMarketRecapRunner`，见 `collection_task_runners.py:1327–1368` |
| 容器装配 | `application/orchestrators/bootstrap.py:77–187` |
| 复盘任务 | `BuildPostMarketRecapJob.execute`（`build_post_market_recap_job.py`，2564 行） |
| API | `api_app.py`。例如 `/api/v1/emotion/{trade_date}`（`:8034`）；弱转强选股（`:911`） |
| API 启动循环 | `api_app.py:267` K 线破位检测循环 |
| 盘前简报 | `pre_market_brief_auto_scheduler.py` → `BuildPreMarketBriefJob` |

---

## 1. 总表

| # | 生产者 | 位置 | 输入 | 输出 | 语义层 | 下游 | 状态 | 展示 | 决策权威 | 代际 | boundary_status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P-01 | `MarketMetricsService` | `application/services/market_metrics/service.py` | DB（自建连接，19 处 `fetch` / `asyncpg`）、复盘快照 | 大盘指标快照；情绪动能（含 `first_board_red_ratio`，口径错误） | L1 指标 | P-02、分析师图表、工作台、`api_app.py:7503` | LIVE | 是 | **否** | 新 | DIRECT_DB_VIOLATION |
| P-02 | `NarrativeEngine` | `market_metrics/narrative_engine.py` | P-01 快照 | `market_phase`（只看反馈分一个变量，见 L1-09） | L1，但用了 L3 的词 | `/api/v1/emotion`（`api_app.py:8034`，`:8057–8061` 映射成周期词）→ 前端 `EmotionDashboard`、`WorkbenchSectionsPanel` | LIVE | **是**（情绪页） | **否** | 新 | COMPLIANT（本身不访问 DB） |
| P-03 | `MarketRegimeFactContextBuilder` | `application/services/market_regime/market_regime_fact_context_builder.py` | report_context.market（**缺失时用默认快照**，L1-01）、指数 K 线（直连 DB；无数据时用 akshare 实时数据，L1-03） | 大盘事实上下文 | L1 事实 | P-04 | LIVE | 否 | **是**（经 P-04） | 新 | **DIRECT_DB_VIOLATION**（`:65–66`、`:120–121` 直接 `asyncpg.connect`） |
| P-04 | `MarketRegimeEngine` = Broad + ShortTerm + MainlineEnvironment + TradingPermission | `domain/services/market_regime/*` | P-03、周期复核（P-09） | `market_regime_review`：`allow_trade`、`trade_mode`、`position_limit` | **L1 + L4** | 复盘文档 → P-12（PDV2）、P-13（1进2，`one_to_two_rule_engine.py:115`）；前端 `EnginePostMarketView`、`RecapPage` | LIVE | 是 | **是** | 新 | COMPLIANT |
| P-05 | `MarketEnvironmentEngine`（旧） | `domain/services/post_market_decision/market_environment_engine.py` | 复盘上下文 | `market_environment_review`（含仓位） | L1 + L4（旧） | P-11 → 日复盘 V2（`post_market_daily_review_v2_builder.py:112`）、前端 `api.ts` | LEGACY_LIVE | 是 | 部分（经 P-11 的 trading_principle） | 旧 | UNKNOWN |
| P-06 | `MarketEmotionEngine` | `application/services/market_cognition/emotion_engine.py` | DB | 带周期词的大盘节点 | L1（混用 L3 词） | **无**（.py / .ts / .tsx 全仓库零引用） | **DEAD_CODE** | 否 | 否 | 新（未接线） | DIRECT_DB_VIOLATION |
| P-07 | `CycleFSM` + `config/market_cognition/cycle_fsm_v1.yaml` | — | — | 混合词汇状态机 | L1 / L3 混用 | 只有 3 个脚本：`scripts/batch_replay_runner.py:773`、`scripts/simulate_world_transition.py:51`、`stock_processing_service/scripts/verify_phase_a_world_state.py:82` | DIAGNOSTIC | 否 | 否 | 新 | — |
| P-08 | 主线发现链：`MainlineDiscoveryFactContextBuilder` → `MainlineLogicChainBuilder` → `MainlineMarketAcceptanceBuilder` → `MajorEventClassifier` → `MainlineDiscoveryEngine` → `AnalystReviewQueueBuilder` | 复盘任务 `:1405–1660`；`domain/services/mainline_discovery/*` | 事实上下文、DB | 机器候选（**从不输出已确认**，`mainline_discovery_engine.py:15`）、复核队列 → 人工确认 → `mainline_registry` | **L2** | 复核队列；人工确认后写入 registry，由 P-09、P-12、P-13 读取 | LIVE | 前端未检索到 `mainline_discovery_*` 键（**待确认**是否有其他展示入口） | 间接（人工确认后） | 新 | **DIRECT_DB_VIOLATION**：`MainlineLogicChainBuilder`（**Domain 层**）持有 pool 并直接 `conn.fetch`（`mainline_logic_chain_builder.py:125–154`） |
| P-09 | 周期链：`BuildThemeCycleEvidenceDailyJob` → `BuildDailySnapshotJob` → `SubjectCycleJudgementService`（**对所有题材**判定）→ Layer B 判定表 → `MainlineLifecycleFactContextBuilder`（**只读已确认主线**）→ `MainlineLifecycleLayerBAdapter` | `build_daily_snapshot_job.py:140–160`；`subject_cycle_judgement_service.py`；`mainline_lifecycle/*`；复盘任务 `:1676–1717` | 题材周期证据（缺失时 fail-fast，`build_daily_snapshot_job.py:148–152`，这一点做得好） | Layer B 题材状态；`mainline_lifecycle_reviews`（只针对已确认主线） | **L3** | P-04、P-12、P-13、强势股池 | LIVE | 前端未检索到 `mainline_lifecycle` 键 | **是** | 新 | COMPLIANT（经 read_port） |
| P-10 | `ActiveMainlineUniverseBuilder` | 复盘任务 `:1409–1413`、`:1755–1760` | registry | `active_mainline_universe` | L2 投影 | P-12 | LIVE | 否 | 是 | 新 | COMPLIANT |
| P-11 | **旧决策链** `PostMarketDecisionEngine` = MarketEnvironment + ThemeDecision + LeaderCore + NextDayWatchlist + TradingPrinciple | `domain/services/post_market_decision/*`；复盘任务 `:27`、`:129`、`:828–835` | 复盘上下文、题材上下文、强势股复核 | `market_environment_review`、`theme_decision_reviews`（35/30/20/15 加权，LEG-01）、`strong_stock_decision_reviews`、`watchlist_reviews`、`trading_principle` | L1 / L2 / L4 / L5 / L10 混合 | 通过 `recap_doc.update(...)` 并入复盘文档 → 日复盘 V2 透传（`post_market_daily_review_v2_builder.py:112–136`）→ 前端 `RecapPage`（`watchlist_reviews`，`:1127`）；Notion 渲染器；**1进2 事实构建要求 `trading_principle` 必须存在**（`post_market_setup_fact_context_builder.py:43–47`） | **LEGACY_LIVE** | **是** | **是**（1进2 硬依赖其存在；观察清单在前端展示） | 旧 | UNKNOWN |
| P-12 | `PostMarketDecisionEngineV2` | `domain/services/post_market_decision_v2/post_market_decision_engine_v2.py`；复盘任务 `:1766–1797` | 已确认主线、周期复核、P-04 许可（`:68–70`）、Layer C 行 | `post_market_decision_v2` | L10 | 前端 `RecapPage`、`EnginePostMarketView`、`EngineMissingState` | LIVE | 是 | **是** | 新 | COMPLIANT（本轮只核实了输入） |
| P-13 | **1进2**：`PostMarketSetupFactContextBuilder` → `OneToTwoRuleEngine` + `TechnicalGate` + `Scorer` → `OneToTwoSetupPlanEngine` | 复盘任务 `:927–950` | 复盘文档：要求 `market_regime_review`（`:42–45`）和**旧链的** `trading_principle`（`:43–47`）；主线上下文**只取已确认主线**（`:52`、`:318–345`） | `post_market_setup_plan` / `watchlists.one_to_two` | L7 / L8 | 前端 `OneToTwoWatchPanel` | LIVE | 是 | **是**（观察计划） | 新 | COMPLIANT（经 read_port） |
| P-14 | **弱转强 D1（A）**：`BuildWeakToStrongCandidateUseCase` | `application/use_cases/build_weak_to_strong_candidate.py`；`bootstrap.py:91`；API `api_app.py:911` | D1 输入行 | 候选（最多 10 只）及竞价预期 | L7 | API 选股器 | LIVE | 是（选股器） | **是** | 新 | UNKNOWN |
| P-15 | **弱转强 D1（B）**：`W2SCandidateService.build_candidates` | `domain/services/w2s_candidate_service.py`；`build_pre_market_brief_job.py:80` | K 线、池子行、前一状态 | 候选（最多 20 只） | L7 | 盘前简报快照 | LIVE | 是 | **是** | 新 | COMPLIANT |
| P-16 | **弱转强 D2**：`W2SConfirmService` + `W2SAuctionScorer` | `w2s_confirm_service.py`、`w2s_auction_scorer.py`；`build_pre_market_brief_job.py:42`；`api_app.py` | 竞价快照、P-15 的候选 | 确认结果与等级 | L9 | 盘前简报、API | LIVE | 是 | **是** | 新 | COMPLIANT |
| P-17 | `AuctionConfirmationService` | `domain/services/auction_confirmation_service.py` | — | 另一套竞价打分（A / B / C） | L9 | 只有 `backtest/historical_backtest_ports.py` | DIAGNOSTIC | 否 | 否 | 新 | COMPLIANT |
| P-18 | `KlineBreakDetector` | `domain/services/kline_break_detector.py`；`api_app.py:267`、`:6606–6616` | DSN 直连 | 破位预警 | L11（风控提示） | 实时预警 | LIVE（API 启动后循环运行） | 是 | 提示类 | 新 | **DIRECT_DB_VIOLATION（Domain 层）** |
| P-19 | 弱转强盘中预警系列：`w2s_intraday_alert_service`（v1 / v2）、`w2s_support_alert_service`、`w2s_alert_service`、`w2s_market_context_service`、`w2s_intraday_backtest`、`intraday_minute_state_builder` | `domain/services/*` | DSN 直连 | 预警 / 回测 | L9 / L11 | 脚本（`scripts/check_w2s_intraday_alert_*.py`）；Application 层零引用 | DIAGNOSTIC | 否 | 否 | 新 | **DIRECT_DB_VIOLATION（Domain 层，7 个文件）** |
| P-20 | `w2s_unified_alert_service` | `domain/services/w2s_unified_alert_service.py` | DSN 直连 | 统一预警 | L11 | Application 层有 1 处引用（未细查） | LIVE？（待确认） | ？ | 提示类 | 新 | **DIRECT_DB_VIOLATION（Domain 层）** |
| P-21 | `PostMarketDailyReviewV2Builder` | 复盘任务 `:1003–1015`；`post_market_daily_review_v2_builder.py` | 复盘文档（**新旧两条链的输出都读**） | `daily_review_v2` | 投影层 | 前端 `RecapPage`（`dataMode === "daily_review_v2_first"` 时，`:1031`） | LIVE | 是 | 否（展示），但会把旧链结论原样透传 | 新 | COMPLIANT |
| P-22 | `NewChainPostMarketReportBuilder`、叙事组合器、Notion 渲染器 | `new_chain_post_market_report_builder.py`、`post_market_narrative_composer.py`、`publishers/notion_post_market_report_renderer.py` | 复盘文档 | 报告文本 / Notion | 投影层 | Owner 阅读 | LIVE | 是 | 否 | 新 | UNKNOWN |
| P-23 | M8 / market_cognition（`cognition.py`、`replay.py`）、`analyst_alignment/turing_score.py` | `application/services/market_cognition/*` | — | 认知 / 回放 | L12 | `api_app.py` 中只有 1 处 M8 相关引用 | **本轮未核实** | ？ | 按架构文档应为否 | 新 | UNKNOWN |

---

## 2. 十条链

### 2.1 L1 大环境：三个生产者，只有一个有决策权威

```text
P-01 MarketMetricsService ──→ P-02 NarrativeEngine ──→ /api/v1/emotion ──→ 前端情绪页     【展示，无决策权威】
       （口径错误、估算）            （单变量 + 周期词）

P-03 FactContextBuilder ──→ P-04 MarketRegimeEngine ──→ market_regime_review ──→ PDV2 / 1进2  【决策权威】
  （默认快照、实时兜底）        （Broad / ShortTerm / Permission）

P-11 旧 MarketEnvironment ──→ market_environment_review ──→ 日复盘 V2 / 前端 / trading_principle  【旧链在线】

P-06 MarketEmotionEngine：死代码 · P-07 CycleFSM：只在脚本里
```

**要点**：
- **Owner 在前端情绪页看到的大盘阶段（P-02）**，和**系统实际用来决定能不能交易的大盘状态（P-04）**，是两套互不相干的计算。
- 前者有口径错误和作用域错误，但**不决定交易**；后者在缺数据时会用虚构快照，而且**决定交易**。

R1 的 DR-002 应拆成两个对象：
- P-02：展示语义纠偏，P1；
- P-03 / P-04：决策事实纠偏，P0。

### 2.2 L2 主线身份

```text
P-08 主线发现（机器只出候选） ──→ 复核队列 ──→ 【人工确认】 ──→ mainline_registry
                                                                 ├─→ P-09 周期（只读已确认）
                                                                 ├─→ P-10 → P-12 PDV2
                                                                 └─→ P-13 1进2（主线上下文只读已确认）
```

**要点**：
- “机器不确认、只有人工确认”这条设计与 OP-03 一致，应该保留。
- 问题出在下游：**所有消费者都只认 registry 里的已确认主线**，机器候选在发现链之后就断了，没有往下传。
- 发现链中 `MainlineLogicChainBuilder` 位于 Domain 层，却直接查数据库。

### 2.3 L3 主线周期

```text
题材证据（缺失时 fail-fast）──→ SubjectCycleJudgementService（对所有题材按分数阈值判定）──→ Layer B 表
                                                                 │
                     MainlineLifecycleFactContextBuilder ←───────┘  只取已确认主线
                                     │
                                     └─→ LayerBAdapter ──→ mainline_lifecycle_reviews ──→ P-04 / P-12 / P-13
```

**要点**：
- Layer B 对**所有题材**都给出了状态，所以候选主线**其实有状态**。只是这个状态在进入周期复核层时被过滤掉了。
- Layer B 的 `start` 是**残差默认值**，不是“初期”（L3-02）。

### 2.4 L4 交易许可

- **新**：P-04 中的 `TradingPermissionEngine`。决策权威，供 PDV2 和 1进2 使用。
- **旧**：P-11 中的 `TradingPrincipleEngine`。展示 + 1进2 的存在依赖。

两者都输出 `position_limit`，数值规则不同（L4-04 对比 L4-08）。

### 2.5 旧决策链 P-11

- 状态是 LEGACY_LIVE，**不是影子**：输出被并入复盘文档，日复盘 V2 原样透传，前端展示观察清单，1进2 依赖它存在。
- **切换前必须先解除的依赖**：`post_market_setup_fact_context_builder.py:43–47`。1进2 只检查 `trading_principle` 是否存在，不使用其内容；这个依赖可以单独拿掉，不影响 1进2 的语义。

### 2.6 PDV2 P-12

- 状态是 LIVE、有决策权威、前端展示。
- 它和 P-11 同时进入同一份复盘文档，前端 `RecapPage` 按 `dataMode` 选择展示哪一路。这就是 R1 DR-001 的双写。

### 2.7 1进2 P-13

```text
复盘文档 ─┬─ market_regime_review（P-04）──→ allow_trade ──→ 不允许交易时只观察（L4 阻断）
          ├─ trading_principle（P-11，旧）──→ 只检查存在
          └─ 已确认主线 ──→ 主线上下文 ──→ 非已确认主线时“不得 focus”（规则引擎阻断）
```

### 2.8 弱转强：D1 有两套生产者

| | P-14（API 选股） | P-15（盘前简报） |
|---|---|---|
| 弱的定义 | 涨幅 >−1% 排除（W-01） | 跌幅分档打分（W-12） |
| 强势背景 | 龙头 OR 昨日涨停 OR 近期涨停 ≥1 OR 排名 ≤5 | 龙头 OR 涨停 OR 近期涨停 ≥2 OR 排名 ≤3 |
| 主线和周期 | **没有门槛**，只作加分 | 只作打分；退潮观察 75 分 > 分歧 55 分 |
| 缺失处理 | — | 周线缺失 → 通过；前一状态未知 → 软通过 |
| 上限 | 10 只 | 20 只 |

D1 是 **MULTI_TRUTH_PRODUCER**：同一天、同一个“弱转强候选”的概念，两条路径给出的结果可能不同。
D2 只有一套在线生产者（P-16），P-17 只用于回测。

### 2.9 日复盘 / 复盘投影

P-21 和 P-22 是投影层，本身不做判断。但 P-21 把旧链（P-11）的结论原样透传给前端，所以旧链结论会以“日复盘 V2”的名义出现在 Owner 面前。

### 2.10 M8

本轮没有核实（P-23）。R1 认为 M8 是只读认知层、不拥有业务真相。这一点需要下一轮追调用链确认。

---

## 3. EARLY 发现窗口的阻断链

### 3.1 已批准的语义（v0.6.4）

```text
候选主线（L2） + 初期（L3） + 大盘允许（L1 / L4）
   → EARLY_PROBE（初期试错，OP-11）
   → 或 1进2 有资格（§5.5）
```

### 3.2 现在的代码

```text
候选主线（P-08 机器候选）
   │
   ▼  B0：下游只认人工确认主线 —— 阻断
   │     post_market_setup_fact_context_builder.py:52 · get_active_confirmed_mainlines
   │     post_market_setup_fact_context_builder.py:318–345 · source != "confirmed_mainline" 时跳过
   │     消费者：P-13 1进2
   │
   ▼  B1：周期复核只覆盖已确认主线 —— 阻断
   │     mainline_lifecycle_fact_context_builder.py:41–46 · MainlineLifecycleFactContextBuilder.build
   │     消费者：P-04（经 MainlineEnvironmentEngine）、P-12、P-13
   │     B1'（语义）：即使放开范围，Layer B 的 "start" 也只是残差默认值，不是“初期”
   │       subject_cycle_judgement_service.py:128–130 · else → "start(default)"
   │
   ▼  B2：没有已确认主线时，许可层整体关闭交易 —— 阻断
   │     mainline_environment_engine.py:30 · env 默认为 "no_confirmed_mainline"
   │     trading_permission_engine.py:31–34 · TradingPermissionEngine → allow_trade=False, position_limit=0.0
   │     消费者：P-12 PDV2（:68–70）；P-13 1进2（one_to_two_rule_engine.py:115–123 → 只观察）
   │
   ▼  B3：1进2 要求已确认主线才能 focus —— 阻断
         one_to_two_rule_engine.py:125–127 · OneToTwoRuleEngine → "pending_review_only"，“不得 focus”
         消费者：P-13 → 前端 OneToTwoWatchPanel
```

### 3.3 结论

```text
EARLY_DISCOVERY_BLOCKERS = [
  B0  application/services/post_market_setup_fact_context_builder.py:52, :318–345
        PostMarketSetupFactContextBuilder（主线上下文只取已确认）        → P-13 1进2
  B1  application/services/mainline_lifecycle/mainline_lifecycle_fact_context_builder.py:41–46
        MainlineLifecycleFactContextBuilder.build（只读已确认主线）      → P-04 / P-12 / P-13
  B1' domain/services/subject_cycle_judgement_service.py:128–130
        SubjectCycleJudgementService.judge_one（"start" 是残差默认值，不是 EARLY） → 全链
  B2  domain/services/market_regime/mainline_environment_engine.py:30
      domain/services/market_regime/trading_permission_engine.py:31–34
        MainlineEnvironmentEngine / TradingPermissionEngine（无已确认 → 仓位 0）
                                                                        → P-12 PDV2；P-13 1进2（:115–123）
  B3  domain/services/one_to_two_rule_engine.py:125–127
        OneToTwoRuleEngine（非已确认 → 不得 focus）                     → P-13 1进2
]
```

**对实施顺序的含义**：只修 B3，1进2 仍会被 B2 改成“只观察”；只修 B2，B0 和 B1 仍然拿不到候选主线和它的周期状态。

按依赖关系，顺序应该是：

```text
B0 / B1（让候选主线和它的周期状态能往下传）
  → B1'（让 EARLY 由正面证据判定，而不是残差）
  → B2（许可层区分“无主线”与“有候选主线、处于初期”）
  → B3（1进2 的 focus 条件）
```

**B1' 需要 Owner 先定一件事**：EARLY 的可观测进入条件是什么。v0.6.4 把它归在 OP-06，属于交给回放验证的项目。所以 B1' 在实施时只能先做到“EARLY 状态可以被表达，但阈值标为 POLICY_UNFROZEN”，不能直接写死数字。

---

## 4. boundary_status 汇总（Phase A 要锁的位置）

| 层 | 位置 | 在线情况 | 说明 |
|---|---|---|---|
| **Domain** | `mainline_discovery/mainline_logic_chain_builder.py:125–154` | **LIVE**（复盘任务） | 持有 pool，直接 `conn.fetch` |
| **Domain** | `kline_break_detector.py` | **LIVE**（API 启动循环） | 直连 DSN |
| **Domain** | `w2s_unified_alert_service.py` | 待确认 | 直连 |
| Domain | `w2s_intraday_alert_service.py`（v1 / v2）、`w2s_support_alert_service.py`、`w2s_alert_service.py`、`w2s_market_context_service.py`、`w2s_intraday_backtest.py`、`intraday_minute_state_builder.py` | DIAGNOSTIC | 直连 |
| **Application** | `market_regime/market_regime_fact_context_builder.py:65–66`、`:120–121` | **LIVE，决策权威** | 硬编码 DSN `asyncpg.connect` |
| Application | `market_metrics/service.py`（19 处） | LIVE，展示 | 自建连接 |
| Application | 其余约 31 个文件 | 未逐个分类 | 粗扫命中，含误报 |
| — | `market_cognition/emotion_engine.py` | DEAD_CODE | 直连；随死代码一起清理 |

**说明**：Domain 层命中 11 个文件。逐个核对后，`auction_confirmation_service.py` 是误报，`w2s_intraday_alert_service_v2.py` 只有 import、没有实际查询，其余 9 个有实际查询。Application 层 33 个文件只是粗扫，Phase A 需要逐个分类。

---

## 5. 对 R1 和上一份核验的更正

1. **更正我自己上一份核验（R1_INDEPENDENT_VERIFICATION §2.1）**：
   - 我写过“新链周期词汇里没有 EARLY”。**这句不准确。** Layer B 有 `start`，适配器还有 `seed` / `start`，许可层也把 `start` 当成可交易。
   - 准确的说法是：`start` 是**残差默认值**，所有没达到阈值的题材都落在这里，包括本来就很弱的题材。所以它**在语义上不等于 EARLY**。
   - 阻断的主因是 B0 / B1 的范围限制，再加上 B1' 的语义问题，而不是“词汇里没有”。
2. **R1 DR-002 应拆成两个对象**：NarrativeEngine（展示，P1）；MarketRegime 事实构建（决策，P0）。见 §2.1。
3. **R1 DR-001 的性质**：不是“影子链未切换”，而是**双写**。两条链都有下游消费者，旧链还是新链 1进2 的存在依赖。
4. **R1 没有提到的 P0**：
   - L1-01 默认快照、L1-03 实时兜底导致的未来函数（都在 P-03）；
   - L4-07 未知状态落入最积极档；
   - 弱转强 D1 的双生产者（P-14 / P-15）。

---

## 6. 状态

```text
本清单                    = 只读；没有改代码、测试、数据库、分支
LIVE 新链生产者            = P-01, P-02, P-03, P-04, P-08, P-09, P-10, P-12, P-13, P-14, P-15, P-16, P-18, P-21, P-22
LEGACY_LIVE               = P-05, P-11
DIAGNOSTIC                = P-07, P-17, P-19
DEAD_CODE                 = P-06
待确认                     = P-20, P-23
SHADOW                    = 无（新旧两条链是双写，不是影子）
EARLY 阻断点               = B0, B1, B1', B2, B3
下一步                     = 等 Owner 基于两份清单重排实施顺序；在那之前不改代码
```
