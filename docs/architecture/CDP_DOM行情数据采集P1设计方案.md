# CDP 行情数据采集 — P1 设计方案

> 版本: 1.0
> 日期: 2026-05-25
> 状态: 设计冻结
> 前置: P0 已验证 9 个行情接口，Token 可用

---

## 一、架构定论

### 升级后的角色分工

| 组件 | 职责 |
|------|------|
| **CDP** | 仅负责：启动 JYHF App、获取/刷新 JWT Token、必要时接口探测 |
| **httpx + Token** | **行情主链路**：直接请求 `https://app.txcfgl.com` 已验证接口 |
| **DOM** | 不再用于行情数据采集 |

### 数据流

```
CDP (Token hook)
  → /tmp/jyhf_auth_token.json
    → JyhfTokenProvider
      → JyhfMarketApiClient (httpx + Bearer Token)
        ├→ Normalizer (Quote / Subject / Index)
        │   ├→ Redis Stream: stream:market:jyhf
        │   └→ PostgreSQL (5 表)
        └→ raw_json → jyhf_market_raw_capture
```

---

## 二、P1 目标与成功标准

### 目标

建立 `jyhf_market_service`，使用已验证 JWT Token 和 9 个接口，完成候选股票池与题材股票池的实时行情采集、标准化、Redis Stream 推送和 PostgreSQL 落地。

### 成功标准

1. 不依赖 DOM innerText
2. 能读取 `/tmp/jyhf_auth_token.json` 或主动通过 CDP 刷新 Token
3. 能采集指定 `stock_id` 的实时行情
4. 能采集指定 `subject_id` 下的实时股票列表
5. 能采集指数行情
6. 能把 quote / subject_quote / index_quote 写入 DB
7. 能把关键变化推入 Redis Stream
8. 能为后续尾盘、竞价、资金流信号预留字段

---

## 三、服务结构

```
services/
  jyhf_market_service/           # 新增 — 独立于 jyhf_cdp_service
    __init__.py
    app.py                       # FastAPI 入口
    config.py                    # 配置
    service.py                   # 采集循环编排

    token_provider.py            # Token 读取/校验/刷新
    api_client.py                # 9 个接口统一封装
    endpoint_registry.py         # 接口配置

    schemas.py                   # JyhfStockQuote / JyhfIndexQuote 等
    normalizers.py               # 原始响应 → 标准化模型

    stock_universe.py            # 候选池管理
    scheduler.py                 # 分时段调度

    redis_pusher.py              # Redis Stream 发布
    db_sink.py                   # PostgreSQL 写入
    state.py                     # 采集状态
    logging_config.py            # 日志
```

---

## 四、核心模块设计

### 4.1 TokenProvider

```python
class JyhfTokenProvider:
    def get_token(self) -> str:
        token = self._load_from_file()
        if self._validate(token):
            return token
        self._refresh_by_cdp()
        token = self._load_from_file()
        if self._validate(token):
            return token
        raise RuntimeError("JYHF token unavailable")
```

**校验接口**: `GET https://app.txcfgl.com/api/app/realtime/index`

**降级策略**: 401/403 → 标记 token_invalid → CDP 刷新 → 重试一次 → 仍失败则暂停采集

### 4.2 JyhfMarketApiClient

```python
class JyhfMarketApiClient:
    async def get_stock_realtime(self, stock_id: str) -> dict: ...
    async def get_stock_daily(self, stock_id: str, days: int = 120) -> dict: ...
    async def get_index_realtime(self) -> dict: ...
    async def get_subject_stocks_realtime(self, subject_id: str) -> dict: ...
    async def get_stock_subject_tree(self, stock_id: str) -> dict: ...
    async def get_subject_stock_rank(self, subject_id: str) -> dict: ...
    async def get_subject_daily(self, subject_id: str, days: int = 365) -> dict: ...
    async def get_subject_realtime(self, subject_id: str) -> dict: ...
```

**原则**: 所有响应先完整保存 `raw_json`，不过早清洗。

### 4.3 StockUniverseProvider

P1 仅采三类股票：

| 来源 | 方式 |
|------|------|
| 强势池 / 弱转强候选 | 读取 existing strong_watch API / DB |
| 今日热门题材下股票 | `stock/realtime-by-subject/v2` |
| 手动 watchlist | 配置文件 |

```json
{
  "watch_stocks": ["002361.SZ", "603XXX.SH"],
  "watch_subjects": ["9019807", "9043089"]
}
```

规模控制: `watch_stocks <= 200`, `watch_subjects <= 30`

### 4.4 Normalizer — 4 类标准化对象

```python
class JyhfStockQuote:
    trade_date: str; ts: str
    stock_id: str; stock_name: str | None
    current: float | None; open: float | None
    high: float | None; low: float | None
    close: float | None; pct_chg: float | None
    amount: float | None; vol: float | None
    pe: float | None; market_value: float | None
    limit_up: float | None; limit_down: float | None
    source_endpoint: str; raw_json: dict

class JyhfSubjectRealtime:
    trade_date: str; ts: str
    subject_id: str; subject_name: str | None
    pct_chg: float | None; heat: float | None
    stock_count: int | None; raw_json: dict

class JyhfSubjectStockQuote:
    trade_date: str; ts: str
    subject_id: str; stock_id: str; stock_name: str | None
    current: float | None; pct_chg: float | None
    amount: float | None; vol: float | None
    rank: int | None; raw_json: dict

class JyhfIndexQuote:
    trade_date: str; ts: str
    index_code: str; index_name: str
    current: float | None; pct_chg: float | None
    amount: float | None; vol: float | None
    raw_json: dict
```

---

## 五、PostgreSQL 表设计

### 5.1 个股实时行情快照

```sql
CREATE TABLE IF NOT EXISTS jyhf_stock_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT,
    current NUMERIC, open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
    pct_chg NUMERIC, amount NUMERIC, vol NUMERIC,
    pe NUMERIC, market_value NUMERIC, limit_up NUMERIC, limit_down NUMERIC,
    source_endpoint TEXT, raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, stock_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_jyhf_stock_quote_snapshot_stock_ts
    ON jyhf_stock_quote_snapshot(stock_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_jyhf_stock_quote_snapshot_trade_date
    ON jyhf_stock_quote_snapshot(trade_date);
```

### 5.2 指数实时行情

```sql
CREATE TABLE IF NOT EXISTS jyhf_index_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL, ts TIMESTAMPTZ NOT NULL,
    index_code TEXT NOT NULL, index_name TEXT,
    current NUMERIC, open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
    pct_chg NUMERIC, amount NUMERIC, vol NUMERIC,
    raw_json JSONB, created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, index_code, ts)
);
```

### 5.3 题材实时行情

```sql
CREATE TABLE IF NOT EXISTS jyhf_subject_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL, ts TIMESTAMPTZ NOT NULL,
    subject_id TEXT NOT NULL, subject_name TEXT,
    pct_chg NUMERIC, heat NUMERIC, amount NUMERIC, stock_count INT,
    raw_json JSONB, created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, subject_id, ts)
);
```

### 5.4 题材下股票实时行情

```sql
CREATE TABLE IF NOT EXISTS jyhf_subject_stock_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL, ts TIMESTAMPTZ NOT NULL,
    subject_id TEXT NOT NULL, subject_name TEXT,
    stock_id TEXT NOT NULL, stock_name TEXT,
    current NUMERIC, pct_chg NUMERIC, amount NUMERIC, vol NUMERIC,
    rank_no INT, raw_json JSONB, created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, subject_id, stock_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_jyhf_subject_stock_quote_subject_ts
    ON jyhf_subject_stock_quote_snapshot(subject_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_jyhf_subject_stock_quote_stock_ts
    ON jyhf_subject_stock_quote_snapshot(stock_id, ts DESC);
```

### 5.5 原始接口响应留痕

```sql
CREATE TABLE IF NOT EXISTS jyhf_market_raw_capture (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    endpoint_key TEXT NOT NULL, endpoint TEXT NOT NULL,
    method TEXT DEFAULT 'GET', request_params JSONB,
    response_hash TEXT, raw_json JSONB,
    parse_status TEXT DEFAULT 'ok', error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_jyhf_market_raw_capture_endpoint_time
    ON jyhf_market_raw_capture(endpoint_key, captured_at DESC);
```

---

## 六、Redis Stream

P1 统一 stream: `stream:market:jyhf`

```json
{
  "item_id": "jyhf_quote:20260525:002361.SZ:093005",
  "item_type": "stock_quote",
  "source_channel": "jyhf_market_api",
  "trade_date": "2026-05-25",
  "occurred_at": "2026-05-25T09:30:05+08:00",
  "stock_id": "002361.SZ",
  "stock_name": "神剑股份",
  "current": 12.34,
  "pct_chg": 5.21,
  "amount": 123456789,
  "vol": 123456,
  "subject_keys": ["9019807"],
  "raw_ref": "jyhf_market_raw_capture:12345"
}
```

---

## 七、采集调度

| 时段 | 数据 | 频率 |
|------|------|------|
| 09:15-09:20 | 竞价初段 | 10s |
| 09:20-09:25 | 竞价关键段 | 5s |
| 09:25-09:30 | 开盘前定格 | 10s |
| 09:30-11:30 | 盘中 | 指数 10s / 候选股 10s / 题材 30s |
| 13:00-14:30 | 午后 | 指数 10s / 候选股 10-15s / 题材 30s |
| 14:30-15:00 | 尾盘 | 候选股 3-5s / 题材 15s / 指数 5s |
| 15:00后 | 日线补齐 | 一次性 backfill |

---

## 八、接口优先级

| 优先级 | 接口 | 原因 |
|--------|------|------|
| **P0** | `stock/realtime-by-subject/v2` | 一次性返回题材下股票行情+题材关联，战略价值最高 |
| P1 | `stock/realtime/{stockId}` | 个股精准行情 |
| P2 | `realtime/index` | 市场环境 |
| P3 | `subject/realtime/{subjectId}` | 题材热度 |
| P4 | `data/one-stock-daily` | 日线补全 |
| P5 | `subject/daily/{subjectId}` | 题材历史 |

---

## 九、P1 最小实现路线

### Step 1: 只读 API Client
- `token_provider.py` + `api_client.py` + `endpoint_registry.py`
- 验证: `python -m services.jyhf_market_service.probe_client --stock-id 002361.SZ --subject-id 9019807`

### Step 2: 标准化 + raw 落盘
- `normalizers.py` + `db_sink.py`
- 先写: `jyhf_market_raw_capture`, `jyhf_stock_quote_snapshot`, `jyhf_index_quote_snapshot`

### Step 3: 接入候选池
- `stock_universe.py`
- 第一版: 配置文件驱动

### Step 4: 服务化
- `app.py` + FastAPI (仿照 `jyhf_cdp_service/app.py`)
- `GET /health`, `POST /collector/start`, `POST /collector/stop`, `GET /market/quote/{stock_id}`

---

## 十、工程风险

| 风险 | 措施 |
|------|------|
| Token 过期 | 401/403 → 标记 token_invalid → CDP 刷新 → 重试一次 → 仍失败则暂停 |
| 限频 | watch_stocks ≤ 200, watch_subjects ≤ 30 |
| 字段不稳定 | 所有响应保留 raw_json，作为修复依据 |
| 服务隔离 | 新建 `jyhf_market_service/`，不修改 `jyhf_cdp_service/` |

---

## 十一、P2 展望（策略信号层）

P1 完成后再做：

1. **尾盘异动信号**: 14:30后涨幅 + 成交额占比 + 均线承接 + 题材内排名
2. **竞价强度信号**: 竞价涨幅 + 成交额 + 昨日成交额占比 + 题材热度
3. **题材内前排确认**: 题材内涨幅排名 + 成交额排名 + 与题材指数同步性

---

## 十二、P1.5: 弹窗消息采集（2026-06-18 实施）

### 12.1 背景与动机

账户过期后，JYHF App 的 Feed（"新事件"/"新题材"标签页）数据被客户端遮盖：

| 字段 | Feed（过期账户） | 弹窗（推送通知） |
|------|-----------------|-----------------|
| 题材名称 | `********` | ✅ 明文 |
| subject_id | 无 | ✅ `extraId` URL参数 |
| 驱动事件标题 | 截断（`...`） | ✅ 完整 |
| 驱动事件描述 | 隐藏 | ✅ 完整 |
| 新闻来源 | 隐藏 | ✅ 完整 |
| 事件时间 | ✅ 明文 | ❌ |
| 涨跌幅 | ✅ 明文 | ❌ |

Feed API 响应体为加密 hex blob，解密后数据已在服务端遮盖。弹框通过 WebSocket 推送到达，路由到 `#/notification?...` 携带 URL 参数，数据**完全不遮盖**，是过期账户下获取完整事件数据的唯一渠道。

### 12.2 弹框数据结构

```
#/notification?
  route=TopicView
  &extraId=9055879          ← subject_id（完整）
  &extraName=国产AI芯片大全   ← 题材名称（明文，不遮盖）
  &title=您关注的（国产AI芯片大全）有更新
  &content=【驱动事件：...】（新闻来源：财联社）
```

弹框**不会自动消失**，用户点击"查看详情"或导航离开后消失。

### 12.3 架构：三层采集防御

```
Layer 1: Vue Router beforeEach hook  ← 推送到达时即捕获，存 window.__cdp_notifications__
Layer 2: Popup polling (URL解析)     ← 弹框仍在显示时通过 URL 参数解析
Layer 3: Feed polling (innerText)    ← 全量事件（但被遮盖，已过滤）
```

**Layer 1 实现** — `PersistentHookInjector`（`extractors.py`）：

```python
class PersistentHookInjector:
    _INJECTED_FLAG = "__cdp_persistent_hooks_injected__"
    _NOTIF_STORE = "__cdp_notifications__"

    def ensure_injected(self, cdp: CDPClient) -> bool:
        """注入 Vue Router beforeEach + hashchange listener。
        只执行一次（idempotent），后续 CDP 连接只读取。"""
        # router.beforeEach 拦截 #/notification?...
        # window.addEventListener('hashchange') 兜底
```

**Layer 2 实现** — `NotificationPopupExtractor`（`extractors.py`）：

```python
class NotificationPopupExtractor:
    def detect(self, cdp) -> bool:
        """检查 window.location.hash 是否包含 /notification?"""
    
    def read(self, cdp) -> list[dict]:
        """解析 URL query string → event dict（兼容 Feed 格式）"""
```

### 12.4 采集流程集成

弹框采集已集成到 `JyhfCdpCollectorService._capture_once_locked`：

```
CDP connect
  ├─ Phase 0: ensure_injected() — 注入 Router hook（首次）
  ├─ Phase 1: inject token hooks
  ├─ Phase 2a: drain_notifications() — 排空 hook 累积的弹框
  ├─ Phase 2b: detect + read popup — 当前显示的弹框
  ├─ Phase 3: Feed extraction（best-effort，失败不阻塞弹框）
  │            └─ 过滤: subject_name='********' 的事件丢弃
  └─ Merge: hook_events + popup_events + feed_events
       └─ 弹框事件直接写入 subject_history_staging
```

**关键修改** — `service.py`：

```python
# 弹框和 Feed 解耦：Feed prepare/read 失败不阻塞弹框处理
try:
    self._extractor.prepare(cdp)
    feed_events, feed_date, body_text = self._extractor.read(cdp)
    feed_events = [e for e in feed_events if e.get("subject_name") != "********"]
    raw_events.extend(feed_events)
except PrepareRetryError as e:
    self._logger.warning("feed extraction skipped: %s", e)
```

弹框事件通过 `_write_popup_rows_to_staging()` 直接写入 `subject_history_staging` 表（`source_type='jyhf_cdp'`），SPS 的 `load_subject_history_items` 读取后推送到前端 Intel Feed。

### 12.5 数据流

```
弹框到达 → Router beforeEach 拦截
  → window.__cdp_notifications__ 暂存
  → 20s轮询排空 → _raw_notification_to_event()
  → _write_popup_rows_to_staging() → subject_history_staging
  → SPS load_subject_history_items → /api/v1/intel_feed
  → web_app HTTP轮询(5s) → /api/v2/intel/stream (SSE)
  → 前端 IntelListItem（标签: "JYHF实时"）
```

### 12.6 新题材处理

弹框 `extraId` 用于存在性判断：

```sql
SELECT 1 FROM subject_detail WHERE subject_key = '{extraId}'
```

**已有题材** → 事件写入 `subject_history_staging`。

**新题材** → 完整入库流程：
1. `subject_detail` INSERT — 题材详情
2. `theme_gate_profile` INSERT — 题材注册
3. `subject_history_staging` INSERT — 事件数据
4. API `stock/realtime-by-subject/v2` → `subject_stock_staging` — 成分股
5. CDP DOM `/subject/detail/{id}` → `subject_children_staging` — 子题材

### 12.7 题材图谱

基于 `jyhf_subject_taxonomy_relation`（题材继承关系表，7173行）构建完整层级：

```
API: /api/v1/theme_workspace/{subject_key} → graph 字段
  ├─ jyhf_subject_taxonomy_relation → 继承树（父→子→孙）
  ├─ subject_child_stock_reason → 股票→子题材映射
  └─ subject_stock_map → 主股票表（补充 pct_chg）

SPS → Web App proxy → Frontend ThemeWorkspacePage
  └─ SubjectGraphCard 组件（左→右横向图谱布局）
```

图谱数据修复：全库 `child_name='cdp_extracted'` 的股票通过继承关系关键词匹配重新分配（2026-06-18 处理 13641 条）。

### 12.8 改动文件清单

| 文件 | 改动 |
|------|------|
| `services/jyhf_cdp_service/extractors.py` | 新增 `NotificationPopupExtractor` + `PersistentHookInjector` |
| `services/jyhf_cdp_service/service.py` | 弹框/Feed解耦 + 遮挡过滤 + 弹框DB直写 |
| `services/jyhf_cdp_service/normalizer.py` | `subject_key` 穿透保留 |
| `stock_processing_service/api_app.py` | graph 字段（三级继承+股票） |
| `frontend/src/components/theme/SubjectGraphCard.tsx` | 新增题材图谱组件 |
| `frontend/src/routes/theme/ThemeWorkspacePage.tsx` | 新增"题材图谱"标签页 |
| `frontend/src/hooks/useThemeWorkspace.ts` | graph 数据提取 |
| `frontend/src/lib/api.ts` | ThemeWorkspaceView.graph 字段 |
| `scripts/run_jyhf_popup_collector.py` | 独立弹框采集器（备用） |
