# FEATURE SPEC - P3.phaseB

> 历史别名文件。当前 canonical 文档已迁移至 [FEATURE_SPEC_P3.phase3.md](/Users/admin/Desktop/ai_theme_app/docs/project_control/FEATURE_SPEC_P3.phase3.md)。
> 本文件保留用于兼容既有引用，不再作为后续增量维护主文件。

## 0. Meta
- Phase: `P3.phaseB`
- 目标: 为 `/intel` 情报台补齐实时刷新能力，使后台持续抓取、结构化、题材匹配成功后的新增情报能自动推送到前端页面。
- 范围:
  - 新增 `GET /api/intel/stream`（SSE）
  - 定义 `intel_feed_event` 增量事件模型
  - 前端 `/intel` 页面接入 `EventSource`
  - 保留 `/api/intel/feed` 轮询兜底
- 非目标:
  - 不实现完整 WebSocket Hub
  - 不实现前端离线缓存与消息确认协议
  - 不实现完整复盘推送

## 1. 设计结论

- 推送方案优先采用 `SSE`，而不是第一步直接 `WebSocket`
- BFF 作为唯一前端实时出口，新增：
  - `GET /api/intel/stream`
- 前端 `/intel` 页面实时刷新采用“双轨”：
  - 主路径：SSE 增量推送
  - 兜底：`30s` 周期性拉取 `/api/intel/feed`

## 2. 数据流

```text
news抓取
-> news_event 结构化
-> ThemeMatchEngine 匹配成功 / new_theme 候选产出
-> intel_feed_event 生成
-> frontend_bff:/api/intel/stream (SSE)
-> frontend /intel 列表顶部插入
-> /api/intel/feed 定时补拉兜底
```

## 3. 实时事件模型

```ts
interface IntelFeedEvent {
  event_id: string
  occurred_at: string
  event_type: 'event' | 'theme_move' | 'new_theme'
  item: IntelFeedItem
  cursor?: string
}
```

说明：
- `item` 直接复用现有 `IntelFeedItem`
- `cursor` 用于未来断点恢复
- 首期不要求 ACK

## 4. 后端接口设计

### 4.1 SSE 接口

- 接口:
  - `GET /api/intel/stream`
- 参数:
  - `date?`
  - `session=all|pre|intra|post`
  - `type=all|event|theme_move|new_theme`
  - `subject_key?`
  - `stock_id?`
- 输出:
  - `text/event-stream`

事件名建议：
- `intel_item`
- `heartbeat`

### 4.2 兜底拉取接口

- 继续使用：
  - `GET /api/intel/feed`
- 用途：
  - 首屏加载
  - SSE 断线重连后的补拉
  - 浏览器后台休眠后的恢复

## 5. 前端行为设计

### 5.1 默认行为

- 页面初始化：
  - 先拉 `/api/intel/feed`
  - 再建立 `EventSource(/api/intel/stream)`

### 5.2 收到新情报时

- 若通过当前筛选条件：
  - 插入列表顶部
  - 不打断当前已选详情
- 若不符合当前筛选：
  - 不插入当前列表
  - 可累计“未匹配新情报数”

### 5.3 断线处理

- `EventSource` 断线后自动重连
- 同时每 `30s` 轮询一次 `/api/intel/feed`
- 若发现列表顶部出现新 `item_id`，则补齐缺失项

## 6. 子功能分解

### Task P3.phaseB-T01 — `intel_feed_event` 实时事件出口
- 输入:
  - `news_event`
  - `event_theme_map`
  - `theme_move`
  - `new_theme`
- 输出:
  - 标准化 `IntelFeedEvent`
- 要求:
  - 不直接暴露底层表结构
  - 与 `IntelFeedItem` DTO 对齐

### Task P3.phaseB-T02 — `GET /api/intel/stream`
- 输入:
  - 前端 SSE 请求
- 输出:
  - 增量情报事件流
- 要求:
  - 定时 heartbeat
  - 断线可恢复

### Task P3.phaseB-T03 — `/intel` 页面实时刷新
- 输入:
  - `EventSource`
  - `/api/intel/feed`
- 输出:
  - 列表实时插入
  - 断线兜底补拉

## 7. 风险与取舍

- 风险:
  - 直接上 WebSocket 会把当前前置版复杂度拉高
  - 页面切换和筛选条件下增量事件容易造成状态漂移
- 取舍:
  - 先做 `SSE + 轮询`
  - 把“消息确认、离线恢复、全量 replay”留到后续阶段

## 8. 验收建议

- 页面打开后无需手动刷新即可看到新增情报
- 新情报满足当前筛选时，`5s` 内出现在列表顶部
- SSE 中断后，轮询兜底仍能恢复新增情报
- 当前选中项不应被新消息强制打断
