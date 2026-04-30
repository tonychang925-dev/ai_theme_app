# ACCEPTANCE — Phase P4.phase0（前端统一出口与三栏作战台）

## 冲突裁决说明
- 强势股接口口径冲突已裁决：前端页面统一使用 `/api/v2/intel/strong-stocks/watch`；`/api/v2/strong_watch` 仅保留兼容/内部口径。
- 实时链路裁决：本阶段采用 `SSE 主通道 + feed 兜底`，`WS` 不作为验收必选项。

## Phase P4.phase0 — 前端统一出口与三栏作战台

### 1) 目标（Objective）
- 建立前端统一 `/api/v2/*` 出口，完成 `/intel` 三栏最小可用。
- 验收关注“可执行、可回放、可阻断”：接口可用、SSE/兜底可用、A/B/D 门禁可用。

### 2) 验收目标（Acceptance Targets）
- [ACPT-P4.phase0-001] `frontend/src` 不存在非 `/api/v2/*` 的 `/api/*` 请求路径。
- [ACPT-P4.phase0-002] `GET /api/v2/intel/feed` 可用并返回标准结构。
- [ACPT-P4.phase0-003] `GET /api/v2/intel/stream` 可建立 SSE，事件类型受白名单约束。
- [ACPT-P4.phase0-004] `GET /api/v2/intel/strong-stocks/watch` 可用且无 405。
- [ACPT-P4.phase0-005] `/api/v2/workspace/theme-radar|intel-context|market-validation` 全部可用。
- [ACPT-P4.phase0-006] v2 contract tests 全部通过并纳入 CI。
- [ACPT-P4.phase0-007] A/B 回放无差异（目标日期 Disagreement=0）。
- [ACPT-P4.phase0-008] Layer B confirmed 覆盖率 >= 95%。
- [ACPT-P4.phase0-009] D 层输入收口单测通过（7日窗口/Universe/Admission）。

### 3) 验收用例（Given/When/Then）

- [ACC-P4.phase0-01]
  - Given: 代码在当前分支
  - When: 执行 `rg -n --pcre2 "['\"]/api/(?!v2/)" frontend/src`
  - Then: 无输出（退出码 0），否则 Fail

- [ACC-P4.phase0-02]
  - Given: frontend_bff 可运行
  - When: 执行 `PYTHONPATH=. .venv/bin/python -m pytest -q frontend_bff/tests/unit/test_v2_contract_aliases.py`
  - Then: 全通过（当前基线 3 passed），否则 Fail

- [ACC-P4.phase0-03]
  - Given: stock_processing_service 单测环境可用
  - When: 执行 `PYTHONPATH=. pytest -q stock_processing_service/tests/unit/test_post_market_recap_7d_window_guards.py stock_processing_service/tests/unit/test_strong_watch_universe.py stock_processing_service/tests/unit/test_strong_watch_admission_policy.py`
  - Then: 全通过（当前基线 9 passed），否则 Fail

- [ACC-P4.phase0-04]
  - Given: DB 可访问，`RUN_REPLAY_DB=1`
  - When: 执行 `RUN_REPLAY_DB=1 .venv/bin/python -m stock_processing_service.tests.replay._dual_run_compare --trade-dates=2026-04-07,2026-04-15,2026-04-22`
  - Then: 每个交易日 `Disagreement=0`，否则 Fail

- [ACC-P4.phase0-05]
  - Given: DB 可访问，`RUN_REPLAY_DB=1`
  - When: 执行 `RUN_REPLAY_DB=1 .venv/bin/python stock_processing_service/scripts/calc_b_confirmed_coverage.py --trade-dates 2026-04-07,2026-04-15,2026-04-22`
  - Then: `b_confirmed_coverage >= 0.95`（当前基线 0.97959），否则 Fail

- [ACC-P4.phase0-06]
  - Given: `frontend_bff` 与 `web_app_service` 已重启
  - When: 请求
    - `GET /api/v2/intel/stream?date=2026-04-29&type=all&session=all&limit=20`
    - `GET /api/v2/intel/strong-stocks/watch?date=2026-04-29&window_days=7&limit=20`
  - Then: 均非 405；返回 2xx 或可解释的业务错误码（非方法错误）

### 4) 边界与非目标（Boundary/Non-Goals）
- 不验收 Tick 级实时行情平台。
- 不验收全量 WebSocket Hub（仅 SSE + feed fallback）。
- 不验收产业链独立服务化与复杂图谱渲染。
- 不在本阶段要求完成全部页面（`/themes/:subjectKey`、`/stocks/:stockId`、`/screener`、`/collection` 可后续阶段推进）。

### 5) 数据样例（Data Samples）
- SSE 请求样例：`/api/v2/intel/stream?date=2026-04-29&type=all&session=all&limit=20`
- Strong Watch 请求样例：`/api/v2/intel/strong-stocks/watch?date=2026-04-29&window_days=7&limit=20`
- 覆盖率输出样例关键字段：
  - `ok: true`
  - `b_confirmed_coverage: 0.9795918367`

### 6) 失败判定（Fail Fast Criteria）
- 任一命令出现 traceback / 非零退出码（且非已知可忽略告警）。
- 出现 `/api/v2/intel/stream` 或 `/api/v2/intel/strong-stocks/watch` 405。
- 回放任一交易日 `Disagreement > 0`。
- `b_confirmed_coverage < 0.95`。
- `frontend/src` 扫描到非 v2 `/api/*` 路径。

### 7) 可观察性要求（Observability）
- 必需日志字段：
  - `request_path`, `status_code`, `error_code`, `trade_date`
  - SSE：`event_type`, `reconnect_count`, `fallback_triggered`
- 必需指标：
  - `intel_feed_success_rate`
  - `intel_stream_connect_success_rate`
  - `intel_stream_fallback_count`
  - `layer_b_confirmed_coverage`

### 8) 变更兼容性说明（Compatibility）
- DTO 字段遵循“只增不改语义”。
- 兼容期允许后端保留旧别名路由，但前端不得回退调用旧路径。
- 破坏性接口调整需先更新契约文档并通过变更评审。

### 9) 通过判定（Exit Criteria）
- 以下条件必须全部满足（AND）：
  1. ACPT-P4.phase0-001 ~ 009 全部通过
  2. CI 中 v2 路径阻断与 contract tests 生效
  3. 关键服务重启后线上抽检不出现 405
  4. 无未关闭 P0 阻断缺陷
