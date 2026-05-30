# 盘后复盘交易引擎架构设计方案 v1.1

> 项目：`ai_theme_app` / AI 投资个人助理 / 久赢恒丰 2.0  
> 版本：v1.1  
> 日期：2026-05-30  
> 当前重点：第一阶段 **主线发现 Mainline Discovery**  
> 本版修正重点：`report_context` 不作为事实真源；新增 `MainlineDiscoveryFactContextBuilder`；主线确认分快线/慢线路径；LLM 只做叙事裁判；机器候选与灰色区域进入人工审核；快线/慢线确认后共用统一生命周期；交易前必须经过市场环境过滤。

---

## 0. 文档目标

本文档用于固化当前盘后复盘交易引擎架构共识，并指导后续开发。

本阶段不是继续“发现更多题材”，而是建设：

```text
Mainline Discovery 主线发现系统
```

它的目标是：

```text
从每天大量热点题材中，识别极少数真正可能成为市场主线的对象。
```

最终系统遵循：

```text
没有主线，不交易；
有主线，还要看市场环境；
市场允许，才看龙头；
龙头明确，才等买点；
买点确认，才执行。
```

---

# 1. 核心认知原则

## 1.1 题材发现 ≠ 主线发现

### 题材 Theme / Subject

题材是市场每天出现的热点标签。

特征：

```text
- 数量很多，全年可能几百个
- 可以只活 1 天、2 天、3 天
- 很多只是消息刺激、资金轮动、一日游
- 不一定有持续事件
- 不一定被市场反复买单
- 不一定产生稳定赚钱效应
```

项目中的 `subject_key` 是题材业务主键，用于连接：

```text
theme_history_event
subject_rank_daily / top-history
theme_tree_relation
theme_stock_map
subject_stock_daily_snapshot
event_theme_map
```

但 `subject_key` 不应直接等同于 `mainline`。

### 主线 Mainline

主线是少数真正能统领一段时间市场风险偏好的核心叙事。

特征：

```text
- 数量很少，全年可能只有十几个
- 至少持续一周左右，强主线可持续数月甚至全年
- 必须有持续事件、重大政策、产业趋势、技术突破、订单、冲突、供需变化等逻辑刺激
- 必须被市场持续买单
- 必须产生龙头、龙二、补涨、分支扩散和生命周期演化
```

主线不是单个题材，而是高阶对象。

示例：

```text
主线：AI算力
  核心题材：CPO、液冷、服务器、HBM、国产算力
  分支题材：AI应用、AI眼镜、数据中心电源
```

因此需要逐步沉淀：

```text
mainline_id
  ↓
mainline_subject_binding[]
  ↓
subject_key[]
```

---

## 1.2 主线确认 ≠ 主线生命周期

### 主线确认

回答：

```text
它是不是主线？
```

核心判断：

```text
事件逻辑强 + 市场买单
```

只有同时满足：

```text
有逻辑 + 有人买 + 龙头或核心前排出现
```

才有主线资格。

### 主线生命周期

回答：

```text
已经确认是主线之后，它现在处于什么阶段？
```

生命周期阶段包括：

```text
seed / 启动前观察
start / 启动
fermentation / 发酵
acceleration / 加速
climax / 高潮
divergence / 分歧
repair / 修复
fade_watch / 退潮观察
fade_confirmed / 退潮确认
dead / 死亡
```

生命周期判断不能替代主线确认。

---

## 1.3 快线 / 慢线只影响确认路径，不影响生命周期逻辑

主线确认可以分为：

```text
快线确认路径 fast_line_confirmation_path
慢线确认路径 slow_line_confirmation_path
```

但一旦经过人工审核确认为主线，后续共用一套生命周期管理逻辑：

```text
confirmed_mainline
  ↓
UnifiedMainlineLifecycleEngine
```

不需要拆成：

```text
fast_line_lifecycle
slow_line_lifecycle
```

原因：

```text
快线 / 慢线只是主线是如何被发现和确认的；
生命周期管理的是主线确认后如何演化。
```

只要主线没有退潮，在分歧阶段都可以参与，前提是：

```text
1. 主线仍 alive
2. 市场环境安全
3. 龙头核心仍然存在
4. 买点经过确认
```

---

## 1.4 有主线不等于可以交易

即使主线仍然存在，市场大环境不利时，也应观望。

典型情况：

```text
主线仍有利好消息
但大盘处于下降通道或弱反抽
短线情绪差
亏钱效应扩散
高标反馈不好
```

此时正确策略是：

```text
高手观望
最多超短线小仓试探
禁止机械性弱转强
禁止追涨非核心后排
```

因此，主线生命周期之后必须经过：

```text
MarketRegimeEngine 市场环境识别层
```

---

# 2. 修正后的完整交易引擎流程

```text
采集控制台 / 数据事实层
  ↓
MainlineDiscoveryFactContextBuilder
主动从真实数据源构建主线发现事实包
  ↓
MainlineDiscoveryEngine
  ├── FastLinePath：重大事件当天触发
  └── SlowLinePath：多日事件和市场发酵
  ↓
AnalystReviewQueue
机器候选 / LLM 建议 / 灰色区域均提交人工审核
  ↓
HumanConfirmedMainline
分析师确认主线
  ↓
UnifiedMainlineLifecycleEngine
确认主线后共用统一生命周期
  ↓
MarketRegimeEngine
识别大盘环境 + 短线情绪 + 主线当前交易环境
  ↓
TradingPrincipleEngine
生成今日交易原则：是否交易、仓位、允许动作、禁止动作
  ↓
LeaderCoreEngine
只在允许交易的主线里识别龙头、龙二、卡位、补涨
  ↓
SetupPlanEngine / WatchlistEngine
生成次日观察计划、弱转强计划、失效条件
  ↓
DailyReviewV2
结构化复盘输出
  ↓
PreMarketBrief
盘前推演：结合隔夜消息、外围、竞价前计划
  ↓
RealtimeBuyPointConfirmation
竞价、开盘、分时、承接、放量、支撑、背离确认
  ↓
交易闭环 / T+1 / T+n 回测反馈
```

一句话：

```text
主线是方向；
生命周期是阶段；
市场环境是开关；
龙头是标的；
买点是执行。
```

---

# 3. 当前项目已有基础与架构修正

## 3.1 已有基础

当前项目已经具备：

```text
news_raw
news_event
event_theme_map
theme_history_event
subject_rank_daily / top-history
subject_stock_daily_snapshot
theme_cycle_evidence_daily
theme_cycle_judgement_v2
strong_watch_pool
weak_to_strong_candidate_pool
post_market_recap_snapshot
daily_review_v2
```

已有能力：

```text
新闻事件识别
新闻事件与题材匹配
题材历史事件入库
top-history 连续事件记录
题材股票池采集
题材日快照
主题周期证据
强势股观察池
弱转强候选池
盘后复盘 P0 决策结构化输出
P1 watchlist / theme diagnostics
```

---

## 3.2 核心修正：report_context 不是主线发现事实真源

旧错误设计：

```text
MainlineLogicChainBuilder
  ↓
从 report_context 被动抽 event_theme_map / news_event / subject_history
```

问题：

```text
report_context 当前大概率没有完整事件数据；
它更像复盘展示聚合对象，不是主线发现事实真源。
```

正确设计：

```text
MainlineDiscoveryFactContextBuilder
  ↓ 主动调用 read_port
get_subject_event_chain_rows
  ↓
StockReadGatewayAdapter
  ↓
DB Gateway / postgres_manager
  ↓
theme_history_event 主源
event_theme_map + news_event 辅助源
subject_rank_daily / top-history 补充源
```

因此，主线发现第一阶段必须主动构建：

```text
MainlineDiscoveryFactContext
```

而不是从 `report_context` 中“碰运气”。

---

# 4. MainlineDiscoveryFactContextBuilder 设计

## 4.1 模块位置

建议：

```text
stock_processing_service/application/services/mainline_discovery_fact_context_builder.py
```

原因：

```text
它负责调用 read_port 读取多张事实表并组装上下文，属于应用层编排。
```

## 4.2 职责

```text
1. 构建 candidate_subjects
2. 读取事件链明细
3. 读取 subject 事件统计
4. 读取 top-history / subject_rank_daily 连续记录
5. 读取 theme_cycle_evidence_daily
6. 读取 theme_cycle_judgement_v2
7. 读取资金 / 龙头 / 股票池 / 强势池数据
8. 输出 MainlineDiscoveryFactContext
```

## 4.3 输出结构

```json
{
  "trade_date": "2026-04-29",
  "lookback_days": 7,
  "candidate_subjects": [
    {
      "subject_key": "9019807",
      "theme_name": "卫星互联网",
      "candidate_source": "hot_rank",
      "priority_score": 80
    }
  ],
  "event_rows_by_subject": {
    "9019807": [
      {
        "event_id": "the_123",
        "subject_key": "9019807",
        "theme_name": "卫星互联网",
        "event_date": "2026-04-29",
        "occurred_at": "2026-04-29T00:00:00",
        "title": "某重大政策推动卫星互联网应用",
        "summary": "......",
        "event_type": "policy",
        "event_type_source": "keyword_fallback",
        "impact_score": 0.86,
        "confidence": 0.70,
        "source_channel": "jyhf_history",
        "source_table": "theme_history_event"
      }
    ]
  },
  "event_stats_by_subject": {
    "9019807": {
      "today_event_count": 2,
      "recent_event_count": 6,
      "distinct_event_days": 4,
      "key_event_count": 3,
      "sample_summaries": []
    }
  },
  "rank_history_by_subject": {},
  "cycle_evidence_by_subject": {},
  "cycle_judgement_by_subject": {},
  "capital_by_subject": {},
  "stock_facts_by_subject": {},
  "diagnostics": {
    "candidate_subject_count": 49,
    "event_chain_row_count": 58,
    "event_chain_subject_count": 40,
    "event_stats_subject_count": 49,
    "source_counts": {
      "theme_history_event": 58,
      "event_theme_map+news_event": 0
    },
    "empty_event_subject_count": 9,
    "missing_sources": [],
    "fallback_used": []
  }
}
```

## 4.4 已验证事实链路

当前事件链事实链路已经完成验证：

```text
2026-04-28:
  candidates = 47
  event_rows = 60
  event_subjects = 43
  sources = {"theme_history_event": 60}
  logic_score_non_null = 43

2026-04-29:
  candidates = 49
  event_rows = 58
  event_subjects = 40
  sources = {"theme_history_event": 58}
  logic_score_non_null = 40
```

已修复 SQL 问题：

```text
全局 LIMIT 500 → ROW_NUMBER() OVER(PARTITION BY subject_key) Top 10 / subject
无去重 → (subject_key, event_date, title[:80]) 去重
日期混合字符串 → event_date + occurred_at 分离
无来源标记 → source_table 字段
事件类型无来源 → event_type_source 字段
```

---

# 5. 主线确认：快线 / 慢线双路径

## 5.1 快线 Fast Line

适用于：

```text
特别重大政策
国际冲突 / 地缘突发
国家级工程
产业规则变化
重大机构成立
重大技术突破
重大供需冲击
重大价格变化
巨头级产品 / 订单 / 产业链事件
```

特点：

```text
不要求多日连续发酵
可以当天进入机器候选
必须有重大事件 + 当天市场快速买单
必须提交人工审核
```

示例：

```text
雅江水电站
以伊冲突
成立航天司 → 商业航天
```

快线机器候选公式：

```text
fast_line_score =
  major_event_score * 0.45
+ same_day_market_acceptance_score * 0.30
+ front_row_strength_score * 0.15
+ narrative_scope_score * 0.10
```

快线候选门槛：

```text
major_event_score >= 85
same_day_market_acceptance_score >= 60
front_row_strength_score >= 50
```

输出：

```text
machine_fast_candidate
pending_human_review
```

---

## 5.2 慢线 Slow Line

适用于：

```text
消费趋势
社会现象
产业趋势
资金逐步形成共识
连续事件发酵
慢慢从轮动题材升级为主线
```

特点：

```text
需要多日观察
需要事件连续性
需要市场反复买单
需要资金和龙头逐步确认
也必须提交人工审核
```

示例：

```text
苏超
泡泡玛特
```

慢线机器候选公式：

```text
slow_line_score =
  llm_narrative_score * 0.35
+ event_continuity_score * 0.20
+ multi_day_market_acceptance_score * 0.25
+ heat_persistence_score * 0.10
+ leader_resilience_score * 0.10
```

慢线候选门槛：

```text
llm_narrative_score >= 70
event_continuity_score >= 60
multi_day_market_acceptance_score >= 60
```

输出：

```text
machine_slow_candidate
pending_human_review
```

---

# 6. MajorEventClassifier

快线识别需要新增：

```text
MajorEventClassifier
```

职责：

```text
判断单条或少数事件是否具备快线触发资格。
```

输出：

```json
{
  "major_event_score": 92,
  "major_event_level": "A",
  "is_fast_line_trigger": true,
  "trigger_type": "national_project",
  "impact_scope": "industry_chain",
  "expected_duration": "1-2_weeks",
  "reason": "事件具备国家级工程/产业链扩散特征，可能引发短期主线级资金聚焦。"
}
```

---

# 7. MainlineNarrativeJudge

## 7.1 定位

生产阶段不能只靠规则判断主线逻辑强不强。

因此新增：

```text
MainlineNarrativeJudge
```

职责：

```text
用 LLM 作为证据裁判，判断事件链是否构成主线级叙事。
```

注意：

```text
LLM 不是最终确认者；
LLM 是主线候选分析师。
```

## 7.2 LLM 只回答逻辑，不判断市场买单

LLM 负责：

```text
这些事件是否指向同一条清晰叙事？
叙事是否有产业/政策/技术/订单层面的真实驱动？
事件是否具备连续性，而不是孤立刺激？
事件影响范围是个股、局部分支，还是产业链？
这个逻辑是否可能持续一周以上？
是否只是旧题材反抽或一日游噪音？
```

LLM 不负责：

```text
市场是否买单
是否允许交易
仓位多少
是否确认买点
```

## 7.3 LLM 输出

```json
{
  "is_mainline_logic": true,
  "narrative_score": 82,
  "narrative_level": "strong",
  "logic_type": "policy_industry_chain",
  "impact_scope": "industry_chain",
  "time_horizon": "multi_week",
  "narrative_consistency_score": 86,
  "novelty_score": 72,
  "event_continuity_assessment": "continuous",
  "supporting_event_ids": ["the_123", "ne_456"],
  "negative_reasons": [],
  "logic_summary": "近一周政策与产业事件连续出现，均指向卫星互联网规模化应用和产业链落地，具备主线级叙事基础。",
  "confidence": 0.84
}
```

证据不足时：

```json
{
  "is_mainline_logic": false,
  "narrative_score": 35,
  "narrative_level": "weak",
  "negative_reasons": [
    "事件数量不足",
    "事件之间缺少一致叙事",
    "缺少产业或政策级催化"
  ],
  "supporting_event_ids": [],
  "confidence": 0.72
}
```

## 7.4 LLM 硬约束

```text
只允许基于输入事件判断
不允许补充外部事实
必须引用 supporting_event_ids
如果 supporting_event_ids 为空，不允许给 strong narrative
如果事件不足，必须输出 insufficient / weak
```

---

# 8. logic_score 生产版

生产版不建议纯规则，也不建议纯 LLM。

建议混合：

```text
logic_score =
  llm_narrative_score * 0.55
+ event_continuity_score * 0.20
+ event_impact_score * 0.15
+ novelty_score * 0.10
```

字段建议：

```json
{
  "rule_logic_score": 68,
  "llm_narrative_score": 82,
  "logic_score": 76,
  "logic_score_method": "hybrid_v1",
  "narrative_judge": {}
}
```

LLM 可以判断叙事，但不能凭空创造叙事。

硬门槛：

```text
event_chain_count = 0 → logic_score = null，不能进入主线候选
distinct_event_days < 2 且 key_event_count = 0 → 慢线不能确认，只能观察
narrative_score 高但 event_continuity_score 低 → 最多 mainline_watch / fast_candidate，不能自动 confirmed_mainline
LLM 找不到 supporting_event_ids → 降级
```

---

# 9. MarketAcceptanceBuilder

## 9.1 定位

市场是否接受，必须主要靠量化硬数据，不应由 LLM 判断。

回答：

```text
市场是否真的相信这个逻辑，并用真金白银反复交易？
```

## 9.2 推荐公式

```text
market_acceptance_score =
  heat_persistence_score * 0.15
+ relative_strength_score * 0.15
+ board_breadth_score * 0.20
+ leader_strength_score * 0.25
+ capital_confirmation_score * 0.15
+ resilience_repair_score * 0.10
```

其中：

```text
heat_persistence_score:
  题材热度是否连续

relative_strength_score:
  是否强于指数和市场平均题材

board_breadth_score:
  是否是板块级行情，而非孤股行情

leader_strength_score:
  是否有龙头或核心前排

capital_confirmation_score:
  是否有资金确认

resilience_repair_score:
  分歧时是否抗跌，回调后是否修复
```

## 9.3 市场接受度要看连续性

主线不是一天确认的。

建议市场接受度拆分：

```text
single_day_acceptance_score
multi_day_acceptance_score
```

综合：

```text
market_acceptance_score =
  single_day_acceptance_score * 0.4
+ multi_day_acceptance_score * 0.6
```

原因：

```text
一天强只是热点；
连续强才可能是主线。
```

快线例外：

```text
重大事件快线允许当天形成机器候选，但仍需人工确认。
```

---

# 10. AnalystReviewQueue 人工审核机制

## 10.1 核心原则

```text
机器发现候选；
LLM 提供叙事判断；
分析师最终确认；
系统执行策略。
```

生产环境中：

```text
LLM 判定为确认主线 → 必须人工审核
灰色区域无法判定 → 必须人工审核
快线重大事件触发 → 必须人工审核
```

## 10.2 进入人工审核的条件

```text
1. LLM 判定为主线：
   narrative_score >= 75
   AND market_acceptance_score >= 60

2. 快线重大事件触发：
   major_event_score >= 85
   AND same_day_market_acceptance_score >= 60

3. 灰色区域：
   logic_score 60~75
   OR market_acceptance_score 55~70
   OR LLM confidence < 0.75

4. 市场很热但逻辑不足：
   market_acceptance_score >= 75
   AND logic_score < 55

5. 逻辑极强但市场刚开始反应：
   logic_score >= 80
   AND market_acceptance_score 45~60
```

## 10.3 审核队列结构

```json
{
  "review_id": "ml_review_20260530_9019807",
  "trade_date": "2026-05-30",
  "subject_key": "9019807",
  "theme_name": "商业航天",
  "mainline_type": "fast_line",
  "machine_state": "machine_fast_candidate",
  "review_reason": "major_event_trigger",
  "logic_score": 88,
  "market_acceptance_score": 72,
  "major_event_score": 92,
  "llm_narrative_score": 86,
  "event_chain": [],
  "market_evidence": {},
  "suggested_decision": "confirm_mainline",
  "human_decision": null,
  "human_reviewer": null,
  "human_notes": null,
  "created_at": "...",
  "review_status": "pending"
}
```

## 10.4 人工审核结果

分析师可以选择：

```text
confirm_mainline
watch
reject
downgrade_to_theme
merge_into_existing_mainline
mark_as_fast_line
mark_as_slow_line
```

只有：

```text
human_decision = confirm_mainline
```

才进入：

```text
final_mainline_state = confirmed_mainline
```

交易系统只使用：

```text
final_mainline_state = confirmed_mainline
```

不直接使用：

```text
machine_fast_candidate
machine_slow_candidate
```

---

# 11. UnifiedMainlineLifecycleEngine

快线 / 慢线确认后，统一进入同一套生命周期。

## 11.1 统一生命周期状态

```text
seed
start
fermentation
acceleration
climax
divergence
repair
fade_watch
fade_confirmed
dead
```

## 11.2 统一交易映射

```text
start / fermentation:
  重点观察龙头确认、前排扩散

acceleration:
  不追后排，重点看核心换手承接

climax:
  谨慎，避免一致高潮后接力

divergence:
  可参与主线核心弱转强 / 分歧低吸，前提是市场环境安全

repair:
  可参与修复确认，重点看龙头和龙二

fade_watch:
  只观察，不主动开仓

fade_confirmed / dead:
  回避
```

这套逻辑不区分快线 / 慢线。

---

# 12. MarketRegimeEngine

主线发现和生命周期之后，必须经过市场环境识别。

## 12.1 大盘环境

```text
bullish_supportive
neutral_choppy
downtrend_rebound
bearish_adverse
crash_risk
```

## 12.2 短线情绪

```text
early_trial
fermentation
acceleration
climax
divergence
retreat
dead
```

## 12.3 主线交易环境

```text
mainline_tradable
mainline_watch_only
mainline_ultra_short_only
mainline_risk_off
mainline_fading
```

## 12.4 交易总闸门

```text
没有 confirmed_mainline：
  market_structure = rotation_chaos
  allow_trade = false

有主线但 broad_market_regime = bearish_adverse / crash_risk：
  allow_trade = false

有主线但 broad_market_regime = downtrend_rebound：
  allow_trade = true
  position_limit <= 0.2
  allowed_actions = ["只允许主线核心超短确认"]

短线情绪 = retreat / dead：
  禁止主动开仓
```

---

# 13. MainlineDiscoveryReview 输出结构 v1.1

```json
{
  "trade_date": "2026-05-30",
  "mainline_id": "ml_9019807_202605",
  "mainline_name": "商业航天",
  "mainline_type": "fast_line",
  "confirmation_path": "fast_event_driven",
  "trigger_mode": "major_policy",
  "machine_state": "machine_fast_candidate",
  "human_review_required": true,
  "review_reason": "major_event_trigger",
  "human_review_status": "pending",
  "final_mainline_state": "pending_review",
  "fast_line_score": 86,
  "slow_line_score": 42,
  "major_event_score": 91,
  "rule_logic_score": 68,
  "llm_narrative_score": 84,
  "logic_score": 76,
  "market_acceptance_score": 70,
  "mainline_score": 73,
  "core_subject_keys": ["9019807"],
  "branch_subject_keys": [],
  "noise_subject_keys": [],
  "event_chain": [],
  "event_series": [],
  "narrative_judge": {},
  "market_evidence": {},
  "leader_evidence": {},
  "subject_bindings": [],
  "suggested_human_decision": "confirm_mainline",
  "diagnostics": {
    "logic_sources": ["theme_history_event"],
    "market_sources": ["theme_cycle_evidence_daily"],
    "missing_fields": [],
    "hard_veto_flags": [],
    "reject_reason": null
  }
}
```

---

# 14. 第一阶段工程实施计划 v1.1

## PR-0：FactContextBuilder + 事件事实链路

已完成方向：

```text
MainlineDiscoveryFactContextBuilder
get_subject_event_chain_rows
StockReadGatewayAdapter
DB Gateway / postgres_manager
theme_history_event + event_theme_map/news_event
SQL 修复与集成验证
```

验收：

```text
2026-04-28 / 2026-04-29 能取到事件链
logic_score_non_null_count > 0
```

## PR-1：DTO models

定义：

```text
MainlineDiscoveryReview
MainlineLogicEvidence
MainlineMarketAcceptance
MainlineEventSeries
MainlineSubjectBinding
MainlineDiscoveryDiagnostics
AnalystReviewItem
NarrativeJudgeResult
MajorEventClassification
```

## PR-2：MainlineLogicChainBuilder

职责：

```text
从 fact_context.event_rows_by_subject 构建 event_chain / event_series
计算 rule_logic_score
输出 logic_evidence
```

## PR-2.5：事件链集成验证

已完成方向：

```text
每 subject TopN
去重
日期标准化
source_table 标记
event_type_source 标记
集成测试
```

## PR-3：MainlineMarketAcceptanceBuilder

职责：

```text
从 fact_context 中计算 market_acceptance_score
```

公式：

```text
market_acceptance_score =
  heat_persistence_score * 0.15
+ relative_strength_score * 0.15
+ board_breadth_score * 0.20
+ leader_strength_score * 0.25
+ capital_confirmation_score * 0.15
+ resilience_repair_score * 0.10
```

验收：

```text
市场接受度只用硬数据
数据缺失不默认高分
leader_alive=false 不可确认主线
```

## PR-4：MajorEventClassifier + MainlineNarrativeJudge

职责：

```text
MajorEventClassifier:
  识别快线重大事件触发

MainlineNarrativeJudge:
  LLM 判断事件链是否构成主线级叙事
```

约束：

```text
LLM 只能基于输入事件判断
必须引用 supporting_event_ids
不能直接确认主线
```

## PR-5：MainlineDiscoveryEngine

职责：

```text
执行快线 / 慢线双路径机器候选判断
生成 machine_fast_candidate / machine_slow_candidate / logic_only / market_noise / rotation_hotspot / rejected
触发 pending_human_review
```

## PR-6：AnalystReviewQueue

职责：

```text
生成人工审核队列
支持 confirm_mainline / watch / reject / merge_into_existing_mainline 等审核结果
```

第一版可以先写入 snapshot，后续再建表。

## PR-7：接入 BuildPostMarketRecapJob + DailyReviewV2

并行输出：

```text
recap_doc.mainline_discovery_reviews
recap_doc.mainline_discovery_diagnostics
daily_review_v2.mainline_reviews
```

不直接改现有 `theme_decision_reviews / watchlist_reviews / trading_principle` 主链。

## PR-8：历史回测脚本

新增：

```text
scripts/backtest_mainline_discovery.py
```

指标：

```text
machine_candidate_count_by_day
pending_review_count_by_day
human_confirmed_mainline_count_by_day
logic_only_to_confirmed_rate
market_noise_failure_rate
confirmed_mainline_3d_continuation_rate
false_mainline_rate
rotation_chaos_no_trade_correct_rate
```

---

# 15. 第一阶段验收标准 v1.1

```text
1. 主线发现不依赖 report_context 被动抽事件。
2. event_chain 能从真实数据源构建。
3. logic_score 有 rule 和 LLM 两套来源，并能形成 hybrid。
4. 快线重大事件可以当天进入 machine_fast_candidate。
5. 慢线可以通过多日发酵进入 machine_slow_candidate。
6. LLM 判定强或灰色区域必须进入人工审核。
7. 机器候选不能直接变成 confirmed_mainline。
8. 人工确认后才允许进入 confirmed_mainline。
9. 快线 / 慢线确认后共用统一生命周期。
10. 没有 confirmed_mainline 时输出 rotation_chaos。
11. 有主线但市场环境不利时仍然可以输出不交易。
12. 一日游热点不会误判为已确认主线。
```

---

# 16. 推荐开发顺序 v1.1

```text
P2-0：冻结 v1.1 架构设计文档
P2-1：FactContextBuilder + event_chain 数据链路
P2-2：DTO / models
P2-3：MainlineLogicChainBuilder
P2-4：事件链集成验证
P2-5：MainlineMarketAcceptanceBuilder
P2-6：MajorEventClassifier
P2-7：MainlineNarrativeJudge
P2-8：MainlineDiscoveryEngine 双路径机器候选
P2-9：AnalystReviewQueue
P2-10：接入 DailyReviewV2 并并行输出
P2-11：历史回测脚本
P2-12：回测调参
P2-13：UnifiedMainlineLifecycleEngine
P2-14：MarketRegimeEngine
P2-15：TradingPrincipleEngine 重构
P2-16：再恢复 T+1 验证字段与实时确认
```

---

# 17. 给 Codex 的更新任务提示词

```text
修正 Mainline Discovery v1 架构，升级为 v1.1。

核心原则：
1. report_context 不是主线发现事实真源。
2. 必须通过 MainlineDiscoveryFactContextBuilder 主动从真实数据源构建事实包。
3. 主线确认分为 fast_line 和 slow_line 两条确认路径。
4. fast_line 可由重大事件当天触发机器候选。
5. slow_line 由多日事件发酵和市场持续买单形成机器候选。
6. LLM 只做 MainlineNarrativeJudge，不直接确认主线。
7. LLM 判定强、快线重大事件、灰色区域都必须进入 AnalystReviewQueue。
8. 只有人工审核 confirm_mainline 后，final_mainline_state 才能变成 confirmed_mainline。
9. 快线 / 慢线只影响确认路径，不影响生命周期。
10. 所有 confirmed_mainline 共用 UnifiedMainlineLifecycleEngine。
11. 市场接受度必须由量化硬数据计算，不能由 LLM 判断。
12. 第一阶段先并行输出 mainline_discovery_reviews，不破坏现有 P0/P1 主链。
```

---

# 18. 最终结论

主线发现生产版应遵循：

```text
事件事实链
  ↓
快线 / 慢线候选识别
  ↓
LLM 叙事裁判
  ↓
市场买单量化
  ↓
机器生成主线候选
  ↓
人工审核确认
  ↓
confirmed_mainline
  ↓
统一生命周期管理
  ↓
市场环境过滤
  ↓
交易原则与买点确认
```

最终原则：

```text
机器可发现；
LLM 可建议；
人来确认；
系统来执行。
```

主线发现的目标不是每天给出机会，而是帮助系统识别真正值得等待、跟踪和交易的市场核心叙事。
