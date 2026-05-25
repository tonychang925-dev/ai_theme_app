# TDX Market Agent

macOS 本地通达信行情采集边车。隔离 mootdx 依赖，通过 HTTP API 提供 quote / minute / bars。

## 环境隔离

mootdx 会降级 httpx，**禁止安装到主项目 Python 环境**。本 Agent 使用独立 venv。

## 安装

```bash
cd tools/tdx_market_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8766
```

或直接：

```bash
source .venv/bin/activate
python app.py
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/quote/{stock_id}` | 实时行情（5档盘口） |
| GET | `/minute/{stock_id}` | 分时数据 |
| GET | `/bars/{stock_id}?frequency=9&offset=100` | K线数据 |

stock_id 支持格式：`002361` / `002361.SZ` / `600000.SH`

## 验收

```bash
curl http://127.0.0.1:8766/health
curl http://127.0.0.1:8766/quote/002361
curl http://127.0.0.1:8766/minute/002361
curl http://127.0.0.1:8766/bars/002361
curl http://127.0.0.1:8766/quote/600000.SH
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TDX_AGENT_HOST` | `127.0.0.1` | 监听地址 |
| `TDX_AGENT_PORT` | `8766` | 监听端口 |
| `TDX_AGENT_TIMEOUT` | `15.0` | mootdx 超时秒数 |
| `TDX_AGENT_LOG_LEVEL` | `info` | 日志级别 |

## 架构约束

- 不 import stock_processing_service
- 不依赖 Windows VM
- 不依赖通达信 L2 登录态
- 只返回 mootdx 标准行情（5档盘口 + 分时 + K线）
