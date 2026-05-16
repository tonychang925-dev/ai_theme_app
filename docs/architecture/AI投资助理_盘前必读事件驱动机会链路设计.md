# AI投资助理：实时新闻事件、题材匹配与盘前必读事件驱动机会链路设计

> 版本：v1.0  
> 日期：2026-05-15  
> 状态：设计稿  
> 适用项目：`tonychang925-dev/ai_theme_app`  
> 设计原则：基于现有 Redis Stream + ThemeProcessor + ThemeMatchEngine + DecisionExecutor 架构做业务串联，不从零重造新闻荐股系统。

---

## 1. 背景与目标

当前项目已经具备较完整的新闻事件处理与题材匹配主链路：

```text
新闻源
→ news_raw
→ stream:news:raw
→ news_stream_handler.py
→ news_raw 落库
→ news_stream_processor.py
→ ReliableDeepSeekParser / model_service
→ news_event
→ stream:events:structured
→ ThemeProcessor
→ ThemeService.match_event()
→ ThemeMatchEngine
→ stream:events:decision
→ DecisionExecutor
→ event_theme_map / theme_heat / unknown_event_pool / review_queue / theme_updates
```

这个链路已经被第二阶段架构文档定义为项目的题材匹配主链路，并且当前运行时 `ThemeMatchEngine` 已经按高精度离线裁决链路生产化，包括：

- Dense Recall
- Sparse Recall
- Feature Recall
- Fused Rerank
- Dynamic Top-K
- Direct-Hit Reserve
- Gate Evidence
- Final LLM Judge
- `MATCH / UNKNOWN / HUMAN_REVIEW` 三分支输出

本阶段的目标不是新增一套独立“新闻荐股系统”，而是将现有能力串联成完整业务闭环：

```text
结构化新闻事件
→ 本地题材匹配
→ 决策落库 / 决策流
→ matched_subject_key
→ 久赢恒丰题材股票映射再评估
→ 事件驱动股票机会
→ 盘前必读 draft/final 报告
```

最终目标是在每日 8:30 前形成一份可解释、可追溯、可迭代的“盘前必读”报告，用于汇总盘后、隔夜、早盘新闻事件对 A 股题材与股票机会的影响。

---

## 2. 核心澄清与边界

### 2.1 StockMatchEngine 的定位

`StockMatchEngine` 是移动端“零散新闻即时荐股”能力，主要服务场景是：

```text
用户手动输入一条新闻事件
→ 快速识别题材
→ 返回可能相关股票
```

它适合移动端临时查询，不应作为盘前必读主链路。

盘前必读主链路应基于：

```text
ThemeProcessor
→ ThemeService.match_event()
→ ThemeMatchEngine
→ DecisionExecutor
```

### 2.2 JYHF CDP 采集的定位

JYHF CDP 采集主要用于盘中同步久赢恒丰已经结构化分析过的题材事件，适合实时情报台与盘中事件跟踪。

但以下事件并不适合依赖 JYHF CDP：

- 盘后重大新闻
- 隔夜外围市场重大事件
- 海外科技、宏观、政策、商品价格变化
- 次日早盘需要提前消化的事件

这些事件更适合作为“盘前必读”的输入源，通过项目自身的新闻采集、LLM 结构化、ThemeMatchEngine 题材匹配链路处理。

### 2.3 CDP 生命周期已冻结

JYHF CDP 生命周期已经完成独立冻结，不应在本阶段改动：

```text
1. JyhfCdpManager 是 JYHF CDP 服务生命周期唯一管理者。
2. shell 脚本仅用于外部调试，不被 manager 调用。
3. Electron 不直接启动、不直接 kill 8095。
4. managed 才允许 killpg。
5. external 永不误杀。
6. force-stop 只用于诊断清理旧残留。
7. start API 必须确认 collector_running=true 才返回成功。
```

本阶段所有改造不得破坏 `docs/realtime/jyhf_cdp_lifecycle.md` 中定义的约束，也必须保持 `scripts/test_jyhf_cdp_lifecycle.sh` 回归测试通过。

---

## 3. 当前已确认的主链路

### 3.1 ThemeProcessor

文件：

```text
database_service/streams/handlers/theme_processor.py
```

当前 `ThemeProcessor` 虽然保留了 `normal / major / structured` 三类配置，但实际运行主路径已收敛为：

```text
stream:events:structured
```

关键逻辑：

```text
_process_message_structured()
  → _extract_structured_payload()
  → gateway.get_news_event_for_match(event_id)
  → theme_service.match_event(event_row, database_gateway=self.gateway)
  → _build_structured_decision()
  → _publish_decision()
  → stream:events:decision
```

这说明主链路已经实现：

```text
结构化事件
→ 本地题材匹配
→ 决策流输出
```

### 3.2 ThemeService

文件：

```text
theme_service/services/theme_service.py
```

`ThemeService.set_database_gateway()` 会初始化：

```text
ThemeProfileRepository
ThemeMatchEngine
```

`ThemeService.match_event()` 负责：

```text
event_row
→ build_theme_match_request()
→ ThemeMatchEngine.match_event(request)
→ ThemeDecisionEnvelope.to_dict()
```

### 3.3 ThemeMatchEngine

文件：

```text
theme_service/services/theme_match_engine.py
```

`ThemeMatchEngine.match_event()` 是线上运行时题材匹配内核，主流程：

```text
ThemeMatchRequest
→ Dense Recall
→ Sparse Recall
→ RRF Merge
→ Feature Recall
→ Merge Recall
→ Rerank
→ Dynamic Top-K
→ Direct-Hit Reserve
→ Gate Evidence
→ Final LLM Judge / Rule-only Decision
→ ThemeDecisionEnvelope
```

输出结果：

```text
MATCH
UNKNOWN
HUMAN_REVIEW
```

并包含：

```text
matched_subject_key
matched_theme_name
matched_theme_id
confidence
reason_code
review_required
audit.top_candidates
audit.best_evidence
```

### 3.4 stream:events:decision

`theme_processor.py` 会把 structured 路径结果发布到：

```text
stream:events:decision
```

其中 structured decision 包含：

```text
decision_id
decision_type
action
operations
event_id
trace_id
event_type
event_title
timestamp
processor
event_data
confidence
reason
source
match_result
theme_data
```

这正是盘前必读聚合器的最佳输入。

---

## 4. 目标架构

### 4.1 整体架构图

```text
AKShare / 财联社 / 隔夜新闻源 / JYHF CDP
        ↓
news_raw / Redis stream:news:raw
        ↓
news_stream_processor.py
        ↓
ReliableDeepSeekParser / model_service
        ↓
news_event
        ↓
stream:events:structured
        ↓
ThemeProcessor
        ↓
ThemeService.match_event()
        ↓
ThemeMatchEngine
        ↓
stream:events:decision
        ↓
DecisionExecutor
        ↓
event_theme_map / theme_heat / unknown_event_pool / review_queue
        ↓
PreMarketBriefBuilder
        ↓
EventDrivenOpportunityBuilder
        ↓
pre_market_brief_snapshot
        ↓
盘前必读页面
```

### 4.2 新增模块职责

#### 4.2.1 PreMarketBriefBuilder

建议路径：

```text
stock_processing_service/application/services/pre_market_brief_builder.py
```

职责：

```text
1. 读取已完成题材匹配的事件。
2. 筛选 MATCH / HUMAN_REVIEW / UNKNOWN。
3. 按 trade_date、时间窗口、source、subject_key 聚合。
4. 生成盘前必读 draft payload。
5. 管理 draft/final 状态。
6. 为前端 API 提供可展示结构。
```

输入优先级：

```text
第一优先级：DecisionExecutor 落库结果
第二优先级：stream:events:decision 扫描结果
```

#### 4.2.2 EventDrivenOpportunityBuilder

建议路径：

```text
stock_processing_service/application/services/event_driven_opportunity_builder.py
```

职责：

```text
1. 输入 matched_subject_key + 事件组。
2. 读取久赢恒丰题材股票映射。
3. 叠加强势池、弱转强池、龙头池、题材周期数据。
4. 对候选股票进行二次评估。
5. 输出 event_driven_opportunities。
```

它不做新闻结构化，不做题材匹配，只做：

```text
题材 → 股票池 → 交易机会再评估
```

---

## 5. 输入数据源设计

### 5.1 推荐输入源

盘前必读应优先从已完成题材匹配的结果读取，而不是从原始新闻流读取。

推荐顺序：

```text
1. event_theme_map + news_event + theme_heat 等落库结果
2. stream:events:decision 中的 structured decision
3. 仅在调试或补偿场景下读取 stream:events:structured
```

### 5.2 不建议直接读取原始新闻流

不建议从以下源直接生成盘前必读：

```text
stream:news:raw
原始 akshare 新闻
未结构化的临时文本
```

原因：

```text
1. 原始新闻噪声大。
2. 尚未经过 LLM 结构化。
3. 尚未经过本地题材匹配。
4. 不具备 ThemeDecisionEnvelope 审计信息。
5. 会绕开第二阶段题材知识中台架构。
```

---

## 6. 事件筛选规则

### 6.1 MATCH 事件

进入盘前必读主报告的事件应满足：

```text
source = structured_theme_match
match_result.decision = MATCH
matched_subject_key 非空
confidence >= 0.65
review_required = false 优先
```

进入：

```text
sections.major_events
sections.matched_themes
sections.event_driven_opportunities
```

### 6.2 HUMAN_REVIEW 事件

`HUMAN_REVIEW` 不进入 A/B 股票机会，建议进入：

```text
sections.review_events
```

用途：

```text
1. 提醒用户存在高影响但裁决不稳定的事件。
2. 作为人工复核入口。
3. 不直接生成股票推荐。
```

### 6.3 UNKNOWN 事件

`UNKNOWN` 不进入盘前主报告，建议进入：

```text
unknown_event_pool
sections.unknown_watch，可选展示
```

用途：

```text
1. 新题材观察。
2. 聚类成团。
3. 人审后生成新题材草案。
```

---

## 7. 盘前必读快照表设计

如果当前没有独立盘前快照表，建议新增：

```sql
CREATE TABLE IF NOT EXISTS pre_market_brief_snapshot (
    trade_date date PRIMARY KEY,
    status varchar(20) NOT NULL DEFAULT 'draft',
    snapshot_version varchar(50) NOT NULL DEFAULT 'pre_market_brief.v1',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    generated_at timestamptz,
    finalized_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

### 7.1 状态字段

```text
draft    盘前持续迭代中
final    8:30 前后冻结
stale    数据不完整或生成异常
```

### 7.2 payload 建议结构

```json
{
  "version": "pre_market_brief.v1",
  "trade_date": "2026-05-16",
  "status": "draft",
  "last_updated_at": "2026-05-16T07:45:00+08:00",
  "sections": {
    "overnight_global": [],
    "major_events": [],
    "matched_themes": [],
    "event_driven_opportunities": [],
    "weak_to_strong_watch": [],
    "review_events": [],
    "unknown_watch": [],
    "risk_alerts": []
  },
  "diagnostics": {
    "source": "event_theme_map_or_stream_events_decision",
    "event_count": 0,
    "matched_event_count": 0,
    "theme_count": 0,
    "opportunity_count": 0,
    "last_rebuild_at": "2026-05-16T07:45:00+08:00"
  }
}
```

---

## 8. 盘前必读 draft/final 迭代机制

### 8.1 时间窗口

```text
T 日盘后 15:30-22:00
→ 吸收盘后重大事件、题材周期、复盘结果、强势池、弱转强池。

隔夜 22:00-07:00
→ 吸收外围市场、海外科技、宏观政策、商品、地缘事件。

次日 07:00-08:20
→ 吸收早间新闻、公告、政策、机构观点、JYHF 早盘信息。

08:20-08:30
→ 最后一轮重算事件驱动机会。

08:30
→ finalize，冻结 final。
```

### 8.2 8:30 后策略

8:30 后默认不覆盖主报告。

如果发生重大突发事件，可进入：

```text
sections.breaking_updates
```

但不应反复重写 `final` 主体内容。

---

## 9. EventDrivenOpportunityBuilder 设计

### 9.1 输入

```text
matched_subject_key
matched_theme_name
event_group
ThemeDecisionEnvelope.confidence
ThemeDecisionEnvelope.audit
```

### 9.2 股票候选来源

按优先级读取：

```text
1. theme_stock_map
2. subject_stock_staging / subject_stock_map
3. subject_children_staging
4. subject_child_stock_reason
5. theme_leader_candidate
6. strong_stock_watch_pool
7. weak_to_strong_candidate_pool
8. stocks / stock_profile_ext
```

### 9.3 评分因子

```text
event_theme_score       事件与题材匹配置信度
source_quality_score    事件来源质量
theme_heat_score        题材热度
theme_cycle_score       题材周期 / 主线强度
jyhf_relation_score     久赢恒丰题材-股票映射强度
leader_score            龙头 / 核心股程度
strong_watch_score      是否在强势追踪池
w2s_score               是否在弱转强候选池
risk_penalty            高位、退潮、负面事件、冲突题材风险
```

### 9.4 分级规则

```text
A档：
高置信事件 + 主线题材 + JYHF 核心映射股 + 强势池/龙头池支撑。

B档：
高置信事件 + 题材映射成立 + 有股票映射，但市场强度一般。

C档：
题材匹配成立，但股票机会较弱，仅观察。
```

### 9.5 输出结构

```json
{
  "subject_key": "9019807",
  "theme_name": "卫星互联网",
  "event_count": 2,
  "latest_event_title": "隔夜卫星互联网重大事件",
  "event_summary": "事件摘要...",
  "theme_confidence": 0.86,
  "stocks": [
    {
      "stock_id": "002361.SZ",
      "stock_name": "神剑股份",
      "level": "A",
      "score": 86.5,
      "reason": "JYHF题材映射核心股，强势池活跃，事件催化匹配",
      "risk": "需观察竞价承接",
      "evidence": {
        "jyhf_relation_type": "core",
        "strong_watch": true,
        "weak_to_strong": false,
        "leader_candidate": true
      }
    }
  ]
}
```

---

## 10. API 设计

建议新增：

```text
GET  /api/v1/pre_market_brief?trade_date=YYYY-MM-DD
POST /api/v1/pre_market_brief/rebuild
POST /api/v1/pre_market_brief/finalize
```

### 10.1 GET /api/v1/pre_market_brief

用途：读取盘前必读快照。

参数：

```text
trade_date，可选，默认最近交易日或当前交易日
```

返回：

```json
{
  "ok": true,
  "trade_date": "2026-05-16",
  "status": "draft",
  "payload": {}
}
```

### 10.2 POST /api/v1/pre_market_brief/rebuild

用途：手动或定时重建 draft。

请求：

```json
{
  "trade_date": "2026-05-16",
  "source": "db_or_stream",
  "limit": 200,
  "dry_run": false
}
```

行为：

```text
1. 读取 matched events。
2. 过滤 MATCH / HUMAN_REVIEW / UNKNOWN。
3. 聚合 matched_themes。
4. 构建 event_driven_opportunities。
5. 写入 pre_market_brief_snapshot.status=draft。
```

### 10.3 POST /api/v1/pre_market_brief/finalize

用途：冻结最终版。

请求：

```json
{
  "trade_date": "2026-05-16",
  "force": false
}
```

行为：

```text
1. 如果 status=final 且 force=false，不覆盖。
2. 最后一轮 rebuild。
3. status 改为 final。
4. 写 finalized_at。
```

---

## 11. 前端展示设计

盘前必读页面建议模块：

```text
盘前必读
├── 生成状态：draft/final，最后更新时间
├── 一、隔夜重大事件
├── 二、今日重点题材
├── 三、事件驱动机会
├── 四、弱转强观察
├── 五、待复核事件
└── 六、风险提示
```

### 11.1 事件驱动机会卡片

展示结构：

```text
【题材】卫星互联网
事件：隔夜卫星互联网重大事件
匹配置信度：0.86
题材状态：主线维持 / 强度 78

推荐股票：
1. 神剑股份 A档 86.5分
   理由：JYHF题材映射核心股，强势池活跃，事件催化匹配。
   风险：需观察竞价承接。

2. xxx B档 75.2分
   理由：题材映射成立，但市场强度一般。
```

### 11.2 待复核事件

展示：

```text
高影响但裁决不稳定事件
→ matched candidates
→ confidence
→ review_required=true
```

不直接给股票机会。

---

## 12. 实施阶段

### Phase 0：核查 DecisionExecutor

目标：确认以下链路是否已经完整：

```text
stream:events:decision
→ DecisionExecutor
→ event_theme_map
→ theme_heat
→ unknown_event_pool
→ review_queue
```

核查项：

```text
1. DecisionExecutor 是否存在并运行。
2. stream:events:decision 是否有消费者组。
3. MATCH 是否落库 event_theme_map。
4. UNKNOWN 是否进入 unknown_event_pool。
5. HUMAN_REVIEW 是否进入 review_queue。
6. theme_heat 是否更新。
```

如果完整，后续从 DB 聚合；如果不完整，MVP 先从 decision stream 聚合。

### Phase 1：PreMarketBriefBuilder MVP

目标：

```text
已匹配事件 → matched_themes / major_events → pre_market_brief_snapshot
```

不做股票机会。

### Phase 2：EventDrivenOpportunityBuilder

目标：

```text
matched_subject_key
→ JYHF 股票映射
→ 强势池 / 弱转强池 / 龙头池 / 周期状态
→ event_driven_opportunities
```

### Phase 3：API 与页面

新增：

```text
GET /api/v1/pre_market_brief
POST /api/v1/pre_market_brief/rebuild
POST /api/v1/pre_market_brief/finalize
```

前端盘前必读页面展示 draft/final 与事件驱动机会。

### Phase 4：自动迭代

先使用定时 rebuild：

```text
每 5 分钟扫描最新 decision / DB 匹配结果
→ 更新 draft
```

后续再接入 decision stream 增量消费者。

### Phase 5：8:30 finalize

实现：

```text
08:20-08:30 最后一轮 rebuild
08:30 finalize
08:30 后默认只读 final
```

---

## 13. 验收标准

### 13.1 链路验收

```text
1. 写入一条 stream:events:structured 测试事件。
2. ThemeProcessor 消费并生成 stream:events:decision。
3. PreMarketBriefBuilder rebuild。
4. pre_market_brief_snapshot 生成 matched_themes。
5. EventDrivenOpportunityBuilder 生成 event_driven_opportunities。
6. GET /api/v1/pre_market_brief 返回完整 payload。
7. 前端盘前必读页面可展示事件驱动机会。
```

### 13.2 质量验收

```text
1. 只处理 MATCH 事件。
2. confidence 低于阈值不进入事件驱动机会。
3. HUMAN_REVIEW 只进入待复核，不荐股。
4. UNKNOWN 不进入主报告。
5. 同一 event_id 不重复进入报告。
6. 同一 subject_key 下多事件合并。
7. 同一股票在单日报告中不刷屏。
```

### 13.3 稳定性验收

```text
1. rebuild 可重复执行且幂等。
2. final 后默认不覆盖。
3. dry_run 不写库。
4. 决策流为空时返回空报告而不是报错。
5. 数据源异常时 status=stale 并记录 diagnostics。
```

---

## 14. 风险与注意事项

### 14.1 不要绕过主链路

禁止：

```text
原始新闻 → StockMatchEngine → 盘前必读
```

原因：

```text
1. 绕开 ThemeMatchEngine 主链路。
2. 绕开 DecisionExecutor。
3. 无法复用 MATCH / UNKNOWN / HUMAN_REVIEW 分支。
4. 审计与题材知识中台不一致。
```

### 14.2 不要直接消费 raw stream

盘前必读应消费匹配结果，不消费原始新闻。

### 14.3 不要改 CDP 生命周期

CDP 生命周期已冻结，本阶段只允许读取 CDP 进入主链后的事件结果。

### 14.4 先 DB 后 Stream

长期建议从 DecisionExecutor 落库结果聚合，而不是长期依赖 Redis Stream 历史扫描。

Redis Stream 更适合实时增量，不适合长期作为报告真源。

---

## 15. 给 Claude / Codex 的实施指令模板

```text
请基于现有第二阶段题材匹配架构，实现“盘前必读：事件驱动机会”链路。

核心约束：
1. 不使用 StockMatchEngine 作为盘前必读主链路。
2. 不重新消费原始新闻流。
3. 不改 JYHF CDP 生命周期。
4. 主链路必须基于：
   stream:events:structured
   → ThemeProcessor
   → ThemeService.match_event()
   → ThemeMatchEngine
   → stream:events:decision
   → DecisionExecutor
5. 盘前必读应接在 stream:events:decision 或 DecisionExecutor 落库结果之后。

第一步先核查：
1. DecisionExecutor 是否存在并运行。
2. stream:events:decision 是否被消费。
3. MATCH 是否已落库到 event_theme_map。
4. UNKNOWN 是否进入 unknown_event_pool。
5. HUMAN_REVIEW 是否进入 review_queue。
6. theme_heat 是否更新。

如果落库链路完整：
- PreMarketBriefBuilder 从数据库读取事件匹配结果。

如果落库链路不完整：
- MVP 先从 stream:events:decision 扫描 MATCH 事件生成 pre_market_brief_snapshot。
- payload.diagnostics.source 标记为 decision_stream。

新增能力：
1. pre_market_brief_snapshot
   - trade_date
   - status draft/final
   - payload jsonb
2. PreMarketBriefBuilder
   - 聚合 MATCH 事件
   - 按 matched_subject_key 分组
   - 生成 matched_themes / major_events
3. EventDrivenOpportunityBuilder
   - 输入 matched_subject_key
   - 读取 theme_stock_map / strong_stock_watch_pool / weak_to_strong_candidate_pool / theme_leader_candidate / theme_cycle_judgement_v2
   - 输出 event_driven_opportunities
4. API：
   - GET /api/v1/pre_market_brief
   - POST /api/v1/pre_market_brief/rebuild
   - POST /api/v1/pre_market_brief/finalize
5. 8:30 final 机制：
   - 8:30 前 status=draft，可反复 rebuild
   - 8:30 后 status=final，默认不覆盖
6. smoke 测试：
   - 写入一条 structured event
   - ThemeProcessor 生成 decision
   - rebuild 盘前必读
   - 校验 matched_themes 与 event_driven_opportunities
```

---

## 16. 最终结论

本阶段的正确方向是：

```text
不是新增一套新闻荐股系统，
而是把第二阶段题材匹配主链路的输出，转化为盘前必读的业务报告能力。
```

最终系统分工应固定为：

```text
ThemeProcessor
→ 负责 structured event 消费与决策流发布

ThemeMatchEngine
→ 负责事件与本地题材的高精度匹配

DecisionExecutor
→ 负责 MATCH / UNKNOWN / HUMAN_REVIEW 的落库与业务分叉

PreMarketBriefBuilder
→ 负责已匹配事件聚合，生成盘前必读 draft/final

EventDrivenOpportunityBuilder
→ 负责 matched_subject_key 到股票机会的再评估

StockMatchEngine
→ 保留为移动端手动新闻即时荐股工具
```

盘前必读应成为题材知识中台的下游产品输出，而不是独立于主链路之外的新系统。
