# CDP 采集服务问题排查报告

> 日期：2026-05-15  
> 状态：待修复

---

## 1. 问题现象

| # | 现象 | 严重程度 |
|---|------|---------|
| 1 | 点击"启动JYHF DOM采集"按钮后，动画闪一下即消失，采集器仍显示"未运行" | 致命 |
| 2 | 重启App后，CDP采集服务自动在运行（上一轮残留） | 致命 |
| 3 | 启动成功后，CDP服务运行几分钟即自动退出（Shutting down），需重新点击启动 | 高 |
| 4 | 点击停止按钮后无法停止采集 | 高 |
| 5 | 关闭App窗口导致web_app_service退出，前端API全挂 | 高 |

---

## 2. 架构与链路

```
Electron App
  ├── 启动: spawnCommand → web_app_service (:8000) + SPS (:8090)
  ├── 退出: stopAll() → kill web_app + SPS
  └── CDP: 不管理（由BFF manager按需启停）

web_app_service (:8000)
  ├── 托管 frontend/dist （SPA静态文件）
  └── BFF: /api/v2/realtime/jyhf-cdp/start|stop|status|logs
        └── JyhfCdpManager
              ├── _run_start_script() → bash start_jyhf_cdp_service.sh
              ├── _stop_service() → kill PID
              └── 代理 CDP service (:8095)

CDP service (:8095, uvicorn)
  ├── /collector/start → 启动采集循环
  ├── /collector/stop  → 停止采集循环
  └── 采集循环:
        JYHF App (:9223 CDP) → DOM读取 → 事件提取
        → IntelPusher → Redis stream:event:feed
        → SPS消费 → /api/v2/intel/feed → 前端情报台

JYHF App (久赢恒丰 Electron, :9223 CDP)
  └── 需以 --remote-debugging-port=9223 启动
```

---

## 3. 各问题根因分析

### 问题1: 启动按钮无响应（前端层面）

**调用链**:
```
按钮点击 → handleStartJyhfCdp()
  → setJyhfBusy(true)    // 按钮显示spinner + disabled
  → POST /api/v2/realtime/jyhf-cdp/start (30s超时)
  → refreshJyhfCdpStatus() → GET /api/v2/realtime/jyhf-cdp/status (10s超时)
  → setJyhfStatus(result) → 更新UI
  → setJyhfBusy(false)   // 恢复按钮
```

**可能原因**:
- A. `refreshJyhfCdpStatus()` 抛异常，catch块吞掉错误，UI未更新
- B. Electron内嵌浏览器缓存了旧版index.html，加载了不存在的旧JS文件(404)
- C. 前端构建后的代码懒加载chunk未被正确加载

**后端实际情况**: API返回200 OK，CDP服务正常启动（curl验证通过）

---

### 问题2: CDP服务残留运行

**原因**: 
1. CDP服务由BFF manager按需启动（非Electron spawnCommand管理）
2. Electron的stopAll()不感知CDP进程
3. 修改后的start脚本使用`nohup`使CDP脱离父进程，即使App退出也不死

**已尝试修复**: 
- serviceManager.ts增加`_stopCdpService()`在stopAll()时杀8095端口
- 但PID文件可能丢失导致查找失败
- 第一次修复后`_cdProjectRoot`可能未设置

---

### 问题3: CDP服务运行几分钟后自动退出

**日志证据**:
```
INFO:     Shutting down
INFO:     Application shutdown complete
INFO:     Finished server process [PID]
```

**可能原因**:
- A. 原start脚本使用`exec`，uvicorn生命周期绑定到BFF manager的asyncio subprocess对象。Python GC回收Process对象时触发transport.close()，可能间接导致子进程退出
- B. 多实例竞争：两个start请求同时触发，第二个实例覆盖PID文件
- C. 资源限制或系统级信号

**已尝试修复**: start脚本改用`nohup` + `&`替代`exec`

**副作用**: nohup导致问题2（服务残留）

---

### 问题4: 停止按钮无效

**原因**:
- BFF manager的`_managed`标记仅在进程内有效，App重启后丢失
- 原`stop_service()`检查`_managed`为False时直接return，拒绝停止
- 用户看到"未运行"状态点停止，实际CDP进程仍在运行

**已尝试修复**: 移除`_managed`检查，增加`_findPidByPort()`端口查找回退

---

### 问题5: 关闭窗口导致web_app退出

**原因**:
- main.ts中`window-all-closed`直接调`quitSafely()` → `stopAll()` → kill web_app
- 这是原始设计："关窗口=退出App"

**已尝试修复（已回退）**:
- 改为隐藏窗口不退出，但导致Cmd+Q也无法退出
- 已回退恢复原始行为

---

## 4. 当前代码修改状态

### 已修改的文件（未验证生效）

| 文件 | 改动 | 风险 |
|------|------|------|
| `scripts/start_jyhf_cdp_service.sh` | exec→nohup | 导致CDP残留 |
| `desktop/src/runtime/serviceManager.ts` | 新增`_stopCdpService()`、`_findPidByPort()`、`_httpPost()` | 端口强杀逻辑 |
| `services/jyhf_cdp_service/app_manager.py` | 启动超时6s→15s、重试1次 | - |
| `services/jyhf_cdp_service/extractors.py` | 新增`PrepareRetryError` | - |
| `services/jyhf_cdp_service/service.py` | capture retry + intel counter | - |
| `web_app_service/services/jyhf_cdp_manager.py` | 停止不再检查_managed、增加端口回退 | - |
| `frontend/src/routes/collection/RealtimeCollectorPage.tsx` | 按钮spinner动画、状态文字、防连点 | 构建后可能缓存未生效 |
| `frontend/src/routes/collection/RealtimeCollectorPage.tsx` | 状态栏文字修改 | - |
| `desktop/src/main.ts` | window-all-closed（已回退） | 已恢复原始行为 |
| `desktop/src/windowManager.ts` | close事件拦截（已回退） | 已恢复原始行为 |

### 后端API验证结果（curl直接调用）

| API | 结果 |
|-----|------|
| POST /api/v2/realtime/jyhf-cdp/start | ✅ 200 OK, CDP启动成功 |
| GET /api/v2/realtime/jyhf-cdp/status | ✅ collector_running=true |
| CDP service :8095/status | ✅ running, collector active |
| Redis stream:event:feed | ✅ 10006条数据 |
| GET /api/v2/intel/feed | ✅ 有CDP事件数据 |

---

## 5. 未解决的核心矛盾

**后端完全正常，前端不工作**。所有API通过curl调用均正常返回、CDP服务正常启停。但用户在Electron窗口内操作按钮无反应。

最可能的解释：**Electron浏览器缓存了旧版前端构建产物**。

- Vite构建使用hash命名（如`chunk-collection-vxXxF6iP.js`），每次构建hash变化
- Electron窗口的Chromium缓存了旧`index.html`（引用旧hash的JS文件）
- 旧JS文件已被新构建清理，HTTP 404
- React组件未加载/未hydrate → 按钮只是裸HTML，所有交互失效

**验证方法**: 在Electron窗口内按Cmd+Shift+R强制刷新，或在DevTools中查看Console错误和Network加载失败。

---

## 6. 建议修复顺序

1. **立即**: 确认前端加载问题（缓存或构建问题）
2. **然后**: 统一定义CDP服务生命周期（谁启动、谁停止、何时清理）
3. **最后**: 前端按钮状态机完善（loading/success/error三态）
