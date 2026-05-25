# CDP DOM 采集久赢恒丰 — 实现设计文档

> 版本: 1.0
> 日期: 2026-05-25
> 状态: Frozen
> 范围: 从久赢恒丰 Electron App 通过 Chrome DevTools Protocol 进行 DOM 采集，到 Redis Stream 与 PostgreSQL 双路落地的完整设计与实现

---

## 一、设计目标

构建一个**无头/半无头 DOM 采集服务**，通过 CDP (Chrome DevTools Protocol) 连接久赢恒丰 Electron App 的远程调试端口，自动：

1. 启动/重启久赢恒丰 App（带 `--remote-debugging-port=9223`）
2. 注入 Token 拦截钩子（网络层截获 JWT）
3. 导航到 "新事件" 页面
4. 从 `document.body.innerText` 提取结构化事件数据
5. 标准化、去重后双路落地：**Redis Stream**（实时情报台） + **PostgreSQL**（历史真源）

---

## 二、总体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend (React SPA, :5173)                                         │
│    ── HTTP ──> /api/v2/realtime/jyhf-cdp/*                          │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────────┐
│  web_app_service (BFF, :8000)                                        │
│  ├── api/routes.py                                                   │
│  │   ├ GET  /api/v2/realtime/jyhf-cdp/status                         │
│  │   ├ POST /api/v2/realtime/jyhf-cdp/start                          │
│  │   ├ POST /api/v2/realtime/jyhf-cdp/stop                           │
│  │   ├ GET  /api/v2/realtime/jyhf-cdp/logs                           │
│  │   ├ POST /api/v2/realtime/jyhf-cdp/service/stop                   │
│  │   └ POST /api/v2/realtime/jyhf-cdp/service/force-stop  [诊断]     │
│  └── services/jyhf_cdp_manager.py                                    │
│      └ JyhfCdpManager                                               │
│         ├ 管理 uvicorn 子进程 (:8095) 生命周期                        │
│         ├ managed / external / none 三态所有权模型                    │
│         └ 通过 httpx 与 CDP 微服务通信                                │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ HTTP (httpx, 127.0.0.1:8095)
┌───────────────────────────▼──────────────────────────────────────────┐
│  jyhf_cdp_service (FastAPI, :8095)                                   │
│  ├── app.py              — 入口, 注册路由, 信号处理                    │
│  ├── config.py           — 冻结配置 (环境变量 → 数据类)                │
│  ├── service.py          — JyhfCdpCollectorService 主循环编排          │
│  ├── cdp_client.py       — CDP WebSocket 客户端                        │
│  ├── extractors.py       — DOM 导航 + 文本提取                         │
│  ├── token_extractor.py  — JWT Token 多策略提取                        │
│  ├── normalizer.py       — 原始 dict → RawJyhfCdpEvent Pydantic 模型   │
│  ├── intel_pusher.py     — Redis Stream 发布                           │
│  ├── db_sink.py          — PostgreSQL 三表写入                          │
│  ├── state.py            — StatusStore + DedupStore 持久化状态          │
│  ├── schemas.py          — CollectorStatus / CommandResult / Event     │
│  └── app_manager.py      — JyhfAppManager: 久赢恒丰 App 进程管理       │
└──────────┬───────────────────────┬───────────────────────────────────┘
           │                       │
           ▼                       ▼
    ┌──────────────┐      ┌──────────────────┐
    │ Redis Stream │      │ PostgreSQL        │
    │ stream:event │      │ stock_data_test   │
    │ :feed        │      │ ├ subject_history │
    │ (maxlen=     │      │ │ _staging        │
    │  10000)      │      │ ├ news_event      │
    └──────────────┘      │ └ event_subject   │
                          │ _map              │
                          └──────────────────┘
```

---

## 三、核心采集循环

```
┌──────────────────────────────────────────────────────────────────┐
│ _loop(run_id) — 每 interval_seconds (默认20s) 执行一次             │
│                                                                  │
│  1. JyhfAppManager.ensure_running()                              │
│     ├ 检查 :9223/json 是否已有久赢恒丰页面                         │
│     ├ 是 → 复用（external 模式）                                   │
│     └ 否 → subprocess.Popen /Applications/久赢恒丰.app            │
│            --remote-debugging-port=9223, 轮询最多 15s              │
│                                                                  │
│  2. CDPClient(:9223).connect()                                   │
│     └ 发现 webSocketDebuggerUrl → 打开 WS → Runtime.enable       │
│                                                                  │
│  3. TokenExtractor.inject_hooks(cdp)          ← Phase 1          │
│     └ 注入 JS monkey-patch: window.fetch / XHR.setRequestHeader   │
│                                                                  │
│  4. NewEventExtractor.prepare(cdp)                                │
│     ├ $router.push('/') → 等待 hash 变化                           │
│     ├ 找到 "新事件" tab → click                                   │
│     └ 轮询 document.body.innerText 含 "驱动事件"/"搜索" (最多3s)   │
│                                                                  │
│  5. NewEventExtractor.read(cdp) → (events[], feed_date, body)    │
│     └ 单次 CDP evaluate: JS 内解析 innerText 为结构化事件列表      │
│                                                                  │
│  6. TokenExtractor.read_captured_tokens(cdp)  ← Phase 2          │
│     └ 读取 window.__cdp_captured_tokens__ (导航触发的 API 请求)    │
│                                                                  │
│  7. CDPClient.close()                                            │
│                                                                  │
│  8. Per-event: normalizer.normalize() → IntelPusher.push()       │
│     └ Redis XADD stream:event:feed                               │
│                                                                  │
│  9. _flush_db_events()                                           │
│     └ DatabaseSink.write_events() → PostgreSQL                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 四、组件详细设计

### 4.1 CDP 客户端 (`cdp_client.py`)

**职责**: 底层 Chrome DevTools Protocol WebSocket 通信。

**协议**:
1. `GET http://localhost:{port}/json` → 发现 JYHF 页面的 `webSocketDebuggerUrl`
2. 打开 WebSocket 连接
3. 发送 `{"id":1, "method":"Runtime.enable"}` 启用 Runtime 域
4. 核心方法: `evaluate(expression, timeout=8.0)` → `Runtime.evaluate` 并等待响应

**关键约束**:
- 连接仅在一次采集周期内有效，用完即关闭
- 异常策略: fail-open，采集失败 → 本轮跳过 → 下一周期重试
- 不保持长连接（避免 CDP 连接超时断开）

### 4.2 DOM 提取器 (`extractors.py`)

**职责**: 导航久赢恒丰 Vue 路由到 "新事件" 页面，从 `document.body.innerText` 提取结构化事件。

**两阶段操作**:

#### prepare(cdp) — DOM 导航
1. `$router.push('/')` 回到首页
2. 查找 "新事件" tab 并点击（精确匹配 → 模糊匹配 → 叶子节点优先）
3. 轮询等待 DOM 渲染完成（最多 3s）
4. 失败 → 抛出 `PrepareRetryError`（下一周期重试，不阻塞采集循环）

#### read(cdp) → (events, feed_date, body_text)
单次 `Runtime.evaluate` 在 JS 环境内完成所有解析：

```
状态机解析规则:
  - "HH:MM" 格式行 → 新事件开始
  - "+X.X%" 行 → pct_chg
  - "【驱动事件：XXX】" → driver_title
  - "（新闻来源：XXX）" → news_source
  - 长文本行 → driver_desc
  - 跳过: "连板复盘"、"热门题材复盘"、"龙虎榜" 等非事件板块
  - 搜索 "搜索" 锚点后的日期格式 "YYYY-M-D" → feed_date
  - 遇到第二个日期头 → 停止（仅提取当日数据）
```

### 4.3 Token 提取器 (`token_extractor.py`)

**背景**: 久赢恒丰 App 的 JWT Token 仅存在于 JS 运行时内存，不在 localStorage/sessionStorage 中。

**多策略提取** (按优先级):

| 优先级 | 策略 | 方法 |
|--------|------|------|
| 1 | 网络拦截 (主策略) | inject hooks → monkey-patch fetch/XHR → 拦截 Authorization header → 写入 `window.__cdp_captured_tokens__` |
| 2 | localStorage | 枚举所有 key → JSON dump → 正则匹配 `token/jwt/bearer` 或 JWT 三段式 |
| 3 | sessionStorage | 同 localStorage |
| 4 | Vue 全局属性 | 探测 `$auth` 插件 → dump 非函数属性 |
| 5 | Vuex/Pinia Store | 遍历 `$store.state` / `$pinia._s`，含 Axios `defaults.headers` |

**两阶段注入**:
- Phase 1 (prepare 前): 注入钩子代码
- Phase 2 (read 后): 读取捕获到的 Token（导航触发的 API 请求已被拦截）

Token 写入 `/tmp/jyhf_auth_token.json` 供其他服务读取。

### 4.4 事件标准化器 (`normalizer.py`)

**职责**: 将 `extractors.py` 产出的原始 dict 转换为 `RawJyhfCdpEvent` Pydantic 模型。

```python
class RawJyhfCdpEvent:
    event_id: str          # jyhf_cdp_{YYYYMMDD}_{dedup_key[:12]}
    dedup_key: str         # SHA-256(trade_date|event_time|subject|driver_title|driver_desc)
    source_system: str     # "jyhf"
    source_channel: str    # "jyhf_cdp"
    source_type: str       # "cdp_dom_new_event"
    capture_time: datetime
    trade_date: str        # YYYY-MM-DD
    event_time: str
    subject_name: str
    subject_key: str | None
    pct_chg: float | None
    driver_title: str
    driver_desc: str
    news_source: str | None
    event_type: str        # "驱动事件" | "新题材更新"
    raw_text: str          # 原始 DOM 文本
    parse_version: str
```

### 4.5 Intel Pusher (`intel_pusher.py`)

**职责**: 将 `RawJyhfCdpEvent` 转换为 intel feed 格式，发布到 Redis Stream。

**启用条件**: `JYHF_CDP_PUSH_INTEL=1`

**Stream 配置**:
- Key: `stream:event:feed`
- MAXLEN: 10000
- 消费者组: 无（新链通过 DB 查询，不依赖 Redis 消费组）

**Feed Item 结构**:
```json
{
  "item_id": "jyhf_cdp:{event_id}",
  "event_type": "event",
  "occurred_at": "2026-05-25T09:26:00+08:00",
  "title": "MLCC电容",
  "summary": "MLCC电容价格上涨",
  "theme_names": ["MLCC电容"],
  "theme_subject_keys": ["MLCC电容"],
  "confidence": 0.8,
  "impact_score": 60,
  "source_type": "jyhf_cdp_dom",
  "source_channel": "jyhf_cdp",
  "pct_chg": 5.2,
  "driver_title": "MLCC电容价格上涨",
  "driver_desc": "...",
  "news_source": "财联社",
  "review_required": false
}
```

**置信度模型**:
| 条件 | confidence |
|------|-----------|
| subject + driver + date + time | 0.8 |
| subject + driver 仅 | 0.5 |
| 仅 subject | 0.3 |

**影响分映射** (pct_chg → impact_score):
| pct_chg | score |
|---------|-------|
| >= 15% | 90 |
| >= 10% | 85 |
| >= 7% | 80 |
| >= 5% | 70 |
| >= 3% | 60 |
| < 3% | 40 |

**Review 要求**: `subject_key` 为空 或 `confidence < 0.7` → `review_required = true`

### 4.6 Database Sink (`db_sink.py`)

**职责**: 将事件写入 PostgreSQL，幂等可重放。

**启用条件**: `JYHF_CDP_PUSH_DB=1`

**三表写入**:

| 表 | INSERT 策略 | idempotent key |
|----|-----------|----------------|
| `subject_history_staging` | ON CONFLICT DO NOTHING | `(subject_key, subject_rank_id)` |
| `news_event` | ON CONFLICT DO NOTHING | `source_trace_id = 'jyhf_cdp:{event_id}'` |
| `event_subject_map` | ON CONFLICT DO NOTHING | `(event_id, subject_key, source)` |

**news_event 字段映射**:
```python
{
    "source_category": "jyhf_dom",
    "source_trace_id": f"jyhf_cdp:{event_id}",
    "theme_directive_processed": True,
    "confidence": 1.0,
    "news_id": 0,  # 无原始新闻关联
    "event_type": "主题驱动" | "新题材",
}
```

**event_subject_map 写入条件**: `subject_key` 和 `subject_name` 均存在时写入

### 4.7 状态管理 (`state.py`)

**StatusStore**: JSON 文件持久化 CollectorStatus
- 原子写入 (write to `.tmp` → rename)
- 线程安全 (threading.Lock)

**DedupStore**: LRU 去重键持久化 (max 5000 keys)
- OrderedDict 内存缓存 + JSON 磁盘备份
- 目前去重主要依赖 DB 层 `ON CONFLICT DO NOTHING`

---

## 五、生命周期管理

### 5.1 BFF 管理层 (`web_app_service/services/jyhf_cdp_manager.py`)

**所有权模型**:

| owner | 含义 | 启动行为 | 停止行为 |
|-------|------|---------|---------|
| `none` | 8095 端口无进程 | 先 launch 进程 | 无操作 |
| `managed` | 本 BFF 实例通过 Popen 启动 | 直接启动 collector | killpg 进程组 |
| `external` | 8095 已运行但非本实例启动 | 仅启动 collector | **不杀进程** |

**启动流程**:
1. 检查 8095 端口 → 确定 owner
2. 若 `none`: `_launch_process()` → subprocess.Popen uvicorn
3. POST `/collector/start` → 轮询 `/status` 等待 `collector_running=true` (最多 7.5s)
4. 超时返回 `ok=true` + 等待消息（不杀进程，允许 CDP 在后续周期连接）

**停止约束**:
- `stop_collector`: 停止采集循环，managed 则杀进程
- `stop_service`: 仅杀 managed
- `force_stop_service`: 诊断接口，lsof + SIGKILL，不限 owner

**BFF 关闭行为**: 默认不杀 CDP 服务 (`JYHF_CDP_STOP_ON_BFF_SHUTDOWN=0`)，避免 BFF 重启导致 CDP 采集中断。

### 5.2 App 进程管理 (`app_manager.py`)

**JyhfAppManager**:
- `is_running_with_cdp()`: HTTP GET `http://localhost:9223/json` → 检查页面标题含 "久赢恒丰"
- `ensure_running()`: 幂等启动，带互斥锁防并发，最多重试 2 次
- `stop_app()`: pkill -f 久赢恒丰，轮询等端口释放

**启动参数**: `/Applications/久赢恒丰.app --remote-debugging-port=9223`

---

## 六、配置一览

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `JYHF_CDP_SERVICE_PORT` | 8095 | CDP 微服务 HTTP 端口 |
| `JYHF_CDP_PORT` | 9223 | Electron CDP 调试端口 |
| `JYHF_CDP_INTERVAL_SECONDS` | 20 | 采集周期间隔 |
| `JYHF_APP_PATH` | `/Applications/久赢恒丰.app` | App Bundle 路径 |
| `JYHF_CDP_PUSH_INTEL` | 0 | 启用 Redis Stream 发布 |
| `JYHF_CDP_PUSH_DB` | 0 | 启用 PostgreSQL 写入 |
| `JYHF_CDP_REDIS_STREAM_FEED` | `stream:event:feed` | Redis Stream Key |
| `JYHF_CDP_STOP_ON_BFF_SHUTDOWN` | 0 | BFF 关闭时是否杀 CDP |
| `REDIS_HOST/PORT/DB` | localhost/6379/0 | Redis 连接 |
| `PG_HOST/PORT/DATABASE/USERNAME/PASSWORD` | localhost/5432/stock_data_test | PostgreSQL 连接 |
| `PYTHON` / `CONDA_PYTHON` | — | Python 解释器路径（BFF 启动子进程用） |

---

## 七、异常处理与容错

| 场景 | 处理策略 |
|------|----------|
| CDP 连接失败 | 本轮跳过，日志记录，下一周期重试 |
| "新事件" tab 未找到 | `PrepareRetryError` → 不阻塞循环，下周期重试 |
| DOM 解析返回空 | 状态更新为 "error"，继续循环 |
| Redis 推送失败 | 异常日志 + 继续处理后续事件 |
| DB 写入失败 | 异常日志 + 批次标记失败，不阻塞采集 |
| Token 提取失败 | 非致命，仅记录警告，事件提取不受影响 |
| JYHF App 启动超时 | 最多重试 2 次，每次最多等待 15s |
| Qwen 熔断 (prefilter) | p95 > 20s 或 error_rate > 20% → 降级为 rule-only |

---

## 八、API 端点参考

### CDP 微服务 (`:8095`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/status` | CollectorStatus JSON |
| POST | `/collector/start` | 启动采集循环 |
| POST | `/collector/stop` | 停止采集循环 |
| POST | `/collector/restart` | 重启采集循环 |
| GET | `/collector/logs?lines=300` | 获取日志 |

### BFF 代理 (`:8000/api/v2`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/realtime/jyhf-cdp/status` | 聚合状态 (含 owner/pid 等) |
| POST | `/realtime/jyhf-cdp/start` | 启动 CDP 采集 |
| POST | `/realtime/jyhf-cdp/stop` | 停止 CDP 采集 |
| GET | `/realtime/jyhf-cdp/logs?lines=300` | 获取日志 |
| POST | `/realtime/jyhf-cdp/service/stop` | 停止 managed 进程 |
| POST | `/realtime/jyhf-cdp/service/force-stop` | 强杀 8095 (诊断) |

---

## 九、部署方式

```bash
# 方式1: BFF 管理 (推荐)
# web_app_service 启动时自动初始化 JyhfCdpManager
# 通过 API POST /api/v2/realtime/jyhf-cdp/start 启动

# 方式2: 独立启动 (调试)
JYHF_CDP_PUSH_INTEL=1 JYHF_CDP_PUSH_DB=1 \
python -m uvicorn services.jyhf_cdp_service.app:app \
  --host 127.0.0.1 --port 8095
```

---

## 十、与系统其他组件的联动

| 下游消费者 | 消费方式 | 用途 |
|-----------|---------|------|
| 前端情报台 `/intel` | `GET /api/v2/intel/feed` → DB 查询 | 实时事件展示 |
| 题材匹配引擎 | Redis `stream:event:feed` → 消费 | 题材聚合与匹配 |
| 每日复盘 | DB `news_event` + `event_subject_map` | 复盘事件链构建 |

---

## 十一、设计约束与冻结项

1. CDP 连接仅在一轮采集周期内有效，不保持长连接
2. DOM 提取依赖久赢恒丰 App 的 Vue 路由结构 — "新事件" tab 文本必须匹配
3. Token 提取失败不影响事件采集（非致命）
4. managed/external 所有权模型不可破坏 — external 进程绝不被误杀
5. Shell 脚本 (`start_jyhf_cdp_service.sh`) 不再被 manager 调用，仅用于外部调试
6. DB 写入幂等 — 同一 `source_trace_id` 不会重复插入

---

## 十二、变更历史

| 日期 | 变更 |
|------|------|
| 2026-05-15 | 初始实现: Popen 直接启动、managed/external 模型、多策略 Token 提取 |
| 2026-05-25 | 编写设计文档，冻结架构 |
