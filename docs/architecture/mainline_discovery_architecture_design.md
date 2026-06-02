# 盘后复盘交易引擎架构设计方案 v1.1

> 项目：`ai_theme_app` / AI 投资个人助理 / 久赢恒丰 2.0  
> 版本：v1.2  
> 日期：2026-05-31  
> 当前重点：第一阶段 **主线发现 Mainline Discovery**（已上线验证）  
> v1.2 修正重点：CDP DOM 与旧链数据断层修复；四源事件合并；Legacy 主线注册表 backfill；PDV2 branch 展开与诊断增强；registry 去重与 theme_name 修复。

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

# 14. 第一阶段工程实施状态 v1.2

## 已完成 (2026-05-31)

| PR | 模块 | 状态 |
|---|---|---|
| PR-0 | FactContextBuilder + 事件事实链路 | ✅ 4-source merge |
| PR-1 | DTO / models | ✅ |
| PR-2 | MainlineLogicChainBuilder | ✅ event_rows_by_subject primary |
| PR-3 | MainlineMarketAcceptanceBuilder | ✅ |
| PR-4 | MajorEventClassifier + MainlineNarrativeJudge | ✅ |
| PR-5 | MainlineDiscoveryEngine (快线/慢线) | ✅ 双路径 |
| PR-6 | AnalystReviewQueue | ✅ |
| PR-7 | BuildPostMarketRecapJob 集成 | ✅ |
| PR-8 | 历史回测脚本 | ✅ backtest_mainline_discovery.py |
| PR-9 | mainline_review_queue 持久化 | ✅ |
| PR-10 | MainlineLifecycle (Layer B 复用) | ✅ |
| PR-11 | MarketRegimeEngine | ✅ |
| PR-12 | PostMarketDecisionV2 (Layer C/D1) | ✅ (branch 展开补全) |
| PR-12.5 | ActiveMainlineUniverse | ✅ (去重 + backfill) |
| — | CDP DOM staging 候选补充 | ✅ _fetch_staging_subjects |
| — | Legacy 主线 backfill | ✅ 6 条导入 |
| — | Registry 去重 + theme_name 修复 | ✅ |

## 待开发

| PR | 模块 | 状态 |
|---|---|---|
| PR-followup | Subject Key 规范化 | 待开始 |
| PR-followup | MarketRegimeEngine no_trade 验证 | 待开始 |
| PR-followup | 前端存量主线导入入口 | 待开始 |
| PR-followup | PDV2 D2 竞价/盘中确认 | 未开始 |
| PR-followup | T+1 回测闭环 | 未开始 |

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

---

# 19. 开发实战记录：CDP DOM 与旧链数据断层（2026-05-31）

## 19.1 问题发现

2026-05-29 回测时发现 `event_chain_subject_count = 0`，所有 65 个候选题材均无事件数据。

根因链：

```text
_fetch_event_theme_map_rows
  → SELECT id, subject_key FROM theme_master WHERE subject_key = ANY(...)
  → theme_master 表没有 subject_key 列
  → PostgreSQL UndefinedColumnError
  → 异常传播至 gateway.get_subject_event_chain_rows
  → except Exception: return []
  → 4 个事件源全部静默丢失
```

## 19.2 两级根因

### 根因 1：数据断层

`theme_history_event`（jyhf_history 源）数据停在 **2026-04-30**。5 月的数据由 CDP DOM 管线写入 `subject_history_staging`，但 FactContextBuilder 的候选来源 `MainlineIdentityUniverseBuilder` 只从 `theme_cycle_judgement_v2` 拉取 6 个 subject，与 staging 的 65 个 subject **零交集**。

### 根因 2：废弃表引用

`_fetch_event_theme_map_rows` 使用了两跳查询：
1. `theme_master` → 获取 `theme_id → subject_key` 映射（但 `theme_master` 无 `subject_key` 列）
2. `event_theme_map JOIN news_event` → 按 `theme_id` 过滤

正确做法：`event_theme_map` 本身已经包含 `tree_subject_key` 和 `branch_subject_key` 列，不需要通过 `theme_master` 做二次映射。

## 19.3 四源事件合并架构

修复后的事件链查询合并四个来源：

```text
Source 1: theme_history_event (jyhf_history)
  - 数据停在 2026-04-30
  - 使用 ROW_NUMBER() OVER(PARTITION BY subject_key) 取每 subject Top 10

Source 2: event_theme_map + news_event (JYHF legacy)
  - 改用 tree_subject_key / branch_subject_key 直查
  - 不再依赖 theme_master
  - 当前无近期数据（tree_subject_key 全为 NULL）

Source 3: subject_history_staging (CDP DOM primary)
  - jyhf_cdp_service/db_sink.py 写入
  - 包含 subject_key（中文名，来自 subject_name 推导）
  - 2026-05-22 ~ 05-29 共 106 条，覆盖 65 个 subject

Source 4: event_subject_map + news_event (CDP DOM supplementary)
  - 直接使用 event_subject_map.subject_key
  - 不依赖 theme_master
```

## 19.4 Staging 候选补充

FactContextBuilder 新增 `_fetch_staging_subjects()` 方法，从 `subject_history_staging` 查询回溯窗口内的 distinct subject_keys，补充到候选列表中：

```text
MainlineIdentityUniverseBuilder → 6 候选 (cycle_judgement)
  +
_fetch_staging_subjects → 65 候选 (CDP DOM staging)
  =
65 候选题材（合并去重后）
```

方法链涉及 5 个文件：
- `postgres_manager.py` — SQL 查询
- `gateway.py` — 委托封装
- `database_gateway_stock_facade.py` — 协议声明
- `stock_read_gateway_adapter.py` — 适配器
- `mainline_discovery_fact_context_builder.py` — 调用方

## 19.5 MainlineLogicChainBuilder 事件来源修正

`MainlineLogicChainBuilder.build()` 原本只从 DB pool 或 `report_context` 获取事件，但 FactContextBuilder 已经预获取了全部事件数据。修改为接受 `event_rows_by_subject` 参数作为**首选来源**：

```text
事件来源优先级:
1. event_rows_by_subject (FactContextBuilder 预获取, 权威源)
2. DB pool (如果可用)
3. report_context (兜底)
```

## 19.6 修复后验证结果（2026-05-29）

```text
修复前:
  event_chain_subject_count: 0
  logic_score_non_null_count: 0
  machine_fast_candidate: 0

修复后:
  candidate_subject_count: 65
  event_chain_subject_count: 59
  logic_score_non_null_count: 59
  machine_fast_candidate: 2 (电力运营 major_event=97, PCB印制电路板 major_event=92)
  analyst_review_items: 8
```

---

# 20. 主线注册表继承与 Backfill（2026-05-31）

## 20.1 两套注册表的隔离

项目中存在两个主线注册表：

| 表 | 行数 | 确认数 | 用途 |
|---|---|---|---|
| `theme_mainline_identity_registry` | 691 | 173 | 旧架构 — cycle_judgement 产出，每天重复写入 |
| `mainline_registry` | 6 (清理后) | 6 | 新架构 — 人工确认后写入，完整生命周期字段 |

新架构代码查询 `mainline_registry`，旧注册表的 173 条确认数据**从未被迁移**。

## 20.2 对 Layer C 的影响

PDV2 引擎按 `mainline_sks`（来自 `mainline_registry` 的 canonical + related + branch subject_keys）过滤股票池。如果存量主线不在 registry 中，其关联股票会被**全部过滤掉**：

```python
filtered_pool = [r for r in pool_rows
                 if r["subject_key"] in mainline_sks]
```

这导致：
- 旧架构已确认的 3 个主线（9065632, 9065423, 9059825）未被继承
- 其股票被从 Layer C 强股池中排除
- `active_subject_count = 3`（修复前仅 AI算力/商业航天/低空经济）

## 20.3 LegacyMainlineRegistryBackfill

创建 `scripts/legacy_mainline_registry_backfill.py`，按人工确认清单批量导入 6 条存量主线：

| 主线 | canonical_key | related keys | branch keys |
|---|---|---|---|
| 商业航天 | 9019807 | 商业航天8大IPO, 广州商业航天 | — |
| AI算力 | 9013933 | 算力租赁, AIDC绿电供应, AI一体机 | AI软件, AI智能体, AI十大应用, AI光纤, 英伟达电源方案 |
| 低空经济 | 9015778 | 低空经济 | — |
| 机器人 | 9014636 | 国内机器人, 宇树机器人, 深圳机器人 | 华为机器人, 特斯拉机器人, 机器人丝杠, 机器人材料, etc. |
| PCB印制电路板 | 9018144 | AI六大短缺硬件-PCB钻针, 英伟达PCB核心 | — |
| 电力运营 | 9013416 | 电力运营-火电, 电力运营 | — |

写入规则：
- `identity_status = 'confirmed'`
- `tracking_status = 'active'`
- `valid_from = 2026-05-01`（保守起点）
- `valid_to = NULL`（永久有效，除非人工归档）
- `source_review_id = 'legacy_backfill_20260529'`

## 20.4 Registry 去重

清理了：
- 4 条测试条目（`ml_ai`, `ml_low` 等，`source_review_id = NULL`）
- 4 条误确认条目（`source_review_id` 包含 `rejected`/`rotation_hotspot`）
- 2 对中英文 key 重复（电力运营/PCB — 发现管线用中文名，旧架构用数字 ID）

`ActiveMainlineUniverseBuilder` 新增去重逻辑：按 `canonical_subject_key` 保留 `valid_from` 最新的条目，防止同一主线多次注册导致的集合膨胀。

## 20.5 修复后验证

```text
修复前:
  active_mainline_count: 6 (含重复/测试数据)
  active_subject_key_count: 3

修复后:
  active_mainline_count: 6 (去重后，全部唯一)
  active_subject_key_count: 31 (canonical + related + branch 完全展开)
  missing_registry_subject_keys: [9065423, 9065632] (均为 review_pending，非确认主线，过滤正确)
```

---

# 21. PDV2 Layer C/D1 主线过滤链路

## 21.1 Branch 展开修复

`PostMarketDecisionV2.evaluate()` 原本只展开 `canonical_subject_key` 和 `related_subject_keys_json`，但遗漏了 `branch_subject_keys_json`。这与 `ActiveMainlineUniverseBuilder` 的展开逻辑不一致。

修复后三路展开：

```python
# canonical
mainline_sks.add(csk)
# related
for rsk in related_subject_keys_json:
    mainline_sks.add(str(rsk))
# branch (was missing!)
for bsk in branch_subject_keys_json:
    mainline_sks.add(str(bsk))
```

## 21.2 诊断增强

`post_market_decision_v2.diagnostics` 新增字段：

```json
{
  "active_mainline_count": 6,
  "active_subject_key_count": 31,
  "layer_c_subject_keys": ["9015778", "9065423", "9065632"],
  "mainline_filtered_subject_keys": ["9015778"],
  "missing_registry_subject_keys": ["9065423", "9065632"]
}
```

一眼可见：
- Layer C 输入池有哪些 subject
- 主线过滤通过了哪些
- 哪些因为没有 registry 记录被过滤

## 21.3 当前过滤效果

```text
Layer C 输入: 100 行, 3 个 subject
  → 9015778 (低空经济): 52 行 → PASS (已确认主线)
  → 9065423 (Token经济): filtered out (review_pending, 从未确认)
  → 9065632 (重组概念): filtered out (review_pending, 从未确认)

Strong Pool: 52 只
D1 候选: 20 只 (observe_only)
Focus Stocks: 0 (market_regime 判 no_trade, 正确)
```

## 21.4 关于 `focus_count = 0`

这不是 bug。`trade_mode = no_trade` 是 `MarketRegimeEngine` 判定的结果。此时 D1 只进入 `observe_only`，不生成正式次日关注股。这是交易风控的正确行为。

后续应单独排查 MarketRegimeEngine 对 2026-05-29 的判市逻辑，确认 no_trade 是否合理。但绝大多数交易日 `focus_count` 应该较低——只有主线明确 + 市场环境配合时才会有正式关注标的。

---

# 22. 已验证的完整链路（2026-05-29）

```text
┌─────────────────────────────────────────────────────┐
│ 事件采集层                                            │
│ theme_history_event (4/30 停止)                       │
│ + subject_history_staging (CDP DOM, 106 rows)         │
│ + event_subject_map + news_event (CDP DOM supp)       │
└──────────────────┬──────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────┐
│ MainlineDiscoveryFactContextBuilder                  │
│ - _build_candidates: 6 (cycle_judgement)             │
│ - _fetch_staging_subjects: 65 (CDP DOM)              │
│ - _fetch_event_rows: 4-source merge → 59 subjects    │
│ 输出: 65 candidates, 59 with events, full diagnostics│
└──────────────────┬──────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────┐
│ MainlineDiscoveryEngine                             │
│ - MainlineLogicChainBuilder (event_rows优先)         │
│ - MainlineMarketAcceptanceBuilder                   │
│ - MajorEventClassifier                              │
│ - MainlineNarrativeJudge (LLM, DeepSeek)            │
│ 输出: 2 Fast Line, 0 Slow Line, 5 rotation_hotspot  │
│      1 rejected, 0 logic_only, 0 market_noise       │
└──────────────────┬──────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────┐
│ AnalystReviewQueue + Frontend Confirmation           │
│ 8 items pending review                               │
│ - 电力运营 (major_event=97, Fast Line)               │
│ - PCB (major_event=92, Fast Line)                    │
│ - 6 others (rotation_hotspot/rejected)               │
└──────────────────┬──────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────┐
│ mainline_registry (6 confirmed, 31 subject_keys)     │
│ ActiveMainlineUniverseBuilder (dedup by canonical)   │
└──────────────────┬──────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────┐
│ PostMarketDecisionV2 (Layer C/D1)                   │
│ - 100 pool rows → 52 filtered (9015778 only)         │
│ - Strong Pool: 52, D1: 20 observe_only               │
│ - Focus: 0 (market_regime: no_trade)                 │
└─────────────────────────────────────────────────────┘
```

## 22.1 关键指标

| 指标 | 值 | 说明 |
|---|---|---|
| 候选题材 | 65 | 6 cycle_judgement + 59 staging |
| 有事件题材 | 59 | 4-source merge |
| logic_score > 0 | 59 | 事件数据成功注入 LogicChainBuilder |
| Fast Line 候选 | 2 | 电力运营(97), PCB(92) |
| 审核队列 | 8 | 待人工确认 |
| 已确认主线 | 6 | 经过去重清理 |
| active subject_keys | 31 | canonical + related + branch 展开 |
| Layer C 输出 | 52 只 | 仅已确认主线过滤 |
| D1 候选 | 20 只 | observe_only (no_trade) |

## 22.2 已验证的异常场景处理

| 场景 | 处理 | 状态 |
|---|---|---|
| jyhf_history 数据断档 (4/30后) | CDP DOM staging 补充 | ✅ |
| theme_master 无 subject_key 列 | 改用 tree/branch_subject_key 直查 | ✅ |
| 某事件源查询失败 | 异常静默返回空，不影响其他源 | ✅ |
| 旧架构主线未注册 | backfill 导入 6 条 | ✅ |
| registry 重复条目 | ActiveMainlineUniverseBuilder 去重 | ✅ |
| theme_name 显示为事件原文 | 移除 description fallback | ✅ |
| PDV2 未展开 branch keys | 补全三路展开 | ✅ |
| Layer C 过滤不可见 | diagnostics 完整暴露 | ✅ |

---

# 23. 前端主线确认页面

## 23.1 位置

`/realtime-collector` → Segmented Tab「主线确认」，与「新闻/题材待复核」同级。

## 23.2 功能

- **待确认** Tab：展示 `mainline_review_queue` 中 `review_status = 'pending'` 的条目
- **已确认** Tab：展示 `mainline_registry` 中所有 active confirmed mainlines
- 操作：确认 / 观察 / 拒绝 / 合并（合并到已有主线）
- 详情抽屉：展示完整 diagnostic、event chain、market evidence

## 23.3 后端 API

通过 BFF (`web_app_service`) 代理到 SPS：

- `GET /api/v2/mainline/review/items` — 审核队列
- `GET /api/v2/mainline/confirmed` — 已确认列表
- `POST /api/v2/mainline/review/decide` — 提交审核决定
- `POST /api/v2/mainline/confirmed/merge` — 合并主线

---

# 24. 已知待解决问题

## 24.1 Subject Key 规范化

CDP DOM 管线使用中文名作为 `subject_key`（如 "电力运营"），而旧架构使用数字 ID（如 "9013416"）。两者代表同一题材但 key 不同，导致注册表可能出现重复。需要建立 `subject_key_alias` 映射表或规范化层。

## 24.2 MarketRegimeEngine no_trade 验证

2026-05-29 判为 `no_trade`，需要单独排查判市逻辑是否过严。

## 24.3 旧架构 3 个未继承主线

`9065423`（Token经济）、`9065632`（重组概念）、`9059825` 在旧注册表中为 `review_pending` 状态，未被 backfill 导入。是否应按"事实主线"导入需人工判断。

## 24.4 人工确认后注册表重复防护

`_persist_review_queue` 只写入 `mainline_review_queue` 表。人工确认操作通过 BFF API 直接写入 `mainline_registry`。当前缺少「确认前检查 canonical_subject_key 是否已存在」的防护。建议在 BFF 的 confirm 端点增加去重检查。

## 24.5 前端确认页面的存量主线导入入口

建议在「已确认」子标签增加「导入存量主线」按钮，允许分析师手动录入老主线，避免每次依赖 backfill 脚本。
