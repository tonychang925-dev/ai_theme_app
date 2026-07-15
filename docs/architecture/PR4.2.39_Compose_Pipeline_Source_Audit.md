# PR4.2.39 Compose Pipeline Source Audit — 正式报告数据源审计

> 审计日期：2026-07-15
> 目标：逐项列出 compose-from-workbench 所有 Section 及 M4g 题材强度面板的数据源，标记 Legacy 依赖，制定 SSOT 迁移路线。

---

## 一、当前双轨架构

```
┌──────────────────────────────────────────────────────────────┐
│                      Recap Page 复盘页面                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │  题材强度面板 (M4g Evidence Engine)               │       │
│  │  API: /api/v2/recap/{date}                       │       │
│  │  独立渲染，不依赖 payload / dailyReviewV2         │       │
│  │  丰富数据: theme_name, strength_score, leaders,   │       │
│  │            catalyst, evidence_sources             │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐       │
│  │  正式复盘 (compose-from-workbench)                │       │
│  │  API: POST /api/v2/daily-review-v2/compose-      │       │
│  │       from-workbench                             │       │
│  │  数据流:                                          │       │
│  │    WorkbenchReportComposer.compose()              │       │
│  │    ├── engine_report (← recap_doc)  ← 7/14为空!  │       │
│  │    └── snapshot fields (← approved snapshot)      │       │
│  │         ↓                                         │       │
│  │    PostMarketDailyReviewV2Builder.build()         │       │
│  │    ├── recap_doc → builder reviews → 7/14空!     │       │
│  │    └── 输出 theme_reviews, capital_reviews, etc.  │       │
│  │         ↓                                         │       │
│  │    FormalReviewProjectionCompiler.compile()       │       │
│  │    ├── snapshot_* 字段 ✓ (有数据)                 │       │
│  │    ├── builder_* 字段 ✗ (recap为空→全空)         │       │
│  │    └── engine_report ✗ (recap为空→空)            │       │
│  └──────────────────────────────────────────────────┘       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**核心矛盾**：M4g 和正式报告使用了**完全不同的数据管线**。

- M4g：`/api/v2/recap/` → 独立的 M4g Evidence Engine，直接从 DB/Producer 读取
- 正式报告：`compose-from-workbench` → recap_doc → engine_report → builder reviews → projection

---

## 二、正式报告全部 Section 数据源矩阵

### compose-from-workbench 入口

```
API: POST /api/v2/daily-review-v2/compose-from-workbench (api_app.py:10250)

Step 1: WorkbenchReportComposer.compose(td, recap_doc)  → report_composer.py:53
  ├── engine_report = PostMarketEngineReportComposer.compose(recap_doc)  ← recap_doc
  └── snapshot fields: emotion_review, chart_reviews, cognition_cards,
       narrative, playbook, override_summary                           ← snapshot

Step 2: PostMarketDailyReviewV2Builder.build(td, recap_doc)            ← recap_doc
  └── 产出: theme_reviews, theme_capital_reviews, strong_stock_reviews,
           watchlist_reviews, stock_capital_reviews, money_flow_reviews,
           dragon_tiger_reviews, abnormal_reviews, etc.

Step 3: FormalReviewProjectionCompiler.compile(...)  → compiler.py:92
  └── 6 章 + 图表附录
```

### 正式报告 6+1 章 — 数据源逐项矩阵

| # | Chapter | Projection Module | 当前数据源 | 数据源类型 | 7/14状态 |
|---|---------|------------------|-----------|-----------|----------|
| **1** | **Executive Summary** | `projections/executive_summary.py` | | | |
| | market_conclusion | | snapshot_emotion.summary → engine_report.engine_summary | Snapshot + Legacy | ✓ |
| | main_story | | snapshot_narrative.main_story → emotion_desc → engine headline | Snapshot + Legacy | ✓ |
| | primary_theme | | snapshot_cognition_cards (CRITICAL优先) → engine mainline_states | Snapshot + Legacy | ✓ |
| | trade_mode | | engine_summary.action_bias → "" | **Legacy** | -- |
| | risk_level | | snapshot_emotion.risk_level → "UNKNOWN" | Snapshot | ✓ |
| | top_risks | | engine_report.market_overview_narrative.risks | **Legacy** | -- |
| **2** | **Market State** | `projections/market_state.py` | | | |
| | facts (up/down/limit_up/limit_down) | | snapshot_chart_reviews[market_breadth].key_metrics | Snapshot | ✓ |
| | facts (active_amount_yi, total_amount_yi) | | snapshot_chart_reviews[active_capital].key_metrics | Snapshot | ✓ |
| | facts (max_board_height, promotion) | | snapshot_chart_reviews[relay_ecology].key_metrics | Snapshot | ✓ |
| | emotion (node, score, risk, confidence) | | snapshot_emotion | Snapshot | ✓ |
| | emotion.dimensions (5 sub-scores) | | snapshot_emotion.dimensions | Snapshot | ✓ |
| | regime (market_regime, trade_mode, etc.) | | snapshot_emotion | Snapshot | ✓ |
| | market_health_score | | 硬编码 None | **无源** | -- |
| | new_high_brief | | 全部硬编码 None/"" | **无源** | -- |
| | index_technical | | 空 list | **无源** | -- |
| | relay_summary | | chart_reviews[relay_ecology] | Snapshot | ✓ |
| **3** | **Theme Structure** | `projections/theme_structure.py` | | | |
| | role (MAINLINE/SECONDARY/WATCH) | | builder_theme_reviews → engine mainline → cognition | **Legacy** + Snapshot | ✓ (role) / ✗ (capital) |
| | stage (lifecycle) | | engine mainline.lifecycle_state → cognition stage_judgement → builder | **Legacy** + Snapshot | ✓ |
| | state_evolution | | engine mainline_daily_states → builder theme_reviews | **Legacy** | 稀疏 |
| | capital (total_inflow, leader_inflow, etc.) | | builder_theme_capital_reviews | **Legacy** | ✗ 空 |
| | drivers (catalyst events) | | engine_report.theme_driver_events | **Legacy** | ✗ 空 |
| | analyst_view (overrides) | | snapshot_cognition_cards | Snapshot | ✓ |
| **4** | **Stock Structure** | `projections/stock_structure.py` | | | |
| | stocks (code, name, role, scores) | | builder_strong_stock_reviews (主) → engine strong_stock_pool (回退) | **Legacy** | ✗ 空 |
| | groups (leaders/mid_cap/frontline) | | 同上 | **Legacy** | ✗ 空 |
| | capital (main_net_inflow, money_flow_tier) | | builder_stock_capital_reviews | **Legacy** | ✗ 空 |
| | today_status, rationale | | builder strong_stock_reviews | **Legacy** | ✗ 空 |
| **5** | **Capital Evidence** | `projections/capital_evidence.py` | | | |
| | market (active_amount, state, hot_money_net_buy, institution_net_buy, evidence_count) | | builder rows + engine_report evidence_layer/seat_money/active_capital | **Legacy** | ✗ 全空/0 |
| | themes (total_inflow, leader_inflow, rank_order, capital_validation) | | builder_theme_capital_reviews | **Legacy** | ✗ 空 |
| | stocks (capital fact/assessment, dragon_tiger, abnormal_signals) | | builder_stock_capital + money_flow + dragon_tiger + abnormal | **Legacy** | ✗ 空 |
| | institution_direction, hot_money_direction | | engine seat_money_summary → institution_buy_rows/hot_money_buy_rows | **Legacy** | ✗ 空 |
| | limitup_classification | | engine limit_up_ladder → limit_up_theme_matrix | **Legacy** | ✗ 空 |
| | orphan_seats, seat_summary, evidence_layer, alignment, event_narrative | | engine_report | **Legacy** | ✗ 空 |
| **6** | **Next Day Plan** | `projections/next_day_plan.py` | | | |
| | scenario | | snapshot_playbook → snapshot_emotion.tomorrow_outlook → trading_principle | Snapshot + Legacy | ✓ |
| | watch_themes, watch_stocks | | builder_watchlist_reviews + builder_post_market_setup_plan + engine post_market_decision | **Legacy** | ✗ 空 |
| | confirmation_signals | | snapshot_playbook → snapshot_emotion.tomorrow_watchpoints | Snapshot | ✓ |
| | invalidation_signals | | snapshot_playbook → collected from watch_stocks | Snapshot + Legacy | ✓ (partial) |
| | forbidden_actions | | snapshot_playbook → snapshot_emotion.tomorrow_forbidden → trading_principle | Snapshot + Legacy | ✓ |
| | principles (position_limit, main_strategy) | | builder_trading_principle → engine trading_principle | **Legacy** | ✗ 空 |
| **7** | **Evidence Charts** | `projections/evidence_charts.py` | | | |
| | market_breadth, emotion_momentum, active_capital, relay_ecology, institution_style, hot_money_style | | snapshot_emotion + snapshot_chart_reviews + engine_report | Snapshot + Legacy | ✓ (snapshot) / ✗ (engine) |

---

## 三、数据源类型统计

| 数据源类型 | Section 数量 | 说明 |
|-----------|-------------|------|
| **Snapshot** (✓ 可用) | ~25 | emotion_review, chart_reviews, cognition_cards, narrative, playbook |
| **Legacy Recap** (✗ 7/14为空) | ~18 | engine_report, builder_*_reviews (全部6类) |
| **硬编码/无源** (永远空) | ~3 | market_health_score, new_high_brief, index_technical |

**关键结论**：
- **Snapshot 字段占比 ~55%**，这些在 7/14 有数据
- **Legacy 字段占比 ~40%**，这些在 7/14 全部为空（recap_doc 缺失）
- **无源字段占比 ~5%**，硬编码 None/""，从未有数据

---

## 四、四层架构问题归纳

### 第一层：M4g 和正式报告用两套数据源

| 面板 | API | 数据源 | 主题数据 |
|------|-----|--------|---------|
| 题材强度 (M4g) | `/api/v2/recap/` | M4g Evidence Engine (独立) | PCB/HBM、芯片、机器人、创新药... |
| 主线题材 (正式报告) | `compose-from-workbench` | builder_theme_reviews ← recap_doc ← 空 | 锂电池、有色金属、化工...（不同！） |

**根因**：M4g 自己从 DB/Producer 实时计算，正式报告从 recap_doc 派生。两套数据完全独立，主题列表不重叠。

### 第二层：正式报告没读取 Producer 输出

Dashboard (EmotionDashboard) 已正确显示：
- Institution Style: ✓（AI算力 +169亿、先进半导体 +51亿）
- HotMoney Style: ✓
- Direction Flow: ✓

但 compose-from-workbench 的 `capital_evidence` projection 读的是：
- `builder_theme_capital_reviews` ← `PostMarketDailyReviewV2Builder.build(recap_doc)` ← 空
- `engine_report.seat_money_summary` ← `PostMarketEngineReportComposer.compose(recap_doc)` ← 空

**根因**：compose pipeline 从未调用 `_inject_capital_producer_outputs_async`（这个函数在 workbench API 中已实现，直接从 DB 读取 stock_fund_flow 和 direction 数据）。

### 第三层：正式报告大量依赖 Legacy Recap

| 字段 | 显示值 | 来源 |
|------|--------|------|
| 成交额 | -- | recap_doc.total_amount → 空 |
| 市场健康度 | -- | 硬编码 None |
| 仓位约束 | -- | engine trading_principle → 空 |
| 观察题材 | -- | builder_watchlist_reviews → 空 |
| 资金状态 | -- | builder capital rows → 空 |
| 活跃资金 | -- | engine active_capital → 空 |
| 游资净买 | 0 | engine seat_money → 空 |
| 机构净买 | 0 | engine seat_money → 空 |
| 证据数量 | 0 | engine evidence_layer → 空 |

这些全部是 `recap_doc → engine_report → builder → projection` 链路断裂的结果。

### 第四层：Snapshot 未成为 Single Source of Truth

Workbench 已完成的方向/资金/计划数据（在 Approved Snapshot 中）大部分**没有被 compose pipeline 读取**：

| Workbench Producer | Snapshot 中有？ | compose 读取？ |
|-------------------|----------------|---------------|
| InstitutionStyle | ✓ (chart_reviews) | ✗ (capital 读 builder_theme_capital_reviews) |
| HotMoneyStyle | ✓ (chart_reviews) | ✗ (同上) |
| DirectionFlow | ✓ (injected via _inject_capital) | ✗ (从不调用) |
| SeatMoney | ✓ (draft_context.seat_money_summary) | ✗ (读 engine seat_money) |
| PlanSnapshot | ✓ (draft_context.plan_state) | ✗ (读 builder + engine) |
| TomorrowPlaybook | ✓ (snapshot.playbook) | ✓ (next_day_plan 读取了) |

---

## 五、SSOT 迁移路线图

### Phase 1: 接入 Producer（消除第二层问题）

将 `_inject_capital_producer_outputs_async` 逻辑接入 `compose-from-workbench`，使 `capital_evidence` projection 直接从 DB 读取：

```
capital_evidence:
  当前: builder_theme_capital_reviews ← recap_doc ← 空
  目标: _inject_capital_producer_outputs_async() ← stock_fund_flow_daily + direction tables (DB)
```

### Phase 2: 消除 engine_report 依赖（消除第三层问题）

`market_state` projection 中所有 `engine_report` 回退路径替换为 Snapshot + DB：

```
market_state.facts:
  当前: chart_reviews (Snapshot ✓) + engine active_capital (Legacy ✗)
  目标: chart_reviews (Snapshot) + MarketMetricsService DB (回退)
```

### Phase 3: 统一主题数据源（消除第一层问题）

将 M4g Evidence Engine 的输出接入 `theme_structure` projection：

```
theme_structure:
  当前: builder_theme_reviews ← recap_doc ← 空 → 锂电池/有色/化工
  目标: /api/v2/recap/ + snapshot_cognition_cards → PCB/HBM/芯片/机器人
```

### Phase 4: Snapshot 成为唯一真源（消除第四层问题）

compose 不再传入 any `builder_*` review rows，全部改成：

```
compose-from-workbench:
  ├── snapshot (唯一入口)
  │     ├── emotion_review
  │     ├── chart_reviews
  │     ├── cognition_cards
  │     ├── narrative
  │     ├── playbook
  │     └── override_summary
  ├── Producer adapter (DB直读)
  │     ├── stock_fund_flow_daily
  │     ├── institution_style_daily
  │     ├── hot_money_style_daily
  │     ├── direction_relation
  │     └── seat_money_snapshot
  └── MarketMetrics DB (回退)
        └── stock_daily_snapshot
```

---

---

## 七、深层诊断：两套投影系统

### 7.1 当前不是"一条链"，而是"两条链"

审计的第三、第四节揭示了同一个问题的不同表现。将所有表象归纳到一起：

```
                    Snapshot (Approved)
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
   Analyst Dashboard              Formal Report
   (EmotionDashboard)             (compose-from-workbench)
         │                               │
         │ 读取：                         │ 读取：
         │ ├── Snapshot ✓                │ ├── Snapshot ✓ (55%)
         │ ├── Producer ✓ (直接调用)      │ ├── recap_doc ✗ (40%)
         │ └── trend_data ✓              │ ├── Builder ✗
         │                               │ ├── Engine ✗
         │                               │ └── Producer ✗ (未调用)
         │                               │
         ▼                               ▼
    数据完整、一致                    数据残缺、不一致
```

**核心结论**：这不是"Legacy 太多"的问题。这是**系统存在两套独立投影系统**的问题。

Dashboard 和 Formal Report 已经不是同一个 Projection。它们读取不同的数据源、调用不同的 Producer、经过不同的管线，最终产出不同的视图。这才是"Dashboard 看到的世界 ≠ Report 看到的世界"的根源。

### 7.2 compose-from-workbench 职责过重

当前 compose 的职责：

```
compose-from-workbench
  ├── 读取 recap_doc (legacy)
  ├── 调用 PostMarketEngineReportComposer (legacy engine)
  ├── 调用 PostMarketDailyReviewV2Builder (legacy builder)
  ├── 调用 FormalReviewProjectionCompiler
  │     ├── 融合 snapshot + engine + builder + ...
  │     ├── 逐字段 fallback chain
  │     └── 输出 6 章
  ├── 补字段
  └── 最终 HTML 渲染
```

**它应该是**：

```
compose = read(snapshot) → render
```

不再负责：数据融合、字段补全、fallback chain、Builder、Engine、Producer 调用。

### 7.3 Approved Snapshot → Canonical Snapshot

当前 Snapshot 的内容（`snapshot.py:ReviewSnapshot`）：

```
attention_state, cognition_cards, narrative, playbook,
override_summary, emotion_review, chart_reviews
```

这些都是"分析师审核"层面的数据。但正式的**市场事实**数据（资金流向、机构方向、游资方向、龙虎榜、强势股、计划、图表等）并不在 Snapshot 中——它们散落在 Producer、Builder、Engine、recap_doc 各处。

**升级为 Canonical Snapshot**：所有 Producer 的输出在 APPROVE 时一次性写入 Snapshot：

```
Canonical Snapshot
  ├── market (up/down, limit_up/down, turnover, breadth, health)
  ├── emotion (phase, score, risk, dimensions, key_evidence)
  ├── theme_structure (themes with role/stage/capital/drivers/analyst_view)
  ├── stock_structure (strong_stocks with scores/capital/status)
  ├── capital_evidence (market_capital, theme_capital, stock_capital, seats, limitup)
  ├── institution_style (direction + themes)
  ├── hot_money_style (direction + themes)
  ├── direction_view (unified direction flow ranking)
  ├── next_day_plan (scenario, watch_themes, signals, forbidden)
  ├── charts (all 6 chart types + trend data)
  ├── seat_money (institution + hot money buy rows)
  └── review (analyst overrides, calibration, approval metadata)
```

**所有计算发生在 Snapshot 之前。Snapshot 之后只允许 READ。**

---

## 八、Architecture Invariants（架构不变量）

以下规则适用于本项目所有展示端（Dashboard、Formal Report、PDF、API、Mobile）：

### I1 — Canonical Snapshot 是唯一真源 (SSOT)

所有展示端只能读取 Canonical Snapshot。禁止从 Recap、Builder、Engine 或任何其他中间层读取数据。

### I2 — Producer 只负责生成，不允许在展示端再次调用

```
✓ Producer → Snapshot.write()
✗ compose → Producer.read()
✗ Dashboard → Producer.read()
✗ Report → Producer.read()
```

Producer 的输出在 APPROVE 时一次性写入 Snapshot。后续所有展示端只读取 Snapshot 中已持久化的数据。

### I3 — 同一份 Snapshot，同一个世界

Dashboard、Formal Report、PDF、API 必须使用同一份 Snapshot。不允许出现两个 Projection 使用不同数据源导致主题列表、资金数据、强势股不一致。

### I4 — Legacy 组件仅作为迁移期兼容层

Legacy Recap、Builder、Engine 只允许在迁移过渡期存在。不允许成为正式报告的数据来源。迁移完成后移除。

### I5 — 可选模块缺失只降级，不阻断

任何可选模块（如 one_to_two、龙虎榜、北向资金等）缺失时：
- ✓ 降级为空数据或占位符
- ✗ 不允许抛 HTTP 4xx/5xx 阻断整个报告生成

### I6 — Snapshot Completeness Contract

Canonical Snapshot 必须能够**独立生成正式报告**。不允许依赖以下任何外部数据源：

```
禁止依赖：
  ✗ Builder (PostMarketDailyReviewV2Builder)
  ✗ Recap (post_market_recap_snapshot)
  ✗ Engine (PostMarketEngineReportComposer)
  ✗ Producer 实时调用 (InstitutionStyle, HotMoney, Direction, etc.)
  ✗ Live DB Query (除 Snapshot 加载本身)

必须独立：
  ✓ Canonical Snapshot → Formal Report (100%)
```

### I7 — Snapshot 只保存审核事实（Approved Facts），不保存 Projection

Snapshot 的内容边界：

```
✓ 允许写入 Snapshot：
  - 审核后的业务事实 (emotion 节点、风险等级、主线判断)
  - Producer 产出的结构化结果 (institution_style 方向列表、hot_money_style 方向列表)
  - 分析师修正后的值 (overrides)
  - 计划与策略 (playbook, next_day_plan)

✗ 禁止写入 Snapshot：
  - Projection / View (Direction View, Capital Ranking, Hierarchy Tree)
  - UI State (折叠/展开、选中项、排序)
  - Temporary Ranking (运行时排序结果)
  - Interactive State (图表缩放、Tab 状态)
  - Raw DB rows (不要整表复制)
```

Direction View 是 Projection，不是事实。Snapshot 保存它的构成部件（institution_style, hot_money_style, observation_direction, capital），Direction View 在运行时渲染。Hierarchy 算法一变，所有 Snapshot 不应废掉。

---

## 八-B、Snapshot 内容边界：Approved Facts ≠ Raw Producer Output

### 8B.1 Snapshot 保存 Projection，不保存 Raw Output

```
✗ 错误做法：
  Snapshot.institution_style = copy(institution_style_daily 全部字段)

✓ 正确做法：
  Snapshot.capital.institution_style = [
    { direction, score, confidence, state, top_stocks, signals }
  ]
```

Report 不需要 Producer 的全部字段。只保存 Report 实际需要的字段子集。Snapshot 的职责是"冻结审核时刻的事实"，不是"数据库镜像"。

### 8B.2 修订后的 Canonical Snapshot 结构

```
Canonical Snapshot (版本号, 审核时间戳, 审核人)
  │
  ├── market (up/down, limit_up/down, turnover — 冻结的市场快照)
  ├── emotion (phase, score, risk, dimensions, key_evidence)
  │
  ├── capital
  │     ├── institution_style  (direction + score + top_stocks — 精简投影)
  │     ├── hot_money_style     (direction + score + top_stocks — 精简投影)
  │     ├── observation_direction (analyst_watch — 审核后冻结)
  │     ├── active_amount        (活跃资金快照值)
  │     └── seat_money           (席位资金摘要)
  │
  ├── themes[] (subject_key, role, stage, analyst_overrides)
  ├── stocks[] (stock_code, role, theme — 审核后的股票池)
  ├── plan (scenario, watch_themes, signals, forbidden)
  ├── charts (6 chart snapshots at approval time)
  └── review (calibration, overrides, approval metadata)

✗ 不保存：
  - Direction View (运行时从 capital.* 渲染)
  - Trend Series (Dashboard 实时查询 Trend API)
  - M4g evidence engine 全量输出 (只保存精简后的 theme_structure)
  - Raw Builder rows / Engine output
```

---

## 八-C、Dashboard 分两类：静态审核数据 vs 动态可视化

Dashboard 不能全部改读 Snapshot。拆分为：

### 第一类：审核数据 → 必须从 Snapshot

这些是分析师**审核并冻结**的事实，Dashboard 和 Report 必须一致：

| 数据 | 来源 |
|------|------|
| 机构方向 (institution_style) | Snapshot.capital.institution_style |
| 游资方向 (hot_money_style) | Snapshot.capital.hot_money_style |
| 观察方向 (observation_direction) | Snapshot.capital.observation_direction |
| 情绪判断 (emotion phase/score) | Snapshot.emotion |
| 明日计划 (playbook) | Snapshot.plan |
| 分析结论 (overrides) | Snapshot.review |

### 第二类：动态图 → 实时查询

这些是**可视化**，不是审核内容。Dashboard 运行时查询：

| 数据 | 来源 | 原因 |
|------|------|------|
| 走势折线图 (近30日趋势) | Trend API (`/api/v1/analyst-charts/{date}/trends`) | 跨日动态查询，不应每次存入 Snapshot |
| 大盘势能趋势 | Trend API | 同上 |
| 资金热力图 | 实时 DB 查询 | 交互式可视化 |
| Chart 渲染数据 | 已有 chart_reviews (Snapshot 保存审核时的快照值) | — |

**原则**：Snapshot 保存"审核时刻的点值"（今天的 composite_score = 6），不保存"连续序列"（近 30 天每天的 composite_score）。

---

## 八-D、Snapshot 版本化

### 8D.1 问题

分析师第一次审核 v1 → 修改 → v2 → 再次审核 → v3 → Approved。如果只保留最终版本，无法追溯演变过程。

### 8D.2 方案

```
tmp/analyst_workbench/{trade_date}/
  ├── snapshot_v1.json   ← 初次审核
  ├── snapshot_v2.json   ← 修改后再次审核
  ├── snapshot_v3.json   ← Approved (最终)
  └── snapshot.json      ← 最新版本 (符号链接或复制)
```

### 8D.3 长期价值

M7 学习路径可追溯：

```
AI draft v1
  ↓ 分析师覆盖 (overrides_v1)
Snapshot v1
  ↓ 分析师再审核 (overrides_v2)
Snapshot v2
  ↓ Approved
Snapshot v3 (Final)
```

每个版本的 diff 构成分析师的决策轨迹——这比只看最终版本更有价值。

---

## 八-E、方向 View 不应写入 Snapshot

Direction View 已是 Projection：

```
Direction View =
  System Direction (来自 institution_style + hot_money_style)
  + Observation Direction (analyst watch)
  + Hierarchy (parent/child)
  + Overlap (同一股票多个方向)
  + Ranking (流动排名)
```

它是从底层事实**计算**出来的视图，不是事实本身。

```
✓ Snapshot 保存：
  - institution_style (机构方向列表 + scores)
  - hot_money_style (游资方向列表)
  - observation_direction (分析师观察方向)
  - capital (资金事实)

✗ Snapshot 不保存：
  - Direction View (运行时从上述部件渲染)

如果 Hierarchy 算法 v2 升级：
  - Snapshot 不受影响 (事实未变)
  - Direction View 重新渲染 (使用新算法)
```

---

## 九（修订）、终局架构

```
                        Collectors
                           │
                        Producers
                           │
                           ▼
              ┌────────────────────────┐
              │  Canonical Snapshot     │
              │  (Approved Facts Only)  │
              │  v1 → v2 → v3 → Final  │
              │  ~50-100KB per version  │
              └────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
    Dashboard          Formal Report      Trend API
  ┌──────────────┐   (纯 Snapshot)   (近30日走势)
  │ Static (审核) │        │               │
  │ → Snapshot   │        ▼               ▼
  │ Dynamic (图表)│  Frontend Render  实时 DB Query
  │ → Trend API  │
  └──────────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           ▼
                     Frontend Render

运行时 Projection (不写入 Snapshot):
  - Direction View (← capital.* 组合渲染)
  - Theme Hierarchy (← themes[] 运行时构建)
  - Capital Ranking (← capital + stocks 排序)
```

```
                        Collectors
                           │
                        Producers
                           │
                           ▼
                   Canonical Snapshot
                    (唯一真源 SSOT)
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
       ▼                   ▼                   ▼
  Dashboard          Formal Report           API
  (只读Snapshot)     (只读Snapshot)     (只读Snapshot)
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                     Frontend Render
```

**关键原则**：所有计算发生在 Snapshot 之前。任何 compose/report/dashboard/pdf/export 全部禁止重新计算。

---

## 十、M4g 重新定位

| | 当前 | 目标 |
|---|------|------|
| M4g 输出 | Dashboard 直接渲染 | 写入 `Snapshot.theme_structure` |
| Dashboard 读取 | M4g API 实时调用 | `Snapshot.theme_structure`（同一份） |
| Formal Report 读取 | Legacy builder_theme_reviews ← recap_doc | `Snapshot.theme_structure`（同一份） |
| 一致性 | ✗ 两套完全不同的主题列表 | ✓ 完全一致 |

M4g 不再直接渲染到 Dashboard。它变成一个 Producer，输出写入 Canonical Snapshot。Dashboard 和 Formal Report 读取同一份 `Snapshot.theme_structure`。

---

## 十一（修订）、P0 行动项

| 编号 | 行动 | 说明 |
|------|------|------|
| **P0-A** | Producer 输出在 Approve 时写入 Snapshot | InstitutionStyle, HotMoneyStyle, SeatMoney, PlanSnapshot 的输出精简为 Projection（不是 Raw rows）后写入 Snapshot |
| **P0-B** | Compose 只允许 `read(snapshot)` | 禁止 `Builder()`、`Engine()`、`Producer()`、`recap_doc`。Compose 降级为纯渲染层 |
| **P0-C** | Snapshot 升级为 Canonical Snapshot | 包含 market/emotion/capital/themes/stocks/plan/charts/review（Approved Facts only，不含 Projection） |
| **P0-D** | 拆分 Dashboard 数据源 | 静态审核数据 → Snapshot；动态图表 → Trend API |
| **P0-E** | Snapshot 版本化 | snapshot_v1 → v2 → ... → Final。保留审核演变轨迹 |
| **P0-F** | Direction View 从 Snapshot 移除 | 作为运行时 Projection，从 Snapshot.capital.* 组合渲染 |

---

## 十二（修订）、迁移阶段总览

```
Phase 0 (P0-A/B/C/D/E/F): 建立 Canonical Snapshot + 数据边界
  ├── approve 时将 Producer 输出精简为 Projection 写入 Snapshot (P0-A)
  ├── Compose 降级为 read(snapshot) → render (P0-B)
  ├── Snapshot 结构升级 (P0-C)
  │     ├── market, emotion, capital (institution/hotmoney/observation/seatmoney)
  │     ├── themes, stocks, plan, charts, review
  │     └── 不含 Direction View, Trend Series, Raw DB rows
  ├── Dashboard 拆分：静态 → Snapshot, 动态 → Trend API (P0-D)
  ├── Snapshot 版本化：v1 → v2 → ... → Final (P0-E)
  ├── Direction View 作为运行时 Projection (P0-F)
  └── 移除 compose 中的 Builder/Engine/recap_doc 依赖

Phase 1: 统一数据源
  ├── Dashboard 静态数据改为读取 Snapshot（不再实时调用 Producer）
  ├── M4g 输出精简后写进 Snapshot.themes
  └── 移除所有 builder_reviews、engine_report 回退路径

Phase 2: 清理 Legacy
  ├── 移除 PostMarketEngineReportComposer 调用
  ├── 移除 PostMarketDailyReviewV2Builder 调用
  └── recap_doc 从 compose 管线移除

Phase 3: SSOT 达成
  ├── 所有展示端 100% 从 Canonical Snapshot 渲染
  ├── Projection (Direction View, Ranking, Hierarchy) 运行时生成
  └── Invariants I1-I9 全部生效

Phase 4 (终局): Snapshot 退化为 Freeze Pointer
  ├── Snapshot 只保存 Approved Reference，数据在 Immutable Projection 中
  ├── Snapshot ≈ 几十 KB（纯引用）
  ├── 同一 Projection 版本被多个 Snapshot 共享
  └── compose() 被删除，只保留 render(snapshot)
```

---

## 十三、终局架构：Snapshot 退化为 Freeze Pointer

### 13.1 当前文档的问题

当前 Canonical Snapshot 仍然把数据**嵌入**自己内部：

```
Snapshot {
  capital: {
    institution_style: [ {...}, {...}, ... ],   ← 数据在 Snapshot 中
    hot_money_style: [ {...}, {...}, ... ],
  }
}
```

这会导致：
- 几十万个 Snapshot，每个都复制同样的 institution_style 数据
- 算法升级 → 无法区分"同一个 Projection v12"和"重新计算的 v13"
- Snapshot 越来越胖，最终变成数据库镜像

### 13.2 终局方案：Snapshot = Freeze Pointer

```
Snapshot (Approved References)
  │
  ├── trade_date: 2026-07-14
  ├── approved_by: analyst
  ├── approved_at: 2026-07-15T04:39Z
  │
  ├── refs:
  │     ├── market:       "market_projection/v12"
  │     ├── emotion:      "emotion_projection/v8"
  │     ├── capital:      "capital_projection/v15"
  │     │     ├── institution_style:  → capital_projection/v15
  │     │     ├── hot_money_style:    → capital_projection/v15
  │     │     ├── observation_dir:    → capital_projection/v15
  │     │     └── seat_money:         → capital_projection/v15
  │     ├── themes:       "theme_projection/v22"
  │     ├── stocks:       "stock_projection/v9"
  │     ├── plan:         "plan_projection/v7"
  │     └── charts:       "chart_projection/v11"
  │
  └── overrides: { ... }   ← 唯一嵌入的数据：分析师修正
```

Snapshot ≈ **2-5 KB**（纯引用 + 审批元数据 + overrides）。

真正的数据在 **Immutable Projection** 中：

```
Immutable Projections (版本化, 不可变, 共享)

  market_projection/
    ├── v12 → { up_count, down_count, limit_up, limit_down, turnover, ... }
    └── v11 → { ... }

  capital_projection/
    ├── v15 → { institution_style: [...], hot_money_style: [...], ... }
    └── v14 → { ... }

  theme_projection/
    ├── v22 → { themes: [...], hierarchy: ... }
    └── v21 → { ... }
```

**同一 Projection 版本被多个 Snapshot 共享**。如果 7/14 和 7/15 的 institution_style 都来自同一版本算法且数据未变，两个 Snapshot 引用同一个 `capital_projection/v15`。

### 13.3 为什么这是正确的设计

| 问题 | 嵌入数据（当前） | Freeze Pointer（终局） |
|------|----------------|----------------------|
| 存储 | 每个 Snapshot 几百 KB | Snapshot 几 KB，Projection 共享 |
| 算法升级 | 所有历史 Snapshot 数据"冻结"在旧算法 | 生成新 Projection 版本，Snapshot 引用不变 |
| 审计追溯 | 只知道最终结果 | 知道引用哪个 Projection 版本 → 可完全复现 |
| 一致性 | 不同 Snapshot 间的数据可能不一致 | 共享同一 Projection 版本的 Snapshot 完全一致 |

### 13.4 I8 和 I9

**I8 — Projection Immutable**：一旦生成，禁止修改。算法升级不修改已有 Projection，而是生成新版本。

**I9 — Snapshot 和 Producer 互相不知道对方**：

```
✗ 当前耦合:
  Producer → Snapshot.write()

✓ 解耦后:
  Producer → ProjectionBuilder → Immutable Projection
  Snapshot ← ProjectionWriter ← Immutable Projection

  Producer 不知道 Snapshot 的存在
  Snapshot 不知道 Producer 的存在
  中间通过 ProjectionWriter 连接
```

### 13.5 Report Composer 最终命运

```
Phase 0:  compose(td, recap_doc, snapshot)  ← 当前
Phase 1:  compose(td, snapshot)              ← 降级
Phase 2:  render(snapshot_refs)              ← 纯渲染
Phase 3:  compose() 被删除                    ← 终局

终局只有:
  render(snapshot) → Jinja/React/Markdown/PDF Template
```

### 13.6 终局架构全图

```
                      Collectors
                         │
                      Producers
                         │
                Projection Builders
                         │
                         ▼
              Immutable Projections
            (market, capital, emotion,
             theme, stock, plan, chart)
             v1, v2, v3, ... vN
                         │
                ┌────────┴────────┐
                │                 │
                ▼                 ▼
        ProjectionWriter    Trend API
                │           (近30日走势)
                ▼
    Canonical Snapshot
   (Approved References)
       ≈ 2-5 KB
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           ▼           ▼
Dashboard  Formal Report  PDF/Mobile
    │           │           │
    └───────────┼───────────┘
                ▼
         render(snapshot)
         (Template Engine)
```

**四层解耦**：

| 层 | 职责 | 可变性 |
|----|------|--------|
| Producer | 从原始数据计算业务指标 | 可重写 |
| Projection | 不可变的事实快照，版本化 | **不可变** |
| Snapshot | 审核后的引用集合 | 版本链 (v1→v2→...→Final) |
| Render | 纯模板渲染 | 可替换 |

---

## 十四、增补 Invariants

### I1~I7（已确认）

### I8 — Projection Immutable

Projection 一旦生成即不可变。算法升级不修改已有 Projection，而是创建新版本。

```
✗ 算法升级 → UPDATE projection SET score = ... WHERE version = v12
✓ 算法升级 → INSERT projection_v13 (重新计算，v12 保持不变)
```

### I9 — Snapshot 不感知 Producer

Snapshot 和 Producer 互相不知道对方的存在。中间通过 ProjectionWriter 解耦。

```
Producer → Projection (不知道 Snapshot)
Snapshot ← ProjectionWriter ← Projection (不知道 Producer)
```

Producer 可以完全重写，Snapshot 不受影响。Snapshot 格式可以演进，Producer 不受影响。

---

## 十五、修订后完整 Invariants 清单

| # | 不变量 |
|---|--------|
| I1 | Canonical Snapshot 是唯一真源 (SSOT) |
| I2 | Producer 只负责生成，不在展示端调用 |
| I3 | 同一份 Snapshot，同一个世界 |
| I4 | Legacy 组件仅作为迁移期兼容层 |
| I5 | 可选模块缺失只降级，不阻断 |
| I6 | Snapshot Completeness Contract — 独立生成报告 |
| I7 | Snapshot 只保存 Approved Facts，不保存 Projection |
| **I8** | **Projection Immutable — 写入后不可变** |
| **I9** | **Snapshot 和 Producer 互相不感知（依赖倒置）** |
