# DailyReview Field Consolidation Matrix

> 版本：v2.2
> 日期：2026-07-11
> 审核：已通过 | v2.3 — PR1a + PR2.1 + PR2.2 + PR2.3 实施状态已记录，Recap 正式入口修复已纳入边界约束
> 样本数据：2026-07-09 compose-from-workbench 响应 (63 top-level keys, 4771 flattened keys)
> 目的：逐字段审计当前 DailyReviewV2 响应，识别重复、归属业务章节，制定保留/合并/废弃策略
>
> 相关文档：
> - `docs/architecture/Phase_4.5.4_设计文档.md`
> - `docs/architecture/分析师工作台设计方案.md`
> - `docs/architecture/AI_Theme_App_Overall_Architecture_v4.0.md`

---

## 0. 合并优先级规则（字段级 Merge Policy）

**禁止按对象整体覆盖。每个字段必须按分类独立合并。**

### 字段分类与优先级

```
FACT（原始市场事实）:
  原始事实 > Engine 结构化事实 > 其他来源
  禁止人工覆盖
  示例：涨停数、成交额、上涨家数

ASSESSMENT（对当前状态的判断）:
  分析师 final_value > Approved AI 结论 > Engine Assessment > legacy
  示例：主线判断、市场阶段、情绪节点

PLAN（明日策略与计划）:
  分析师 final_value > Approved playbook > Engine plan > legacy
  示例：明日观察点、失效条件、策略倾向

AUDIT（审计信息）:
  只追加，不覆盖
  示例：override log、snapshot hash、source trace
```

### 逐字段实施规则

1. 涨停数、成交额、上涨家数：永远不能因为 Workbench 有值就覆盖 Engine
2. PCB 是否成为主线：允许分析师覆盖 Engine 判断
3. FACT 字段在 Projection Builder 中只做映射，不做 fallback 猜测
4. 每个 FACT 必须有唯一 owner Producer

### 关键事实 Owner 注册

| 事实字段 | 唯一 Owner Producer |
|---|---|
| up_count / down_count | MarketBreadth Producer |
| limit_up_total / limit_down_total | Limit Pool Producer |
| total_amount | Market Metrics Producer |
| relay metrics (promotion_rate, max_board_height) | Relay Ecology Producer |
| active_capital / ratio | Active Capital Producer |

---

## 1. 最终目标：5 顶层对象收敛

```
{
  "metadata": {
    "schema_version": "daily_review_v3",
    "projection_version": "formal_review_v1",
    "trade_date": "2026-07-09",
    "snapshot_version": "...",
    "generated_at": "...",
    "approval": {},
    "source": {},
    "theme_name_map": {}
  },
  "formal_review": {
    "version": "1.0",
    "executive_summary": {},
    "market_state": {},
    "theme_structure": { "summary": {}, "themes": [] },
    "stock_structure": { "stocks": [], "groups": {} },
    "capital_evidence": { "market": {}, "themes": [], "stocks": [] },
    "next_day_plan": {}
  },
  "evidence_appendix": {},
  "diagnostics": {},
  "compatibility": {}
}
```

`metadata.schema_version` 与 `formal_review.version` 独立演进，允许 `daily_review_v3` + `formal_review_v2` 组合。

`compatibility` 有明确生命周期：
- Phase 4.5.6: `compatibility` enabled（双轨运行）
- 5–10 交易日: monitor（观察旧字段消费者）
- Phase 4.5.7: remove compatibility（清理完毕）

---

## 2. Metadata（元数据）

| # | 当前字段 | 分类 | 来源 | 消费者 | 决策 |
|---|---|---|---|---|---|
| 1 | `schema_version` | AUDIT | Builder | 前端 bootstrap | KEEP → `metadata.schema_version` |
| 2 | `trade_date` | AUDIT | Builder | 所有组件 | KEEP → `metadata.trade_date` |
| 3 | `report_type` | AUDIT | Builder | 前端 bootstrap | KEEP → `metadata.report_type` |
| 4 | `snapshot_version` | AUDIT | Builder | 前端 debug | KEEP → `metadata.snapshot_version` |
| 5 | `generated_at` | AUDIT | Builder | 前端 debug | KEEP → `metadata.generated_at` |
| 6 | `data_mode` | AUDIT | Builder | 前端 bootstrap | KEEP → `metadata.data_mode` |
| 7 | `source` | AUDIT | Builder | 前端 debug | KEEP → `metadata.source` |
| 8 | `workbench_approval` | AUDIT | Composer | RecapPage buttons, ApprovalBadge | KEEP → `metadata.approval` |
| 9 | `theme_name_map` | AUDIT | Builder | 所有主题名称解析 | KEEP → `metadata.theme_name_map` |

---

## 3. 六大业务章节

### 3.1 Chapter 1: Executive Summary（今日核心结论）

**合并目标**：`formal_review.executive_summary`

**关键修正**：
- narrative_review.main_story 不入 emotion_review.summary（两者语义不同：前者是"为什么"，后者是"是什么"）
- risk_flags 与 risk_level 分开保留（一个是列表，一个是级别）

| # | 当前字段 | 分类 | 来源 | 消费者 | 是否重复 | 决策 |
|---|---|---|---|---|---|---|
| 10 | `engine_summary` | ASSESSMENT | Engine Composer | MarketOverviewNarrativePanel | 否（唯一 engine 总结源） | **MERGE** → `executive_summary.engine_conclusion` |
| 11 | `market_summary.conclusion` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 与 #10 高度重叠 | **FOLD** — 取 engine_summary 优先；若 workbench 有 analyst override 则覆盖 |
| 12 | `market_summary.action_bias` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 与 emotion_review.strategy_bias 重叠 | **FOLD** → 取 emotion_review.strategy_bias |
| 13 | `market_summary.highlights` | ASSESSMENT | Builder (recap_doc) | RecapPage legacy fallback | 与 engine_summary 核心点重复 | **FOLD** → 合并入 executive_summary.key_points |
| 14 | `narrative_review.main_story` | ASSESSMENT | Workbench Snapshot | 无组件渲染 | 语义不同：市场叙事（"为什么"），非情绪总结 | **KEEP** → `executive_summary.main_story` |
| 15 | `market_summary.risk_flags` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 是风险列表，与 emotion_review.risk_level（风险级别）不同维度 | **KEEP** → `executive_summary.top_risks` |
| 16 | `emotion_review.risk_level` | ASSESSMENT | Workbench Snapshot | EmotionReviewCard | 与 #15 维度不同（级别 vs 列表） | **KEEP** → `executive_summary.risk_level` |
| 17 | `daily_recap_essentials` | ASSESSMENT | Engine Composer (Narrative) | DailyRecapStoryPanel | 结构化故事摘要 | **MERGE** → `executive_summary.story` |

**建议 executive_summary 结构**：
```json
{
  "market_conclusion": "市场处于分歧后的弱修复",
  "main_story": "机器人高位分歧，资金从高位科技切换至PCB容量方向",
  "primary_theme": "PCB",
  "secondary_themes": ["人形机器人"],
  "trade_mode": "控制仓位，关注低位承接",
  "risk_level": "HIGH",
  "top_risks": ["高位股补跌", "量能不足", "主线扩散失败"],
  "engine_conclusion": "...",
  "story": {}
}
```

### 3.2 Chapter 2: Market State（市场环境与情绪）

**合并目标**：`formal_review.market_state`

**关键修正**：
- market_health_score 和 emotion_score 并列，不混成综合分
- 每个 FACT 字段有唯一 Owner Producer
- relay_summary（涨停梯队摘要）留在正式报告，完整 ladder 进 appendix
- new_high 摘要留在正式报告，详情进 appendix

| # | 当前字段 | 分类 | 来源 | 消费者 | 是否重复 | 决策 |
|---|---|---|---|---|---|---|
| 18 | `market_regime_review` | ASSESSMENT | Engine Composer | MarketRegimePanel | 否 | **MERGE** → `market_state.regime` |
| 19 | `market_environment_review` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 与 #18 重叠 | **FOLD** — 取 market_regime_review，合并 evidence 子字段 |
| 20 | `market_overview_review` | FACT | Builder (recap_doc) | MarketOverviewPanel | up/down/limit counts 进入 market_state.facts；theme_limitup_matrix 进 appendix | **SPLIT** |
| 21 | `emotion_review` (核心) | ASSESSMENT | Workbench Snapshot | EmotionReviewCard | 唯一 AI + 分析师情绪源 | **KEEP** → `market_state.emotion` |
| 22 | `market_summary.breadth_status` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 与 emotion_review.breadth_label 重复 | **FOLD** — 取 emotion_review.breadth_label |
| 23 | `market_summary.short_term_sentiment_status` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 与 emotion_review 重复 | **FOLD** |
| 24 | `market_summary.relay_sentiment_status` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 与 emotion_review.relay_label 重复 | **FOLD** |
| 25 | `market_summary.intraday_fade_status` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 无对应 workbench 字段 | **FOLD** → `market_state.fade_status` |
| 26 | `market_summary.market_health_score` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 与 emotion_score 不同维度（市场健康 vs 情绪强度） | **KEEP** → `market_state.market_health_score`（不混成综合分） |
| 27 | `market_overview_narrative` | ASSESSMENT | Engine Composer (Narrative) | MarketOverviewNarrativePanel | 与 engine_summary 和 emotion_review 部分重叠 | **FOLD** — 核心点合并入 market_state.summary |
| 28 | `index_technical_reviews` | FACT | Engine Composer | MarketRegimePanel, RecapDataQualityBar | 否 | **KEEP** → `market_state.index_technical` |
| 29 | `market_chart_reviews` (6 chart reviews) | FACT + ASSESSMENT | Workbench Snapshot | ChartReviewCard grid | 五维评分与 emotion_review 五维重复 | **FOLD** — 摘要入 market_state.chart_summary；完整 6 张入 evidence_appendix.chart_details |
| 30 | `limit_up_ladder` (摘要部分) | FACT | Builder | DailyRecapStoryPanel | relay 摘要（最高板、晋级率、梯队形状）直接影响情绪判断 | **SPLIT** — 摘要入 `market_state.relay_summary`；完整 ladder 入 evidence_appendix |
| 31 | `new_high_summary` (摘要部分) | FACT | Builder | DailyRecapStoryPanel | 新高数量与方向 | **SPLIT** — 摘要入 `market_state.new_high_brief`；完整入 evidence_appendix |

**建议 market_state 结构**：
```json
{
  "regime": {},
  "emotion": {},
  "facts": {
    "up_count": 2357,
    "down_count": 2642,
    "limit_up_total": 149,
    "limit_down_total": 25,
    "total_amount": 2892582174.84
  },
  "market_health_score": 56.88,
  "emotion_score": -8,
  "fade_status": "分歧观察",
  "relay_summary": {
    "max_board_height": 4,
    "ladder_shape": "完整",
    "promotion_rate": 0.18
  },
  "new_high_brief": {
    "count": 33,
    "direction": "EDA/ICT/IT基础设施"
  },
  "index_technical": [],
  "chart_summary": {},
  "summary": "..."
}
```

### 3.3 Chapter 3: Theme Structure（主线与题材演化）

**合并目标**：`formal_review.theme_structure`

**关键修正**：
1. 主题主键集合 = 所有来源 subject_key 的并集（不单以 theme_reviews 为基础行）
2. mainline_daily_states → theme_structure[].state_evolution（不笼统折叠）
3. mainline_narrative 不入带下划线的 _narrative，改为独立 summary 区
4. 结构 = { summary: {}, themes: [] } 而非纯数组

| # | 当前字段 | 分类 | 来源 | 消费者 | 是否重复 | 决策 |
|---|---|---|---|---|---|---|
| 32 | `theme_reviews` | ASSESSMENT | Builder (recap_doc) | RecapPage theme summary | 多个底层表聚合 | **MERGE** — 作为 theme_structure.themes[] 的输入之一 |
| 33 | `theme_decision_reviews` | ASSESSMENT | Builder (recap_doc) | 无直接渲染 | 与 #32 重叠 | **FOLD** — #32 已包含其大部分字段 |
| 34 | `theme_capital_reviews` | FACT | Builder (recap_doc) | RecapPage theme capital flow | 与 #32 共享 subject_key | **FOLD** — 核心字段合并入 theme_structure.themes[] |
| 35 | `theme_driver_events` | FACT | Builder + EventDriverTracer | 无直接渲染 | 当前已是 capital + events 合并 | **MERGE** — driver_events 合并入 theme_structure.themes[].events |
| 36 | `mainline_reviews` | ASSESSMENT | Builder (recap_doc) | 无直接渲染 | 与 theme_reviews 同域 | **FOLD** |
| 37 | `mainline_daily_states` | ASSESSMENT | Engine Composer | MainlineStateBoard, RecapPage fallback | 包含 state_evolution（持续天数、fade risk、状态迁移、昨日/今日变化），未必都在 theme_reviews 中 | **MERGE** → `theme_structure.themes[].state_evolution` |
| 38 | `mainline_lifecycle_reviews` | ASSESSMENT | Builder (recap_doc) | 无直接渲染 | 与 theme_reviews.cycle_stage 重叠 | **FOLD** — 合并入 theme_structure.themes[].lifecycle |
| 39 | `mainline_narrative` | ASSESSMENT | Engine Composer (Narrative) | MainlineNarrativePanel | 叙事文本，与结构数据互补 | **MERGE** → `theme_structure.summary.mainline_narrative` |
| 40 | `cognition_reviews` (cognition_cards) | ASSESSMENT | Workbench Snapshot | 无组件渲染 | 每题材一行，与 theme_reviews 同域；独特价值：12 个双轨 override 字段 | **MERGE** — 每个 theme 增加 `analyst_overrides` 子对象（仅 override=true 时非空） |
| 41 | `analyst_review_items` | ASSESSMENT | Builder (recap_doc) | 无直接渲染 | 与 mainline_reviews 重叠 | **FOLD** |
| 42 | `pending_mainline_reviews` | ASSESSMENT | Builder (recap_doc) | 无直接渲染 | 实为 #41 的别名 | **REMOVE** — PR1 前提：全仓库 grep 无外部引用 |
| 43 | `confirmed_mainlines` | list | Builder (hardcoded `[]`) | 无消费者 | 永远空数组 | **REMOVE** — PR1 前提：全仓库 grep 无外部引用 |
| 44 | `mainline_discovery_diagnostics` | AUDIT | Builder (recap_doc) | 无组件渲染 | diagnostics | **FOLD** → `diagnostics` |
| 45 | `analyst_review_diagnostics` | AUDIT | Builder (recap_doc) | 无组件渲染 | diagnostics | **FOLD** → `diagnostics` |
| 46 | `mainline_lifecycle_diagnostics` | AUDIT | Builder (recap_doc) | 无组件渲染 | diagnostics | **FOLD** → `diagnostics` |

**Theme 合并规则（防丢行）**：
```
subject_keys = union(
    theme_reviews[].subject_key,
    cognition_reviews[].subject_id,
    theme_driver_events[].subject_key,
    mainline_daily_states[].canonical_subject_key,
    theme_capital_reviews[].subject_key,
)
```
按 subject_key merge，不单以 theme_reviews 为基础行。

**建议 theme_structure 结构**：
```json
{
  "summary": {
    "mainline_narrative": "...",
    "rotation_summary": "..."
  },
  "themes": [
    {
      "subject_key": "9018144",
      "theme_name": "PCB印制电路板",
      "role": "MAINLINE",
      "stage": "FERMENTATION",
      "strength_score": 82,
      "capital_state": "INFLOW",
      "leader_stocks": [],
      "events": [],
      "state_evolution": {},
      "lifecycle": {},
      "yesterday_view": "...",
      "today_actual": "...",
      "expectation_delta": "...",
      "tomorrow_view": "...",
      "analyst_overrides": {
        "stage_judgement": {
          "ai_value": "人形机器人延续主线",
          "analyst_value": "PCB成为资金承接方向",
          "final_value": "PCB成为资金承接方向",
          "reason": "机器人高位分歧，资金切换PCB"
        }
      },
      "evidence_refs": []
    }
  ]
}
```

### 3.4 Chapter 4: Stock Structure（龙头与强势股 — 仅今日）

**合并目标**：`formal_review.stock_structure`

**关键修正**：
- Chapter 4 只描述今天：谁是龙头、中军、被淘汰
- 明日 watchlist/1进2 统一归入 Chapter 6（next_day_plan）
- 避免同一只股票重复三次：核心实体唯一化，groups 用 stock_code 引用

| # | 当前字段 | 分类 | 来源 | 消费者 | 是否重复 | 决策 |
|---|---|---|---|---|---|---|
| 47 | `strong_stock_reviews` | ASSESSMENT | Builder (recap_doc) | LayerCStrongPoolPanel | 唯一结构化强股源 | **MERGE** → `stock_structure.stocks[]` |
| 48 | `strong_stock_decision_reviews` | ASSESSMENT | Builder (recap_doc) | 无直接渲染 | 与 #47 重叠 | **FOLD** — #47 已包含 + 增强字段 |
| 49 | `post_market_decision_v2` | ASSESSMENT | Builder + Engine overlay | LayerCStrongPoolPanel | strong_stock_pool_reviews 与 #47 重叠 | **FOLD** — 作为 #47 的 fallback |

**建议 stock_structure 结构**（唯一实体 + 分组引用）：
```json
{
  "stocks": [
    {
      "stock_code": "002384.SZ",
      "stock_name": "东山精密",
      "theme_name": "PCB印制电路板",
      "today_role": "LEADER",
      "today_status": "换手首板",
      "key_scores": {
        "composite": 70,
        "capital": 75,
        "structure": 81
      },
      "analyst_notes": ""
    }
  ],
  "groups": {
    "leaders": ["002384.SZ"],
    "mid_cap": [],
    "frontline": [],
    "eliminated": []
  }
}
```

### 3.5 Chapter 5: Capital Evidence（资金与关键证据）

**合并目标**：`formal_review.capital_evidence`

**关键修正**：
- 股票级所有资金证据按 stock_code 合并（不分别保留 stock_flows / seat_evidence / abnormal 独立列表）
- 只有无法映射到股票的席位数据才进入 `capital_evidence.orphan_seats`

| # | 当前字段 | 分类 | 来源 | 消费者 | 是否重复 | 决策 |
|---|---|---|---|---|---|---|
| 50 | `stock_capital_reviews` | FACT | Builder (recap_doc) | RecapPage stock capital flow | 否 | **MERGE** → `capital_evidence.stocks[]`（按 stock_code） |
| 51 | `money_flow_reviews` | FACT | Builder (recap_doc) | RecapPage money flow | 与 #50 存在维度重叠 | **FOLD** — 作为 stock 资金增强字段，不独立列表 |
| 52 | `dragon_tiger_reviews` | FACT | Builder (recap_doc) | **无组件渲染** | 结构性龙虎榜数据 | **FOLD** → `capital_evidence.stocks[].dragon_tiger`（按 stock_code 合并） |
| 53 | `abnormal_reviews` | FACT | Builder (recap_doc) | RecapPage abnormal signals | 否 | **FOLD** → `capital_evidence.stocks[].abnormal_signals`（按 stock_code 合并） |
| 54 | `seat_money_summary` | FACT | Builder (recap_doc) | DailyRecapStoryPanel | 席位摘要（非个股） | **KEEP** → `capital_evidence.seat_summary` |
| 55 | `evidence_layer_review` | FACT | Engine Composer | EvidenceLayerPanel | 证据层编排 | **MERGE** → `capital_evidence.evidence_layer` |
| 56 | `evidence_alignment_index` | FACT | Engine Composer | 无组件渲染 | 证据对齐索引 | **FOLD** → `capital_evidence.alignment` |
| 57 | `market_hotspot_overview` | FACT | Engine Composer | 无组件渲染 | 热点概览，与 limit_up_theme_matrix + theme_reviews 重叠 | **FOLD** |
| 58 | `market_hotspot_narrative` | ASSESSMENT | Engine Composer (Narrative) | 无组件渲染 | 热点叙事，与 mainline_narrative 重叠 | **FOLD** → theme_structure.summary |
| 59 | `driver_event_narrative` | ASSESSMENT | Engine Composer (Narrative) | 无组件渲染 | 单字符串摘要 | **FOLD** → `capital_evidence.event_narrative` |

**建议 capital_evidence 结构**（股票级统一合并）：
```json
{
  "market": {
    "active_amount": 0,
    "active_ratio": 0,
    "state": "回流"
  },
  "themes": [],
  "stocks": [
    {
      "stock_code": "002384.SZ",
      "main_net_inflow": 0,
      "active_buy": 0,
      "institution_net": 0,
      "hot_money_net": 0,
      "dragon_tiger": {},
      "abnormal_signals": []
    }
  ],
  "seat_summary": {},
  "orphan_seats": [],
  "evidence_layer": {},
  "event_narrative": "..."
}
```

### 3.6 Chapter 6: Next Day Plan（明日计划）

**合并目标**：`formal_review.next_day_plan`

**关键修正**：
- 明日所有内容统一归入此章（watchlist、1进2、playbook）
- Stock Structure (Ch4) 只保留今日角色
- emotion_review.tomorrow_* → 情绪约束
- playbook → 综合交易计划

| # | 当前字段 | 分类 | 来源 | 消费者 | 是否重复 | 决策 |
|---|---|---|---|---|---|---|
| 60 | `watchlist_reviews` | PLAN | Builder (recap_doc) | RecapPage watchlist | 明日观察池 | **MERGE** → `next_day_plan.watch_universe` |
| 61 | `post_market_setup_plan` | PLAN | Builder (recap_doc) | OneToTwoWatchPanel | 1进2专项 | **MERGE** → `next_day_plan.watch_universe.one_to_two` |
| 62 | `watchlists` | PLAN | Builder → _build_one_to_two_watchlists 覆盖 | OneToTwoWatchPanel | 与 #61 重叠 | **FOLD** — post_market_setup_plan 已是更完整版本 |
| 63 | `playbook_review` | PLAN | Workbench Snapshot | 无组件渲染 | 战略层交易剧本 | **MERGE** → `next_day_plan.playbook` |
| 64 | `emotion_review.tomorrow_outlook` | PLAN | Workbench Snapshot | EmotionReviewCard | 情绪约束 | **KEEP** → `next_day_plan.market_scenario` |
| 65 | `emotion_review.tomorrow_watchpoints` | PLAN | Workbench Snapshot | EmotionReviewCard | 确认信号 | **KEEP** → `next_day_plan.confirmation_signals` |
| 66 | `emotion_review.tomorrow_forbidden` | PLAN | Workbench Snapshot | EmotionReviewCard | 禁止行为 | **KEEP** → `next_day_plan.forbidden_actions` |
| 67 | `decision_diagnostics` | AUDIT | Builder (recap_doc) | 无组件渲染 | diagnostics | **FOLD** → `diagnostics` |
| 68 | `trading_principle` | ASSESSMENT | Builder (recap_doc) | 无组件渲染 | 交易原则 | **FOLD** → `next_day_plan.principles` |

**建议 next_day_plan 结构**：
```json
{
  "market_scenario": "...",
  "playbook": {},
  "primary_actions": [],
  "confirmation_signals": [],
  "invalidation_signals": [],
  "forbidden_actions": [],
  "principles": {},
  "watch_universe": {
    "stocks": [],
    "one_to_two": []
  }
}
```

---

## 4. Evidence Appendix（证据附录）

| # | 当前字段 | 决策 |
|---|---|---|
| 69 | `limit_up_ladder` (完整) | **KEEP** → `evidence_appendix.limit_up_ladder` |
| 70 | `limit_up_theme_matrix` | **KEEP** → `evidence_appendix.limit_up_theme_matrix` |
| 71 | `limit_up_theme_events` | **KEEP** → `evidence_appendix.limit_up_theme_events` |
| 72 | `new_high_summary` (完整) | **KEEP** → `evidence_appendix.new_high_summary` |
| 73 | `market_chart_reviews` (完整 6 张) | **FOLD** → `evidence_appendix.chart_details` |
| 74 | `d1_narrative` | **FOLD** → `evidence_appendix.d1_narrative`（当前无组件渲染） |
| 75 | 无法映射到 stock_code 的席位数据 | **KEEP** → `capital_evidence.orphan_seats` |

---

## 5. Diagnostics

| # | 当前字段 | 决策 |
|---|---|---|
| 76 | `diagnostics` | **KEEP** → `diagnostics` |
| 77 | `mainline_discovery_diagnostics` | **FOLD** → `diagnostics.mainline_discovery` |
| 78 | `analyst_review_diagnostics` | **FOLD** → `diagnostics.analyst_review` |
| 79 | `mainline_lifecycle_diagnostics` | **FOLD** → `diagnostics.mainline_lifecycle` |
| 80 | `decision_diagnostics` | **FOLD** → `diagnostics.decision` |
| 81 | `analyst_override_review` (override_summary) | **FOLD** → `diagnostics.audit`（非主章节；有 override 时在对应字段旁 inline 显示，完整列表放 audit） |

---

## 6. Compatibility（兼容层）

所有旧字段在兼容期统一放入，不散落顶级：

```
compatibility: {
  "legacy_daily_review_v2": { ... }
}
```

---

## 7. 移除清单（分两批）

### PR1a — 可直接删除（前提：全仓库 grep 无引用）

| # | 字段 | 原因 |
|---|---|---|
| 82 | `workbench_data` | 7 个 workbench section 的重复 blob，不同 key 名，前端零引用 |
| 83 | `confirmed_mainlines` | 永远返回 `[]`，全仓无消费者 |
| 84 | `pending_mainline_reviews` | 与 analyst_review_items 同源重复别名 |

### PR1b — 先迁移再删除

| # | 字段 | 迁移目标 | 迁移后删除 |
|---|---|---|---|
| 85 | `attention_review` | charts_available → diagnostics；watch_groups → workbench session only | 是 |
| 86 | `narrative_review` (独立顶级) | main_story → executive_summary；其余字段已被 emotion_review 覆盖 | 是 |
| 87 | `playbook_review` (独立顶级) | → next_day_plan.playbook | 是 |
| 88 | `market_environment_review` (独立顶级) | 内容分散到 market_state | 是 |
| 89 | `market_overview_review` (独立顶级) | 内容分散到 market_state + evidence_appendix | 是 |
| 90 | `theme_decision_reviews` (独立顶级) | 合并入 theme_structure | 是 |
| 91 | `strong_stock_decision_reviews` (独立顶级) | 合并入 stock_structure | 是 |
| 92 | `market_hotspot_overview` | 合并入 theme_structure + limit_up 证据 | 是 |
| 93 | `market_hotspot_narrative` | 合并入 theme_structure.summary | 是 |
| 94 | `analyst_review_items` | 合并入 theme_structure | 是 |
| 95 | `mainline_reviews` | 合并入 theme_structure | 是 |
| 96 | `watchlists` | 合并入 next_day_plan.watch_universe | 是 |

---

## 8. 合并前后对比

| 指标 | 当前 | 目标 |
|---|---|---|
| 顶级字段数 | **63** (compose-from-workbench) | **5** (metadata + formal_review + evidence_appendix + diagnostics + compatibility) |
| formal_review 内部章节 | N/A | **6** |
| 市场状态相关字段 | 13 (scattered) | 1 (`market_state` dict) |
| 题材相关字段 | 16 (scattered) | 1 (`theme_structure` {summary, themes}) |
| 强势股相关字段 | 6 (scattered) | 1 (`stock_structure` {stocks, groups}) |
| 明日相关字段 | 6 (scattered across Ch4/Ch6) | 1 (`next_day_plan` dict) |
| 全空无用字段 | 3 | 0 |
| 重复 blob | 1 (`workbench_data`) | 0 |
| 命名不一致 | 5 处 workbench→composer key 映射 | 0（统一为 workbench 源命名） |

---

## 9. 实施顺序

### 命名约定

- Projection 层命名为 **`FormalReviewProjectionCompiler`**（非 Builder）
  - 理由：它 merge → resolve conflict → normalize → project → schema transform，不是简单 build
  - 输入：多个认知源（Engine Report + Approved Snapshot + recap_doc）
  - 输出：一个正式认知模型（`formal_review`）
  - 边界：不查询数据库、不重新计算指标、不调模型、不修改事实

### PR 顺序

```
PR1a: Output Cleanup（✅ 已完成 2026-07-11）
  - 删除 workbench_data blob
  - 删除 confirmed_mainlines（全仓 grep 确认无引用）
  - 删除 pending_mainline_reviews（全仓 grep 确认无引用）
  - 只影响 response，不删除内部函数

PR1b: 迁移后删除（后续）
  - attention_review: charts_available → diagnostics, watch_groups → workspace-only
  - 其余标记为 PR1b 的字段完成迁移映射

PR2: FormalReviewProjectionCompiler 新增
  - metadata（含 schema_version + projection_version）
  - formal_review {6 chapters, version: "1.0"}
  - evidence_appendix
  - diagnostics
  - compatibility
  - 旧字段继续保留（双轨运行期）

PR3: Golden Projection Test + Projection Diff（基于 2026-07-09）
  
  3a. Golden Test — 业务一致性验证：
  - 输入：AI=机器人，分析师=PCB
  - 输出：formal_review.theme_structure.final_theme == "PCB"
  - FACT 数值一致（limit_up_total, total_amount, up_count）
  - snapshot hash 一致
  - 题材数、股票数不丢失（subject_keys 并集无缺行）
  - 无重复 subject_key / stock_code

  3b. Projection Diff — 新旧对比测试：
  新增 test_daily_review_projection_diff.py
  - 输入：旧 DailyReviewV2 vs 新 formal_review
  - FACT 必须一致（数值对比）
  - ASSESSMENT 允许变化但必须符合 analyst final_value priority
  - PLAN 允许变化但必须 playbook > engine
  - 防止 Projection Compiler 把信息压缩丢失

PR4: FormalReviewView 前端双轨
  - 新增六大章节前端组件
  - 通过开关与 legacy view 对照
  - 不立即删除 EnginePostMarketView / MarketRecapPanel / WorkbenchSectionsPanel

PR5: 真实交易日观察（不少于 5 天）
  - 覆盖：主线明确日 / 多题材轮动日 / 退潮日 / 数据降级日 / 无 Approved Snapshot 场景

PR6: 移除旧字段和旧组件
  - 不在 Compiler 第一版就删除全部旧字段
  - 5+ 交易日验证通过后执行
  - compatibility 层一并移除
```

---

## 10. 最终架构约束

1. FACT 字段禁止人工覆盖（涨停数、成交额等原始事实）
2. ASSESSMENT 和 PLAN 允许分析师 override
3. 每个 FACT 字段有唯一 Owner Producer，ProjectionCompiler 只做映射（不查 DB、不重算、不调模型）
4. 主题主键集合 = 所有来源 subject_key 的并集（防丢行）
5. Stock Structure 只描述今天；Next Day Plan 统一管理明天
6. 同一 stock_code 在 capital_evidence.stocks 中只保留一条记录
7. relay_summary 和 new_high_brief 摘要留在正式报告 market_state
8. 最终 API 响应为 5 个顶级对象
9. `metadata.schema_version` 与 `formal_review.version` 独立演进
10. `compatibility` 生命周期：Phase 4.5.6 enable → 5–10交易日 monitor → Phase 4.5.7 remove
11. ProjectionCompiler 不是新的 Engine：不查 DB、不重算指标、不调模型、不修改事实

## 11. PR1a 实施记录（2026-07-11）

| 变更 | 文件 | 结果 |
|---|---|---|
| 删除 `workbench_data` blob | `report_composer.py` (approved + non-approved 分支) | ✅ |
| 删除 `workbench_data` fallback 注入 | `api_app.py` (_enrich_v2_with_workbench_sections) | ✅ |
| 删除 `confirmed_mainlines` | `post_market_daily_review_v2_builder.py` | ✅ |
| 删除 `pending_mainline_reviews` | `post_market_daily_review_v2_builder.py` | ✅ |
| 移除 workbench_data 断言 | `test_workbench_phase454.py` | ✅ |
| 移除 confirmed/pending 断言 | `test_mainline_registry.py` | ✅ |
| **验证** | **50 backend tests + 3 frontend contracts** | **全部通过** |

## 12. PR2.1 实施记录（2026-07-11）

**目标**：新增 `FormalReviewProjectionCompiler` 核心骨架，并先实现 `metadata + executive_summary + market_state`。

### 新增结构

| 文件 | 职责 | 状态 |
|---|---|---|
| `stock_processing_service/application/services/daily_review/formal_review_projection_compiler.py` | 主编译器；输出 5 顶层对象；保持 Compiler Boundary | ✅ |
| `daily_review/policies/merge_policy.py` | 字段级 Merge Policy：FACT / ASSESSMENT / PLAN / AUDIT | ✅ |
| `daily_review/projections/metadata.py` | `schema_version=daily_review_v3` + `projection_version=formal_review_v1` | ✅ |
| `daily_review/projections/executive_summary.py` | 保留 `main_story != emotion.summary`、`risk_level != top_risks` | ✅ |
| `daily_review/projections/market_state.py` | `market_health_score` 与 `emotion_score` 并列；relay/new_high 摘要入正式报告 | ✅ |
| `daily_review/projections/theme_structure.py` | Stub，PR2.2 实现 | ✅ |
| `daily_review/projections/stock_structure.py` | Stub，PR2.2 实现 | ✅ |
| `daily_review/projections/capital_evidence.py` | Stub，PR2.3 实现 | ✅ |
| `daily_review/projections/next_day_plan.py` | Stub，PR2.3 实现 | ✅ |

### 集成方式

`POST /api/v2/daily-review-v2/compose-from-workbench` 在 legacy 响应之上追加：

```json
{
  "metadata": {},
  "formal_review": {
    "version": "1.0",
    "executive_summary": {},
    "market_state": {}
  },
  "evidence_appendix": {},
  "diagnostics": {},
  "compatibility": {}
}
```

当前仍为 **dual-track**：旧字段保留，`formal_review` 作为新投影并行输出。

### Compiler Boundary

允许：

- 字段 merge
- schema mapping
- conflict resolution
- rename / grouping / dedup

禁止：

- 查询数据库
- 调 LLM
- 重新计算指标
- 修改 snapshot / draft / recap_doc 输入

### PR2.1 验证

| 验证项 | 结果 |
|---|---|
| 50 backend tests | ✅ 通过 |
| 3 frontend contracts | ✅ 通过 |
| Compiler smoke test | ✅ 输出结构符合 Matrix v2.1 |

## 13. PR2.2 实施记录（2026-07-11）

**目标**：实现 `formal_review.theme_structure` 与 `formal_review.stock_structure`。

### PR2.2a Theme Structure

已实现 Subject Union，避免以单一 `theme_reviews` 作为基表导致丢行：

```python
subject_keys = union(
    theme_reviews,
    theme_capital_reviews,
    mainline_daily_states,
    theme_driver_events,
    cognition_cards,
)
```

每个主题统一编译为：

```json
{
  "subject_key": "",
  "theme_name": "",
  "role": "",
  "stage": "",
  "state_evolution": {},
  "capital": {},
  "drivers": [],
  "analyst_view": {}
}
```

实施约束：

- `analyst_view` 只包含 `override=true` 的双轨字段。
- `state_evolution` 保留 `mainline_daily_states` 独有数据，例如 `fade_risk`、`alive`、`strength`。
- ASSESSMENT 合并顺序：`analyst > AI > engine > builder`。
- FACT 仍禁止人工覆盖。

### PR2.2b Stock Structure

已实现按 `stock_code` 的股票实体合并：

```python
stocks_by_code[stock_code] = merged_stock_entity
```

输入来源：

- `strong_stock_reviews`
- `post_market_decision_v2.pool_reviews`

输出规则：

- 同一 `stock_code` 只保留一个实体。
- `roles` 聚合，不重复复制为多个股票。
- 今日角色分组：`leaders / mid_cap / frontline / eliminated`。
- 每只股票只保留 4-6 个关键评分字段，全量评分后续进入 `evidence_appendix`。

后续约束：

- `roles` 建议升级为带优先级结构，排序规则属于 Projection，不属于 UI：

```json
{
  "roles": [
    { "type": "leader", "priority": 1 },
    { "type": "watch", "priority": 3 }
  ]
}
```

- 正式报告内每只股票仅保留关键评分，例如：

```json
{
  "strength_score": 0,
  "capital_score": 0,
  "structure_score": 0,
  "confidence": 0
}
```

- 其他细分评分进入 `evidence_appendix.stock_scores`，避免正式报告重新膨胀为评分表。

### PR2.2 测试

| Case | 验证点 | 结果 |
|---|---|---|
| AI/Analyst 冲突 | AI=机器人，Analyst=PCB → `final_value=PCB` | ✅ |
| 主题来源缺失 | `theme_reviews` 无 PCB，但 `cognition_cards + driver_events` 有 → 不丢主题 | ✅ |
| 股票去重 | `strong_stock + pool_review` 同 `stock_code` → 一个 stock entity | ✅ |

### PR2.2 验证

| 验证项 | 结果 |
|---|---|
| 55 backend tests | ✅ 通过 |
| 3 frontend contracts | ✅ 通过 |

## 14. Recap 正式报告入口修复记录（2026-07-11）

### 问题

7/9 验证中发现：Recap 页处于 `DRAFT_READY` 预览模式时仍展示 AI + 分析师 draft 内容；点击“刷新正式报告”后，前端旧链路仍会触发：

- `generatePostMarketRecap()`
- `generateDailyReviewV2()`
- `post_market_recap_generate`

这会绕过 “Formal Report = Approved Snapshot Only” 的产品语义，造成用户误以为 draft 已刷新成正式报告。

### 修复

`frontend/src/routes/recap/RecapPage.tsx` 已收紧为：

- 正式报告按钮只调用 `composeDailyReviewFromWorkbench()`。
- `workbench_approval.can_generate_formal_report !== true` 时按钮禁用。
- 预览状态按钮文案显示 `待审核批准`。
- 页面提示：必须进入分析师工作台完成审核并批准 Snapshot。
- 不再从 Recap 页触发旧 `post_market_recap_generate`。

`frontend/scripts/test-recap-workbench-first-contract.mjs` 已补强：

- 禁止 `RecapPage` 出现 `generatePostMarketRecap(`。
- 禁止 `RecapPage` 出现 `generateDailyReviewV2(`。
- 要求 `RecapPage` 使用 `composeDailyReviewFromWorkbench`。

### 验证

| 验证项 | 结果 |
|---|---|
| `npm run build` | ✅ 通过 |
| `node scripts/test-recap-workbench-first-contract.mjs` | ✅ 通过 |

## 15. 当前 Phase 4.5.6 状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| PR1a Output Cleanup | ✅ Completed | 删除重复 blob 与永空/别名字段输出 |
| PR1b Migration Cleanup | ⏳ Planned | `attention_review` 等迁移后删除 |
| PR2.1 Compiler Core | ✅ Completed | `metadata + executive_summary + market_state` |
| PR2.2 Theme + Stock | ✅ Completed | Subject Union + stock_code entity merge |
| PR2.3a Capital Evidence | ✅ Completed | `market capital + theme capital + stock evidence` 三层模型 |
| PR2.3b Next Day Plan | ✅ Completed | `scenario + watch + confirmation + invalidation + forbidden` |
| PR3 Projection Diff | ✅ Completed | 7/9 Golden + FACT/ASSESSMENT/PLAN diff |
| PR4 FormalReview UI | ✅ Completed | FormalReviewView 双轨 UI |
| PR5 Multi-day Observe | ⏳ Planned | 5+ 交易日观察 |
| PR6 Legacy Removal | ⏳ Planned | compatibility 与旧字段移除 |

下一步建议：

1. 进入 PR5 Multi-day Observe，至少观察 5 个交易日。
2. 保持 dual-track，等待 PR5 结果稳定。
3. PR6 再移除 compatibility 与旧字段。

## 16. PR2.3 设计约束（2026-07-11）

PR2.3 是 FormalReviewProjectionCompiler 的最后两块业务章节：`capital_evidence` 与 `next_day_plan`。这两块最容易重新膨胀，因此进入实施前固定以下边界。

### 16.1 Capital Evidence 三层模型

Capital Evidence 固定为三层，不再增加第四层：

```json
{
  "capital_evidence": {
    "market": {},
    "themes": [],
    "stocks": []
  }
}
```

| 层级 | 职责 | 示例 |
|---|---|---|
| Level 1: market capital | 市场整体资金状态 | 全市场成交额、活跃资金、资金扩张/收缩 |
| Level 2: theme capital | 题材资金状态 | 题材净流入、题材内核心股资金集中度 |
| Level 3: stock evidence | 个股资金证据 | 主力净流入、龙虎榜、异常信号 |

实施规则：

- `stock_capital_reviews`、`money_flow_reviews`、`dragon_tiger_reviews`、`abnormal_reviews` 按 `stock_code` 合并为同一条 `capital_evidence.stocks[]`。
- 龙虎榜、资金流、异常信号不再分别形成独立股票列表。
- 无法映射到 `stock_code` 的席位或资金证据进入 `capital_evidence.orphan_seats`。
- FACT 不做人工覆盖；Compiler 只做映射与合并，不重新计算资金指标。

### 16.2 Next Day Plan 收敛结构

Next Day Plan 统一承接所有“明天怎么办”的信息来源。

目标结构：

```json
{
  "next_day_plan": {
    "scenario": "",
    "watch_themes": [],
    "watch_stocks": [],
    "confirmation_signals": [],
    "invalidation_signals": [],
    "forbidden_actions": []
  }
}
```

来源映射：

| 来源 | 目标 |
|---|---|
| `playbook_review` | `next_day_plan.scenario / principles` |
| `watchlist_reviews` | `next_day_plan.watch_stocks` |
| `post_market_setup_plan` | `next_day_plan.watch_stocks` 或 `one_to_two` 子标签 |
| `emotion_review.tomorrow_outlook` | `next_day_plan.scenario` |
| `emotion_review.tomorrow_watchpoints` | `next_day_plan.confirmation_signals` |
| `emotion_review.tomorrow_forbidden` | `next_day_plan.forbidden_actions` |

实施规则：

- Chapter 4 `stock_structure` 只描述今天发生了什么。
- Chapter 6 `next_day_plan` 只描述明天看什么、等什么确认、什么情况下放弃。
- `watchlist_reviews + playbook_review + tomorrow_*` 只是来源字段，不再作为正式报告内的独立章节名。
- PLAN 合并顺序保持：`analyst final_value > Approved playbook > Engine plan > legacy`。

### 16.3 PR2.3 拆分

| 子阶段 | 范围 | 验收 |
|---|---|---|
| PR2.3a Capital Evidence | `market capital + theme capital + stock evidence` | 同 `stock_code` 合并；龙虎榜/资金流/异常合并；FACT 不改变 |
| PR2.3b Next Day Plan | `scenario + watch + confirmation + invalidation + forbidden` | AI plan + analyst adjustment 正确合并；今天/明天不混放 |

### 16.4 当前完成度

Phase 4.5.6 当前约完成 90%。FormalReviewProjectionCompiler 已具备完整六章输出能力，FormalReviewView 已双轨接入 Recap：

```text
Market State
  +
Theme Entity
  +
Stock Entity
  +
Capital Evidence
  +
Next Day Plan
```

PR4 FormalReview UI 已通过。下一步进入 PR5 Multi-day Observe，验证新结构跨交易日稳定性。

## 17. PR2.3 实施记录（2026-07-11）

### PR2.3a Capital Evidence

实现文件：

- `daily_review/projections/capital_evidence.py`
- `daily_review/formal_review_projection_compiler.py`
- `api_app.py` compose-from-workbench 投影入参

完成：

- `capital_evidence.market` 汇总市场级资金状态、证据层摘要与席位摘要。
- `capital_evidence.themes[]` 映射 `theme_capital_reviews`，保留题材级资金事实。
- `capital_evidence.stocks[]` 按 `stock_code` 合并：
  - `stock_capital_reviews`
  - `money_flow_reviews`
  - `dragon_tiger_reviews`
  - `abnormal_reviews`
- 无 `stock_code` 的席位证据进入 `orphan_seats`，不污染股票实体。
- FACT 数据只映射和合并，不做人工覆盖，不重新计算。

### PR2.3b Next Day Plan

实现文件：

- `daily_review/projections/next_day_plan.py`
- `daily_review/formal_review_projection_compiler.py`
- `api_app.py` compose-from-workbench 投影入参

完成：

- `next_day_plan.scenario` 按 PLAN 策略合并：
  - analyst override
  - approved playbook
  - emotion tomorrow outlook
  - trading principle legacy
- `watchlist_reviews + post_market_setup_plan + decision_v2 focus/D1` 按 `stock_code` 合并为 `watch_stocks[]`。
- `watch_themes[]` 从 `watch_stocks[]` 聚合生成，只作为明日观察主题索引。
- `confirmation_signals / invalidation_signals / forbidden_actions` 收敛为正式计划字段。
- Chapter 4 继续只描述今天，Chapter 6 只描述明天计划。

### PR2.3 测试

新增：

- `stock_processing_service/tests/unit/test_projection_capital_plan.py`

覆盖：

| Case | 验证点 | 结果 |
|---|---|---|
| Capital stock merge | 同一股票来自资金、资金行为、龙虎榜、异动时只输出一个 stock entity | ✅ |
| Orphan seats | 无 `stock_code` 的席位证据进入 `orphan_seats` | ✅ |
| Watch merge | `watchlist_reviews + one_to_two` 同股票合并，标签聚合 | ✅ |
| Plan override | 分析师 playbook override 优先于 emotion/trading_principle | ✅ |

### PR2.3 验证

| 验证项 | 结果 |
|---|---|
| `py_compile` projection/compiler/API | ✅ 通过 |
| `test_projection_capital_plan.py` | ✅ 4 passed |
| `test_projection_theme_stock_merge.py` | ✅ 5 passed |
| Phase 4.5.5/4.5.6 相关后端测试 | ✅ 19 passed |
| `test-recap-workbench-first-contract.mjs` | ✅ 通过 |
| `test-workbench-generate-flow-contract.mjs` | ✅ 通过 |

## 18. PR3 Projection Diff 实施记录（2026-07-11）

新增：

- `stock_processing_service/tests/unit/test_projection_formal_schema.py`
- `stock_processing_service/tests/unit/test_projection_diff_20260709.py`
- `docs/test_reports/projection_diff_20260709.md`

完成：

- 冻结 `formal_review` 六章模型：
  - `executive_summary`
  - `market_state`
  - `theme_structure`
  - `stock_structure`
  - `capital_evidence`
  - `next_day_plan`
- 防止 `workbench_data / confirmed_mainlines / pending_mainline_reviews` 回流。
- 基于 2026-07-09 Golden 样本建立语义 diff：
  - FACT Diff
  - ENTITY Diff
  - ASSESSMENT Diff
  - PLAN Diff
- 修正 PR2.3 边界：
  - `capital_evidence.stocks[].capital.fact` 与 `capital.assessment` 分离。
  - `next_day_plan` 在分析师明确 watch override 时只输出 final watch universe，AI/legacy watch 仅保留在 audit/playbook 中。

验证：

| 验证项 | 结果 |
|---|---|
| PR3 focused projection tests | ✅ 12 passed |
| Phase 4.5.5/4.5.6 相关后端测试 | ✅ 22 passed |
| 前端 Workbench/Recap 契约 | ✅ 通过 |

结论：

`FormalReviewProjectionCompiler` 已证明可以压缩结构复杂度，同时保持核心市场认知价值：FACT 稳定、ENTITY 不丢、ASSESSMENT 尊重分析师校准、PLAN 消费最终确认结果。

## 19. PR4 FormalReview UI 实施记录（2026-07-11）

新增：

- `frontend/src/routes/recap/components/FormalReviewView.tsx`
- `frontend/scripts/test-formal-review-view-contract.mjs`

修改：

- `frontend/src/lib/api.ts`
  - 新增 `FormalReviewProjection` 类型。
  - `PostMarketDailyReviewV2` 暴露 `metadata / formal_review / evidence_appendix`。
- `frontend/src/routes/recap/RecapPage.tsx`
  - 在 `WorkbenchSectionsPanel` 与 `EnginePostMarketView` 前双轨渲染 `FormalReviewView`。
  - 不删除旧 Workbench/Engine 视图，支持对照观察。

FormalReviewView 只消费：

- `formal_review.executive_summary`
- `formal_review.market_state`
- `formal_review.theme_structure`
- `formal_review.stock_structure`
- `formal_review.capital_evidence`
- `formal_review.next_day_plan`

边界：

- 不读取 `theme_reviews / strong_stock_reviews / watchlist_reviews / post_market_decision_v2` 等 legacy DailyReviewV2 字段。
- 不替换旧 Recap 组件。
- 不新增第七章。

验证：

| 验证项 | 结果 |
|---|---|
| `node scripts/test-formal-review-view-contract.mjs` | ✅ 通过 |
| `node scripts/test-recap-workbench-first-contract.mjs` | ✅ 通过 |
| `npm run build` | ✅ 通过 |
