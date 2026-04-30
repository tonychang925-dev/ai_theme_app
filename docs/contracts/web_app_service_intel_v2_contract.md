# web_app_service `/api/v2/intel/*` 契约（V1）

## 1. GET `/api/v2/intel/feed`

### Query
- `date?: string` (`YYYY-MM-DD`)
- `session?: "all"|"pre"|"intra"|"post"`（默认 `all`）
- `type?: "all"|"event"|"event_review"|"theme_move"|"new_theme"|"stock_move"`（默认 `all`）
- `subject_key?: string`
- `stock_id?: string`
- `limit?: number`（1~500，默认 100）

### 200 Response (DTO)
```ts
interface IntelFeedViewV1 {
  items: IntelItem[]
  count: number
  date?: string
  session?: string
  type?: string
  diagnostics?: {
    partial?: boolean
    [k: string]: unknown
  }
}

interface IntelItem {
  item_id?: string
  occurred_at?: string
  item_type?: string
  title?: string
  ai_summary?: string
  subject_key?: string
  stock_id?: string
  [k: string]: unknown
}
```

### Error
- `400` 参数错误
- `502` 上游不可用/响应非法
- `504` 上游超时

---

## 2. GET `/api/v2/intel/stream` (SSE)

### Query
同 `/api/v2/intel/feed`，其中 `limit` 默认 `20`，范围 `1~100`。

### SSE Event Types
- `intel_item`
- `heartbeat`
- `stream_state`
- `theme_update`
- `validation_update`
- `error`

### Payload 示例

#### `intel_item`
```json
{
  "eventId": "evt_20260429_0001",
  "eventTime": "2026-04-29T09:35:01+08:00",
  "themeId": "9035101",
  "themeName": "钠离子电池",
  "title": "盘中异动",
  "aiSummary": "主线回流，强度提升",
  "impactScore": 78.4,
  "stockId": "600152.SH"
}
```

#### `heartbeat`
```json
{ "status": "ok", "ts": "2026-04-29T09:35:15+08:00" }
```

#### `stream_state`
```json
{ "state": "connected", "source": "sse", "ts": "2026-04-29T09:35:01+08:00" }
```

#### `theme_update`
```json
{ "themeId": "9035101", "heat": 82.1, "stage": "ACCELERATE", "stockCount": 14 }
```

#### `validation_update`
```json
{
  "themeId": "9035101",
  "stockId": "600152.SH",
  "candidateLevel": "observe_only",
  "supportType": "prior_breakout_retest",
  "supportScore": 71.2,
  "rejectReasons": ["末端跳水"]
}
```

#### `error`
```json
{ "code": "UPSTREAM_ERROR", "message": "...", "retryable": true }
```

### Error
- HTTP 连接建立阶段：`400/502/504`
- 流中错误：通过 `event:error` 推送

---

## 3. 兼容策略
- 当前实现为代理模式（上游 `/api/intel/*`）。
- 字段策略：向后兼容，新增字段只增不删。
- 版本升级：新增破坏性变更时发布 `V2` DTO/新路径。

## 4. 服务端校验规则（2026-04-29 增补）

`/api/v2/intel/stream` 代理层执行最小事件校验：
- 事件类型必须在白名单：`intel_item/heartbeat/stream_state/theme_update/validation_update/error`
- 若上游出现未知 `event`，服务端改写为 `event:error` 并返回：
```json
{ "code": "INVALID_EVENT_TYPE", "message": "...", "retryable": true }
```
- 上游流异常统一返回：
```json
{ "code": "UPSTREAM_STREAM_ERROR", "message": "...", "retryable": true }
```
