# JYHF CDP 服务生命周期管理 — 架构约束文档

> 版本: 1.0  
> 日期: 2026-05-15  
> 状态: Frozen

## 核心原则（不可破坏）

1. **JyhfCdpManager 是 JYHF CDP 服务生命周期的唯一管理者**  
   文件: `web_app_service/services/jyhf_cdp_manager.py`  
   一切启停必须通过 BFF API，不允许其他模块直接操作 8095 进程。

2. **Shell 脚本仅用于外部调试，不被 manager 调用**  
   文件: `scripts/start_jyhf_cdp_service.sh`  
   `JyhfCdpManager._launch_process()` 使用 `subprocess.Popen` 直接启动，不通过 shell 脚本。

3. **Electron 不直接启动、不直接 kill 8095**  
   文件: `desktop/src/runtime/serviceManager.ts`  
   `ENABLE_CDP` 分支已禁用。App 退出时通过 `POST /api/v2/realtime/jyhf-cdp/service/stop` 委托 web_app 停止。

4. **managed 才允许 killpg**  
   `_stop_managed_process()` 使用 `os.killpg(os.getpgid(pid), SIGTERM/SIGKILL)`。  
   仅当 `self._owner == "managed"` 且 `self._process` 非空时执行。

5. **external 永不误杀**  
   `stop_collector()` 和 `stop_service()` 对 external 仅停止 collector，不动进程。  
   `force_stop_service()` 是唯一可以杀 external 的入口，且明确标记为诊断接口。

6. **force-stop 只用于诊断清理旧残留**  
   端点: `POST /realtime/jyhf-cdp/service/force-stop`  
   不接普通停止按钮，前端不应暴露此接口给常规用户。

7. **start API 必须确认 collector_running=true 才返回成功**  
   `_start_collector_locked()` 轮询 `/status` 等待 `collector_running` 确认。  
   15 次轮询（约 7.5 秒）后未确认则返回 `ok=False` 并回收 managed 进程。

8. **get_status 检测到 alive + owner=none 时自动标记 external**  
   避免状态面板显示 "运行中（none）"。

## 所有权模型

```
owner=none      — 8095 端口无进程
owner=managed   — 本 JyhfCdpManager 实例通过 Popen 启动
owner=external  — 8095 已运行但非本实例启动（旧残留、手动调试等）
```

## 启停行为矩阵

| 操作 | managed | external | none |
|------|---------|----------|------|
| start_collector | 启动 collector | 启动 collector | 先 launch 进程，再启动 collector |
| stop_collector | 停 collector + killpg 进程 | 只停 collector | 无操作 |
| stop_service | killpg 进程 | 不杀，返回 "not managed" | 无操作 |
| force_stop_service | killpg 进程 | lsof+SIGKILL 进程 | 无操作 |

## API 返回结构（统一 _cmd_result）

```json
{
  "ok": true,
  "message": "...",
  "service_running": true,
  "service_owner": "managed",
  "service_pid": 12345,
  "service_port": 8095,
  "collector_running": true,
  "last_error": null
}
```

## 相关端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v2/realtime/jyhf-cdp/status` | 状态（含 owner） |
| POST | `/api/v2/realtime/jyhf-cdp/start` | 启动 collector |
| POST | `/api/v2/realtime/jyhf-cdp/stop` | 停止 collector（managed 则杀进程） |
| POST | `/api/v2/realtime/jyhf-cdp/service/stop` | 停止 managed 进程（Electron quit 调用） |
| POST | `/api/v2/realtime/jyhf-cdp/service/force-stop` | 诊断：强杀 8095（不限 owner） |
| GET | `/api/v2/realtime/jyhf-cdp/logs` | 日志 |

## 前端展示约定

状态面板需显示 `service_owner`：

- `managed` → "运行中（web_app管理）"
- `external` → "运行中（外部启动）"
- `none` → "未启动"

## 变更历史

| 日期 | 变更 |
|------|------|
| 2026-05-15 | 初始版本：Popen 直接启动、managed/external 模型、force-stop 诊断接口 |
