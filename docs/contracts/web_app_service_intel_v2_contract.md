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
{ "status": "connected", "source": "sse", "ts": "2026-04-29T09:35:01+08:00" }
```

#### `theme_update`
```json
{ "subject_key": "9035101", "heat": 82.1, "stage": "ACCELERATE", "stock_count": 14 }
```

#### `validation_update`
```json
{
  "trade_date": "2026-04-29",
  "subject_key": "9035101",
  "stock_id": "600152.SH",
  "candidate_level": "observe_only",
  "support_type": "prior_breakout_retest",
  "support_score": 71.2,
  "reject_reasons": ["末端跳水"]
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
- 当前实现为新链读口模式（上游 `stock_processing_service /api/v1/intel_feed`），禁止回退旧 `/api/intel/*` 主路径。
- 字段策略：向后兼容，新增字段只增不删。
- 版本升级：新增破坏性变更时发布 `V2` DTO/新路径。

---

## 3.1 Workspace 三栏最小字段冻结（P4.phase0-R02）

### GET `/api/v2/workspace/theme-radar`
```ts
interface ThemeRadarViewModel {
  date?: string
  themes: Array<{
    theme_id: string
    theme_name: string
    heat: number
    stage: string
    stock_count: number
  }>
  source?: string
  diagnostics?: Record<string, unknown>
}
```

### GET `/api/v2/workspace/intel-context`
```ts
interface IntelContextViewModel {
  date?: string
  subject_key?: string | null
  stock_id?: string | null
  items: IntelItem[]
  count: number
  source?: string
  diagnostics?: Record<string, unknown>
}
```

### GET `/api/v2/workspace/market-validation`
```ts
interface MarketValidationViewModel {
  trade_date: string
  subject_key?: string | null
  stock_id?: string | null
  candidate_level: string
  support_type: string
  support_score: number | null
  reject_reasons: string[]
  strong_watch_count: number
  w2s_candidate_count: number
  stock_validation?: Record<string, unknown> | null
  source?: string
}
```

字段策略：以上字段只增不破，语义不可漂移。

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
- data 行先于 event 行时统一返回：
```json
{ "code": "MISSING_EVENT_BEFORE_DATA", "message": "...", "retryable": true }
```
- payload 非 JSON 对象或缺失事件必填字段时统一返回：
```json
{ "code": "INVALID_EVENT_PAYLOAD", "message": "...", "retryable": true, "event_type": "intel_item" }
```

### 前端 fallback diagnostics（P4.phase1-T07）
- Intel 页面需暴露下列诊断字段用于灰度观测：
```ts
interface StreamDiagnosticsView {
  fallbackActive: boolean
  fallbackReason: string | null
  streamRecoveredAt: string | null
}
```

## 3.2 字段可空性与语义冻结（2026-05-01，P4.phase0-R02 增量）

### 强制可空性
- `ThemeRadarViewModel.date`：可空。
- `ThemeRadarViewModel.source`：可空。
- `ThemeRadarViewModel.diagnostics`：可空。
- `IntelContextViewModel.date`：可空。
- `IntelContextViewModel.subject_key`：可空。
- `IntelContextViewModel.stock_id`：可空。
- `IntelContextViewModel.source`：可空。
- `IntelContextViewModel.diagnostics`：可空。
- `MarketValidationViewModel.subject_key`：可空。
- `MarketValidationViewModel.stock_id`：可空。
- `MarketValidationViewModel.support_score`：可空。
- `MarketValidationViewModel.stock_validation`：可空。
- `MarketValidationViewModel.source`：可空。

### 非可空核心字段
- `ThemeRadarViewModel.themes`（数组，允许空数组，不允许缺失）
- `IntelContextViewModel.items`（数组，允许空数组，不允许缺失）
- `IntelContextViewModel.count`（number，不允许缺失）
- `MarketValidationViewModel.trade_date`（string，不允许缺失）
- `MarketValidationViewModel.candidate_level`（string，不允许缺失）
- `MarketValidationViewModel.support_type`（string，不允许缺失）
- `MarketValidationViewModel.reject_reasons`（数组，允许空数组，不允许缺失）
- `MarketValidationViewModel.strong_watch_count`（number，不允许缺失）
- `MarketValidationViewModel.w2s_candidate_count`（number，不允许缺失）

### 语义冻结规则
1. 只增不破：允许新增字段，不允许删除/重命名现有字段。
2. 类型冻结：既有字段类型不可变更（例如 `count` 不得从 number 变 string）。
3. 错误语义冻结：workspace 三接口上游异常时，优先返回 `200 + diagnostics.partial=true`，禁止直接向页面抛 503。
4. 计算边界冻结：页面禁止临时重算 A/B/C/D，仅消费对象快照或聚合 DTO。
