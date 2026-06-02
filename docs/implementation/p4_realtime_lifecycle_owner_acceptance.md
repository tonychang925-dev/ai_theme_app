# P4 Realtime Lifecycle Owner — 验收文档

## 基线

- **Tag**: `p4-realtime-lifecycle-owner-baseline-20260529`
- **分支**: `p4/realtime-ops-dashboard` (merged into `main` 2026-05-29)
- **验收人**: tonychang925-dev

## 问题背景

实时采集页面三个长期 bug：

1. **stop 后刷新页面仍显示"运行中"** — SPS `_restore_from_runtime()` 有 `if self._state.running: return` early return，status 调用不重新验证 PID 是否存活，stale PID 一直保留
2. **BFF 和 SPS 同时管理同一批子进程** — BFF `stop_pipeline()` 直接读 pidfile 发 SIGTERM/SIGKILL，与 SPS `_cleanup_processes()` 形成双 Owner 竞态
3. **Redis raw_len=10k 被误读为"采集运行中"** — 前端把 Redis stream 长度放进 `[采集]` 日志行，stop 后 raw_len 不变，用户误以为采集还在输出

## 根因总结

| 根因 | 表现 |
|------|------|
| stale `if self._state.running: return` | status 不重新验证 PID，返回 ghost running |
| BFF/SPS 双 Owner | BFF direct pidfile kill 与 SPS 同时杀进程 |
| Redis 指标混入运行日志 | raw_len 不变 → 用户误判"采集还在跑" |
| 前端每 8 秒刷 `[采集]` 日志 | stop 后日志持续输出，强化误判 |

## 最终架构

```
┌─────────────────────────────────────────────────────┐
│ SPS (stock_processing_service)                       │
│   - 唯一 lifecycle owner                             │
│   - _refresh_observed_state(): 每次 live-PID 验证     │
│   - stop: SIGTERM → 1.5s → SIGKILL → 0.5s → verify  │
│   - running_verified: 显式来自 raw_pid || dec_pid    │
│   - status_source: sps_live_pid_check | cleared      │
├─────────────────────────────────────────────────────┤
│ BFF (web_app_service)                                │
│   - 纯代理，不管理 pipeline 子进程                    │
│   - /realtime/collector/* → 透传 SPS                 │
│   - 已删除: stop_pipeline(), _pipeline_start_task    │
├─────────────────────────────────────────────────────┤
│ Frontend                                             │
│   - running 判断: raw_news_pid || decision_pid       │
│   - 日志三分类: [操作] / [生命周期] / 诊断 Tab         │
│   - Redis 指标: 仅诊断区，标注"历史数据，非运行状态"    │
│   - 生命周期日志去重: signature change 时才写          │
└─────────────────────────────────────────────────────┘
```

## 验收结果

| # | 检查项 | 结果 |
|---|--------|:--:|
| 1 | `check_realtime_lifecycle.sh` 全过 | ✅ |
| 2 | SPS stop 后: `running=false, verified=false, source=cleared, all PIDs null` | ✅ |
| 3 | ps 无当前 run_id 的 realtime 子进程 | ✅ |
| 4 | 启动脚本默认不启动 realtime | ✅ |
| 5 | `--start-realtime` 显式 opt-in | ✅ |
| 6 | 前端首次进入 stopped | ✅ |
| 7 | 启动后 PID alive + 状态正确 | ✅ |
| 8 | 停止后 PID 清空 + alive_after=[] | ✅ |
| 9 | 刷新后仍 stopped（无 stale PID） | ✅ |
| 10 | 生命周期日志只在状态变化时输出 | ✅ |
| 11 | Redis 指标只在诊断 Tab | ✅ |
| 12 | `npm run build` 通过 | ✅ |

## 关键代码位置

| 文件 | 行号 | 说明 |
|------|------|------|
| `stock_processing_service/.../realtime_stack_manager.py` | 588-644 | `_refresh_observed_state()` — live-PID 验证 |
| 同上 | 397-470 | `stop()` — SIGTERM → wait → SIGKILL → verify 完整流程 |
| 同上 | 553-560 | `status_sync()` — `running_verified` 显式来自 PID |
| 同上 | 87-101 | `RealtimeStackState.clear()` — 统一清空 |
| `web_app_service/services/realtime_stack_manager.py` | 46-87 | `start()` — 同步 SPS proxy |
| 同上 | 89-139 | `stop()` — 同步 SPS proxy |
| `web_app_service/api/routes.py` | 909-941 | `/new-chain/*` → deprecated, 指向 `/collector/*` |
| `frontend/.../RealtimeCollectorPage.tsx` | 74-87 | `buildRealtimeSig` — 去重签名（仅含 PID） |
| 同上 | 140-156 | 生命周期日志：只在 sig change 时写入 |
| `scripts/start_new_chain_stack.sh` | 73-75 | 默认不自动启动 realtime 的明确说明 |
| `scripts/check_realtime_lifecycle.sh` | - | 自动化验收脚本 |

## 后续禁止回退的原则

1. **BFF 不得再 direct pidfile kill** — 已删除 `stop_pipeline()`
2. **BFF 不得再维护 realtime pipeline task** — 已删除 `_pipeline_start_task`
3. **Frontend 不得再调用 new-chain start/stop** — 已从页面 import 中移除
4. **Frontend 不得用 Redis stream length 判断 running** — 改为基础 PID 判断
5. **SPS status 必须每次 live PID verified** — `_refresh_observed_state()` 替代 `_restore_from_runtime()`
6. **start_new_chain_stack.sh 默认不得自动启动 realtime** — `--start-realtime` 显式 opt-in
