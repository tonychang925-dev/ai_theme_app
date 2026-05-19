# AI投资助理：实时新闻事件、题材匹配与盘前必读事件驱动机会链路设计

> 版本：v1.6  
> 日期：2026-05-19  
> 状态：主链路已实现，Theme Profile v2 灰度验证中，Phase 4.6 完整新链 E2E100 执行闭环通过，召回恢复待处理  
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

## 17. 最终结论

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
