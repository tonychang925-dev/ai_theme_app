# CDP 采集服务 — 问题清单与当前状态

> 日期：2026-05-15  
> 状态：部分已修复，部分待定

---

## 一、后端问题

### 1. extractors.py prepare() 盲目 sleep 10 秒

**根因**：`prepare()` 用 `time.sleep(5)` + `time.sleep(3)` + `time.sleep(2)` 等待 JYHF DOM 响应，不检测 DOM 是否真的就绪。

**影响**：每次 capture 周期额外浪费 10 秒。加上 jyhf app 启动 15 秒超时，用户点"启动"后等 25-30 秒才看到 collector_running。

**状态**：已修复，改为轮询 DOM（~3s），但运行中的 CDP 进程未重启，新代码未生效。

### 2. jyhf_cdp_manager.py _cmd_result 缺少 service_running 字段（已修复）

### 3. jyhf_cdp_manager.py get_status 不自动标记 external owner（已修复）

### 4. jyhf_cdp_manager.py start_collector 假阳性返回 collector_running=true（已修复）

### 5. serviceManager.ts ENABLE_CDP 自动启动分支（已删除）

### 6. serviceManager.ts stopAll 中 _stopCdpService 硬编码端口 8000

**根因**：`_httpPost('127.0.0.1', 8000, ...)` 始终用 8000 端口调 web_app API 停止 CDP。当 PortManager 分配了其他端口（如 8100），请求打到错误端口，CDP 无法被停止。

**影响**：App 退出后 CDP 进程残留运行，下次启动后 BFF 检测到 `external` owner，无法从 UI 停止。

**状态**：未修复。需要从 `startAll` 保存实际 webPort，传给 `stopAll`。

---

## 二、前端问题

### 1. CDP 状态轮询绑定在主采集器 running 变量上

**根因**：`useEffect(() => {...}, [running])` —— CDP 的 8 秒轮询依赖 `running` 状态变化才启动。`running` 由 `refreshStatus()` 控制，如果该 API 返回慢或 `running` 不变化，CDP 轮询永不起飞。

**影响**：页面加载后，CDP 状态停留在初始 `null` 值（"未运行"/"未连接"），直到 `running` 变化后才开始更新。

**状态**：代码已改为独立 `useEffect([])`，但当前 Electron 窗口加载的是旧构建。

### 2. 启动/停止按钮状态更新不即时

**根因**：`handleStartJyhfCdp` 调用 API 后仅设 `setJyhfBusy(false)`，不保证 `jyhfStatus` 已同步到后端真实状态。UI 更新依赖下一轮 8 秒轮询。

**影响**：用户点启动后看到 spinner 消失但状态仍显示"未运行"，需等 8 秒后轮询才更新。

**状态**：代码已改为 API 调用后轮询确认状态（每秒一次直到确认），但当前 Electron 窗口加载的是旧构建。

### 3. Electron 浏览器缓存导致前端代码不更新

**根因**：Electron BrowserWindow 的 Chromium 缓存了 index.html 和 JS 文件。每次改前端代码后 `npm run build` 产出新的 hash 文件，但旧 index.html 引用旧 hash 文件（已被清理），导致 JS 404，页面功能全挂。

**影响**：今天所有前端修改用户一次都没看到效果，因为 Electron 一直加载缓存的旧文件。

**已做措施**：
- web_app `_NoCacheStaticFiles` 加 no-cache 响应头
- Electron main.ts `clearCache()` + `clearStorageData()` + `clearAuthCache()`
- loadURL 加 `?_cb=` 时间戳

**状态**：三重措施已部署。重启 App 后生效。

---

## 三、架构遗留问题

### 1. 两个采集系统共用一个页面

"控制面板"（AKShare 实时采集）和 "JYHF DOM 采集源" 在同一页面，共享终端输出区。状态标签不够清楚，用户容易混淆哪个在运行。

### 2. 终端显示历史 shutdown 日志

终端合并展示日志文件，CDP 不运行时尾巴恰巧是旧的 shutdown 记录，用户以为服务在关闭。

---

## 四、当前代码状态

| 层级 | 文件 | 改动次数 | 风险 |
|------|------|---------|------|
| CDP 后端 | `services/jyhf_cdp_service/service.py` | 低 | 低 |
| CDP 后端 | `services/jyhf_cdp_service/extractors.py` | 中（sleep→轮询） | 低 |
| CDP 后端 | `services/jyhf_cdp_service/app_manager.py` | 低（超时 6→15） | 低 |
| BFF | `web_app_service/services/jyhf_cdp_manager.py` | 高（完全重写） | 已验证 |
| BFF | `web_app_service/api/routes.py` | 低（增 force-stop） | 已验证 |
| 前端 | `frontend/src/routes/collection/RealtimeCollectorPage.tsx` | 高 | 待构建 |
| 前端 | `frontend/src/lib/api.ts` | 低 | 待构建 |
| 前端缓存 | `web_app_service/main.py` | 中（_NoCacheStaticFiles） | 已验证 |
| Electron | `desktop/src/main.ts` | 中（清缓存+时间戳） | 待构建 |
| Electron | `desktop/src/runtime/serviceManager.ts` | 中 | 待构建 |
| Shell | `scripts/start_jyhf_cdp_service.sh` | 低（exec→nohup） | 不再被调用 |

## 五、验证通过的回归测试（7 项）

```
1. 冷启动无残留              PASS
2. 启动 managed              PASS
3. 停止 managed → 端口释放    PASS
4. 外部脚本启动 → external    PASS
5. external stop → 不杀进程   PASS
6. force-stop → 端口释放      PASS
7. 状态口径正确               PASS
```
