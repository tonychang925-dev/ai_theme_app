# Phase 6：一手信息接入与预警引擎设计文档

> 适用项目：AI Theme App / 盘前必读新链路  
> 文档版本：v1.0  
> 日期：2026-05-19  
> 目标：在现有新闻驱动盘前必读链路基础上，新增公司公告、业绩预告、业绩快报、研报、机构调研等一手/准一手信息输入，形成“公告/财报/研报/调研 → LLM结构化 → 题材匹配 → 机会/风险预警 → 盘前必读”的完整闭环。

---

## 1. 背景与目标

当前项目已经完成 Phase 4.7，新闻链路完整 E2E100 验收通过，主链路稳定。现有链路为：

```text
stream:news:raw
→ news_raw / news_event
→ stream:events:structured
→ ThemeProcessor
→ ThemeMatchEngine
→ stream:events:decision
→ DecisionExecutor
→ event_subject_map / review / pending
→ PreMarketBriefBuilder
→ EventDrivenOpportunityBuilder
→ pre_market_brief_snapshot
```

Phase 4.7 的关键基线为：

```text
theme_set_recall@5 = 0.72
wrong_related_count = 0
generic_only_related_count = 0
terminal_distinct_event = 100
dead_letter_count = 0
brief_stock_opportunity_count = 144
A+B stock count = 74
numeric_theme_name_count = 0
```

这说明“新闻 → 题材 → 股票机会 → 盘前必读”的后半段已经成熟。Phase 6 的核心目标是补齐“一手信息输入”，让系统从“新闻驱动题材系统”升级为：

```text
新闻 + 公告 + 财报 + 研报 + 调研 的综合事件情报系统
```

最终支持：

- 盘前必读中的公司公告催化
- 业绩预告/快报/财报异动
- 个股风险预警
- 机构研报/调研摘要
- 重大合同、并购重组、减持、处罚等重大决策提醒
- 个股机会与风险的自动分级

---

## 2. 当前架构适配度评估

### 2.1 现有链路成熟度

现有后半段链路可复用：

```text
ThemeProcessor
→ ThemeMatchEngine
→ DecisionExecutor
→ PreMarketBriefBuilder
→ EventDrivenOpportunityBuilder
→ pre_market_brief_snapshot
```

因此 Phase 6 不应重写后半段，而应新增前半段：

```text
一手信息采集
→ 原始文档入库
→ LLM结构化
→ 转换为 structured event envelope
→ 投递 stream:events:structured
```

从 `stream:events:structured` 开始复用既有链路。

### 2.2 当前缺陷

| 缺陷 | 严重度 | 说明 |
|---|---:|---|
| 新闻源主要依赖 akshare / 财联社 | 高 | 缺少公司公告、业绩报告、研报、机构调研等一手信息 |
| `news_raw` 表语义是“新闻” | 中 | 直接把公告/研报塞入会污染表语义 |
| PreMarketBriefBuilder 缺少公司催化 section | 中 | 当前 section 更偏新闻事件、题材、机会 |
| 无 PDF 正文提取能力 | 中 | 公告、年报、研报大量为 PDF |
| 无个股级 AlertRuleEngine | 中 | 当前 risk_alerts 主要来自 review/unknown，不足以做公司风险预警 |

### 2.3 核心原则

Phase 6 必须遵守：

```text
新增并行链路，不破坏现有新闻链路。
```

新增表：

```text
raw_intel_document
structured_intel_event
```

不要直接把公告、研报、调研塞进 `news_raw`。

---

## 3. 总体架构设计

### 3.1 新链路总览

```text
AKShare / 巨潮 / 交易所 / 研报 / 调研
→ AnnouncementCollector / ReportCollector / SurveyCollector
→ raw_intel_document
→ IntelEventExtractor
→ structured_intel_event
→ IntelStreamProducer
→ stream:events:structured
→ ThemeProcessor
→ ThemeMatchEngine
→ DecisionExecutor
→ event_subject_map / review / pending
→ PreMarketBriefBuilder
→ pre_market_brief_snapshot
→ 前端盘前必读
```

### 3.2 设计边界

不改动：

```text
ThemeProcessor
ThemeMatchEngine
DecisionExecutor
现有 stream:news:raw
现有新闻 E2E100 基线
```

主要新增：

```text
raw_intel_document
structured_intel_event
AnnouncementCollector
IntelEventExtractor
IntelStreamProducer
AlertRuleEngine
PreMarketBriefBuilder section 扩展
```

### 3.3 MVP 兼容性方案

由于当前 `ThemeProcessor._process_message_structured()` 会通过 `event_id` 查询 `news_event` 表，MVP 阶段建议：

```text
一手信息结构化后，也写入 news_event
并增加 source_category = 'intel'
```

这样 intel event 可以完全复用现有 structured event envelope，最小化改动。

后续成熟后，再让 ThemeProcessor 直接支持 `structured_intel_event` 查询。

---

## 4. 数据源规划

### 4.1 P0 数据源：公告与业绩

| 数据源 | 类型 | 优先级 | 价值 |
|---|---|---:|---|
| 巨潮资讯公告 | 公司公告 | P0 | 一手信息核心来源 |
| 沪深京 A 股公告 | 公司公告 | P0 | 覆盖全市场公告 |
| 个股公告 | 公司公告 | P0 | 支持个股事件追踪 |
| 业绩预告 | 财务事件 | P0 | 盘前风险/机会关键 |
| 业绩快报 | 财务事件 | P1 | 财务预期修正 |
| 预约披露时间 | 时间表 | P1 | 未来事件提醒 |

### 4.2 P1 数据源：研报与调研

| 数据源 | 类型 | 优先级 | 注意事项 |
|---|---|---:|---|
| 个股研报 | 机构观点 | P1 | 必须区分事实与观点 |
| 机构调研 | 准一手信息 | P1 | 需标记公司确认/未确认信息 |
| 路演纪要 | 准一手信息 | P2 | 来源质量需要标注 |

### 4.3 信息源优先级

建议使用：

```text
公告 > 业绩预告 / 业绩快报 > 调研纪要 > 研报 > 新闻
```

新闻负责“快”，公告/财报负责“真”，研报/调研负责“逻辑”。

---

## 5. 数据库设计

### 5.1 raw_intel_document

用于存储公告、研报、调研、财报等原始文档。

```sql
CREATE TABLE IF NOT EXISTS raw_intel_document (
    id BIGSERIAL PRIMARY KEY,
    source_system   VARCHAR(64)  NOT NULL,
    source_type     VARCHAR(64)  NOT NULL,
    source_id       VARCHAR(256) NOT NULL,
    source_url      TEXT,
    publish_time    TIMESTAMPTZ,
    fetch_time      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    market          VARCHAR(32),
    stock_code      VARCHAR(32),
    stock_name      VARCHAR(128),
    company_name    VARCHAR(256),
    title           TEXT,
    content_text    TEXT,
    content_html    TEXT,
    pdf_url         TEXT,
    pdf_path        TEXT,
    doc_type        VARCHAR(64),
    doc_subtype     VARCHAR(64),
    announcement_type VARCHAR(64),
    report_period   VARCHAR(32),
    checksum        VARCHAR(128),
    dedupe_key      VARCHAR(256),
    parse_status    VARCHAR(32)  NOT NULL DEFAULT 'raw',
    llm_status      VARCHAR(32)  NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_intel_doc_source_id
ON raw_intel_document(source_system, source_id);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_dedupe
ON raw_intel_document(dedupe_key);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_publish_time
ON raw_intel_document(publish_time);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_stock
ON raw_intel_document(stock_code);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_parse_status
ON raw_intel_document(parse_status);

CREATE INDEX IF NOT EXISTS idx_raw_intel_doc_llm_status
ON raw_intel_document(llm_status);
```

### 5.2 structured_intel_event

用于存储 LLM 结构化后的一手信息事件。

```sql
CREATE TABLE IF NOT EXISTS structured_intel_event (
    id BIGSERIAL PRIMARY KEY,
    raw_doc_id        BIGINT       NOT NULL REFERENCES raw_intel_document(id),
    event_type        VARCHAR(64)  NOT NULL,
    event_subtype     VARCHAR(64),
    event_level       VARCHAR(32)  NOT NULL DEFAULT 'normal',
    stock_code        VARCHAR(32),
    stock_name        VARCHAR(128),
    subject_keys      TEXT[],
    title             TEXT,
    summary           TEXT,
    event_date        DATE,
    publish_time      TIMESTAMPTZ,
    entities          JSONB        NOT NULL DEFAULT '{}',
    financial_metrics JSONB        NOT NULL DEFAULT '{}',
    business_metrics  JSONB        NOT NULL DEFAULT '{}',
    catalyst_tags     TEXT[],
    risk_tags         TEXT[],
    confidence        NUMERIC(5,4),
    impact_score      NUMERIC(5,2),
    urgency_score     NUMERIC(5,2),
    evidence_json     JSONB        NOT NULL DEFAULT '{}',
    llm_model         VARCHAR(64),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sie_raw_doc
ON structured_intel_event(raw_doc_id);

CREATE INDEX IF NOT EXISTS idx_sie_stock
ON structured_intel_event(stock_code);

CREATE INDEX IF NOT EXISTS idx_sie_event_type
ON structured_intel_event(event_type);

CREATE INDEX IF NOT EXISTS idx_sie_event_level
ON structured_intel_event(event_level);

CREATE INDEX IF NOT EXISTS idx_sie_publish_time
ON structured_intel_event(publish_time);
```

### 5.3 news_event 兼容字段

MVP 阶段建议给 `news_event` 增加：

```sql
ALTER TABLE news_event
ADD COLUMN IF NOT EXISTS source_category VARCHAR(32) DEFAULT 'news',
ADD COLUMN IF NOT EXISTS raw_intel_doc_id BIGINT,
ADD COLUMN IF NOT EXISTS structured_intel_event_id BIGINT;
```

用途：

```text
source_category = news / intel
```

intel event 写入 news_event 后，即可复用现有 ThemeProcessor。

---

## 6. Collector 设计

### 6.1 AnnouncementCollector

位置建议：

```text
news_crawler_service/collectors/announcement_collector.py
```

原因：

- 与现有 AKShare base collector 体系一致
- Collector 只负责抓取和标准化
- 不负责 LLM 结构化

### 6.2 统一输出格式

```json
{
  "source_system": "akshare_cninfo",
  "source_type": "announcement",
  "source_id": "cninfo_xxx",
  "source_url": "https://...",
  "publish_time": "2026-05-19T08:30:00+08:00",
  "market": "SZ",
  "stock_code": "300750",
  "stock_name": "宁德时代",
  "company_name": "宁德时代新能源科技股份有限公司",
  "title": "关于签署重大合同的公告",
  "content_text": "",
  "content_html": "",
  "pdf_url": "https://...",
  "doc_type": "announcement",
  "announcement_type": "major_contract",
  "report_period": "",
  "checksum": "...",
  "dedupe_key": "akshare_cninfo:announcement:source_id"
}
```

### 6.3 MVP 策略

Phase 6A 只做：

```text
公告标题
公告类型
股票代码
股票名称
发布时间
PDF URL
去重
入库
```

不做 PDF 深度解析。

理由：

1. PDF 下载/解析/OCR 是独立工程问题
2. 公告标题与类型已经能提供大量有效信号
3. LLM 可以先基于标题、公告类型、摘要做初步结构化
4. 降低 Phase 6A 风险

---

## 7. LLM 结构化设计

### 7.1 IntelEventExtractor

新增：

```text
stock_processing_service/domain/services/intel_event_extractor.py
```

结构：

```python
class IntelEventExtractor:
    async def extract_announcement(self, doc): ...
    async def extract_performance(self, doc): ...
    async def extract_research(self, doc): ...
    async def extract_survey(self, doc): ...
```

### 7.2 公告类输出 Schema

```json
{
  "event_type": "major_contract",
  "event_subtype": "",
  "event_level": "important",
  "stock_code": "",
  "stock_name": "",
  "title": "",
  "summary": "",
  "business_direction": "",
  "related_products": [],
  "amount": "",
  "counterparty": "",
  "contract_period": "",
  "impact_assessment": "",
  "risk_points": [],
  "theme_candidates": [],
  "confidence": 0.0,
  "evidence": []
}
```

### 7.3 业绩类输出 Schema

```json
{
  "event_type": "performance_forecast",
  "event_level": "important",
  "stock_code": "",
  "stock_name": "",
  "report_period": "2025Q4",
  "forecast_type": "pre_increase",
  "net_profit_min": "",
  "net_profit_max": "",
  "yoy_min": "",
  "yoy_max": "",
  "reason": "",
  "main_drivers": [],
  "risk_points": [],
  "surprise_level": "high_positive",
  "confidence": 0.0,
  "evidence": []
}
```

### 7.4 研报类输出 Schema

```json
{
  "event_type": "research_report",
  "event_level": "normal",
  "source_org": "",
  "analyst": "",
  "stock_code": "",
  "stock_name": "",
  "rating": "",
  "target_price": "",
  "forecast_eps": {},
  "key_assumptions": [],
  "theme_logic": [],
  "risk_warnings": [],
  "is_fact_or_opinion": "opinion",
  "confidence": 0.0,
  "evidence": []
}
```

### 7.5 调研类输出 Schema

```json
{
  "event_type": "institutional_survey",
  "event_level": "normal",
  "stock_code": "",
  "stock_name": "",
  "participants": [],
  "topics": [],
  "new_information": [],
  "confirmed_business_progress": [],
  "unconfirmed_forward_looking": [],
  "theme_candidates": [],
  "risk_points": [],
  "confidence": 0.0,
  "evidence": []
}
```

### 7.6 关键约束

1. 研报必须标记 `is_fact_or_opinion = opinion`
2. `source_org` 不能进入题材锚点
3. 所有结构化结果必须保留 evidence
4. 第一版不强制 PDF 全文解析
5. 无法判断时进入 HUMAN_REVIEW，不强行 MATCH

---

## 8. IntelStreamProducer 设计

新增：

```text
stock_processing_service/application/services/intel_stream_producer.py
```

职责：

```text
structured_intel_event
→ structured event envelope
→ stream:events:structured
```

Envelope 示例：

```json
{
  "payload": {
    "event_id": 12345,
    "source_category": "intel",
    "source_type": "announcement",
    "raw_intel_doc_id": 1001,
    "structured_intel_event_id": 2001,
    "run_id": "intel_20260519",
    "title": "某公司签署重大合同公告",
    "summary": "公司公告称...",
    "content": "公告标题与摘要...",
    "event_type": "major_contract",
    "theme_candidates": ["液冷数据中心", "AI服务器"],
    "evidence_json": {}
  }
}
```

MVP 推荐方案：

1. structured_intel_event 同步写入 news_event
2. `news_event.source_category = intel`
3. stream payload 中使用 news_event.id 作为 event_id
4. ThemeProcessor 无需修改

---

## 9. AlertRuleEngine 设计

新增：

```text
stock_processing_service/domain/services/alert_rule_engine.py
```

### 9.1 输出 Schema

```json
{
  "alert_type": "risk",
  "severity": "critical",
  "stock_code": "300750",
  "stock_name": "宁德时代",
  "title": "业绩大幅预亏",
  "reason": "预计净利润大幅下降...",
  "evidence": [
    {
      "page": 1,
      "quote": "公告原文..."
    }
  ],
  "suggested_action": "加入盘前必读风险提示"
}
```

### 9.2 规则分层

| 级别 | 类型 | 示例 |
|---|---|---|
| critical | risk | 业绩大幅预亏、监管处罚、重大合同终止、实控人变更、大额减持、商誉减值、ST风险 |
| important | risk | 业绩低于预期、问询函、毛利率下滑、现金流恶化、高管离职 |
| opportunity | opportunity | 重大合同金额高、新产品量产、产能扩张、业绩超预期、回购增持、研报上调 |
| watch | watch | 机构调研集中、募投项目进展、订单情况 |

### 9.3 规则引擎原则

AlertRuleEngine 不直接调用 LLM。

流程：

```text
LLM 结构化
→ structured_intel_event
→ AlertRuleEngine 规则判断
→ alert list
```

这样可以避免预警完全依赖 LLM 主观判断。

---

## 10. PreMarketBriefBuilder 扩展

新增 section：

```json
{
  "company_announcements": [],
  "earnings_alerts": [],
  "research_highlights": [],
  "institutional_survey": [],
  "opportunity_alerts": [],
  "risk_alerts": []
}
```

其中 `risk_alerts` 当前已存在，但需要扩展为：

```text
review/unknown 自动风险
+
个股公告/业绩/研报/调研风险
```

推荐最终盘前必读结构：

```text
1. 重大宏观/产业事件
2. 重点题材
3. 公司一手公告催化
4. 业绩预告/财报异动
5. 机构研报/调研摘要
6. 事件驱动股票机会
7. 重大风险预警
8. 待人工复核
9. diagnostics
```

---

## 11. 实施阶段

### Phase 6A：公告接入 MVP

目标：

```text
公告能进 raw_intel_document
→ 标题 LLM 结构化
→ 进 stream:events:structured
→ 进盘前必读
```

交付物：

1. raw_intel_document 表
2. structured_intel_event 表
3. AnnouncementCollector
4. IntelEventExtractor 公告类 prompt
5. IntelStreamProducer
6. PreMarketBriefBuilder 新增 company_announcements
7. Smoke test

验收标准：

```text
能抓取并入库最近一天公告 ≥ 50 条
重大合同/业绩预告/风险公告结构化 ≥ 10 条
至少 5 条公告事件进入盘前必读 company_announcements
不影响现有新闻 E2E100 基线
```

### Phase 6B：AlertRuleEngine

目标：

```text
风险/机会规则引擎输出 risk_alerts / opportunity_alerts
```

验收标准：

```text
risk_alerts 非空，至少 3 条
opportunity_alerts 非空，至少 3 条
严重级别分级正确
```

### Phase 6C：PDF 正文解析

目标：

```text
公告 PDF 下载
正文提取
证据页码
长文档分块
```

### Phase 6D：业绩/财报专项

目标：

```text
业绩预告
业绩快报
年报季报
财务指标抽取
业绩超预期/低预期判断
```

### Phase 6E：研报/调研专项

目标：

```text
个股研报
机构调研
调研纪要
观点与事实分离
```

---

## 12. 风险与控制

### 12.1 不污染现有新闻链路

必须保证：

```text
公告/研报/调研 不直接写入 stream:news:raw
```

而是：

```text
raw_intel_document
→ structured_intel_event
→ stream:events:structured
```

或 MVP 同步写入 news_event 后再投递 structured event。

### 12.2 研报 source_org 不得作为题材锚点

研报类事件中：

```text
东方证券、中信证券、国泰君安
```

只能作为 `source_org`，不得进入主题锚点。

### 12.3 PDF 不在 MVP 中强依赖

第一版只抓：

```text
标题
公告类型
PDF URL
发布时间
股票代码
股票名称
```

PDF 正文解析放 Phase 6C。

### 12.4 LLM 输出必须保留 evidence

每个 structured_intel_event 必须带：

```text
evidence_json
```

用于后续人工复核和盘前必读可信度展示。

### 12.5 不破坏 Phase 4.7 基线

每次 Phase 6 改动后，必须回归：

```text
Phase 4.7 新闻链路 E2E100
```

门禁：

```text
theme_set_recall@5 >= 0.70
wrong_related_count = 0
generic_only_related_count = 0
terminal_distinct_event_count = 100
dead_letter_count = 0
A+B stock count >= 70
```

---

## 13. 测试与验收

### 13.1 单元测试

覆盖：

```text
raw_intel_document upsert
structured_intel_event insert
AnnouncementCollector 标准化
IntelEventExtractor JSON schema
IntelStreamProducer envelope
AlertRuleEngine rules
```

### 13.2 Smoke Test

流程：

```text
抓取最近一天公告
→ 入库 raw_intel_document
→ LLM 结构化
→ 写 structured_intel_event
→ 投递 stream:events:structured
→ ThemeProcessor / DecisionExecutor
→ rebuild 盘前必读
→ 前端展示
```

### 13.3 E2E 门禁

```text
公告入库数 >= 50
结构化成功数 >= 10
company_announcements >= 5
risk_alerts >= 3
opportunity_alerts >= 3
news E2E100 基线不回退
```

---

## 14. 推荐开发顺序

```text
1. DDL：raw_intel_document + structured_intel_event
2. DatabaseGateway / PostgresManager 方法
3. AnnouncementCollector MVP
4. IntelEventExtractor 公告类
5. structured_intel_event → news_event 兼容写入
6. IntelStreamProducer
7. PreMarketBriefBuilder 新增 company_announcements
8. AlertRuleEngine
9. Smoke test
10. 回归 Phase 4.7 E2E100
```

---

## 15. 总结

Phase 6 的核心策略是：

```text
新增并行前半段，复用成熟后半段。
```

即：

```text
公告/财报/研报/调研
→ raw_intel_document
→ structured_intel_event
→ stream:events:structured
→ 复用现有 ThemeProcessor / DecisionExecutor / PreMarketBriefBuilder
```

短期重点是 Phase 6A：公告接入 MVP。

不要一开始就追求 PDF 全文、研报深度解析和复杂财务模型。先把公告标题/类型/摘要结构化接入盘前必读，形成最小闭环，再逐步扩展 PDF、财报、研报和调研。
