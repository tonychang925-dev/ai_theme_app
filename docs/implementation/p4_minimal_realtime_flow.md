# P4-0 最小实时业务闭环验收

版本日期：2026-05-29
基于：P0 止血 → P1 Runtime/Envelope/Decision → P2 引擎 Facade → P3 SourceAdapter

## 1. 目标

在新架构基础上打通最小实时业务闭环，不替换旧稳定链路。

```
旧链路（继续负责业务采集）          新架构（统一入口/契约/观测）
─────────────────────────────     ────────────────────────────
raw_news 采集新闻                  NewsSourceAdapter facade
JYHF CDP 采集 DOM                 JyhfDomAdapter facade
jyhf_auction 采集竞价              RealtimeMarketAdapter facade
KlineBreakDetector 支撑告警        SupportEngine facade
W2S scorer 弱转强告警             W2SEngine facade
                                  DecisionEngine 统一输出
                                  Runtime Lite 统一状态
                                  Envelope 统一契约
                                  Stream Alias 统一命名
```

## 2. 核心约束

**不改旧链路** — 所有采集、告警、scorer 继续由旧服务承载。

**新架构只做**：
- 统一健康检查与观测
- SourceAdapter / Engine / Decision facade
- Envelope 兼容包装
- Stream alias 命名兼容
- smoke check 验收脚本

## 3. 业务流程闭环

```
实时新闻采集 (raw_news_services)
    → stream:news:raw (stream:intel.raw.news)
    → Envelope 兼容

JYHF DOM 采集 (jyhf_cdp_service:8095)
    → stream:event:feed (stream:intel.raw.dom alias)
    → Intel Feed → 前端展示

盘前竞价 (jyhf_auction_collector)
    → jyhf_stock_quote_snapshot / pre_market_auction_snapshot
    → W2S 候选池

K线支撑告警 (KlineBreakDetector)
    → SupportEngine.accept_support_signal()
    → DecisionEngine.accept_support_signal()
    → SignalDecision → stream:kline:alerts → SSE

盘中 W2S 告警 (W2S scorer)
    → W2SEngine.accept_w2s_signal()
    → DecisionEngine.accept_w2s_signal()
    → SignalDecision → stream:w2s:alerts → SSE

统一决策输出
    → /api/v1/decision/latest
    → SSE → 前端 Intel 页面

复盘报告 → 继续走旧架构，暂不接入
```

## 4. 服务端口清单

| 服务 | 端口 | 角色 |
|------|------|------|
| web_app_service (BFF) | 8000 | SPA + API 聚合 + status-bundle |
| frontend_bff | 8003 | Intel 专用 BFF |
| SPS | 8090 | 数据处理 + SSE + decision/latest |
| jyhf_cdp_service | 8095 | JYHF DOM CDP 采集 |
| Redis | 6379 | Stream 消息总线 |
| PostgreSQL | 5432 | stock_data_test |

## 5. 验收检查项

| # | 检查项 | 方法 | 预期 |
|---|--------|------|------|
| 1 | Runtime Lite status | `python -m runtime.cli status` | 核心服务全绿 |
| 2 | Runtime Lite health | `python -m runtime.cli health` | 核心服务 OK |
| 3 | status-bundle | `GET /api/v2/realtime/status-bundle` | 200 |
| 4 | new_chain | status-bundle | running=true |
| 5 | jyhf_cdp | status-bundle | owner=managed |
| 6 | auction | status-bundle + ps | 无重复进程 |
| 7 | decision/latest | `GET /api/v1/decision/latest` | 含 support_alert/w2s_alert |
| 8 | Kline SSE | `GET /api/v1/kline-alerts/stream` | 可连接 |
| 9 | W2S SSE | `GET /api/v1/w2s-alerts/stream` | 可连接 |
| 10 | 孤儿进程 | `ps aux` 检查 | 无重复/僵尸进程 |

## 6. 验收命令

```bash
# 一键验收
python scripts/p4_smoke_check.py

# 单独检查
python -m runtime.cli status
python -m runtime.cli health
curl -s http://127.0.0.1:8000/api/v2/realtime/status-bundle | python -m json.tool
curl -s http://127.0.0.1:8090/api/v1/decision/latest?limit=5 | python -m json.tool
```

## 7. 暂不纳入

- 复盘报告（继续旧架构）
- Replay 接入生产链路
- SourceAdapter 接管采集生命周期
- 全量 Stream 迁移
- Runtime 自动重启
- 前端主展示改造
