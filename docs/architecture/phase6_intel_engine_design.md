# Phase 6：一手信息接入与预警引擎设计文档

> 适用项目：AI Theme App / 盘前必读新链路  
> 文档版本：v1.1  
> 日期：2026-05-19  
> 变更：Phase 6A 压缩为 8 个交付单元，AlertRuleEngine 后移 Phase 6B，新增 source_trace_id/stream_status 字段，新增 RawIntelIngestionService，新增 checklist 跟踪表  
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
RawIntelIngestionService
IntelEventExtractor
IntelStreamProducer
AlertRuleEngine（Phase 6B）
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
    stream_status   VARCHAR(32)  NOT NULL DEFAULT 'pending',  -- pending / produced / skipped / failed
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
    stream_status     VARCHAR(32)  NOT NULL DEFAULT 'pending',  -- pending / produced / skipped / failed
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
ADD COLUMN IF NOT EXISTS structured_intel_event_id BIGINT,
ADD COLUMN IF NOT EXISTS source_trace_id VARCHAR(128);
```

用途：

```text
source_category = news / intel
source_trace_id  = {run_id}:{raw_doc_id}:{sie_id}
```

`source_trace_id` 贯穿全链路，用于追踪：

```text
raw_intel_document
→ structured_intel_event
→ news_event
→ stream:events:structured
→ event_subject_map
→ pre_market_brief_snapshot
```

intel event 写入 news_event 后，即可复用现有 ThemeProcessor。

---

## 6. Collector 设计

### 6.1 AnnouncementCollector

位置建议：

```text
news_crawler_service/collectors/announcement_collector.py
```

职责边界：

```text
Collector 只负责：抓取 + 标准化 → 输出 RawIntelDocumentDTO list
Collector 不负责：入库、去重、写 DB
```

原因：

- 与现有 AKShare base collector 体系一致
- Collector 不依赖 DatabaseGateway，方便单测 mock
- 入库逻辑由 RawIntelIngestionService 统一负责

### 6.2 RawIntelIngestionService

位置建议：

```text
stock_processing_service/application/services/raw_intel_ingestion_service.py
```

职责：

```text
1. 接收 Collector 产出的 RawIntelDocumentDTO list
2. checksum 计算与 content_text 去重
3. (source_system, source_id) 唯一性去重
4. dedupe_key 构建
5. 调用 DatabaseGateway.upsert_raw_intel_document() 入库
6. 返回 upsert 统计 {inserted, updated, skipped}
```

不负责：

```text
LLM 结构化
PDF 下载/解析
stream 投递
```

### 6.3 统一输出格式

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

### 6.4 MVP 策略

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

### Phase 6A：公告接入 MVP（8 个交付单元）

**目标**：打通"公告采集 → 入库 → LLM 结构化 → 投递新链 → 盘前必读"最小闭环。

**不改动**：ThemeProcessor / ThemeMatchEngine / DecisionExecutor / stream:news:raw

**暂不做**：AlertRuleEngine、PDF 下载/OCR、研报/调研/财报专项

---

#### 6A-1：DDL

| 项目 | 内容 |
|---|---|
| **文件** | `database_service/scripts/create_raw_intel_document.sql`（新建） |
| | `database_service/scripts/create_structured_intel_event.sql`（新建） |
| | `database_service/scripts/alter_news_event_for_intel.sql`（新建） |
| **依赖** | 无 |
| **估时** | 小 |

**内容**：
- `raw_intel_document` — 26 字段 + 6 索引（含 `stream_status` 字段）
- `structured_intel_event` — 23 字段 + 5 索引（含 `stream_status` 字段，FK → raw_intel_document）
- `news_event` — 新增 `source_category`、`raw_intel_doc_id`、`structured_intel_event_id`、`source_trace_id` 四字段

**验证**：三个 SQL 文件均可通过 `psql -f` 执行成功，`\d` 显示表结构正确，FK 约束生效。

---

#### 6A-2：DB Gateway

| 项目 | 内容 |
|---|---|
| **文件** | `database_service/managers/postgres_manager.py`（修改） |
| | `database_service/gateway.py`（修改） |
| **依赖** | 6A-1 |
| **估时** | 中 |

**PostgresManager 新增方法**：

```python
# raw_intel_document
async def upsert_raw_intel_document(self, doc: dict) -> dict:
    """INSERT ... ON CONFLICT (source_system, source_id) DO UPDATE ... RETURNING *"""

async def get_raw_intel_documents_by_status(self, llm_status: str, limit: int = 100) -> list[dict]:
    """SELECT * WHERE llm_status = $1 ORDER BY publish_time DESC"""

async def update_raw_intel_llm_status(self, doc_id: int, status: str) -> None:

# structured_intel_event
async def insert_structured_intel_event(self, event: dict) -> dict:
    """INSERT INTO structured_intel_event (...) VALUES (...) RETURNING *"""

async def get_pending_intel_events_for_stream(self, limit: int = 50) -> list[dict]:
    """SELECT ... WHERE stream_status = 'pending' ORDER BY publish_time DESC"""

async def update_intel_event_stream_status(self, event_id: int, status: str) -> None:
```

**DatabaseGateway 新增委托方法**：每个方法一行委托（写操作→ `self._client`，读操作→ `self._read_source()`）。

---

#### 6A-3：AnnouncementCollector

| 项目 | 内容 |
|---|---|
| **文件** | `news_crawler_service/collectors/announcement_collector.py`（新建） |
| **依赖** | 无（不依赖 DatabaseGateway） |
| **估时** | 大 |

**职责边界**：

```text
Collector 只负责：抓取 + 标准化 → 输出 RawIntelDocumentDTO list
Collector 不负责：入库、去重、写 DB
```

**AKShare 接口**：

| 接口 | source_system |
|---|---|
| `ak.stock_info_disclosure()` | `akshare_cninfo` |
| `ak.stock_info_a_code_name()` | `akshare_a_notice` |

**核心方法**：

```python
class AnnouncementCollector:
    async def collect(self, days_back: int = 1) -> list[dict]:
        """增量抓取最近N天公告，返回 RawIntelDocumentDTO dict list"""

    def _standardize(self, raw_row, source_config) -> dict:
        """AKShare DataFrame 行 → 统一 raw_intel_document dict"""

    @staticmethod
    def build_dedupe_key(source_system: str, source_type: str, source_id: str) -> str:
        """{source_system}:{source_type}:{source_id}"""

    @staticmethod
    def compute_checksum(title: str, stock_code: str, publish_time: str) -> str:
        """md5(title + stock_code + publish_time)"""
```

**MVP 只抓**：标题、公告类型、股票代码、股票名称、发布时间、PDF URL。

**不做 PDF 下载/解析**。

**验证**：`collect(days_back=1)` 返回 ≥ 50 条，每条包含必需字段。

---

#### 6A-4：RawIntelIngestionService

| 项目 | 内容 |
|---|---|
| **文件** | `stock_processing_service/application/services/raw_intel_ingestion_service.py`（新建） |
| **依赖** | 6A-2, 6A-3 |
| **估时** | 中 |

**职责**：

```python
class RawIntelIngestionService:
    def __init__(self, gateway: DatabaseGateway):
        self.gateway = gateway

    async def ingest(self, docs: list[dict]) -> dict:
        """
        1. 逐条 compute checksum / dedupe_key
        2. 调用 gateway.upsert_raw_intel_document()
        3. ON CONFLICT (source_system, source_id) DO UPDATE
        4. 返回 {inserted: N, updated: N, skipped: N}
        """
```

**不负责**：LLM 结构化、PDF 处理、stream 投递。

**验证**：
- 首次 ingest 50 条 → inserted = 50
- 重复 ingest 相同 50 条 → inserted = 0, updated = 50（或 skipped = 50）
- 无 duplicate key 报错

---

#### 6A-5：IntelEventExtractor（公告类）

| 项目 | 内容 |
|---|---|
| **文件** | `stock_processing_service/domain/services/intel_event_extractor.py`（新建） |
| **依赖** | 6A-2 |
| **估时** | 大 |

**Phase 6A 只实现 `extract_announcement()`。** 其他接口（extract_performance / extract_research / extract_survey）预留在类中，Phase 6D/E 再实现。

**支持的公告事件类型**：

```text
major_contract         重大合同
capex_expansion        投资扩产
mna_restructuring      并购重组
shareholder_change     股权变动（增持/减持）
regulatory_penalty     监管处罚/问询
management_change      高管变动
dividend_plan          分红方案
other                  其他公告
```

**Prompt 约束**：

1. 研报/调研类 `source_org` 不得进入 theme_candidates（本阶段先行约束）
2. 输出必须包含 `evidence` 字段（保留原文关键表述）
3. 信息不足以判断时，`confidence < 0.6`，`event_level = "normal"`
4. 不强制要求 PDF 全文（只用标题 + 公告类型）

**验证**：
- "签署重大合同" → event_type="major_contract", event_level ∈ {important, critical}
- "股东减持计划" → event_type="shareholder_change", risk_points 非空
- 模糊标题 → confidence < 0.6, event_level="normal"

---

#### 6A-6：IntelStreamProducer

| 项目 | 内容 |
|---|---|
| **文件** | `stock_processing_service/application/services/intel_stream_producer.py`（新建） |
| **依赖** | 6A-2, 6A-5 |
| **估时** | 中 |

**MVP 方案**：structured_intel_event → 同步写入 news_event（`source_category='intel'`）→ 投递 `stream:events:structured`

```python
class IntelStreamProducer:
    def __init__(self, gateway: DatabaseGateway, stream_bus):
        ...

    async def produce(self, intel_event_id: int) -> str:
        """
        1. 读取 structured_intel_event
        2. 构建 news_event dict（source_category='intel', source_trace_id=...）
        3. 写入 news_event → 获得 news_event_id
        4. 构建 structured event envelope（payload.event_id = news_event_id）
        5. xadd → stream:events:structured
        6. UPDATE structured_intel_event SET stream_status='produced'
        7. 返回 stream message_id
        """

    async def produce_batch(self, stream_status: str = 'pending', limit: int = 50) -> int:
        """按 stream_status='pending' 批量投递"""
```

**Envelope 与现有 ThemeProcessor 兼容**：`payload.event_id` 对应 `news_event.id`，ThemeProcessor 通过 `gateway.get_news_event_for_match(event_id)` 查询，无需修改。

**stream_status 过滤**：Producer 按 `sie.stream_status = 'pending'` 筛选，不按 `event_level != 'normal'` 筛选。避免遗漏 "normal 但有题材价值" 的公告。

**验证**：
- 投递一条 intel event → news_event 出现 `source_category='intel'` 行
- stream:events:structured 收到消息
- ThemeProcessor 消费不报错
- structured_intel_event.stream_status 更新为 'produced'

---

#### 6A-7：PreMarketBriefBuilder 扩展

| 项目 | 内容 |
|---|---|
| **文件** | `stock_processing_service/application/services/pre_market_brief_builder.py`（修改） |
| **依赖** | 6A-6 |
| **估时** | 中 |

**新增 section**：

```python
sections = {
    # === 现有不变 ===
    "major_events": ...,
    "matched_themes": ...,
    "review_events": ...,
    "unknown_watch": ...,
    "event_driven_opportunities": ...,

    # === 新增 ===
    "company_announcements": [],   # 按 stock_code 分组的公告事件
    "earnings_alerts": [],         # Phase 6D 再填充，先空数组
    "research_highlights": [],     # Phase 6E 再填充，先空数组
    "institutional_survey": [],    # Phase 6E 再填充，先空数组

    # === 现有但扩展 ===
    "risk_alerts": [],             # 现有 + 后续 Phase 6B AlertRuleEngine 补充
    "opportunity_alerts": [],      # Phase 6B 填充
}
```

**company_announcements 数据来源**：从 `event_subject_map` 中筛选 `source_category='intel'` 的事件，按 `stock_code` 分组。

**Phase 6A 不实现**：AlertRuleEngine 的个股风险/机会判断。

**验证**：
- rebuild 后 `payload.sections.company_announcements` ≥ 5 条
- `payload.sections.earnings_alerts` 为空数组（不报错）
- 现有 section（major_events/matched_themes/opportunities）不受影响

---

#### 6A-8：Smoke Test + E2E100 回归

| 项目 | 内容 |
|---|---|
| **文件** | `stock_processing_service/tests/contract/test_phase6a_smoke.py`（新建） |
| **依赖** | 6A-1 ~ 6A-7 |
| **估时** | 中 |

**Smoke 流程**：

```text
AnnouncementCollector.collect(days_back=1)
→ RawIntelIngestionService.ingest()
→ raw_intel_document 入库
→ IntelEventExtractor.extract_announcement()
→ structured_intel_event 入库
→ IntelStreamProducer.produce()
→ news_event (source_category='intel')
→ stream:events:structured
→ ThemeProcessor / DecisionExecutor
→ PreMarketBriefBuilder.rebuild()
→ 验证 company_announcements
```

**验收标准**：

| # | 指标 | 阈值 |
|---|------|------|
| 1 | raw_intel_document_count | ≥ 50 |
| 2 | duplicate_insert_count | = 0 |
| 3 | structured_intel_event_count | ≥ 10 |
| 4 | intel_news_event_count | ≥ 10 |
| 5 | stream_produced_count | ≥ 10 |
| 6 | event_subject_map 中 source_category='intel' 记录数 | ≥ 5 |
| 7 | pre_market_brief.company_announcements | ≥ 5 |
| 8 | 新闻 E2E100 — recall@5 | ≥ 0.70 |
| 9 | 新闻 E2E100 — wrong_related | = 0 |
| 10 | 新闻 E2E100 — dead_letter | = 0 |
| 11 | 新闻 E2E100 — terminal | = 100 |
| 12 | 新闻 E2E100 — A+B stock count | ≥ 70 |

---

### Phase 6B：AlertRuleEngine

**目标**：风险/机会规则引擎输出 risk_alerts / opportunity_alerts。

| 项目 | 内容 |
|---|---|
| **文件** | `stock_processing_service/domain/services/alert_rule_engine.py`（新建） |
| | `stock_processing_service/application/services/pre_market_brief_builder.py`（修改，集成告警） |
| **依赖** | Phase 6A 完成 |
| **估时** | 中 |

**核心设计**：

```python
class AlertRuleEngine:
    """纯规则引擎，不调用 LLM。
       输入 structured_intel_event，输出 alert list。"""

    # critical risk: 业绩大幅预亏、监管处罚、重大合同终止、实控人变更、
    #                大额减持、商誉减值、ST 风险
    CRITICAL_RISK_RULES: list[Rule]

    # important risk: 业绩低于预期、问询函、毛利率下滑、现金流恶化、高管离职
    IMPORTANT_RISK_RULES: list[Rule]

    # opportunity: 重大合同金额高、新产品量产、产能扩张、业绩超预期、
    #              回购增持、研报上调
    OPPORTUNITY_RULES: list[Rule]

    def evaluate(self, intel_event: dict) -> list[dict]: ...
    def evaluate_batch(self, intel_events: list[dict]) -> list[dict]: ...
```

**验收标准**：

| # | 指标 | 阈值 |
|---|------|------|
| 1 | risk_alerts 非空 | ≥ 3 条 |
| 2 | opportunity_alerts 非空 | ≥ 3 条 |
| 3 | 严重级别分级正确 | critical / important / opportunity 无交叉错误 |

---

### Phase 6C：PDF 正文解析

目标：公告 PDF 下载 → 正文提取 → 证据页码 → 长文档分块。

### Phase 6D：业绩/财报专项

目标：业绩预告、业绩快报、年报季报的专用 prompt，财务指标抽取，业绩超预期/低预期判断。

### Phase 6E：研报/调研专项

目标：个股研报、机构调研的结构化 prompt，观点与事实分离。

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
raw_intel_document upsert（RawIntelIngestionService）
structured_intel_event insert
AnnouncementCollector 标准化（DataFrame → RawIntelDocumentDTO）
IntelEventExtractor JSON schema（公告类 8 类型覆盖）
IntelStreamProducer envelope 格式兼容性
API：GET /api/v1/pre_market_brief company_announcements 非空
```

### 13.2 Phase 6A Smoke Test

流程：

```text
AnnouncementCollector.collect(days_back=1)
→ RawIntelIngestionService.ingest()
→ raw_intel_document 入库
→ IntelEventExtractor.extract_announcement()
→ structured_intel_event 入库
→ IntelStreamProducer.produce()
→ news_event (source_category='intel')
→ stream:events:structured
→ ThemeProcessor / DecisionExecutor
→ PreMarketBriefBuilder.rebuild()
→ 前端展示 company_announcements
```

### 13.3 Phase 6A 验收门禁

| # | 指标 | 阈值 | 自动化 |
|---|------|------|--------|
| 1 | raw_intel_document_count | ≥ 50 | ✅ |
| 2 | duplicate_insert_count | = 0 | ✅ |
| 3 | structured_intel_event_count | ≥ 10 | ✅ |
| 4 | intel_news_event_count | ≥ 10 | ✅ |
| 5 | stream_produced_count | ≥ 10 | ✅ |
| 6 | event_subject_map 中 source_category='intel' 记录数 | ≥ 5 | ✅ |
| 7 | pre_market_brief.company_announcements | ≥ 5 | ✅ |
| 8 | 新闻 E2E100 — recall@5 | ≥ 0.70 | ✅ |
| 9 | 新闻 E2E100 — wrong_related | = 0 | ✅ |
| 10 | 新闻 E2E100 — dead_letter | = 0 | ✅ |
| 11 | 新闻 E2E100 — terminal | = 100 | ✅ |
| 12 | 新闻 E2E100 — A+B stock count | ≥ 70 | ✅ |

### 13.4 Phase 6B 验收门禁

| # | 指标 | 阈值 |
|---|------|------|
| 1 | risk_alerts 非空 | ≥ 3 条 |
| 2 | opportunity_alerts 非空 | ≥ 3 条 |
| 3 | 严重级别分级正确 | critical / important / opportunity 无交叉错误 |

---

## 14. 推荐开发顺序

```text
Phase 6A（8 个交付单元）：
  1. 6A-1: DDL（3 个 SQL 文件）
  2. 6A-2: PostgresManager + DatabaseGateway 方法
  3. 6A-3: AnnouncementCollector（只抓取+标准化，不依赖 DB）
  4. 6A-4: RawIntelIngestionService（去重+入库）
  5. 6A-5: IntelEventExtractor 公告类（只实现 extract_announcement）
  6. 6A-6: IntelStreamProducer（news_event 兼容写入 + stream 投递）
  7. 6A-7: PreMarketBriefBuilder company_announcements section
  8. 6A-8: Smoke Test + 新闻 E2E100 回归

Phase 6B：
  9. AlertRuleEngine
  10. PreMarketBriefBuilder 集成 risk_alerts / opportunity_alerts
  11. Phase 6B Smoke Test

Phase 6C：
  12. PDF 正文解析

Phase 6D：
  13. 业绩/财报专项 prompt + extractor

Phase 6E：
  14. 研报/调研专项 prompt + extractor
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

---

## 16. Phase 6A Checklist 状态跟踪

> 状态：🔲 待开始 | 🔄 进行中 | ✅ 已完成 | ⏸️ 暂缓 | ❌ 阻塞

### 6A-1：DDL

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 1.1 | `create_raw_intel_document.sql` 创建并执行成功 | ✅ | 2026-05-19 | stock_data_test，27 列 + 6 索引 + unique(source_system,source_id) |
| 1.2 | `create_structured_intel_event.sql` 创建并执行成功 | ✅ | 2026-05-19 | stock_data_test，24 列 + 6 索引 + FK→raw_intel_document(id) |
| 1.3 | `alter_news_event_for_intel.sql` 执行成功 | ✅ | 2026-05-19 | stock_data_test，4 字段追加，127,597 行 source_category 默认 'news' |

### 6A-2：DB Gateway

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 2.1 | `upsert_raw_intel_document()` 实现 | ✅ | 2026-05-19 | ON CONFLICT (source_system, source_id) DO UPDATE + datetime 类型转换 |
| 2.2 | `get_raw_intel_documents_by_status()` 实现 | ✅ | 2026-05-19 | 按 llm_status 查询，publish_time DESC |
| 2.3 | `update_raw_intel_llm_status()` 实现 | ✅ | 2026-05-19 | |
| 2.4 | `insert_structured_intel_event()` 实现 | ✅ | 2026-05-19 | jsonb 序列化 + datetime 转换 |
| 2.5 | `get_pending_intel_events_for_stream()` 实现 | ✅ | 2026-05-19 | JOIN raw_intel_document，WHERE stream_status = 'pending' |
| 2.6 | `update_intel_event_stream_status()` 实现 | ✅ | 2026-05-19 | |
| 2.7 | `create_news_event_with_intel()` 实现 | ✅ | 2026-05-19 | source_category='intel' + source_trace_id 贯穿 |
| 2.8 | DatabaseGateway facade 方法全部添加 | ✅ | 2026-05-19 | 写→_client，读→_read_source()，7 个方法全部委托 |

### 6A-3：AnnouncementCollector

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 3.1 | `collect(days_back)` 实现 | 🔲 | | 支持增量抓取 |
| 3.2 | AKShare `stock_info_disclosure()` 接入 | 🔲 | | 巨潮资讯 |
| 3.3 | AKShare `stock_info_a_code_name()` 接入 | 🔲 | | 沪深京A股公告 |
| 3.4 | `_standardize()` 列名自动适配 | 🔲 | | 复用 _find_column 模式 |
| 3.5 | `build_dedupe_key()` / `compute_checksum()` 实现 | 🔲 | | 静态方法 |
| 3.6 | 不依赖 DatabaseGateway | 🔲 | | 只输出 dict list，不写 DB |

### 6A-4：RawIntelIngestionService

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 4.1 | `ingest(docs)` 实现 | 🔲 | | 逐条计算 checksum/dedupe_key 后 upsert |
| 4.2 | 返回统计 `{inserted, updated, skipped}` | 🔲 | | |
| 4.3 | 重复 ingest 不产生重复行 | 🔲 | | ON CONFLICT DO UPDATE |
| 4.4 | 单元测试覆盖 | 🔲 | | |

### 6A-5：IntelEventExtractor（公告类）

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 5.1 | `extract_announcement()` 实现 | 🔲 | | 公告类 prompt 模板 |
| 5.2 | 8 种公告事件类型支持 | 🔲 | | major_contract, capex_expansion, mna_restructuring, shareholder_change, regulatory_penalty, management_change, dividend_plan, other |
| 5.3 | 输出 Schema 符合 Section 7.2 定义 | 🔲 | | event_type, event_level, summary, impact_assessment, risk_points, theme_candidates, confidence, evidence |
| 5.4 | confidence < 0.6 时 event_level=normal | 🔲 | | 信息不足不强行判断 |
| 5.5 | evidence 字段非空 | 🔲 | | 保留原文引用 |

### 6A-6：IntelStreamProducer

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 6.1 | `produce(intel_event_id)` 实现 | 🔲 | | 单条投递 |
| 6.2 | `produce_batch(limit)` 实现 | 🔲 | | 按 stream_status='pending' 批量 |
| 6.3 | news_event 兼容写入（source_category='intel'） | 🔲 | | source_trace_id 贯穿 |
| 6.4 | structured event envelope 与 ThemeProcessor 兼容 | 🔲 | | payload.event_id = news_event.id |
| 6.5 | xadd → stream:events:structured 成功 | 🔲 | | |
| 6.6 | stream_status 更新为 'produced' | 🔲 | | |

### 6A-7：PreMarketBriefBuilder 扩展

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 7.1 | `company_announcements` section 新增 | 🔲 | | 按 stock_code 分组 intel 事件 |
| 7.2 | `earnings_alerts` section 新增（空数组） | 🔲 | | Phase 6D 填充 |
| 7.3 | `research_highlights` section 新增（空数组） | 🔲 | | Phase 6E 填充 |
| 7.4 | `institutional_survey` section 新增（空数组） | 🔲 | | Phase 6E 填充 |
| 7.5 | `_load_intel_events()` 从 event_subject_map 读取 | 🔲 | | WHERE source_category='intel' |
| 7.6 | 现有 section 不受影响 | 🔲 | | major_events / matched_themes / opportunities 回归正常 |

### 6A-8：Smoke Test + 回归

| # | 检查项 | 状态 | 完成日期 | 备注 |
|---|--------|------|----------|------|
| 8.1 | Smoke 脚本：全链路验证 | 🔲 | | AnnouncementCollector → PreMarketBriefBuilder |
| 8.2 | raw_intel_document_count ≥ 50 | 🔲 | | |
| 8.3 | duplicate_insert_count = 0 | 🔲 | | 重复 ingest 不产生重复行 |
| 8.4 | structured_intel_event_count ≥ 10 | 🔲 | | LLM 结构化成功 |
| 8.5 | intel_news_event_count ≥ 10 | 🔲 | | news_event 兼容写入 |
| 8.6 | stream_produced_count ≥ 10 | 🔲 | | stream:events:structured 投递 |
| 8.7 | event_subject_map intel 记录 ≥ 5 | 🔲 | | 经 ThemeProcessor → DecisionExecutor |
| 8.8 | company_announcements ≥ 5 | 🔲 | | 盘前必读 section |
| 8.9 | E2E100 recall@5 ≥ 0.70 | 🔲 | | 新闻基线不回退 |
| 8.10 | E2E100 wrong_related = 0 | 🔲 | | |
| 8.11 | E2E100 dead_letter = 0 | 🔲 | | |
| 8.12 | E2E100 terminal = 100 | 🔲 | | |
| 8.13 | E2E100 A+B stock count ≥ 70 | 🔲 | | |
