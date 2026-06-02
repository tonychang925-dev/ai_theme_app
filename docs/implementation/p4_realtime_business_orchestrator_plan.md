# P4-2 Realtime Business Orchestrator — 实施计划

## 基线

- **依赖基线**: `p4-realtime-lifecycle-owner-baseline-20260529`
- **原则**: SPS = sole lifecycle owner, BFF = pure proxy + orchestrator, orchestrator 不绕过 Owner 直接杀进程

## 总体目标

建立 Realtime Business Orchestrator，统一编排盘前竞价、JYHF token/CDP、JYHF market、W2S readiness、K线支撑告警 readiness 的依赖、时段、状态、重试和降级。

## 架构

```
Frontend
  ↓
BFF RealtimeBusinessOrchestrator
  ↓
各 Owner:
  - SPS RealtimeStackManager (realtime pipeline)
  - JyhfCdpManager (CDP service/app)
  - JyhfAuctionManager (auction subprocess)
  - SPS jyhf-market collector (market data)
  - SPS W2S/Kline readiness endpoints
```

## 分阶段实施

| 阶段 | 内容 | 风险 |
|------|------|:--:|
| P4-2A | 只读 Orchestrator Status + dry_run tick | 低 — 不执行动作 |
| P4-2B | 前端 OrchestratorStatusPanel 组件 | 低 — 只读展示 |
| P4-2C | enable/disable + 自动 tick loop | 中 — 首次自动动作 |
| P4-2D | 替换 main.py 旧的 `_auto_start_jyhf_collectors()` | 中 — 删除旧逻辑 |
| P4-2E | W2S / 支撑告警 readiness API 增强 | 低 — 补充端点 |

## P4-2A：只读 Orchestrator Status + dry_run tick（当前阶段）

### 已完成

- [x] `web_app_service/services/realtime_business_orchestrator.py` (~580 行)
  - 5 service nodes: cdp_token, jyhf_market, jyhf_auction, w2s_alert, support_alert
  - 依赖图: cdp_token → jyhf_market → jyhf_auction → w2s_alert, jyhf_market → support_alert
  - 交易时段划分: 8 phases from preopen_prepare to closed
  - dry_run tick: 诊断所有服务，输出 planned_actions 和 blockers
  - P4-2A 安全锁: dry_run 强制为 True
- [x] `web_app_service/api/routes.py` — GET `/api/v2/realtime/orchestrator/status`, POST `/api/v2/realtime/orchestrator/tick`
- [x] `web_app_service/main.py` — `app.state.realtime_business_orchestrator` 注册，旧 `_auto_start_jyhf_collectors` 保留
- [x] `scripts/check_realtime_orchestrator_readonly.sh` — 自动化测试脚本

### 待验证

- [ ] BFF 重启后 API 可用
- [ ] `dry_run_forced` 生效 — `dry_run=false` 请求仍返回 `dry_run: true`
- [ ] token 不可用时 cdp_token.blockers 完整
- [ ] 9:10-9:24 且 token ready 时 planned_actions 输出 `would_start` market + auction
- [ ] 不启动任何新进程

### API

```
GET  /api/v2/realtime/orchestrator/status
POST /api/v2/realtime/orchestrator/tick  {"dry_run": true}
```

### 验收命令

```bash
bash scripts/check_realtime_orchestrator_readonly.sh
```

## P4-2B 预览：前端展示

- 新增 `OrchestratorStatusPanel.tsx` 组件
- 显示 5 个服务 readiness 卡片 + planned_actions + blockers
- 第一版只读，不放 enable 按钮

## P4-2C 预览：自动 tick loop

- `POST /api/v2/realtime/orchestrator/enable|disable`
- `REALTIME_BUSINESS_ORCHESTRATOR_ENABLED` 默认 `false`
- 自动 loop: `while enabled: tick(dry_run=False); sleep(15)`
- 安全机制: once_per_window 幂等, retry_backoff, audit_log

## P4-2D 预览：替换 legacy auto start

- 删除 `main.py` 中 `_auto_start_jyhf_collectors()`
- Orchestrator 接管 9:10 盘前启动流程

## P4-2E 预览：W2S / 支撑告警 readiness

- 新增 SPS `GET /api/v1/w2s-alerts/readiness`, `/api/v1/kline-alerts/readiness`
- Orchestrator 能从 readiness API 判断业务就绪状态

## 不可破坏的 P4 基线

1. SPS = realtime pipeline 唯一生命周期 Owner
2. BFF 不 direct pidfile kill
3. BFF 不自行维护 realtime pipeline task
4. Frontend 不用 Redis stream length 判断 running
5. SPS status 每次 live PID verified
6. start_new_chain_stack.sh 默认不自动启动 realtime

## 文件变更总览

| 阶段 | 文件 | 类型 |
|------|------|------|
| P4-2A | `web_app_service/services/realtime_business_orchestrator.py` | 新建 |
| P4-2A | `web_app_service/api/routes.py` | 修改 +50 行 |
| P4-2A | `web_app_service/main.py` | 修改 +3 行 |
| P4-2A | `scripts/check_realtime_orchestrator_readonly.sh` | 新建 |
| P4-2B | `frontend/src/routes/collection/components/OrchestratorStatusPanel.tsx` | 新建 |
| P4-2B | `frontend/src/lib/api.ts` | 修改 +30 行 |
| P4-2C | `web_app_service/services/realtime_business_orchestrator.py` | 修改 +200 行 |
| P4-2D | `web_app_service/main.py` | 修改 -50 行 |
