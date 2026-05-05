# FEATURE SPEC - P4.phase1

## 0. Meta
- Phase: `P4.phase1`
- 目标: 仅保留未完成任务（`T04~T07`），与 `PLAN_WBS.md` 同步。
- 说明: `T01~T03`（themes/stocks/screener 页面迁移）已完成，不再重复拆解。

## Task P4.phase1-T04 — `/recap` 迁移到 `RecapViewModelV2 + adapter`
### 1) 子功能分解
- `F-P4.phase1-T04-01` 定义 `RecapViewModelV2` 最小字段集与可空策略。
- `F-P4.phase1-T04-02` 在 `web_app_service` 增加 `recap` adapter（旧字段 -> v2 字段）。
- `F-P4.phase1-T04-03` 前端 `/recap` 页面读取 v2 DTO，移除页面端临时拼装。
- `F-P4.phase1-T04-04` 日期切换/分页/空态/错误态 UI 对齐旧链行为。
### 2) 验收映射
- `ACPT-P4-104`

## Task P4.phase1-T05 — `/intel/strong-stocks/watch` 统一口径
### 1) 子功能分解
- `F-P4.phase1-T05-01` 前端强势股页面 API 统一到 `/api/v2/strong_watch/*`。
- `F-P4.phase1-T05-02` 明确 watch list/detail/history 的字段契约与排序语义。
- `F-P4.phase1-T05-03` 清理页面内旧 alias 与兼容分支。
### 2) 验收映射
- `ACPT-P4-105`

## Task P4.phase1-T06 — SSE payload 契约化
### 1) 子功能分解
- `F-P4.phase1-T06-01` 固定事件类型白名单：`intel_item/stream_state/theme_update/validation_update/error`。
- `F-P4.phase1-T06-02` 为各事件定义字段级 schema（含必填/可空/默认值）。
- `F-P4.phase1-T06-03` 非法 payload 统一转换为 `error` 事件并保留 diagnostics。
- `F-P4.phase1-T06-04` 增加 payload contract tests（正常/缺字段/错类型）。
### 2) 验收映射
- `ACPT-P4-106`

## Task P4.phase1-T07 — SSE fallback 语义固化
### 1) 子功能分解
- `F-P4.phase1-T07-01` stream 异常自动退化 feed 轮询（含退避策略）。
- `F-P4.phase1-T07-02` fallback 状态与原因上报 diagnostics（可观测）。
- `F-P4.phase1-T07-03` 恢复 stream 后可自动回切，保证不会双通道重复渲染。
- `F-P4.phase1-T07-04` 增加故障注入测试：断连/超时/405/5xx。
- `F-P4.phase1-T07-05` 页面展示 `streamDiagnostics`：`fallbackActive/fallbackReason/streamRecoveredAt`。
### 2) 验收映射
- `ACPT-P4-107`

## 风险与回滚
- 风险: `recap/watch/stream` 同步推进时可能出现字段漂移导致前端渲染异常。
- 回滚: 保留 v2 adapter 回退分支；SSE 可降级为 feed-only 模式。

## 增量任务分解（2026-05-01 对齐第11章）

### Task P4.phase1-N01 — 复用聚合逻辑迁移到 stock_processing_service
- `F-P4.phase1-N01-01` 识别 `frontend_bff` 可复用聚合函数清单。
- `F-P4.phase1-N01-02` 下沉到 `stock_processing_service/application`。
- `F-P4.phase1-N01-03` 保持 `/api/v2/*` DTO 不破坏。

### Task P4.phase1-N02 — gateway_adapter 统一封装
- `F-P4.phase1-N02-01` 建立 `stock_processing_service` 统一 gateway 访问层。
- `F-P4.phase1-N02-02` 禁止新增直连 SQL 读路径。
- `F-P4.phase1-N02-03` 增加 adapter 单测与 contract 回归。

### Task P4.phase1-N03 — 历史复盘快照回灌与新链对齐
- `F-P4.phase1-N03-01` 盘点缺失交易日的 `pre_market_brief_snapshot/post_market_recap_snapshot`。
- `F-P4.phase1-N03-02` 建立可重复执行的回灌脚本（按交易日回灌，支持 dry-run）。
- `F-P4.phase1-N03-03` 回灌后验证 `stock_processing_service /api/v1/post_market_snapshot` 非 `missing`。
- `F-P4.phase1-N03-04` 验证 `web_app_service /api/v2/recap` 返回真实复盘内容（非兜底摘要）。

## 进度回写（2026-05-01 增量）
- 已完成 `P4.phase1-T06`（SSE payload 契约兼容修复）：
  - `heartbeat` 事件纳入合法事件契约。
  - `intel_item` 支持上游嵌套 `item` payload。
  - contract tests 通过（`web_app_service/tests/test_p4_phase0_contracts.py`）。
- 已完成 `P4.phase1-N01` 第一批（read 路径最小迁移）：
  - `stock_processing_service` 新增 `/api/v1/intel_feed`。
  - `web_app_service` 参数映射修正：`feed_date/item_type`。
  - 空 query 参数清洗（避免 `subject_key=&stock_id=` 导致 0 条）。
- 已完成 `P4.phase1-T07` 前端稳定性子项：
  - 中栏默认不受左栏自动主题选择影响（防止几秒后被误过滤为空）。
  - 新增“按左栏主题过滤中栏”显式开关（默认关闭）。
  - 列表渲染保护：已有 `items` 时不被瞬时 `loading/error` 覆盖清空。
- 已完成 `collection` 新链服务收口（运行边界修正）：
  - `stock_processing_service` 新增 `/api/v1/collection/availability|start|status|cancel|continue`。
  - `web_app_service /api/v2/collection/*` 已改为仅转发 `stock_processing_service:8090`。
  - 明确不再依赖 `frontend_bff:8003` 作为 collection 上游。
