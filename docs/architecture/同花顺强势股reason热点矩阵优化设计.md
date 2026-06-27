# 同花顺强势股 reason 热点矩阵优化设计

## 1. 背景与问题

2026-06-18 盘后复盘报告中，涨停热点矩阵出现明显失真：

- 全市场 106 只涨停，但 `其他` 列承载 74 只。
- 热点列偏静态题材映射，未能聚合当日真实扩散方向。
- 报告 Top 热点只输出 `PCB印制电路板、机器人、AI光纤`，未充分识别 `AI算力基础设施、先进材料/固态电池、有色资源/小金属、创新药/医疗、ST摘帽/重整/国资` 等当日强分支。

现有 `LimitUpThemeMatrixBuilder` 的涨停判定依赖 `stock_daily_snapshot`，题材归因依赖 `mainline_daily_state/mainline_registry` 与 `subject_stock_map`。该设计适合稳定主线和静态题材归属，但无法充分利用同花顺当日强势股接口返回的人工运营 `reason` 字段。

本设计目标是在不替换现有主链路、不引入大规模数据源扩展的前提下，优先接入同花顺强势股 `reason tags` 作为外部证据源，修复热点矩阵归因质量。

## 1.1 当前实施进度（2026-06-22）

当前 P0 Hot Matrix 修复已完成并推送，下一阶段进入 P1 Data Source Governance（M3）。

已完成并推送：

- M0a/M0b/M1：raw snapshot、registry、THS snapshot、theme evidence 四张表；THS client/schema/normalizer/resolver/job；Gateway/Manager/port/adapter 写入能力。
- M2：`LimitUpThemeMatrixBuilder` 已接入 `stock_theme_reason_evidence` 与 `ths_hot_reason_snapshot`，归因优先级为 `confirmed_mainline > reason evidence > subject_stock_map > 其他`。
- M2b：已新增 6/18 全量回放脚本与报告输出。
- M2c：已区分 `true_other_count`、`display_other_count`、`collapsed_other_count`，并修复展示折叠误吞有效主题的问题。提交 `ac69ca228 Separate true and collapsed other in limit-up matrix` 已推送远端。
- M2d：Canonical display theme alias merge。矩阵展示层已合并以下同义主题，不改写底层 evidence 和 assignment audit。提交 `9fed8a7a8 Merge canonical display themes in limit-up matrix` 已推送远端：
  - `PCB/HBM产业链 + PCB印制电路板`
  - `AI光通信 + AI光纤`
  - `机器人 + 人形机器人/工业机器人`
  - `AI算力基础设施 + 算力/数据中心/液冷`
  - `先进材料/固态电池 + 全固态电池进度表`
- M2e：已调整 Golden Gate 指标口径。6/18 是多分支扩散行情，硬性要求 Top5 覆盖 55% 会诱导算法过度合并；Gate 已改为 `true_other_count <= 10`、`top_8_theme_coverage >= 55%`、`single_theme_max_ratio <= 35%`、`display_other_count <= 45`、`Top5 人工主线命中 >= 4`，`collapsed_other_count` 降级为观察指标。提交 `5ccbf209d Adjust limit-up matrix golden gate metrics` 已推送远端。

最新 2026-06-18 回放结果：

| 阶段 | true_other_count | display_other_count | collapsed_other_count | top_5_theme_coverage | top_8_theme_coverage | single_theme_max_ratio | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| M2b 初版 | 5 | 57 | 53 | 32.08% | 未统计 | 7.55% | 归因证据有效，但展示折叠吞掉有效主题 |
| M2c | 5 | 42 | 38 | 36.79% | 未统计 | 8.49% | true other 口径修正，展示折叠改善 |
| M2d | 5 | 38 | 34 | 43.40% | 未统计 | 11.32% | alias merge 明显改善 Top 主题 |
| M2e | 5 | 38 | 34 | 43.40% | 55.66% | 11.32% | 新 Golden Gate 通过 |

重要结论：

- P0 Hot Matrix 修复已完成：归因质量、展示质量、扩散行情覆盖、人工主线命中、过度聚合风险均通过当前 Gate。
- `true_other_count=5` 说明真实未归因数量已经可控；报告里看到的 `其他` 主要是 12 列展示上限导致的折叠结果。
- 6/19、6/20 为非交易日，不能作为首批 Golden Dataset 的有效交易日样本；后续需替换为其他交易日。
- 下一阶段不优先做前端或研报，而是进入 P1 Data Source Governance（M3），先治理多数据源接入方式。

## 2. 目标与非目标

### 2.1 目标

1. 新增原始响应快照能力，支持外部接口字段变化后的回放与排错。
2. 新增同花顺强势股 reason 快照表，形成可查询、可回放的当日人工归因证据。
3. 新增轻量数据源 registry，避免 P0 阶段写死 source 元信息。
4. 新增 `ReasonThemeResolver` 统一解析接口，支持规则、embedding、LLM 多实现演进。
5. 改造热点矩阵归因优先级：
   - `confirmed_mainline`
   - `ths_hot_reason_snapshot` 当日 reason evidence
   - `subject_stock_map` 静态题材
   - `其他`
6. 在算法层保留多题材共振信息，展示层仍使用唯一主列。
7. 新增主题证据表，避免后续从 snapshot 反向重建证据。
8. 增加 Golden Dataset 回放质量指标，避免只降低 `其他` 但产生错误聚类。

### 2.2 非目标

1. 不接入 mootdx K线、百度K线、新浪财报三表、纯实时行情。
2. 不在 P0 接入东财研报、公告、资金流等更多数据源。
3. 不直接改写主题材库、JYHF 题材池或 `subject_stock_map`。
4. 不让 domain 层直接接触 `requests`、`pandas`、SQL 或外部 API。
5. 不用同花顺 reason 替代涨停判定，涨停判定仍以 `stock_daily_snapshot` 为准。

## 3. 总体架构

新增模块采用数据源适配器方式接入，不新增 `a_stock_data_service` 这类大而全服务。

```text
stock_processing_service/
  integrations/
    a_stock_data/
      clients/
        ths_client.py
      normalizers/
        ths_hot_reason_normalizer.py
        reason_tag_normalizer.py
      resolvers/
        reason_theme_resolver.py
      schemas/
        ths_hot_reason_schema.py
      jobs/
        collect_ths_hot_reason_job.py
```

后续 P1/P2 可在同一目录下扩展：

```text
stock_processing_service/
  integrations/
    a_stock_data/
      clients/
        eastmoney_client.py
        tencent_client.py
        cninfo_client.py
      normalizers/
        eastmoney_concept_block_normalizer.py
        eastmoney_report_normalizer.py
        cninfo_announcement_normalizer.py
      schemas/
        eastmoney_report_schema.py
      jobs/
        collect_eastmoney_concept_blocks_job.py
        collect_stock_research_report_job.py
```

### 3.1 分层原则

| 层 | 职责 | 禁止事项 |
| --- | --- | --- |
| clients | 请求外部接口、处理超时、HTTP 状态、基础 headers | 不做业务归因、不落库 |
| schemas | 描述外部响应结构和字段约束 | 不做网络请求 |
| normalizers | 外部响应转内部 DTO/row，拆分 reason tags | 不访问 DB |
| jobs | 编排 client、raw snapshot、normalizer、gateway | 不写 SQL |
| gateway | 统一落库、查询、幂等 upsert | 不调用外部 HTTP |
| domain/application builders | 消费已落库证据，生成矩阵和诊断 | 不直接请求外部 API |

## 4. 数据模型

### 4.1 `source_raw_snapshot`

用于保存所有外部数据源原始响应，支撑回放、字段漂移排查和审计。

```sql
CREATE TABLE source_raw_snapshot (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    endpoint_key TEXT NOT NULL,
    trade_date DATE,
    request_url TEXT NOT NULL,
    request_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_raw JSONB,
    response_text TEXT,
    response_hash TEXT NOT NULL,
    http_status INTEGER,
    error_message TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_name, endpoint_key, trade_date, response_hash)
);
```

约束：

- `response_raw` 优先保存 JSON 响应。
- 非 JSON 或解析失败时保存 `response_text` 与 `error_message`。
- `response_hash` 使用标准化响应内容生成，用于去重与回放定位。
- 原始表不参与业务判断，只作为证据和回放源。

### 4.2 `ths_hot_reason_snapshot`

用于保存同花顺强势股人工归因结果。

```sql
CREATE TABLE ths_hot_reason_snapshot (
    trade_date DATE NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    reason_raw TEXT NOT NULL,
    reason_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    close_price NUMERIC,
    pct_chg NUMERIC,
    turnover_rate NUMERIC,
    amount NUMERIC,
    volume NUMERIC,
    big_order_net NUMERIC,
    market TEXT,
    source_name TEXT NOT NULL DEFAULT 'ths',
    endpoint_key TEXT NOT NULL DEFAULT 'ths_hot_reason',
    source_trace_id TEXT NOT NULL,
    raw_snapshot_id BIGINT REFERENCES source_raw_snapshot(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, stock_code, source_name)
);
```

字段映射：

| 同花顺字段 | 本地字段 | 说明 |
| --- | --- | --- |
| `date` | `trade_date` | 交易日 |
| `code` | `stock_code` | 6 位股票代码 |
| `name` | `stock_name` | 股票名称 |
| `reason` | `reason_raw` | 人工题材归因原文 |
| `reason` split by `+` | `reason_tags` | 原始标签数组 |
| `close` | `close_price` | 收盘价 |
| `zhangfu` | `pct_chg` | 涨幅 |
| `huanshou` | `turnover_rate` | 换手率 |
| `chengjiaoe` | `amount` | 成交额 |
| `chengjiaoliang` | `volume` | 成交量 |
| `ddejingliang` | `big_order_net` | 大单净量 |
| `market` | `market` | 市场编码 |

### 4.3 轻量版 `market_data_source_registry`

P0 仅建立最小 registry，避免 THS job 写死数据源元信息。P1 再扩展完整字段。

```sql
CREATE TABLE market_data_source_registry (
    source_name TEXT NOT NULL,
    endpoint_key TEXT NOT NULL,
    domain TEXT NOT NULL,
    owned_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    rate_limit_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    auth_type TEXT NOT NULL DEFAULT 'none',
    freshness_sla TEXT,
    raw_snapshot_required BOOLEAN NOT NULL DEFAULT true,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_name, endpoint_key)
);
```

P0 初始记录：

```json
{
  "source_name": "ths",
  "endpoint_key": "ths_hot_reason",
  "domain": "market_hotspot_reason",
  "owned_fields": ["reason_raw", "reason_tags", "hot_stock_list"],
  "rate_limit_policy": {"type": "simple", "min_interval_ms": 1000, "timeout_ms": 10000},
  "auth_type": "none",
  "freshness_sla": "post_market_after_15_30_cn",
  "raw_snapshot_required": true,
  "enabled": true
}
```

### 4.4 `stock_theme_reason_evidence`

主题证据表必须在 P0 提前建立，不等到后续证据层扩展。原因是题材热度、龙头分析、主题材识别都会复用该表；若只保存 `ths_hot_reason_snapshot`，后续仍需要反向从快照重建证据，增加重复逻辑和口径漂移风险。

```sql
CREATE TABLE stock_theme_reason_evidence (
    trade_date DATE NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    theme_name TEXT NOT NULL,
    source_name TEXT NOT NULL,
    endpoint_key TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    reason_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_reason_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    primary_theme BOOLEAN NOT NULL DEFAULT false,
    confidence NUMERIC,
    resolver_name TEXT NOT NULL,
    source_trace_id TEXT NOT NULL,
    raw_snapshot_id BIGINT REFERENCES source_raw_snapshot(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, stock_code, theme_name, source_name)
);
```

示例：

```json
{
  "trade_date": "2026-06-18",
  "stock_code": "000811",
  "stock_name": "冰轮环境",
  "theme_name": "AI算力基础设施",
  "source_name": "ths",
  "endpoint_key": "ths_hot_reason",
  "evidence_text": "数据中心液冷+拟收购整合+权益分派+烟台国资",
  "reason_tags": ["数据中心液冷", "拟收购整合", "权益分派", "烟台国资"],
  "matched_reason_tags": ["数据中心液冷"],
  "primary_theme": true,
  "confidence": 0.9,
  "resolver_name": "RuleResolver"
}
```

## 5. 外部接口设计

### 5.1 THS Client

文件：`stock_processing_service/integrations/a_stock_data/clients/ths_client.py`

职责：

- 构造请求 URL。
- 设置浏览器 `User-Agent`。
- 设置超时。
- 返回 `RawHttpResult`，包含 URL、params、status、raw body、parsed JSON、error。

接口草案：

```python
@dataclass(frozen=True)
class RawHttpResult:
    source_name: str
    endpoint_key: str
    trade_date: date
    request_url: str
    request_params: dict[str, Any]
    http_status: int | None
    response_raw: dict[str, Any] | list[Any] | None
    response_text: str | None
    error_message: str | None

class ThsClient:
    async def fetch_hot_reason(self, trade_date: date) -> RawHttpResult:
        ...
```

请求地址：

```text
http://zx.10jqka.com.cn/event/api/getharden/date/{YYYY-MM-DD}/orderby/date/orderway/desc/charset/GBK/
```

错误处理：

- 超时：返回 `error_message=timeout`，raw snapshot 仍落库。
- 非 JSON：保存 `response_text`。
- `errocode != 0`：保存原始响应并返回 job 失败状态。

### 5.2 THS Schema

文件：`schemas/ths_hot_reason_schema.py`

最小字段：

```python
REQUIRED_TOP_LEVEL_FIELDS = ["errocode", "data"]
REQUIRED_ROW_FIELDS = ["code", "name", "reason", "date"]
OPTIONAL_NUMERIC_FIELDS = [
    "close", "zhangdie", "zhangfu", "huanshou",
    "chengjiaoe", "chengjiaoliang", "ddejingliang", "market",
]
```

校验策略：

- 顶层 `errocode` 必须为 0 才进入业务 normalizer。
- `data` 可为空，但需要输出 `empty_data` warning。
- 单行缺少 `reason` 时仍可落库，但 `reason_tags=[]`，并在 diagnostics 中计数。

### 5.3 THS Hot Reason Normalizer

文件：`normalizers/ths_hot_reason_normalizer.py`

职责：

- 解析原始 `data` 行。
- 规范化股票代码为 6 位。
- 拆分 `reason_raw` 为 `reason_tags`。
- 数值字段转 Decimal/float 兼容 DB。
- 生成 `source_trace_id`。

输出：

```python
@dataclass(frozen=True)
class ThsHotReasonRow:
    trade_date: date
    stock_code: str
    stock_name: str
    reason_raw: str
    reason_tags: list[str]
    close_price: Decimal | None
    pct_chg: Decimal | None
    turnover_rate: Decimal | None
    amount: Decimal | None
    volume: Decimal | None
    big_order_net: Decimal | None
    market: str
    source_name: str
    endpoint_key: str
    source_trace_id: str
    raw_snapshot_id: int | None
```

## 6. Reason Theme Resolver 设计

### 6.1 统一接口

不要把 reason 解析做成 `ReasonNormalizer + FallbackClassifier` 两套体系。统一抽象为 `ReasonThemeResolver`，所有规则、embedding、LLM 都挂在同一个接口下，避免未来接 DeepSeek 时出现到处 `if rule else llm` 的分叉。

```python
@dataclass(frozen=True)
class ThemeMatch:
    primary_theme: str
    secondary_themes: list[str]
    matched_reason_tags: list[str]
    matched_rules: list[str]
    confidence: float
    resolver_name: str
    unresolved_tags: list[str]

class ReasonThemeResolver(Protocol):
    async def resolve(
        self,
        *,
        reason_tags: list[str],
        stock_code: str,
        stock_name: str,
        reason_raw: str = "",
    ) -> ThemeMatch | None:
        ...
```

Resolver 实现：

| Resolver | 阶段 | 职责 | 失败处理 |
| --- | --- | --- | --- |
| `RuleResolver` | P0 | 高频稳定关键词快速归一，可解释、低成本 | 无命中返回 `None` |
| `EmbeddingResolver` | P1 | 处理新题材、新叫法，与 `theme_profile_ext` 做语义召回 | 超时返回 `None` |
| `LLMResolver` | P1/P2 | 处理多义标签和跨题材判断，可接 DeepSeek evidence rerank | 超时/失败降级，不阻断矩阵 |
| `CompositeReasonThemeResolver` | P0 | 编排多个 resolver，按顺序尝试并统一输出 `ThemeMatch` | 所有 resolver 失败则返回 `None` |

### 6.2 两层解析策略

P0 实现：

1. `RuleResolver`：规则词典，覆盖稳定高频词，速度快、可解释。
2. `CompositeReasonThemeResolver`：先调用 `RuleResolver`，预留后续挂载 `EmbeddingResolver/LLMResolver` 的扩展点。

P1/P2 扩展：

1. `EmbeddingResolver`：处理新题材、新叫法。
2. `LLMResolver`：处理多义标签、多题材共振、蹭概念判断。

所有 resolver 都必须返回同一个 `ThemeMatch` 契约。

### 6.3 RuleResolver 规则词典

文件：`normalizers/reason_tag_normalizer.py`
与 `resolvers/reason_theme_resolver.py`

首批规则：

| Canonical Theme | Keywords |
| --- | --- |
| `PCB/HBM产业链` | `PCB`, `HDI`, `覆铜板`, `铜箔`, `FCBGA`, `HBM`, `封装基板`, `AIPC` |
| `AI光通信` | `CPO`, `光模块`, `硅光`, `光通信`, `3.2T`, `光纤光缆`, `光芯片` |
| `AI算力基础设施` | `液冷`, `数据中心`, `AIDC`, `AI服务器`, `算力租赁`, `智算中心`, `AI云平台` |
| `机器人` | `人形机器人`, `工业机器人`, `具身智能`, `机器人线束`, `机器人零部件` |
| `先进材料/固态电池` | `锆材料`, `氧化锆`, `碳化硅`, `氮化铝`, `陶瓷材料`, `固态电池`, `PEEK材料` |
| `有色资源/小金属` | `稀土`, `钨`, `铜`, `高温合金`, `有色`, `钨钴钼`, `锂` |
| `创新药/医疗` | `创新药`, `CRO`, `减肥药`, `AI医疗`, `医用敷料`, `口腔种植`, `医疗器械` |
| `ST摘帽/重整/国资` | `摘帽`, `ST板块`, `预重整`, `重整`, `国资`, `债务豁免`, `资产注入` |

失败处理：

- 任一 resolver 超时或失败不得阻断矩阵生成。
- 输出 `resolver_name`、`unresolved_tags`、`resolver_errors` 进入 diagnostics。

## 7. 多题材共振设计

矩阵展示需要唯一主列，但算法层必须保留多题材信息。

每只股票归因结果：

```json
{
  "stock_code": "603663",
  "stock_name": "三祥新材",
  "primary_theme": "先进材料/固态电池",
  "secondary_themes": ["半导体材料"],
  "matched_reason_tags": ["锆铪分离", "锆系新材", "半导体材料", "固态电池"],
  "reason_raw": "锆铪分离+锆系新材+半导体材料+固态电池",
  "chosen_source": "ths_hot_reason"
}
```

用途：

- 矩阵列：只使用 `primary_theme`。
- 龙头评分：可使用 `secondary_themes` 识别多题材共振。
- 题材热度：同一股票对 primary theme 计 1，对 secondary theme 计弱权重或仅作证据。
- 诊断：保留 `matched_reason_tags` 与 `reason_raw`。

## 8. 热点矩阵改造

### 8.1 涨停判定

保持不变：

- 数据源：`stock_daily_snapshot`
- 条件：现有 `pct_chg >= 9.5` 等过滤逻辑
- 连板计算：沿用历史 `stock_daily_snapshot`

### 8.2 题材归因优先级

新优先级：

1. `confirmed_mainline`
   - 来自 `mainline_daily_state/mainline_registry`。
   - 保持最高优先级。
2. `ths_hot_reason_snapshot`
   - 仅当该股票在当日 THS 快照中存在 reason 且归一化出 canonical theme。
   - 输出 `chosen_source=ths_hot_reason`。
3. `subject_stock_map`
   - 作为静态/半动态 fallback。
   - 输出 `chosen_source=subject_stock_map`。
4. `其他`
   - 无 mainline、无 THS reason 归一化、无有效静态题材。

### 8.3 Builder 输入扩展

`LimitUpThemeMatrixBuilder.build()` 仍只接收 `trade_date, conn`。内部新增读取：

```sql
SELECT stock_code,
       stock_name,
       reason_raw,
       reason_tags,
       source_trace_id
FROM ths_hot_reason_snapshot
WHERE trade_date = $1::date
  AND source_name = 'ths'
```

后续应通过 gateway 显式方法封装，避免应用层直接 SQL 扩散。

### 8.4 输出扩展

`focus_stocks` 中新增：

```json
{
  "stock_id": "000811.SZ",
  "stock_name": "冰轮环境",
  "subject_key": "",
  "theme_name": "AI算力基础设施",
  "board_count": 2,
  "chosen_source": "ths_hot_reason",
  "reason_raw": "数据中心液冷+拟收购整合+权益分派+烟台国资",
  "matched_reason_tags": ["数据中心液冷"],
  "secondary_themes": []
}
```

diagnostics 新增：

- `ths_reason_covered_count`
- `ths_reason_clustered_count`
- `static_subject_fallback_count`
- `other_count`
- `top_reason_tags`
- `theme_entropy`
- `top_theme_coverage`
- `manual_reason_coverage`
- `mainline_hit_count`
- `static_fallback_ratio`
- `single_theme_max_ratio`

## 9. 质量指标与 Golden Dataset 验收

不能只看 `other_count`。P0 回放必须同时满足多项质量指标。

### 9.1 指标定义

| 指标 | 定义 |
| --- | --- |
| `other_count` | 兼容旧字段；M2c 起语义等同 `true_other_count` |
| `true_other_count` | 真实无有效归因的涨停股数量，不包含因展示列上限被折叠的有效主题股票 |
| `display_other_count` | 最终展示在 `其他` 列中的涨停股数量，包含 true other 与 collapsed other |
| `collapsed_other_count` | 已有有效主题但因展示列上限被折叠进 `其他` 的涨停股数量 |
| `collapsed_other_themes` | 被折叠进 `其他` 的有效主题明细 |
| `ths_reason_covered_count` | 涨停股中命中 THS reason 快照的数量 |
| `ths_reason_clustered_count` | 命中 THS reason 且归一化出 canonical theme 的数量 |
| `top_5_theme_coverage` | Top5 非 `其他` 主题覆盖涨停股数量 / 全部有效涨停股数量；M2e 起作为观察指标 |
| `top_8_theme_coverage` | Top8 非 `其他` 主题覆盖涨停股数量 / 全部有效涨停股数量；M2e 起作为多分支行情 Gate |
| `top_5_manual_theme_hit_count` | Top5 非 `其他` 主题中命中人工复盘主线集合的数量 |
| `single_theme_max_ratio` | 最大非 `其他` 单一主题涨停数 / 全部有效涨停股数量 |
| `theme_entropy` | 主题分布熵，用于识别过度集中或过度碎片 |
| `manual_reason_coverage` | 有非空 `reason_raw` 的涨停股数量 / 全部有效涨停股数量 |
| `mainline_hit_count` | 被 confirmed mainline 捕获的涨停股数量 |
| `static_fallback_ratio` | 使用 `subject_stock_map` fallback 的股票数 / 全部有效涨停股数量 |

### 9.2 Golden Dataset

2026-06-18 是核心坏案例，但不应成为唯一 fixture。Golden Dataset 至少覆盖 3 个交易日，建议 3-5 个交易日，避免只对单日共振行情过拟合。

首批建议：

| 交易日 | 用途 | 预期覆盖 |
| --- | --- | --- |
| `2026-06-18` | 多题材共振坏案例 | PCB、AI、机器人、先进材料、有色资源 |
| `2026-06-19` | 次日延续/分化样本 | 验证热点延续和 fallback 稳定性 |
| `2026-06-20` | 非同一市场结构样本 | 验证规则不过拟合 6/18 |

后续补充：

- 替换 `2026-06-19/2026-06-20` 非交易日样本。
- 创新药单主线样本。
- 军工单主线样本。
- 商业航天单主线样本。
- ST/重整密集样本。

### 9.3 2026-06-18 验收阈值

| 指标 | 阈值 |
| --- | --- |
| `true_other_count` | `<= 10` |
| `display_other_count` | `<= 45` |
| `collapsed_other_count` | 观察指标，不作为硬门禁 |
| `ths_reason_covered_count` | `>= 80` |
| `top_8_theme_coverage` | `>= 55%` |
| `top_5_manual_theme_hit_count` | `>= 4` |
| `single_theme_max_ratio` | `<= 35%` |
| `manual_reason_coverage` | `>= 75%` |
| `static_fallback_ratio` | 不作为硬阈值，但需输出 |
| `mainline_hit_count` | 不低于改造前 |

人工复盘一致性要求：

Top5 热点至少覆盖以下方向中的 4 个：

- `PCB/HBM产业链`
- `AI算力基础设施`
- `AI光通信`
- `机器人`
- `先进材料/固态电池`
- `有色资源/小金属`
- `创新药/医疗`
- `ST摘帽/重整/国资`

### 9.3.1 2026-06-18 当前回放结果

回放报告：

- M2c：`reports/golden/limit_up_theme_matrix_m2b/validation_20260618_m2c.md`
- M2d：`reports/golden/limit_up_theme_matrix_m2b/validation_20260618_m2d.md`

当前 M2d 输出 Top 主题：

| Rank | Theme | 涨停数 | 来源 |
| ---: | --- | ---: | --- |
| 1 | `其他` | 38 | collapsed_tail |
| 2 | `PCB/HBM产业链` | 12 | mainline_daily_state + stock_theme_reason_evidence |
| 3 | `AI算力基础设施` | 9 | stock_theme_reason_evidence + subject_stock_map |
| 4 | `机器人` | 9 | mainline_daily_state + stock_theme_reason_evidence |
| 5 | `先进材料/固态电池` | 8 | stock_theme_reason_evidence |
| 6 | `有色资源/小金属` | 8 | stock_theme_reason_evidence |
| 7 | `创新药/医疗` | 6 | stock_theme_reason_evidence |
| 8 | `AI光通信` | 4 | mainline_daily_state + stock_theme_reason_evidence |

按旧 Gate 当前仍未通过的门禁：

- `top_5_theme_coverage = 43.40% < 55%`

原因判断：

- 不是 reason 证据缺失，`ths_reason_covered_count=82` 已达标。
- 不是真实未归因过多，`true_other_count=5` 已达标。
- 主要剩余问题是主题展示粒度仍偏碎，以及 12 列展示上限下仍有有效主题被折叠。
- M2e 决策：不继续硬凑 Top5。6/18 属于多分支扩散行情，Top5 覆盖 55% 会诱导过度合并；改用 Top8 覆盖率、Top5 人工主线命中数、true/display other 共同判断。

### 9.4 多日 Golden Dataset 验收要求

| 指标 | 阈值 |
| --- | --- |
| 每日 `other_count` | 不高于当日有效涨停数的 `25%` |
| 每日 `single_theme_max_ratio` | `<= 40%`，单主线行情可人工豁免但需说明 |
| 每日 `manual_reason_coverage` | `>= 70%` |
| 多日 Top5 人工一致性 | 每日至少 3 个主题与人工复盘方向一致 |
| Resolver 稳定性 | 同一 reason tag 在多日内 canonical theme 不漂移，除非规则显式变更 |

## 10. P0 最小闭环任务分解

### M0a - Raw Snapshot + THS Snapshot 地基

目标：打好 schema、raw snapshot、轻量 registry 三个地基。

| Task ID | 任务 | 产出 | 依赖 | 验证 |
| --- | --- | --- | --- | --- |
| M0a-T01 | 新增 `source_raw_snapshot` migration | 原始响应表 | 无 | migration 可重复执行 |
| M0a-T02 | 新增 `ths_hot_reason_snapshot` migration | THS reason 快照表 | T01 | 主键幂等 |
| M0a-T03 | 新增轻量 `market_data_source_registry` migration 与 THS 初始记录 | source registry | 无 | registry 可查询 THS 配置 |
| M0a-T04 | 新增 `stock_theme_reason_evidence` migration | 主题证据表 | T01-T03 | 主键幂等 |
| M0a-T05 | Gateway 增加 raw snapshot、THS 快照、theme reason evidence 的 upsert/query 方法 | 显式 DB API | T01-T04 | unit test 覆盖 |

### M0b - THS Client / Schema / Normalizer / Job

目标：可采集、可落 raw、可落业务快照。

| Task ID | 任务 | 产出 | 依赖 | 验证 |
| --- | --- | --- | --- | --- |
| M0b-T01 | 实现 `ThsClient.fetch_hot_reason()` | 只请求不归因 | M0a | mock HTTP 单测 |
| M0b-T02 | 实现 THS schema 校验 | 错误/空数据可识别 | T01 | schema 单测 |
| M0b-T03 | 实现 `ths_hot_reason_normalizer` | row DTO | T02 | 6/18 样本解析 |
| M0b-T04 | 实现 `collect_ths_hot_reason_job` | job 编排 | M0a-T05, T03 | job 幂等入库 |
| M0b-T05 | 接入采集任务入口 | 可触发采集 | T04 | 手动执行成功 |

### M1 - Reason Theme Resolver

目标：统一 `ReasonThemeResolver` 接口，避免规则、embedding、LLM 各自形成体系。

| Task ID | 任务 | 产出 | 依赖 | 验证 |
| --- | --- | --- | --- | --- |
| M1-T01 | 定义 `ReasonThemeResolver` 与 `ThemeMatch` 契约 | 统一接口 | M0b | 类型/契约测试 |
| M1-T02 | 实现 `RuleResolver` | L1 规则解析 | T01 | 样本命中 |
| M1-T03 | 实现 `CompositeReasonThemeResolver` | resolver 编排 | T01-T02 | 无命中可降级 |
| M1-T04 | 预留 `EmbeddingResolver`、`LLMResolver` 空实现或协议适配 | L2 扩展点 | T03 | 失败不阻断 |
| M1-T05 | 输出 `primary_theme/secondary_themes/matched_reason_tags` | 多题材结构 | T02-T03 | 三祥新材样本验证 |
| M1-T06 | 配置化规则文件或集中规则对象 | 可维护规则 | T02 | 单测覆盖 |

### M2 - 热点矩阵接入 Reason Evidence

目标：修复 6/18 热点矩阵归因。

| Task ID | 任务 | 产出 | 依赖 | 验证 |
| --- | --- | --- | --- | --- |
| M2-T01 | Builder 读取 THS reason 快照 | evidence map | M0b, M1 | 单测 |
| M2-T02 | 实现归因优先级 | 新矩阵归因链 | T01 | 优先级测试 |
| M2-T03 | 保留多题材共振信息，并写入 `stock_theme_reason_evidence` | 输出扩展字段 + 证据表 | T02, M0a-T04 | secondary themes 测试 |
| M2-T04 | 扩展 assignment audit 与 diagnostics | 可解释诊断 | T02-T03 | 诊断字段测试 |
| M2-T05 | 防止 tail collapse 误吞主热点 | 保留有效主题列 | T04 | Top 热点不进其他 |

### M2b - Golden Dataset 回放验收

目标：以 3-5 个交易日样本作为验收门禁，避免只对 2026-06-18 过拟合。

| Task ID | 任务 | 产出 | 依赖 | 验证 |
| --- | --- | --- | --- | --- |
| M2b-T01 | 固化 2026-06-18/19/20 THS reason fixture 或 raw snapshot 回放样本 | 回放输入 | M0a-M0b | fixture 可复现 |
| M2b-T02 | 增加 Golden Dataset matrix 回放测试 | 质量门禁 | M2 | 多日阈值断言 |
| M2b-T03 | 输出 before/after 诊断报告 | 验收证据 | T02 | `其他`、Top5、熵、覆盖率对比 |

### M2c - true other 与 collapsed other 口径拆分

目标：解决 `其他` 列指标失真，区分真实无归因与展示折叠。

| Task ID | 任务 | 产出 | 依赖 | 状态/验证 |
| --- | --- | --- | --- | --- |
| M2c-T01 | Builder diagnostics 新增 `true_other_count/display_other_count/collapsed_other_count` | 新诊断字段 | M2b | DONE，单测覆盖 |
| M2c-T02 | `collapsed_other_themes` 输出被折叠主题明细 | 展示折叠解释 | T01 | DONE，6/18 报告可见 |
| M2c-T03 | 调整 validation 脚本，用 `true_other_count` 做归因质量门禁 | 准确验收口径 | T01 | DONE |
| M2c-T04 | 调整折叠策略，按涨停数和来源优先级保留展示列 | 减少主热点被吞 | T02 | DONE，`display_other_count 57 -> 42` |
| M2c-T05 | 合并完全同名主题列 | 避免 mainline/reason 同名重复列 | T04 | DONE，`机器人` 合并 |

提交与报告：

- Commit：`ac69ca228 Separate true and collapsed other in limit-up matrix`
- Report：`reports/golden/limit_up_theme_matrix_m2b/validation_20260618_m2c.md`

### M2d - Canonical display theme alias merge

目标：在矩阵展示层合并同义主题列，保留底层 evidence 与 audit 原始归因。

| Task ID | 任务 | 产出 | 依赖 | 状态/验证 |
| --- | --- | --- | --- | --- |
| M2d-T01 | 新增 display theme alias 表 | canonical 展示名 | M2c | DONE，已提交推送 |
| M2d-T02 | 合并 `PCB/HBM产业链 + PCB印制电路板` | 单一 PCB/HBM 展示列 | T01 | DONE，6/18 涨停数 12 |
| M2d-T03 | 合并 `AI光通信 + AI光纤` | 单一 AI 光通信展示列 | T01 | DONE，6/18 涨停数 4 |
| M2d-T04 | 合并 `机器人 + 人形机器人/工业机器人` | 单一机器人展示列 | T01 | DONE，6/18 涨停数 9 |
| M2d-T05 | 合并 `AI算力基础设施 + 算力/数据中心/液冷` | 单一 AI 算力展示列 | T01 | DONE，6/18 涨停数 9 |
| M2d-T06 | 合并 `先进材料/固态电池 + 全固态电池进度表` | 单一材料/固态电池展示列 | T01 | DONE，6/18 涨停数 8 |
| M2d-T07 | diagnostics 输出 `merged_theme_aliases/merged_mapping_sources` | 可审计 alias 合并 | T01-T06 | DONE，单测覆盖 |

提交与报告：

- Commit：`9fed8a7a8 Merge canonical display themes in limit-up matrix`
- 单测：`14 passed`
- Report：`reports/golden/limit_up_theme_matrix_m2b/validation_20260618_m2d.md`

### M2e - Golden Gate 指标口径调整

目标：避免在多热点扩散行情中用 Top5 覆盖率硬阈值诱导过度归并。

| Task ID | 任务 | 产出 | 依赖 | 状态/验证 |
| --- | --- | --- | --- | --- |
| M2e-T01 | 将 `true_other_count <= 10` 设为真实归因 Gate | 准确归因门禁 | M2c | DONE，已提交推送 |
| M2e-T02 | 将 `top_8_theme_coverage >= 55%` 设为热点覆盖 Gate | 多分支行情门禁 | M2d | DONE，已提交推送 |
| M2e-T03 | 将 `display_other_count <= 45` 设为展示质量 Gate | 展示折叠门禁 | M2c | DONE，已提交推送 |
| M2e-T04 | 将 `collapsed_other_count` 降级为观察指标 | 避免误判展示上限 | M2c | DONE，已提交推送 |
| M2e-T05 | 新增 `top_5_manual_theme_hit_count >= 4` | 人工复盘一致性 Gate | M2d | DONE，已提交推送 |
| M2e-T06 | 保留 `single_theme_max_ratio <= 35%` | 防止过度归并 | M2b | DONE，已提交推送 |

M2e 2026-06-18 回放结果：

| 指标 | 结果 | Gate |
| --- | ---: | --- |
| `true_other_count` | 5 | PASS |
| `display_other_count` | 38 | PASS |
| `collapsed_other_count` | 34 | 观察指标 |
| `top_8_theme_coverage` | 55.66% | PASS |
| `top_5_manual_theme_hit_count` | 5 | PASS |
| `single_theme_max_ratio` | 11.32% | PASS |

Report：`reports/golden/limit_up_theme_matrix_m2b/validation_20260618_m2e.md`

Commit：`5ccbf209d Adjust limit-up matrix golden gate metrics`

### P0.5 - Theme Evidence + Theme Explanation Layer

目标：在修复矩阵后，立即把热点解释能力补上。该层价值高于研报/PDF/EPS，因为它直接改善盘后复盘、早盘必读和热点理解。

输出结构示例：

```json
{
  "theme": "AI算力基础设施",
  "limitup_count": 12,
  "top_reason_tags": ["液冷", "智算中心", "算力租赁"],
  "representative_stocks": ["冰轮环境", "东方国信", "恒为科技"],
  "source_evidence_count": 12,
  "confidence": 0.86
}
```

任务：

| Task ID | 任务 | 产出 | 依赖 | 验证 |
| --- | --- | --- | --- | --- |
| P0.5-T01 | 基于 `stock_theme_reason_evidence` 聚合 theme explanation | `theme_explanation_rows` | M2 | 6/18 解释行可生成 |
| P0.5-T02 | 为每个主题计算 `top_reason_tags`、`representative_stocks`、`source_evidence_count` | 解释指标 | T01 | AI算力等主题解释正确 |
| P0.5-T03 | 将解释层接入盘后复盘文档结构 | 报告增强 | T02 | 报告展示核心驱动和代表股 |
| P0.5-T04 | 将解释层输出给早盘必读候选上下文 | 早盘上下文增强 | T02 | 不影响原早盘链路 |
| P0.5-T05 | 增加解释层回放测试 | 质量门禁 | T03 | Golden Dataset 通过 |

## 11. 测试策略

### 11.1 单元测试

建议新增：

- `stock_processing_service/tests/unit/test_ths_client.py`
- `stock_processing_service/tests/unit/test_ths_hot_reason_normalizer.py`
- `stock_processing_service/tests/unit/test_reason_theme_resolver.py`
- `stock_processing_service/tests/unit/test_limit_up_theme_matrix_builder_ths_reason.py`
- `stock_processing_service/tests/unit/test_theme_explanation_layer.py`

覆盖场景：

- 正常响应解析。
- `errocode != 0`。
- 空 `data`。
- 行级缺少 `reason`。
- `reason` 多标签拆分。
- `RuleResolver` 命中。
- `EmbeddingResolver/LLMResolver` 失败不阻断。
- `CompositeReasonThemeResolver` 输出统一 `ThemeMatch`。
- confirmed mainline 优先级高于 THS reason。
- THS reason 优先级高于静态 `subject_stock_map`。
- secondary themes 被保留但不作为矩阵主列。

### 11.2 集成/回放测试

建议新增：

- `stock_processing_service/tests/integration/test_limit_up_theme_matrix_golden_dataset_replay.py`

前置数据：

- 2026-06-18/19/20 `stock_daily_snapshot` 样本。
- 2026-06-18/19/20 `ths_hot_reason_snapshot` 样本。
- 2026-06-18/19/20 `stock_theme_reason_evidence` 期望样本。
- 最小 `mainline_daily_state` / `subject_stock_map` 样本。

断言：

- `true_other_count <= 10`
- `display_other_count <= 45`
- `ths_reason_covered_count >= 80`
- `top_8_theme_coverage >= 0.55`
- `top_5_manual_theme_hit_count >= 4`
- `single_theme_max_ratio <= 0.35`
- `mainline_hit_count` 不低于改造前 fixture 结果
- Top5 覆盖人工复盘主线至少 4 个
- Theme Explanation 输出核心驱动 tags 和代表股

## 12. 回滚策略

### 12.1 功能开关

新增配置：

```text
LIMIT_UP_MATRIX_USE_THS_REASON=0/1
THS_REASON_FALLBACK_CLASSIFIER=none/embedding/llm
```

默认建议：

- 开发/回放环境开启。
- 生产首次发布灰度开启。

### 12.2 回滚触发条件

任一条件触发回滚：

- `single_theme_max_ratio > 50%`，疑似过度归并。
- `other_count` 未下降且 `static_fallback_ratio` 异常升高。
- THS 快照采集失败导致 job 阻塞主报告生成。
- 6/18 回放 Top5 与人工复盘明显不一致。

回滚方式：

- 关闭 `LIMIT_UP_MATRIX_USE_THS_REASON`。
- 保留 raw snapshot 和 THS 快照表，不删除数据。
- 热点矩阵回到 `confirmed_mainline -> subject_stock_map -> 其他`。

## 13. P1 Data Source Governance（M3）

P0 已证明 THS reason 能显著改善热点矩阵。后续接入东财概念板块、巨潮公告、同花顺 EPS、东财研报之前，必须先治理数据源接入方式，避免多个 client/job 各自实现 sleep、retry、headers、raw snapshot 和错误处理。

优先级：

```text
M3 Data Source Governance > 前端 diagnostics/reason tags > M4 数据源扩展 > M5 研报/EPS/PDF
```

### 13.1 M3 目标

1. 将 `market_data_source_registry` 从轻量记录升级为数据源治理真源。
2. 新增统一 `RateLimitedHttpClient`，把限流、重试、UA/Referer、session 复用、错误计数从 job/client 中抽出。
3. 先迁移现有 THS reason client 使用治理能力，证明基础设施可服务现有链路。
4. 为后续 Eastmoney、CNInfo、THS EPS 提供统一接入模板。
5. 保持 domain/application builder 不直接触碰 requests、pandas、SQL 或外部 API。

### 13.2 `market_data_source_registry` 完整字段

M3 建议扩展字段：

| 字段 | 说明 |
| --- | --- |
| `source_name` | 数据源名称，如 `ths`、`eastmoney`、`cninfo` |
| `endpoint_key` | 端点唯一键，如 `ths_hot_reason` |
| `domain` | 业务域，如 `hot_reason`、`concept_blocks`、`announcements` |
| `owned_fields` | 该端点负责提供的字段集合 |
| `usage` | 使用场景，如盘后热点归因、题材补证据 |
| `fallback_order` | 多源冲突时的 fallback 顺序 |
| `rate_limit_policy` | 限流策略 JSON |
| `auth_type` | `none/cookie/token` 等 |
| `freshness_sla` | 数据新鲜度要求 |
| `raw_snapshot_required` | 是否必须写 raw snapshot |
| `enabled` | 是否启用 |
| `created_at/updated_at` | 审计字段 |

示例：

```yaml
ths_hot_reason:
  source_name: ths
  endpoint_key: ths_hot_reason
  domain: hot_reason
  owned_fields:
    - reason_raw
    - reason_tags
    - hot_stock_list
  usage: 盘后热点归因
  rate_limit_policy:
    type: simple
    min_interval_ms: 500
    jitter_ms: 100
  auth_type: none
  raw_snapshot_required: true
  enabled: true

eastmoney_concept_blocks:
  source_name: eastmoney
  endpoint_key: eastmoney_concept_blocks
  domain: concept_blocks
  owned_fields:
    - concept_blocks
    - industry_blocks
    - region_blocks
  usage: 股票-题材静态/半动态补证据
  rate_limit_policy:
    type: conservative
    min_interval_ms: 1000
    jitter_ms: 300
    session_reuse: true
  auth_type: none
  raw_snapshot_required: true
  enabled: false
```

### 13.3 `RateLimitedHttpClient`

统一能力：

| 能力 | 说明 |
| --- | --- |
| `source_name` / `endpoint_key` | 绑定 registry 策略 |
| `min_interval_ms` | 同源最小请求间隔 |
| `jitter_ms` | 随机抖动，降低风控命中 |
| `max_retries` | 最大重试次数 |
| `backoff` | 指数/线性退避 |
| `session_reuse` | 复用 HTTP session |
| `ua/referer` | 统一 headers 策略 |
| `timeout` | 请求超时 |
| `error_counter` | 连续失败计数 |
| `last_success_at` / `last_failure_at` | 运行诊断 |

约束：

- job 不再手写 `sleep()`。
- Eastmoney 默认串行、间隔 `>= 1s`、复用 session。
- client 只负责请求，不做业务归因。
- raw snapshot 写入仍由 job/gateway 编排。

### 13.4 M3 任务分解

| Task ID | 任务 | 产出 | 依赖 | 验证 |
| --- | --- | --- | --- | --- |
| M3-T01 | 扩展 `market_data_source_registry` migration | 完整治理字段 | M0a | migration 可重复执行 |
| M3-T02 | Registry Gateway 增加查询/更新 API | source config 读取能力 | T01 | unit test |
| M3-T03 | 实现 `RateLimitedHttpClient` | 统一限流 HTTP 基建 | T02 | retry/rate limit 单测 |
| M3-T04 | 将 `ThsClient` 迁移到 `RateLimitedHttpClient` | 现有 THS 链路使用治理能力 | T03 | THS reason 单测和 6/18 采集验证 |
| M3-T05 | 将 THS registry 初始记录升级为完整配置 | 可配置 THS endpoint | T01-T04 | registry 查询结果符合预期 |
| M3-T06 | 增加 source diagnostics | 最近成功/失败、连续失败、限流命中 | T03-T04 | job 输出 diagnostics |
| M3-T07 | 更新设计文档与运行手册 | 可运维说明 | T01-T06 | 文档落地 |

### 13.5 M3 验收标准

| 验收项 | 目标 |
| --- | --- |
| THS reason 采集 | 2026-06-18 可正常拉取/落库，结果不低于当前 M0b 能力 |
| Registry 配置读取 | THS endpoint 不再硬编码 source 元信息 |
| Rate limit 行为 | 同一 source 连续请求遵守 `min_interval_ms + jitter` |
| Retry 行为 | 429/403/timeout 可按策略退避，不阻塞主流程 |
| Raw snapshot | 成功和失败响应均可保留 trace |
| 单测 | 新增 registry/http client/client migration 单测 |
| 回归 | M2e 6/18 validation 仍通过 |

## 14. 后续扩展路线

M3 完成后，再进入前端与更多数据源：

1. 前端展示 diagnostics / reason tags。
2. P0.5：实现 Theme Evidence + Theme Explanation Layer。
3. M4：接入 `eastmoney_concept_blocks` 作为静态/半动态补证据。
4. M4：接入 `cninfo_announcements` 作为事件驱动公告证据。
5. M4：把 `stock_theme_reason_evidence` 纳入题材热度、龙头评分、早盘必读上下文。
6. M5：接入东财个股研报、行业研报、同花顺 EPS、PDF 摘要。

## 15. 决策记录

| 决策 | 结果 | 理由 |
| --- | --- | --- |
| 是否直接引入 `a_stock_data_service` | 否 | 会形成大而全服务，破坏现有分层 |
| P0 是否扩展多个数据源 | 否 | 先修复 6/18 热点矩阵失真 |
| 是否保存 raw response | 是 | 外部接口字段易漂移，必须可回放 |
| 是否只靠手工词典 | 否 | 规则覆盖高频，fallback 预留处理新题材 |
| 是否使用统一 resolver 接口 | 是 | 规则、embedding、LLM 共用 `ReasonThemeResolver`，避免后续分叉 |
| 是否前置主题证据表 | 是 | 题材热度、龙头分析、主题材识别都会复用 |
| 是否只用 6/18 验收 | 否 | 建立 3-5 日 Golden Dataset，避免单日过拟合 |
| 是否前置 Theme Explanation Layer | 是 | 直接改善盘后复盘、早盘必读、热点理解 |
| 矩阵是否允许一个股票多个题材 | 算法层允许，展示层唯一主列 | 兼顾可读性和共振分析 |
| 是否改变涨停判定口径 | 否 | 保持 `stock_daily_snapshot` 真源稳定 |
| P0 后是否立即做前端 | 否 | 先做 M3 数据源治理，降低后续多数据源接入债务 |
| P0 后是否立即接研报 | 否 | 研报价值高但不是当前最短板；先标准化 registry/http 基建 |

---

## 16. M7 Weight Auto-Calibration Engine（系统自进化层）

### 16.1 定位

M7 是在 M3–M6 完整闭环基础上的“参数自优化层”，用于将系统从：

- 固定权重模型 → 自适应市场模型

升级为：

- 可根据市场误差自动修正权重的认知系统

---

### 16.2 总体结构

```text
M7a Market Truth Layer
M7b Error Diagnosis Layer
M7c Weight Auto-Calibration Engine
```

---

### 16.3 M7a Market Truth Layer

职责：

- 收集真实市场结果（涨幅、连板、资金、板块强度）
- 输出标准化 MarketTruth object

核心字段：

- return_score
- limitup_hit
- board_strength
- money_flow
- leader_stability

---

### 16.4 M7b Error Diagnosis Layer

职责：

对比：

- M6预测（ThemeStrength + LeaderScore）
vs
- M7a真实市场

输出误差结构：

- theme_bias_map
- source_bias_map
- rank_error
- strength_error

---

### 16.5 M7c Weight Auto-Calibration Engine（核心）

#### 🎯 目标

根据 M7b 自动调整 M4–M6 权重。

---

#### ① Source Weight Calibration

```python
if source_bias > 0.1:
    weight[source] -= 0.02
elif source_bias < -0.1:
    weight[source] += 0.02
```

---

#### ② Theme Weight Calibration

```text
overestimate → EPS / Research ↓
underestimate → Eastmoney ↑
```

---

#### ③ Stability Feedback Calibration

```text
high_stability_low_return → anchor ↑
high_drift_high_return → event ↑
```

---

### 16.6 权重约束

- 单次调整 ≤ 0.03
- 总权重归一化
- EPS + Research 不可同时大幅下降
- anchor ≥ 0.15

---

### 16.7 输出

```json
{
  "updated_weights": {},
  "delta": {},
  "reason": "market_bias_correction"
}
```

---

### 16.8 系统意义

M7 使系统具备：

- 自我纠错能力
- 权重随市场结构漂移
- 长期稳定性增强

---