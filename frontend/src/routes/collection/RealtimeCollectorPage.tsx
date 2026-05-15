import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchJyhfCdpCollectorLogs,
  fetchJyhfCdpCollectorStatus,
  fetchRealtimeCollectorLogs,
  fetchRealtimeCollectorStatus,
  startJyhfCdpCollector,
  startRealtimeCollector,
  stopJyhfCdpCollector,
  stopRealtimeCollector,
  type JyhfCdpCollectorStatus,
  type RealtimeCollectorCommandResult,
} from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

function nowText() {
  return new Date().toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function RealtimeCollectorPage() {
  const [running, setRunning] = useState<"unknown" | "up" | "down">("unknown");
  const [mainBusy, setMainBusy] = useState(false);
  const [jyhfBusy, setJyhfBusy] = useState(false);
  const [statusResult, setStatusResult] = useState<RealtimeCollectorCommandResult | null>(null);
  const [jyhfStatus, setJyhfStatus] = useState<JyhfCdpCollectorStatus | null>(null);
  const [jyhfError, setJyhfError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [jyhfLogs, setJyhfLogs] = useState<string[]>([]);
  const [output, setOutput] = useState<string[]>([]);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const initializedRef = useRef(false);
  const logDigestRef = useRef<string>("");
  const statusErrorNotifiedRef = useRef(false);

  function append(line: string) {
    setOutput((prev) => [...prev, `[${nowText()}] ${line}`].slice(-500));
  }

  async function refreshStatus() {
    const result = await fetchRealtimeCollectorStatus();
    setStatusResult(result);
    const text = `${result.stdout}\n${result.stderr}`;
    // NOTE: the status script only checks whether services are alive.
    // "up" here means backend services are reachable, NOT that collection is active.
    const servicesUp = text.includes("[up]   web_app_service") && text.includes("[up]   stock_processing_service");
    if (result.return_code === 0 && servicesUp && text.includes("[down]")) {
      // Mixed state: some services up, some down
      setRunning("down");
    } else if (servicesUp) {
      setRunning("up");
    } else {
      setRunning("down");
    }
    return result;
  }

  async function refreshLogs() {
    const result = await fetchRealtimeCollectorLogs(120);
    const preferredOrder = ["stock_processing_service_8090.log", "web_app_service_8000.log", "frontend_5173.log"];
    const merged = preferredOrder.flatMap((name) => {
      const lines = result.files[name] ?? [];
      if (!lines.length) return [];
      return [`===== ${name} =====`, ...lines, ""];
    });
    const nextLogs = merged.slice(-1500);
    const digest = nextLogs.join("\n");
    if (digest !== logDigestRef.current) {
      logDigestRef.current = digest;
      setLogs(nextLogs);
    }
  }

  async function refreshJyhfCdpStatus() {
    const result = await fetchJyhfCdpCollectorStatus();
    setJyhfStatus(result);
    setJyhfError(null);
    return result;
  }

  async function refreshJyhfCdpLogs() {
    const result = await fetchJyhfCdpCollectorLogs(200);
    setJyhfLogs((result.lines ?? []).slice(-500));
  }

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    append("实时事件采集控制台已加载");

    refreshStatus()
      .then(async (result) => {
        const text = `${result.stdout}\n${result.stderr}`;
        if (text.includes("[up]   web_app_service:8000") || text.includes("[up]   stock_processing_service:8090")) {
          await refreshLogs();
        }
      })
      .catch(() => {
        setRunning("down");
      });
    refreshJyhfCdpStatus().catch((err) => {
      setJyhfError(err instanceof Error ? err.message : "JYHF-CDP 服务未连接");
    });
    refreshJyhfCdpLogs().catch(() => undefined);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshStatus().catch((err) => {
        setRunning("down");
        if (!statusErrorNotifiedRef.current) {
          const msg = err instanceof Error ? err.message : "状态检查失败";
          append(`状态轮询失败，已判定为未运行：${msg}`);
          statusErrorNotifiedRef.current = true;
        }
      });
      refreshLogs().catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(timer);
  }, []);

  // JYHF CDP 独立轮询，不依赖主采集器状态
  useEffect(() => {
    refreshJyhfCdpStatus().catch(() => {});
    refreshJyhfCdpLogs().catch(() => {});
    const timer = window.setInterval(() => {
      refreshJyhfCdpStatus().catch((err) => {
        setJyhfError(err instanceof Error ? err.message : "JYHF-CDP 服务未连接");
      });
      refreshJyhfCdpLogs().catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (running === "up") {
      statusErrorNotifiedRef.current = false;
    }
  }, [running]);

  useEffect(() => {
    const panel = terminalRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [logs, jyhfLogs, output]);

  async function handleStart() {
    setMainBusy(true);
    if (running === "up") {
      append("实时采集链路已在运行，跳过重复启动");
      setMainBusy(false);
      return;
    }
    append("开始启动实时事件采集链路...");
    try {
      // 通过 web_app_service 触发启动时，不能重启 web_app_service 本身，否则会中断当前请求。
      const result = await startRealtimeCollector({ restart: false, with_frontend: false });
      append(`启动完成: rc=${result.return_code}`);
      await refreshStatus();
      await refreshLogs();
    } catch (err) {
      const message = err instanceof Error ? err.message : "启动失败";
      if (message.includes("request timeout")) {
        append("启动请求超时（45s），正在刷新状态确认是否已在后台启动...");
        try {
          await refreshStatus();
          await refreshLogs();
          append("已完成状态刷新。若仍未运行，请再次点击“启动实时采集”。");
        } catch {
          append("启动超时后状态刷新失败，请确认 web_app_service(8000) 与 stock_processing_service(8090) 是否在线。");
        }
      } else {
        append(message.startsWith("启动失败:") ? message : `启动失败: ${message}`);
      }
    } finally {
      setMainBusy(false);
    }
  }

  async function handleStop() {
    setMainBusy(true);
    append("开始停止实时事件采集链路...");
    try {
      const result = await stopRealtimeCollector({ force: false, with_frontend: false });
      append(`停止完成: rc=${result.return_code}`);
      await refreshStatus();
      await refreshLogs();
    } catch (err) {
      const message = err instanceof Error ? err.message : "停止失败";
      append(message.startsWith("停止失败:") ? message : `停止失败: ${message}`);
    } finally {
      setMainBusy(false);
    }
  }

  async function handleRefresh() {
    setMainBusy(true);
    try {
      await refreshStatus();
      await refreshLogs();
      append("已刷新状态与日志");
    } catch (err) {
      const message = err instanceof Error ? err.message : "刷新失败";
      append(`刷新失败: ${message}`);
    } finally {
      setMainBusy(false);
    }
  }

  async function handleStartJyhfCdp() {
    setJyhfBusy(true);
    setJyhfStatus(prev => ({ ...(prev ?? {} as JyhfCdpCollectorStatus), collector_running: false }));
    append("启动 JYHF DOM 采集器...");
    try {
      const result = await startJyhfCdpCollector();
      if (!result.ok) {
        append(`启动失败: ${result.message}`);
        setJyhfBusy(false);
        return;
      }
      append(`CDP 服务已启动 (owner=${result.service_owner})，等待 collector 就绪...`);
      // Poll until status confirms the target state
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try {
          const st = await fetchJyhfCdpCollectorStatus();
          setJyhfStatus(st);
          if (st.collector_running) {
            append(`采集器就绪 (capture_count=${st.capture_count_total})`);
            break;
          }
          if (i % 5 === 0) append(`等待中... (${i + 1}s)`);
        } catch { /* retry */ }
      }
      await refreshJyhfCdpLogs();
      setJyhfBusy(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "启动失败";
      append(message.startsWith("JYHF-CDP 启动失败:") ? message : `JYHF-CDP 启动失败: ${message}`);
      setJyhfBusy(false);
    }
  }

  async function handleStopJyhfCdp() {
    setJyhfBusy(true);
    setJyhfStatus(prev => ({ ...(prev ?? {} as JyhfCdpCollectorStatus), collector_running: true }));
    append("停止 JYHF DOM 采集器...");
    try {
      const result = await stopJyhfCdpCollector();
      append(result.message);
      // Poll until status confirms stopped
      for (let i = 0; i < 15; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try {
          const st = await fetchJyhfCdpCollectorStatus();
          setJyhfStatus(st);
          if (!st.collector_running) {
            append("采集器已停止");
            break;
          }
        } catch { /* retry */ }
      }
      await refreshJyhfCdpLogs();
      setJyhfBusy(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "停止失败";
      append(message.startsWith("JYHF-CDP 停止失败:") ? message : `JYHF-CDP 停止失败: ${message}`);
      setJyhfBusy(false);
    }
  }

  async function handleRefreshJyhfCdp() {
    setJyhfBusy(true);
    try {
      await refreshJyhfCdpStatus();
      await refreshJyhfCdpLogs();
      append("已刷新 JYHF-CDP 状态与日志");
    } catch (err) {
      const message = err instanceof Error ? err.message : "刷新失败";
      append(`JYHF-CDP 刷新失败: ${message}`);
    } finally {
      setJyhfBusy(false);
    }
  }

  const jyhfCollectorRunning = Boolean(jyhfStatus?.collector_running);

  const mergedLogs = useMemo(() => {
    const parts: string[] = [];
    // Section 1: 实时链路日志 (main collector)
    if (logs.length) {
      parts.push("── 实时链路日志 (AKShare) ──", ...logs, "");
    }
    // Section 2: JYHF CDP logs — label by state
    if (jyhfLogs.length) {
      if (jyhfCollectorRunning || jyhfStatus?.service_running) {
        parts.push("── JYHF DOM 采集日志 (运行中) ──", ...jyhfLogs, "");
      } else {
        parts.push("── JYHF DOM 采集日志 (已停止，以下为历史记录) ──", ...jyhfLogs, "");
      }
    }
    return [...output, ...parts];
  }, [output, jyhfLogs, logs, jyhfCollectorRunning, jyhfStatus?.service_running]);

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/")}>
          返回情报台
        </button>
        <div>
          <p className="eyebrow">Realtime Event Collection</p>
          <h1>实时事件采集控制台</h1>
          <p className="subtle">用于启动/停止实时采集链路（AKShare新闻→结构化→匹配→情报SSE）。</p>
        </div>
      </header>

      <main className="collection-debug-grid">
        <section className="workspace-card collection-debug-control">
          <span className="metric-label section-title">控制面板 · 后端服务状态</span>
          <p className="subtle" style={{marginTop:4,marginBottom:12}}>仅检测 web_app / SPS 是否在线，不代表采集正在运行</p>
          <div className="collection-debug-status">
            <div>
              <span className="metric-label">后端服务</span>
              <strong>{running === "up" ? "在线" : running === "down" ? "离线" : "检查中"}</strong>
            </div>
            <div>
              <span className="metric-label">执行状态</span>
              <strong>{mainBusy ? "执行中" : "空闲"}</strong>
            </div>
            <div>
              <span className="metric-label">来源</span>
              <strong>status_realtime_stack.sh</strong>
            </div>
          </div>
          <div className="collection-action-row">
            <button type="button" className={`tag tag-button ${running === "down" ? "tag-active" : ""}`} onClick={handleStart} disabled={mainBusy}>
              {mainBusy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  处理中...
                </span>
              ) : (
                "启动实时采集"
              )}
            </button>
            <button type="button" className={`tag tag-button ${running === "up" ? "tag-active" : ""}`} onClick={handleStop} disabled={mainBusy}>
              {mainBusy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  处理中...
                </span>
              ) : (
                "停止实时采集"
              )}
            </button>
            <button type="button" className="tag tag-button" onClick={handleRefresh} disabled={mainBusy}>
              {mainBusy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  处理中...
                </span>
              ) : (
                "刷新状态"
              )}
            </button>
            <span className="collection-status-indicator">
              {mainBusy
                ? "⏳ 正在执行，请稍候..."
                : running === "up"
                  ? "🟢 后端服务在线（不代表采集运行中）"
                  : running === "down"
                    ? "🔴 后端服务离线"
                    : "⚪ 状态检查中"}
            </span>
          </div>
        </section>

        <section className="workspace-card collection-debug-control">
          <span className="metric-label section-title">JYHF DOM 采集源</span>
          <div className="collection-debug-status">
            <div>
              <span className="metric-label">采集器</span>
              <strong>{jyhfCollectorRunning ? "运行中" : "未运行"}</strong>
            </div>
            <div>
              <span className="metric-label">JYHF App</span>
              <strong>{jyhfStatus?.app_running ? "已启动" : "未确认"}</strong>
            </div>
            <div>
              <span className="metric-label">CDP 服务</span>
              <strong>
                {jyhfStatus?.service_running
                  ? `运行中（${jyhfStatus?.service_owner === "managed" ? "web_app管理" : jyhfStatus?.service_owner === "external" ? "外部启动" : jyhfStatus?.service_owner ?? "未知"}）`
                  : "未启动"}
              </strong>
            </div>
            <div>
              <span className="metric-label">CDP 连接</span>
              <strong>{jyhfStatus?.cdp_connected ? `已连接:${jyhfStatus.cdp_port}` : `未连接:${jyhfStatus?.cdp_port ?? 9223}`}</strong>
            </div>
            <div>
              <span className="metric-label">当前页面</span>
              <strong>{jyhfStatus?.current_tab || jyhfStatus?.current_route || "--"}</strong>
            </div>
            <div>
              <span className="metric-label">最近采集</span>
              <strong>{jyhfStatus?.last_capture_at || "--"}</strong>
            </div>
            <div>
              <span className="metric-label">最近事件</span>
              <strong>{jyhfStatus?.last_event_at || "--"}</strong>
            </div>
          </div>
          <div className="collection-debug-status">
            <div>
              <span className="metric-label">累计采集</span>
              <strong>{jyhfStatus?.capture_count_total ?? 0}</strong>
            </div>
            <div>
              <span className="metric-label">新增/重复</span>
              <strong>{jyhfStatus ? `${jyhfStatus.new_event_count_total}/${jyhfStatus.duplicate_count_total}` : "0/0"}</strong>
            </div>
            <div>
              <span className="metric-label">解析失败</span>
              <strong>{jyhfStatus?.parse_error_count_total ?? 0}</strong>
            </div>
          </div>
          <div className="collection-action-row">
            <button
              type="button"
              className={`tag tag-button ${jyhfBusy && !jyhfCollectorRunning ? "tag-active" : ""}`}
              onClick={handleStartJyhfCdp}
              disabled={jyhfBusy || jyhfCollectorRunning}
            >
              {jyhfBusy && !jyhfCollectorRunning ? (
                <span className="screener-run-inline"><span className="screener-spinner" />启动中，等待 collector 就绪...</span>
              ) : jyhfCollectorRunning ? (
                "采集运行中"
              ) : (
                "启动 JYHF DOM 采集"
              )}
            </button>
            <button
              type="button"
              className={`tag tag-button ${jyhfBusy && jyhfCollectorRunning ? "tag-active" : ""}`}
              onClick={handleStopJyhfCdp}
              disabled={jyhfBusy || !jyhfCollectorRunning}
            >
              {jyhfBusy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  停止中...
                </span>
              ) : (
                "停止 JYHF DOM 采集"
              )}
            </button>
            <button
              type="button"
              className="tag tag-button"
              onClick={handleRefreshJyhfCdp}
              disabled={jyhfBusy}
            >
              {jyhfBusy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  刷新中...
                </span>
              ) : (
                "刷新 JYHF 状态"
              )}
            </button>
            <span className="collection-status-indicator">
              {jyhfBusy
                ? "⏳ 等待状态确认中，请勿重复点击..."
                : jyhfError
                  ? `⚠ 服务未连接：${jyhfError}`
                  : jyhfStatus?.last_error
                    ? `⚠ ${jyhfStatus.last_error}`
                    : jyhfCollectorRunning && jyhfStatus?.last_capture_at
                      ? `采集运行中，捕获 ${jyhfStatus.capture_count_total} 条，数据写入 stream:event:feed`
                      : "就绪，点击启动开始采集 JYHF DOM 数据"}
            </span>
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">终端调试输出</span>
          <div className="collection-log-panel collection-debug-terminal" ref={terminalRef}>
            {(mergedLogs.length ? mergedLogs : ["[等待中] 尚未产生调试日志。"]).map((line, idx) => (
              <div className="collection-log-line" key={`realtime-terminal-${idx}`}>
                {line}
              </div>
            ))}
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">状态脚本原始输出</span>
          <pre className="collection-debug-json">
            {statusResult ? `${statusResult.stdout}\n${statusResult.stderr}` : "暂无输出"}
          </pre>
        </section>
      </main>
    </div>
  );
}
