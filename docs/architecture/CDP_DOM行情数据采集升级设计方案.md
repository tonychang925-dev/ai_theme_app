# CDP 行情数据采集升级设计方案

> 版本: 1.0
> 日期: 2026-05-25
> 状态: 设计冻结，待 P0 验证
> 范围: 从 CDP DOM 文本采集升级为 CDP Network/WebSocket 接口直采 + DOM 兜底

---

## 一、总体判断

| 项目 | 结论 |
|------|------|
| 能否通过 CDP 采集实时行情？ | **能** |
| 最佳方案？ | CDP Network/WebSocket 抓接口 + httpx 直采 + DOM 兜底 |
| 当前工程基础？ | **良好**，CDP 链路已有完整采集循环 |
| 建议升级方向 | `document.body.innerText` 硬解析 → 网络层接口直采 |

---

## 二、现有代码复用评估

### 可直接复用

| 组件 | 文件 | 说明 |
|------|------|------|
| 采集循环 | `jyhf_cdp_service/service.py` | 启动App → CDP → Token → 推送 → 入库循环 |
| CDP 客户端 | `jyhf_cdp_service/cdp_client.py` | 连接 webSocketDebuggerUrl，执行 Runtime.evaluate |
| Token 提取 | `jyhf_cdp_service/token_extractor.py` | Monkey-patch fetch/XHR 捕获 Authorization header |
| Intel Pusher | `jyhf_cdp_service/intel_pusher.py` | Redis Stream 发布 |
| DB Sink | `jyhf_cdp_service/db_sink.py` | PostgreSQL 幂等写入 |
| BFF 管理 | `web_app_service/services/jyhf_cdp_manager.py` | managed/external 生命周期管理 |

### 需新增

| 组件 | 能力 | 说明 |
|------|------|------|
| Network 监听 | `Network.enable` + `Network.responseReceived` + `Network.getResponseBody` | 捕获 XHR/fetch 响应 |
| WebSocket 监听 | `Network.webSocketFrameReceived` | 捕获实时推送数据 |
| 接口直采 | `httpx` + 复用 Token | 绕过 DOM，直接请求行情接口 |
| 分时调度 | 时段感知的采集频率 | 竞价 2-5s / 盘中 10-30s / 尾盘 3-5s |

### 待升级

| 组件 | 当前 | 升级 |
|------|------|------|
| CDPClient | 仅 Runtime.enable + evaluate | 增加 Network.enable + Page.enable + 事件监听 |
| Extractor | innerText 状态机解析 | 网络层接口抓取 + DOM 文本兜底 |

---

## 三、推荐架构

### 服务拆分

```
services/
  jyhf_cdp_service/              # 保留：新事件/题材事件 DOM 采集
  jyhf_market_cdp_service/       # 新增：行情/资金/竞价采集
    ├── app.py                   # FastAPI 入口
    ├── config.py                # 行情专用配置
    ├── service.py               # 采集循环（时段调度）
    ├── cdp_client.py            # 升级版：支持 Network/WebSocket
    ├── token_provider.py        # 读取 /tmp/jyhf_auth_token.json
    ├── market_navigator.py      # 导航到个股/分时/资金/竞价页面
    ├── network_recorder.py      # 捕获 XHR/fetch/WebSocket 响应
    ├── endpoint_registry.py     # 记录已发现的行情接口
    ├── market_fetch_client.py   # token + httpx 直接请求接口
    ├── normalizers.py           # quote/minute/moneyflow/auction
    ├── redis_pusher.py          # Redis Stream 发布
    ├── db_sink.py               # PostgreSQL 写入
    └── schemas.py               # 行情数据模型
```

### 数据流

```
CDP 启动 JYHF App
  └--> Network.enable + 监听
         ├-- 捕获 XHR/fetch/WebSocket 响应
         ├-- 登记 endpoint_registry (接口地图)
         └-- 保存原始响应到 jyhf_market_raw_capture
                │
  TokenProvider ← /tmp/jyhf_auth_token.json
         │
  MarketFetchClient (httpx + token 直采)
         │
         ├── 标准化 → Redis Stream → SSE → 前端
         └── 标准化 → PostgreSQL (quote/minute/moneyflow/auction)
```

---

## 四、接口发现：三阶段推进

### 阶段 1：接口发现（P0 验证）

启用 CDP Network 监听：

```
Network.enable
Network.requestWillBeSent
Network.responseReceived
Network.loadingFinished
Network.getResponseBody
Network.webSocketFrameReceived
```

目标：建立 endpoint_registry：

```
quote_api:        当前价/涨跌幅/成交量/成交额
minute_api:       分时行情数组
money_flow_api:   资金流入/流出
auction_api:      竞价数据
stock_pool_api:   股票池/成分股
websocket_channel:实时推送通道
```

不写复杂算法，只抓包、归类、保存原始响应。

### 阶段 2：接口直采（P1）

1. CDP 启动 App
2. 捕获/刷新 Token
3. MarketFetchClient 用 token + httpx 直接请求行情接口
4. 定时写 Redis + PostgreSQL
5. Token 失效时回 CDP 刷新

### 阶段 3：策略信号层（P2）

```
行情原始数据
  → 标准化 quote/minute/moneyflow/auction
  → 尾盘异动/竞价强度/资金确认/分时承接计算
  → 弱转强候选、强势池、题材龙头评分
  → 盘前必读 / 盘中情报台 / 盘后复盘
```

---

## 五、数据库设计

### 新增表

```sql
-- 实时快照
CREATE TABLE jyhf_stock_quote_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT,
    price NUMERIC, pct_chg NUMERIC, chg NUMERIC,
    volume BIGINT, amount NUMERIC, turnover_rate NUMERIC,
    high NUMERIC, low NUMERIC, open NUMERIC,
    source_channel TEXT DEFAULT 'jyhf_cdp_market',
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, stock_id, ts)
);

-- 分钟线
CREATE TABLE jyhf_stock_minute_bar (
    trade_date DATE NOT NULL,
    stock_id TEXT NOT NULL,
    minute_ts TIMESTAMPTZ NOT NULL,
    open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC,
    volume BIGINT, amount NUMERIC, vwap NUMERIC,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (trade_date, stock_id, minute_ts)
);

-- 资金流
CREATE TABLE jyhf_stock_money_flow_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    stock_id TEXT NOT NULL,
    main_net_inflow NUMERIC, main_net_ratio NUMERIC,
    super_large_net NUMERIC, large_net NUMERIC,
    medium_net NUMERIC, small_net NUMERIC,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, stock_id, ts)
);

-- 竞价数据
CREATE TABLE jyhf_stock_auction_snapshot (
    id BIGSERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    stock_id TEXT NOT NULL,
    auction_price NUMERIC, auction_pct_chg NUMERIC,
    matched_volume BIGINT, unmatched_volume BIGINT,
    auction_amount NUMERIC, bid_strength NUMERIC,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (trade_date, stock_id, ts)
);

-- 原始响应留痕
CREATE TABLE jyhf_market_raw_capture (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data_type TEXT NOT NULL,
    endpoint TEXT,
    method TEXT,
    request_key TEXT,
    response_hash TEXT,
    raw_json JSONB,
    parse_status TEXT DEFAULT 'pending'
);
```

### Redis Stream

```
stream:market:jyhf  (带 data_type=quote/minute/moneyflow/auction/signal)
```

---

## 六、采集调度

| 时段 | 数据 | 频率 |
|------|------|------|
| 09:15-09:20 | 竞价初段 | 5-10s |
| 09:20-09:25 | 竞价关键段 | 2-5s |
| 09:25-09:30 | 开盘前定格 | 5s |
| 09:30-11:30 | 盘中 | quote 5-10s / moneyflow 30-60s |
| 13:00-14:30 | 午后 | quote 10-15s / moneyflow 60s |
| 14:30-15:00 | 尾盘 | quote 3-5s / moneyflow 15-30s |
| 15:00后 | 补齐 | 一次性 backfill 分钟线/资金流 |

---

## 七、策略信号层

### 早盘竞价信号

```
auction_strength_score =
  竞价涨幅分 + 匹配成交额分 + 未匹配买盘强度
  + 相对昨日成交额占比 + 题材热度加权
  - 高开过多惩罚 - 一字板不可参与惩罚
```

### 尾盘异动信号

```
late_session_score =
  14:30后涨幅 + 14:30后成交额占全天比例
  + 分时均线承接 + 主力净流入变化 + 题材当天强度
  - 炸板/回落风险
```

### 资金流确认

- 主力净流入 / 成交额
- 大单净流入趋势
- 资金流入是否与股价同向
- 题材内排名
- 前排股集中流入判定

---

## 八、股票采集分层

| 层级 | 范围 | 策略 |
|------|------|------|
| L1 必采 | 强势池、弱转强候选、题材前排股、昨日涨停/炸板、盘前必读重点 | 高频全字段 |
| L2 低频采 | 热点题材股票池、主线题材股票池 | 中频 |
| L3 不采/日终 | 无题材/无异动股票 | 仅日终备份 |

---

## 九、推荐落地顺序

| 阶段 | 内容 | 产出 |
|------|------|------|
| **P0** | 验证可行性：选 2 个页面抓包 | `jyhf_market_probe/endpoints.json` |
| **P1** | NetworkRecorder + MarketFetchClient + Normalizer | 接口直采链路 |
| **P2** | Redis + PostgreSQL 双路落地（仅候选池） | 行情入库 |
| **P3** | auction_strength / late_session / moneyflow_confirm | 策略信号 |
| **P4** | 接入盘前必读 / 盘中情报台 / 盘后复盘 | 前端闭环 |

---

## 十、风险点

1. **纯 DOM 不稳定** — 虚拟列表、Canvas/SVG 图表、WebSocket 推送时 innerText 不完整
2. **页面结构变化** — 现有 NewEventExtractor 状态机适合低频事件，不适合高频行情
3. **频率控制** — 即使授权账号自用，应限频、仅采候选池、保留原始响应
4. **数据授权边界** — 限于授权账号、个人研究、本地系统使用，不扩散原始付费数据

---

## 十一、P0 原型验证建议

先写 `jyhf_market_probe.py`：

1. 打开久赢恒丰 App，进入个股详情页和资金流页面
2. 启用 Network 监听，记录所有 XHR/WebSocket 响应
3. 保存 5 分钟样本到 `tmp/jyhf_market_probe/`
4. 验证能从响应中稳定提取：`stock_id / price / minute / volume / amount / money_flow`

只要这一步验证通过，后续 Redis、PostgreSQL、策略信号均可直接推进。
