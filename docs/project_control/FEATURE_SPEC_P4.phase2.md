# FEATURE SPEC - P4.phase2

## 0. Meta
- Phase: `P4.phase2`
- 目标: 完成页面迁移收口 + 旧 alias 清零 + CI 阻断 + 灰度/回滚演练。
- 说明: 本阶段以“迁移覆盖完成”为核心门槛，未清零旧 alias 不得进入 `phase3`。
- 强制边界（新增）:
  - 仅允许新链服务运行：`frontend -> web_app_service:8000 -> stock_processing_service:8090 -> database gateway`。
  - 禁止 `web_app_service` 运行态依赖 `frontend_bff:8003`。
  - 允许复用旧链数据表与代码逻辑，但不得复用旧链服务进程。

## Task P4.phase2-T01 — `/collection` 迁移收口
### 1) 子功能分解
- `F-P4.phase2-T01-01` `CollectionPage` 仅调用 `/api/v2/collection/*`。
- `F-P4.phase2-T01-02` 清理页面内历史兼容分支与重复请求路径。
- `F-P4.phase2-T01-03` 核对 start/status/cancel/continue 错误语义一致性。
- `F-P4.phase2-T01-04` `web_app_service` 的 `/api/v2/collection/*` 仅转发 `stock_processing_service:/api/v1/collection/*`。
- `F-P4.phase2-T01-05` `stock_processing_service` 承载 `collection availability/start/status/cancel/continue` 服务接口（可复用旧链代码，不复用旧链服务）。
### 2) 验收映射
- `ACPT-P4-201`

## Task P4.phase2-T02 — `/realtime-collector` 迁移收口
### 1) 子功能分解
- `F-P4.phase2-T02-01` 页面仅调用 `/api/v2/realtime/collector/*`。
- `F-P4.phase2-T02-02` 完成 start/stop/status/logs 四接口联调。
- `F-P4.phase2-T02-03` 明确连接失败提示语义与回退动作。
### 2) 验收映射
- `ACPT-P4-202`

## Task P4.phase2-T03 — 状态治理统一
### 1) 子功能分解
- `F-P4.phase2-T03-01` 对齐 `intel/theme/validation/workspace` 共享字段。
- `F-P4.phase2-T03-02` 移除页面端临时重算与重复派生状态。
- `F-P4.phase2-T03-03` 状态生命周期（loading/error/ready/fallback）统一。
### 2) 验收映射
- `ACPT-P4-203`

## Task P4.phase2-T04 — 旧 alias 清零（阻断项）
### 1) 子功能分解
- `F-P4.phase2-T04-01` 删除 `theme-workspace/stock-workspace` 旧别名回退。
- `F-P4.phase2-T04-02` 删除 `stock-screener` 旧别名回退。
- `F-P4.phase2-T04-03` 删除 `intel/strong-stocks/watch` 旧别名回退。
- `F-P4.phase2-T04-04` 形成“旧路径清零”扫描清单。
### 2) 必跑命令
- `rg -n "/api/v2/theme-workspace|/api/v2/stock-workspace|/api/v2/stock-screener|/api/v2/intel/strong-stocks/watch" frontend/src`
### 3) 验收映射
- `ACPT-P4-204`

## Task P4.phase2-T05 — CI 阻断固化
### 1) 子功能分解
- `F-P4.phase2-T05-01` 将 `T04` 路径扫描加入 CI workflow。
- `F-P4.phase2-T05-02` 增加失败策略与豁免审计说明。
- `F-P4.phase2-T05-03` PR 演练验证阻断有效。
- `F-P4.phase2-T05-04` 新增运行边界阻断：检测到 `frontend_bff:8003` 被 `web_app_service` 依赖则阻断。
### 2) 验收映射
- `ACPT-P4-205`

## Task P4.phase2-T06 — 灰度指标日报（5交易日）
### 1) 子功能分解
- `F-P4.phase2-T06-01` 指标模板：`stream/feed success rate`、`fallback_count`、`first_screen_ms`、`linkage_pass_rate`。
- `F-P4.phase2-T06-02` 每日自动采集与归档。
- `F-P4.phase2-T06-03` 异常阈值告警与复盘说明。
### 2) 执行命令（5交易日模板）
- `for d in 2026-04-24 2026-04-25 2026-04-28 2026-04-29 2026-04-30; do .venv/bin/python scripts/collect_p4_phase2_metrics.py --date \"$d\" --base-url http://127.0.0.1:8000; done`
### 3) 产物路径
- `tmp/p4_phase2_metrics/metrics_YYYY-MM-DD.json`
- `tmp/p4_phase2_metrics/daily_YYYY-MM-DD.md`
### 4) 验收映射
- `ACPT-P4-206`

## Task P4.phase2-T07 — 故障注入演练
### 1) 子功能分解
- `F-P4.phase2-T07-01` 注入 SSE 断连/上游 5xx/405。
- `F-P4.phase2-T07-02` 验证自动 fallback 与自动回切。
- `F-P4.phase2-T07-03` 验证 `streamDiagnostics` 三字段轨迹完整。
### 2) 执行命令
- `.venv/bin/python scripts/run_p4_phase2_fault_drill.py --date 2026-04-29 --base-url http://127.0.0.1:8000`
### 3) 产物路径
- `tmp/p4_phase2_drill/drill_YYYY-MM-DD.json`
- `tmp/p4_phase2_drill/drill_YYYY-MM-DD.md`
### 4) 验收映射
- `ACPT-P4-207`

## Task P4.phase2-T08 — 回滚矩阵演练
### 1) 子功能分解
- `F-P4.phase2-T08-01` 入口回滚（路由/页面）。
- `F-P4.phase2-T08-02` SSE 通道回滚（stream->feed-only）。
- `F-P4.phase2-T08-03` 三栏开关回滚。
### 2) 执行命令
- `.venv/bin/python scripts/run_p4_phase2_rollback_drill.py --date 2026-04-29`
### 3) 产物路径
- `tmp/p4_phase2_rollback/rollback_YYYY-MM-DD.json`
- `tmp/p4_phase2_rollback/rollback_YYYY-MM-DD.md`
### 4) 验收指标
- RTO <= 5 分钟
### 5) 验收映射
- `ACPT-P4-208`

## Task P4.phase2-T09 — phase2 收口门禁
### 1) 子功能分解
- `F-P4.phase2-T09-01` 清点迁移缺口并关闭阻断缺陷。
- `F-P4.phase2-T09-02` 形成 phase2 完成报告与入 phase3 条件。
### 2) 验收映射
- `ACPT-P4-209`

## 风险与回滚
- 风险: 旧 alias 清理过快导致存量分支调用失败。
- 回滚: 按回滚矩阵恢复 route alias + feature flag，RTO <= 5 分钟。

## 增量任务分解（2026-05-01 对齐第11章）

### Task P4.phase2-N01 — 脚本能力服务化（第一批）
- `F-P4.phase2-N01-01` strong_watch 脚本迁移为 job service。
- `F-P4.phase2-N01-02` w2s 脚本迁移为 job service。
- `F-P4.phase2-N01-03` recap 构建脚本迁移为 service。

### Task P4.phase2-N02 — 任务调度与审计
- `F-P4.phase2-N02-01` 任务幂等键与重试策略。
- `F-P4.phase2-N02-02` 执行日志结构化与 trace_id。
- `F-P4.phase2-N02-03` 失败任务可回放与差异报告。
