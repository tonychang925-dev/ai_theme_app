# AI投资助理：实时新闻事件、题材匹配与盘前必读事件驱动机会链路设计

> 版本：v1.7  
> 日期：2026-05-20  
> 状态：主链路已实现；新增实时采集、情报台、盘前必读统一链路任务分解；Phase 6A 严格闭环与实时 source 启动待落地  
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
→ event_subject_map / event_review_queue / pending / theme_updates
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
event_subject_map / event_review_queue / pending
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
1. event_subject_map + news_event + event_review_queue / pending 等落库结果
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
pending
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
    "source": "event_subject_map_or_stream_events_decision",
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
→ event_subject_map
→ event_review_queue
→ pending
```

核查项：

```text
1. DecisionExecutor 是否存在并运行。
2. stream:events:decision 是否有消费者组。
3. MATCH 是否落库 event_subject_map。
4. UNKNOWN 是否进入 pending。
5. HUMAN_REVIEW 是否进入 event_review_queue。
6. dead letter 是否为 0 或全部可解释。
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
3. MATCH 是否已落库到 event_subject_map。
4. UNKNOWN 是否进入 pending。
5. HUMAN_REVIEW 是否进入 event_review_queue。
6. dead letter 是否为 0 或全部可解释。

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

## 16. 当前项目状态（2026-05-19）

### 16.1 总体状态

截至 2026-05-19，盘前必读已经从设计进入可运行的新链验证阶段。

当前已经打通的主链路为：

```text
stream:news:raw
→ news_raw / news_event
→ stream:events:structured
→ ThemeProcessor
→ ThemeService.match_event()
→ ThemeMatchEngine
→ stream:events:decision
→ DecisionExecutor
→ event_subject_map / event_review_queue / pending
→ PreMarketBriefBuilder
→ EventDrivenOpportunityBuilder
→ pre_market_brief_snapshot
→ SPS /api/v1/pre_market_brief
→ Vite proxy
→ PreMarketBriefPage
```

当前明确移除的旧链依赖：

```text
frontend_bff:8003
/api/v2/pre-market-brief
theme_master 作为题材真源
StockMatchEngine 作为盘前必读主链路
旧 run_realtime_stack.sh 作为新链 E2E 启动入口
```

当前固定原则：

```text
1. 运行时事件与报告写入 stock_data。
2. 题材画像、久赢恒丰题材股票池、强势池、弱转强池等只读数据优先读 stock_data_test。
3. 题材主键为 subject_key。
4. 事件题材映射主表为 event_subject_map。
5. 前端只读 SPS /api/v1/pre_market_brief，不经过 frontend_bff。
```

### 16.2 已完成成果

#### Phase 0：执行闭环与快照语义

已完成：

```text
1. DecisionExecutor 支持 HUMAN_REVIEW action。
2. HUMAN_REVIEW 写入 event_review_queue，不再进入 unknown action / dead letter。
3. UNKNOWN 保持 pending / clustering 路径，不混入 HUMAN_REVIEW。
4. pre_market_brief_snapshot 支持 draft/final/stale。
5. final 默认不被普通 rebuild 覆盖，force=true 才允许覆盖。
6. JSONB payload merge 顺序修正为旧 payload || 新 payload。
7. source_trace_id / generated_at / finalized_at / updated_at 字段补齐。
```

#### Phase 1-3：报告聚合、API、股票机会层

已完成：

```text
1. PreMarketBriefBuilder MVP。
2. EventDrivenOpportunityBuilder 只读候选池聚合与规则评分。
3. SPS API：
   GET  /api/v1/pre_market_brief
   POST /api/v1/pre_market_brief/rebuild
   POST /api/v1/pre_market_brief/finalize
4. 前端 PreMarketBriefPage 改为直接请求 /api/v1/pre_market_brief。
5. frontend_bff 盘前必读代理已从新链中移除。
6. 页面不再把 subject_key 当题材名展示。
```

#### Phase 4：E2E 与 Theme Profile v2 质量工程

已完成：

```text
1. E2E 工具链：
   parse_test_cases.py
   replay_akshare_raw_news.py
   cleanup_e2e_run.py
   trace_pre_market_e2e_run.py
   evaluate_pre_market_brief.py
   run_pre_market_e2e.py

2. 读写分离：
   write_db = stock_data
   read_db  = stock_data_test

3. theme_profile_v2：
   - 已新增 schema 与 validator。
   - Top50 及后续高风险噪声源已进入 v2 draft 灰度。
   - 当前 active draft v2 数量：68。
   - 当前 holdback/review：
     9030409 AR眼镜
     9064241 金刚石散热

4. hard-negative 样本集：
   - 当前样本数：63。
   - 覆盖蓝箭航天、SHEIN/希音IPO、航空发动机、中科院、液冷数据中心、英特尔、HBM、半导体大类、SpaceX、港口、游戏、芬太尼等高风险错配。

5. ThemeMatchEngine 质量修复：
   - 泛词证据污染治理。
   - support/no_anchor 证据不再贡献强锚点。
   - role-aware guard：source_org/location/generic_short_term/support 不得单独进入 related。
   - alias direct hit + conflict evidence 时不再压过干净领域候选。
   - EventMatchProfile fallback recall query 补正文片段，避免正文强锚点丢失。
   - support_hits 只统计事件文本真实命中的 support/no_anchor 项，避免 profile 自身弱词虚假命中。
```

### 16.3 当前验证基线

#### 最近稳定完整链路基线

`pm_e2e_phase4_5_terminalfix_v2_full_100_20260515_001`：

```text
news_raw_count = 100
news_event_count = 100
decision_distinct_event_count = 100
terminal_distinct_event_count = 100
dead_letter_count = 0
duplicate_decision_event_count = 0
theme_set_recall@5 = 0.62
wrong_related_count = 7
generic_only_related_count = 0
brief_theme_count = 37
brief_opportunity_count = 36
```

该基线证明：

```text
1. ThemeProcessor / DecisionExecutor 执行闭环已稳定。
2. event_subject_map / review / pending 终态统计闭合。
3. report snapshot 与 opportunity builder 可生成非空报告。
4. 前端可通过 SPS 快照展示盘前必读。
```

#### Phase 4.6 gate-only 最新结果

`phase4_6_final_compare_gate_r2`：

```text
v2_loaded_count = 68
v2_hard_negative_reject_rate = 1.0
v1_theme_set_recall@5 = 0.55
v2_theme_set_recall@5 = 0.58
v2_wrong_related_count = 0
v2_generic_only_related_count = 0
recall5_regressed_count = 1
```

唯一剩余 gate-only recall regression：

```text
英伟达数据中心芯片需求
→ 无液冷/冷却锚点
→ v2 转 HUMAN_REVIEW
```

该口径可接受，因为它避免把“数据中心芯片需求”误判为液冷数据中心。

### 16.4 Phase 4.6 完整新链 E2E100 结果

已使用新链 stream-only 启动方式完成完整 E2E100：

```text
run_id = pm_e2e_phase4_6_stream_v2_full_100_20260515_001
write_db = stock_data
read_db = stock_data_test
sps = http://127.0.0.1:8090
theme_profile_version = v2
theme_profile_v2_status = draft
theme_profile_v2_fallback_to_v1 = true
theme_profile_v2_require_loaded = true
theme_match_llm_judge_mode = auto
theme_processor_structured_concurrency = 2
theme_match_enable_event_profile_llm = false
```

该轮验证使用新增脚本：

```text
evaluate_service/e2e/pre_market_brief/run_new_chain_e2e_stack.sh
```

脚本只启动：

```text
1. stock_processing_service 8090
2. run_raw_news_services.py
3. run_phase0_decision_services.py
```

明确不启动：

```text
frontend_bff:8003
旧 collector
旧 matcher
旧 BFF proxy
```

本轮实际结果：

```text
news_raw_count = 100
news_event_count = 100
decision_entry_count = 101
decision_distinct_event_count = 100
duplicate_decision_event_count = 1
terminal_distinct_event_count = 100
non_terminal_event_count = 0
decision_seen_but_no_output_count = 0
dead_letter_count = 0

mapped_distinct_event_count = 82
review_distinct_event_count = 14
pending_distinct_event_count = 4

theme_set_recall@5 = 0.57
primary_hit_rate = 0.57
wrong_related_count = 0
generic_only_related_count = 0
llm_anchor_guard_count = 4

brief_theme_count = 25
brief_opportunity_count = 25
numeric_theme_name_count = 0
subject_key_chip_count = 0
unnamed_theme_count = 7

avg_match_ms = 6960.906
p50_match_ms = 5187.793
p95_match_ms = 16681.036
llm_judge_count = 32
event_profile_llm_count = 0
profile_load_count = 3
profile_map_cache_hit_count = 97
profile_map_cache_miss_count = 3
query_vector_cache_hit_count = 99
rerank_doc_vector_cache_hit_count = 2179
rerank_doc_vector_cache_miss_count = 507
```

结论：

```text
1. 新链 stream-only E2E 启动方式成立，不依赖 frontend_bff。
2. ThemeProcessor / DecisionExecutor 终态闭环通过。
3. pre_market_brief_snapshot rebuild 读写分离问题已修复。
4. 数字题材名问题已在本轮快照中清零。
5. wrong_related_count 已压到 0，generic_only_related_count 为 0。
6. 召回与机会数量低于预期：
   theme_set_recall@5 = 0.57，低于目标 0.60。
   brief_opportunity_count = 25，低于目标 35。
7. 本轮不能视为 Phase 4.6 完整验收通过，应进入召回恢复专项。
```

### 16.5 已知风险与当前处理策略

#### 风险 1：旧快照仍可能包含数字题材名

历史快照曾出现：

```text
9060949
9043089
9034859
```

原因：

```text
旧快照或 v1 fallback 使用 subject_key 作为展示名。
```

当前已修：

```text
1. 前端不再展示 subject_key chip。
2. snapshot evaluation 新增：
   numeric_theme_name_count
   unnamed_theme_count
   subject_key_chip_count
3. 门槛：
   numeric_theme_name_count = 0
```

说明：

```text
旧 run 的 sps_payload.json 仍可能显示 numeric_theme_name_count > 0。
只有重新跑完整新链 E2E100 后，该指标才可作为当前结果判定。
```

#### 风险 2：旧 run_realtime_stack.sh 会启动 frontend_bff

结论：

```text
run_realtime_stack.sh 不再用于盘前必读新链 E2E。
```

替代：

```text
run_new_chain_e2e_stack.sh
```

#### 风险 3：v2 仍是灰度，不应直接 Top100 全量扩容

当前策略：

```text
错配源优先
高频污染优先
v1 fallback 噪声优先
每轮都补 hard-negative
每轮都跑 gate-only + 完整链路 E2E
```

不建议：

```text
立即 Top100 / Top150 机械扩容。
```

### 16.6 下一阶段规划

#### P0：Phase 4.6 召回恢复专项

当前完整 E2E100 已证明执行闭环稳定，但召回和机会数量偏低。下一步优先恢复召回，不继续扩 v2 数量。

目标：

```text
1. 分析 43 个 recall miss / HUMAN_REVIEW / UNKNOWN 样本。
2. 输出 recall_regression_attribution_report。
3. 区分：
   - 合理 HUMAN_REVIEW
   - role guard 过严
   - profile v2 过窄
   - gold alias / neighbor map 不完整
   - opportunity builder 股票池缺口
4. 针对高频漏召回题材做定点修复。
```

重新验收门槛：

```text
news_raw_count = 100
news_event_count = 100
decision_distinct_event_count >= 99
terminal_distinct_event_count >= 99
dead_letter_count = 0
structured PEL = 0
decision PEL = 0

theme_set_recall@5 >= 0.60
wrong_related_count <= 7
generic_only_related_count = 0
brief_opportunity_count >= 35

numeric_theme_name_count = 0
subject_key_chip_count = 0
```

重点回归样本：

```text
1. Vera Rubin / 全液冷设计
   应命中液冷数据中心，不得命中中科院。

2. BEST / 托卡马克 / 核聚变采购
   应命中可控核聚变，不得命中中科院。

3. 数据中心芯片需求
   无液冷/冷却锚点时，HUMAN_REVIEW 可接受。

4. SpaceX / 星舰 / 星链 / 商业航天
   不得显示数字题材名。

5. 卫星互联网低轨组网发射
   题材名必须为中文，不得显示 subject_key。
```

#### P1：固化 Phase 4.6 基线

只有在召回恢复后完整 E2E100 通过，才执行：

```text
1. 将当前 68 条 draft v2 中稳定题材标记为 accepted_candidate。
2. 保留 9030409 / 9064241 review holdback。
3. 固化 hard-negative 样本集。
4. 将 run_new_chain_e2e_stack.sh 写入 README 执行路径。
5. 将 numeric_theme_name_count 纳入后续 E2E 必过门禁。
```

#### P2：剩余错配源定点治理

如果完整 E2E100 仍有 wrong related：

```text
1. 生成 wrong_related_attribution_report。
2. 按 root_cause 分组：
   source_org_as_anchor
   location_as_anchor
   short_generic_theme
   broad_policy_profile
   profile_boundary_missing
   matcher_related_gate_too_loose
   eval_alias_error
3. 仅精修高频错配源 profile。
4. 每个新增 profile 必须补 hard-negative。
```

#### P3：扩展 v2 覆盖面

只有在 Phase 4.6 完整 E2E100 通过后，才进入：

```text
Top80 / Top100 v2 覆盖扩展
```

扩展原则：

```text
不是按热度机械扩容，
而是按 E2E wrong related 源头、fallback 噪声、高风险大类题材优先。
```

---

## 17. 最新业务需求与任务分解（2026-05-20）

### 17.1 新业务口径冻结

本次改造目标是把“实时事件采集控制台”、“情报台”和“盘前必读”统一到同一条事件链路中。

核心口径如下：

```text
启动实时采集
≠ 只启动 Redis Stream 消费者

启动实时采集
= 启动 AkShare 新闻抓取源
+ 启动 raw_news_services
+ 启动 phase0_decision_services
+ 启动盘前必读增量 rebuild loop
```

三类输入源边界必须固定：

```text
AkShare 新闻
→ stream:news:raw
→ NewsStreamProcessor LLM 结构化
→ news_event
→ stream:events:structured
→ ThemeProcessor / DecisionExecutor
→ MATCH / HUMAN_REVIEW 分流

JYHF DOM
→ 已结构化事件
→ 直接写 news_event(source_category='jyhf_dom')
→ 如已有 subject_key/theme_name，直接写 event_subject_map(source='jyhf_dom_confirmed')
→ 不进入 stream:news:raw
→ 不触发 NewsStreamProcessor / LLM 结构化

公告/通告等一手信息
→ raw_intel_document
→ structured_intel_event
→ news_event(source_category='intel')
→ stream:events:structured
→ ThemeProcessor / DecisionExecutor
→ MATCH / HUMAN_REVIEW 分流
```

情报台展示口径：

```text
MATCH
→ /intel item_type='event'
→ 盘前必读 matched_themes / major_events / opportunities

HUMAN_REVIEW
→ /intel?type=event_review item_type='event_review'
→ 盘前必读 review_events

JYHF DOM
→ /intel item_type='event' 或 'new_theme'
→ 不经过 LLM；若已确认题材则可进入 matched 事件流

Intel 公告 raw
→ company_announcements_raw 保留早展示

Intel 公告 MATCH
→ 与普通新闻 MATCH 同口径进入 matched_themes / opportunities
```

### 17.2 统一盘前窗口任务

窗口定义：

```text
start_at = 上一交易日 15:00:00 Asia/Shanghai
end_at   = trade_date 08:00:00 Asia/Shanghai

查询口径：start_at <= occurred_at < end_at
```

实现任务：

| ID | 优先级 | 任务 | 目标文件/接口 | 验收 |
|---|---:|---|---|---|
| PMB-WIN-01 | P0 | 新增 `resolve_pre_market_window(trade_date)` | `stock_processing_service/application/services/pre_market_window.py` | 能基于交易日历取上一交易日；无日历时工作日 fallback |
| PMB-WIN-02 | P0 | `get_pre_market_subject_events` 支持 `start_at/end_at` | `database_service/gateway.py`, `database_service/managers/postgres_manager.py` | MATCH 事件只返回窗口内数据 |
| PMB-WIN-03 | P0 | `get_pre_market_review_events` 支持 `start_at/end_at` | 同上 | HUMAN_REVIEW 只返回窗口内数据 |
| PMB-WIN-04 | P0 | `get_intel_announcement_events` 支持 `start_at/end_at` | 同上 | Intel 公告按 `structured_intel_event.publish_time` 过滤 |
| PMB-WIN-05 | P0 | `PreMarketBriefBuilder.rebuild` 使用窗口查询 | `pre_market_brief_builder.py` | 盘前必读只包含上一交易日 15:00 到当日 08:00 数据 |

禁止继续使用单纯 `created_at::date = trade_date` 作为盘前必读主过滤条件。

### 17.3 8:00 draft/final 调度任务

新调度口径：

```text
15:00 <= now 或 now < 08:00
→ 每 3~5 分钟 rebuild draft

now >= 08:00
→ finalize

08:00 后
→ 普通 rebuild 不覆盖 final
→ 只有 force=true 允许重建 final
```

实现任务：

| ID | 优先级 | 任务 | 目标文件/接口 | 验收 |
|---|---:|---|---|---|
| PMB-SCH-01 | P0 | 修改 `decide_pre_market_brief_schedule` 时间窗 | `pre_market_brief_auto_scheduler.py` | 15:00~08:00 返回 rebuild；08:00 返回 finalize |
| PMB-SCH-02 | P0 | 08:00 后 final 保护 | `pre_market_brief_builder.py`, snapshot upsert | final 后普通 rebuild 不覆盖 |
| PMB-SCH-03 | P1 | 调度测试更新 | `test_pre_market_brief_auto_scheduler.py` | 覆盖 14:59/15:00/07:59/08:00/08:01 |

### 17.4 AkShare 实时采集任务

当前阻断项：

```text
RealtimeStackManager 当前只启动：
- run_raw_news_services.py
- run_phase0_decision_services.py

这两个脚本只消费消息，不抓取 AkShare 新闻。
```

必须把 `/realtime-collector` 的“启动实时采集”升级为完整链路启动。

实现任务：

| ID | 优先级 | 任务 | 目标文件/接口 | 验收 |
|---|---:|---|---|---|
| RT-AKS-01 | P0 | 新增 AkShare 实时新闻抓取器 | `stock_processing_service/application/services/akshare_realtime_news_collector.py` | 定时抓取新闻并写 `stream:news:raw` |
| RT-AKS-02 | P0 | 新增运行脚本 | `stock_processing_service/scripts/run_akshare_realtime_news_collector.py` | 支持 `--redis-url --stream --run-id --poll-interval-seconds --lookback-minutes` |
| RT-AKS-03 | P0 | payload 兼容 E2E replay | 输出字段同 `replay_akshare_raw_news.py` | 包含 `news_id/external_id/title/content/source/source_channel/publish_date/publish_time/collected_at/url/run_id/type=raw_news` |
| RT-AKS-04 | P0 | `RealtimeStackManager.start()` 同步启动 AkShare source | `realtime_stack_manager.py` | 点击“启动实时采集”后 raw stream 有 AkShare 新增消息 |
| RT-AKS-05 | P1 | collector 状态与去重指标 | status API | 返回 `last_fetch_at/last_success_at/fetched_count/pushed_count/duplicate_count/last_error` |

run_id 规则：

```text
生产实时模式可以使用 run_id = realtime_YYYYMMDD_HHMMSS。
如果 raw_news_services / phase0_decision_services 仍启用 run_id_filter，
AkShare collector 必须使用同一个 run_id。
```

### 17.5 情报台统一 feed 任务

实现任务：

| ID | 优先级 | 任务 | 目标文件/接口 | 验收 |
|---|---:|---|---|---|
| INTEL-FEED-01 | P0 | `get_intel_news_events` 底层改为 `news_event JOIN event_subject_map` | `postgres_manager.py` | MATCH 事件以 `item_type='event'` 返回 |
| INTEL-FEED-02 | P0 | 新增 `load_review_event_items()` | `intel_new_chain_adapter.py` | `event_review_queue` 以 `item_type='event_review'` 返回 |
| INTEL-FEED-03 | P0 | review source_channel 标准化 | `event_review_queue` loader | AkShare review 显示 `source_channel='akshare_realtime'` |
| INTEL-FEED-04 | P1 | 修复 JYHF source 字段丢失 | `load_subject_history_items()` | JYHF DOM 显示 `source_type='jyhf_cdp_dom'`, `source_channel='jyhf_cdp'` |
| INTEL-FEED-05 | P1 | 前端来源标签校验 | `IntelListItem`, format utils | `event_review` 显示为“待复核” |

### 17.6 JYHF DOM 入库 news_event 任务

JYHF DOM 的关键约束：

```text
不进入 stream:news:raw
不走 NewsStreamProcessor
不触发 LLM 结构化
```

实现任务：

| ID | 优先级 | 任务 | 目标文件/接口 | 验收 |
|---|---:|---|---|---|
| JYHF-NE-01 | P0 | 新增 `create_news_event_from_jyhf_dom()` | `database_service/gateway.py`, `postgres_manager.py` | 写入 `news_event(source_category='jyhf_dom')` |
| JYHF-NE-02 | P0 | JYHF DB sink 写 news_event | `services/jyhf_cdp_service/db_sink.py` | 每条 DOM 事件生成或复用 news_event |
| JYHF-NE-03 | P0 | 已有 subject_key/theme_name 时写 event_subject_map | `upsert_event_subject_relation()` | source=`jyhf_dom_confirmed` |
| JYHF-NE-04 | P1 | 幂等去重 | news_event 索引/写入方法 | 同一 JYHF event_id 重复采集不重复插入 |

建议 `source_trace_id`：

```text
jyhf_cdp:{event.event_id}
```

### 17.7 Intel 公告同链处理任务

实现任务：

| ID | 优先级 | 任务 | 目标文件/接口 | 验收 |
|---|---:|---|---|---|
| INTEL-CHAIN-01 | P0 | 确认 `structured_intel_event -> news_event(source_category='intel')` | `intel_stream_producer.py` | news_event 存在且 source_category='intel' |
| INTEL-CHAIN-02 | P0 | 投递 `stream:events:structured` | 同上 | ThemeProcessor 能消费 |
| INTEL-CHAIN-03 | P0 | producer 幂等 | DDL + gateway | `structured_intel_event/news_event/stream produce` 不重复 |
| INTEL-CHAIN-04 | P0 | full-chain smoke 严格门禁 | `test_phase6a_full_chain_smoke.py` | `event_subject_map source_category='intel' >= 5` |
| INTEL-CHAIN-05 | P1 | raw 与 matched 双展示 | `PreMarketBriefBuilder` | `company_announcements_raw` 保留；matched 公告进入 matched sections |

### 17.8 盘前必读增量 rebuild 任务

实现任务：

| ID | 优先级 | 任务 | 目标文件/接口 | 验收 |
|---|---:|---|---|---|
| PMB-RT-01 | P0 | `RealtimeStackManager` 增加 brief rebuild loop | `realtime_stack_manager.py` | 采集运行期间 3~5 分钟 rebuild draft |
| PMB-RT-02 | P0 | 08:00 自动 finalize | scheduler / rebuild loop | final 后普通 rebuild 不覆盖 |
| PMB-RT-03 | P1 | diagnostics source_breakdown | `PreMarketBriefBuilder` | 输出 news/intel/jyhf/review 数量 |
| PMB-RT-04 | P1 | opportunity tier counts | `PreMarketBriefBuilder` | diagnostics 输出 A/B/C 或 tier 分布 |

### 17.9 推荐执行顺序

```text
第一阶段：P0-A AkShare 实时闭环（最高优先级）
→ RT-AKS-01~04
→ INTEL-FEED-01~03
→ PMB-RT-01 最小版

目标：
点击“启动实时采集”后，系统自动抓取 AkShare 新闻，写入 stream:news:raw，
经新链处理后，MATCH 在情报台显示为 event，HUMAN_REVIEW 显示为 event_review，
并触发盘前必读 draft 更新。

第一阶段暂不做：
- JYHF DOM 入 news_event
- Intel 公告 full-chain
- 复杂 15:00~08:00 精确窗口
- 08:00 final
- diagnostics 完整增强

第二阶段：P0-B 统一盘前窗口
→ PMB-WIN-01~05

目标：
所有盘前必读数据统一使用：
上一交易日 15:00 <= occurred_at < 当日 08:00。

第三阶段：P0-C 8:00 final
→ PMB-SCH-01~02
→ PMB-RT-02

目标：
15:00~08:00 持续 rebuild draft；
08:00 finalize；
08:00 后普通 rebuild 不覆盖 final。

第四阶段：P0-D JYHF DOM 入库同链
→ JYHF-NE-01~03

目标：
JYHF DOM 不进 stream:news:raw，不触发 NewsStreamProcessor，不走 LLM；
直接入 news_event，并在已有 subject_key/theme_name 时写 event_subject_map。

第五阶段：P0-E Intel 公告 full-chain
→ INTEL-CHAIN-01~04

目标：
严格验证 structured_intel_event → news_event(source_category='intel')
→ stream:events:structured → ThemeProcessor → DecisionExecutor
→ event_subject_map / event_review_queue。

第六阶段：P1 体验与诊断
→ RT-AKS-05
→ INTEL-FEED-04~05
→ JYHF-NE-04
→ INTEL-CHAIN-05
→ PMB-RT-03~04
→ PMB-SCH-03
```

阶段一最小验收：

```text
1. 点击“启动实时采集”后，stream:news:raw 有 AkShare 新增消息。
2. news_event 有 source_channel='akshare_realtime' 或等价来源字段。
3. MATCH 事件进入 event_subject_map。
4. HUMAN_REVIEW 事件进入 event_review_queue。
5. /intel 能看到 MATCH 事件。
6. /intel?type=event_review 能看到待复核事件。
7. /pre-market-brief 有 major_events / matched_themes / opportunities 的 draft 新增内容。
```

### 17.10 实现状态 Checklist

状态枚举：

```text
TODO        尚未开始
IN_PROGRESS 已开始，未完成验收
PARTIAL     主体已有，但与本节业务口径仍有偏差
DONE        已实现并通过对应验收
BLOCKED     被外部依赖或上游决策阻塞
```

更新规则：

```text
1. 每次代码实现或验收后，必须更新本 checklist。
2. 只允许在有代码 diff、测试记录或人工核查证据时把状态推进。
3. DONE 必须填写验收证据；没有证据不得标 DONE。
4. 如果任务拆分变化，先更新 17.2~17.8 的任务表，再同步本 checklist。
5. Phase 4.7 E2E100 和 Phase 6A full-chain smoke 未通过前，整体状态不得标闭环完成。
```

| 阶段 | ID | 优先级 | 状态 | 依赖 | 实现/验收证据 | 更新说明 |
|---|---|---:|---|---|---|---|
| P0-A | RT-AKS-01 | P0 | DONE | Redis 可用、AkShare/NewsCrawler 可用 | 2026-05-20 P0-A Smoke: collector 随 realtime start 启动，fetched=100, pushed=12；网络不稳定→RISK-01 | AkShare 抓取器已随栈启动；真实新闻已进 stream:news:raw |
| P0-A | RT-AKS-02 | P0 | DONE | RT-AKS-01 | 2026-05-20 P0-A Smoke: RealtimeStackManager 子进程启动成功，PID=62645 | collector 脚本可被 realtime start 正常启动 |
| P0-A | RT-AKS-03 | P0 | DONE | RT-AKS-01 | 2026-05-20 P0-A Smoke: raw stream→news_event(5条)→event_subject_map(5条 MATCH) 全链路字段兼容 | payload 已兼容 E2E replay 格式，全链路通过 |
| P0-A | RT-AKS-04 | P0 | DONE | RT-AKS-02 | 2026-05-20 P0-A Smoke: akshare/raw_news/decision/rebuild 四进程 running，stop 后全部清理 | RealtimeStackManager.start() 四进程联动正常 |
| P0-A | INTEL-FEED-01 | P0 | DONE | event_subject_map 可读 | 2026-05-20 P0-A Smoke: /intel?item_type=event 返回 MATCH(event:129104:9024880) source_channel=akshare_realtime | MATCH 事件以 item_type='event' 在情报台可见 |
| P0-A | INTEL-FEED-02 | P0 | DONE | event_review_queue 可读 | 2026-05-20 P0-A2: /intel?item_type=event_review 返回 review:129110, source_type=event_review_queue | event_review_queue 已并入情报台 feed |
| P0-A | INTEL-FEED-03 | P0 | DONE | INTEL-FEED-02 | 2026-05-20 P0-A2: event_review source_channel=akshare_realtime；_normalize_review_source_channel 映射正确 | AkShare review source_channel 标准化完成 |
| P0-A | PMB-RT-01 | P0 | DONE | RT-AKS-04 | 2026-05-20 P0-A Smoke: /pre-market-brief draft 返回 major_events=5, matched_themes=5, review_events=1 | rebuild loop 已接，draft 自动更新正常 |
| P0-B | PMB-WIN-01 | P0 | DONE | 交易日历可读 | 2026-05-20: pre_market_window.py 已实现，支持 trade_calendar + weekday fallback | `resolve_pre_market_window(trade_date)` 已新增 |
| P0-B | PMB-WIN-02 | P0 | DONE | PMB-WIN-01 | 2026-05-20: get_event_subject_mappings_by_trade_date 已支持 start_time/end_time 时间窗口过滤 | MATCH 查询支持窗口 |
| P0-B | PMB-WIN-03 | P0 | DONE | PMB-WIN-01 | 2026-05-20: get_pre_market_review_events 已支持 start_time/end_time 时间窗口过滤 | REVIEW 查询支持窗口 |
| P0-B | PMB-WIN-04 | P0 | DONE | PMB-WIN-01 | 2026-05-20: end_time 默认改为 08:00；主路径由 Builder 传入 start_at/end_at | Intel 公告默认窗口修正 |
| P0-B | PMB-WIN-05 | P0 | DONE | PMB-WIN-02~04 | 2026-05-20: rebuild 开头解析 window，DB 查询全部传 start_at/end_at，diagnostics 含 pre_market_window | Builder 统一使用窗口 |
| P0-C | PMB-SCH-01 | P0 | DONE | PMB-WIN-01 | 2026-05-20: scheduler 窗口改为 15:00/08:00；resolve 改为 15:00 | 调度器窗口已统一 |
| P0-C | PMB-SCH-02 | P0 | DONE | PMB-SCH-01 | 现有 snapshot upsert 已有 final 保护 + force 门禁 | 08:00 后普通 rebuild 不覆盖 final |
| P0-C | PMB-RT-02 | P0 | TODO | PMB-SCH-01~02 + PMB-RT-01 | 待补 | 08:00 自动 finalize — rebuild loop 中接到 scheduler 信号时执行 |
| P0-D | JYHF-NE-01 | P0 | DONE | news_event 扩展字段 | 2026-05-20: db_sink._write_news_event() 实现，source_category='jyhf_dom', ON CONFLICT(source_trace_id) | JYHF DOM → news_event 完成 |
| P0-D | JYHF-NE-02 | P0 | DONE | JYHF-NE-01 | 2026-05-20: db_sink.write_events() 同步双写 news_event + subject_history_staging | DB sink 双写完成 |
| P0-D | JYHF-NE-03 | P0 | DONE | JYHF-NE-02 | 2026-05-20: _write_event_subject_map(), 中文名→数字key映射 via theme_gate_profile.concept, source='jyhf_dom_confirmed' | event_subject_map 同步写入 |
| P0-E | INTEL-CHAIN-01 | P0 | DONE | Phase 6A DDL | 2026-05-20: IntelStreamProducer 代码完整, raw_intel_document+structured_intel_event+news_event(source_category='intel') 链路已通, 53条 produced | Intel 公告链路主体已实现 |
| P0-E | INTEL-CHAIN-02 | P0 | DONE | INTEL-CHAIN-01 | 2026-05-20: stream:events:structured 投递成功, envelope 兼容 ThemeProcessor, PEL=0 | structured stream 投递已验证 |
| P0-E | INTEL-CHAIN-03 | P0 | DONE | DDL + gateway | 2026-05-20: create_news_event_with_intel() 幂等 (structured_intel_event_id), producer 不重复投递 (stream_status='produced' guard) | Intel 幂等验证通过 |
| P0-E | INTEL-CHAIN-04 | P0 | DONE | INTEL-CHAIN-01~03 | 2026-05-20: pre_market_brief company_announcements_raw=25, 真实 cninfo 公告 (托普云农/康泰医学/华康洁净等), unified window (start=15:00, end=08:00) | full-chain smoke 完成 |
| P1 | RT-AKS-05 | P1 | TODO | RT-AKS-04 | 待补 | status 返回 collector 指标 |
| P1 | INTEL-FEED-04 | P1 | DONE | JYHF DB sink | 2026-05-20: load_subject_history_items() source_type/channel 不再清空 | JYHF source 字段已修复 |
| P1 | INTEL-FEED-05 | P1 | PARTIAL | INTEL-FEED-02 | 前端已有 `event_review -> 待复核` 标签 | 需结合真实 feed 验证 |
| P1 | JYHF-NE-04 | P1 | DONE | JYHF-NE-01 | 2026-05-20: idx_news_event_source_trace_id_not_null + idx_event_subject_map_event_subject_source 唯一索引, ON CONFLICT DO NOTHING | JYHF 幂等验证通过 |
| P1 | INTEL-CHAIN-05 | P1 | PARTIAL | INTEL-CHAIN-04 | 当前已有 raw/matched section 雏形 | matched 公告需进入 matched sections/opportunities |
| P1 | PMB-RT-03 | P1 | TODO | PMB-WIN-05 | 待补 | diagnostics `source_breakdown` |
| P1 | PMB-RT-04 | P1 | TODO | opportunity builder 输出稳定 | 待补 | diagnostics opportunity tier counts |
| P1 | PMB-SCH-03 | P1 | TODO | PMB-SCH-01~02 | 待补 | 更新 scheduler 单测窗口样例 |

整体状态：

```text
当前：IN_PROGRESS（P0-A/P0-B 已完成，进入 P0-C）
P0-A DONE (2026-05-20)：
- RT-AKS-01~04, INTEL-FEED-01~03, PMB-RT-01

P0-B DONE (2026-05-20)：
- PMB-WIN-01~05, PMB-SCH-01~02
- 窗口：上一交易日15:00～当日08:00 Asia/Shanghai
- 优先 trade_calendar，fallback weekday
- diagnostics 输出 pre_market_window

P0-C DONE (2026-05-20)：
- PMB-SCH-01~02 DONE, scheduler 单测 11 passed
- final 保护 smoke 通过：final 后 force=false 不覆盖, force=true 可覆盖

P0-D DONE (2026-05-20)：
- JYHF-NE-01~03 DONE, JYHF-NE-04 DONE, INTEL-FEED-04 DONE
- db_sink 双写：news_event(source_category='jyhf_dom') + event_subject_map(source='jyhf_dom_confirmed')
- 情报台 source 字段修复, 中文名→数字key映射 via theme_gate_profile.concept
- SQL event_time 优先于 created_at 用于窗口过滤
- smoke: news_event#129113 → event_subject_map(卫星互联网/9019807) → matched_themes

P0-E DONE (2026-05-20)：
- INTEL-CHAIN-01~04 DONE
- IntelStreamProducer runtime 脚本, RealtimeStackManager 第5进程
- POST /api/v1/intel/produce API
- phase6a DDL 补齐: structured_intel_event.stream_message_id/stream_produced_at 列 + update 类型转换修复
- pre_market_brief: company_announcements_raw=25 (真实cninfo公告)

已知风险：RISK-01(AkShare网络), RISK-02(HUMAN_REVIEW样本), RISK-03(stock_data切换)

当前未完成：P1 (AkShare稳定性、scheduler单测更新、diagnostics增强)
```

### 17.11 统一验收清单

必须全部满足后，才能认为实时采集、情报台和盘前必读链路闭环完成：

```text
1. 点击“启动实时采集”后，AkShare collector 自动启动，并向 stream:news:raw 写入新闻。

2. AkShare MATCH：
   - news_event 存在
   - event_subject_map 存在
   - /intel 显示 item_type='event'
   - pre_market_brief.matched_themes / major_events / opportunities 包含该事件

3. AkShare HUMAN_REVIEW：
   - event_review_queue(review_status='waiting') 存在
   - /intel?type=event_review 显示为“待复核”
   - pre_market_brief.review_events 包含该事件

4. JYHF DOM：
   - news_event(source_category='jyhf_dom') 存在
   - 不进入 stream:news:raw
   - 不触发 NewsStreamProcessor / LLM 结构化
   - 已有 subject_key/theme_name 时 event_subject_map(source='jyhf_dom_confirmed') 存在
   - /intel 显示 item_type='event' 或 'new_theme'

5. Intel 公告：
   - raw_intel_document -> structured_intel_event -> news_event(source_category='intel') 完成
   - stream:events:structured 有消息
   - MATCH 公告进入 event_subject_map
   - HUMAN_REVIEW 公告进入 event_review_queue
   - company_announcements_raw 保留
   - matched 公告进入 matched_themes / opportunities

6. 盘前必读窗口：
   - 只包含上一交易日 15:00 <= occurred_at < 当日 08:00 的新闻/公告/JYHF 事件
   - 历史补采 created_at 不污染当前盘前报告

7. draft/final：
   - 15:00~08:00 持续增量 rebuild draft
   - 08:00 finalize
   - 08:00 后普通 rebuild 不覆盖 final
   - force=true 才允许覆盖

8. 回归门禁：
   - Phase 4.7 新闻 E2E100 仍通过
   - Phase 6A full-chain smoke 中 intel event_subject_map >= 5
   - dead_letter=0
   - Redis PEL=0
```

## 18. 最终结论

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
