import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchRealtimeCollectorLogs,
  fetchRealtimeCollectorStatus,
  startRealtimeCollector,
  stopRealtimeCollector,
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
  const [busy, setBusy] = useState(false);
  const [statusResult, setStatusResult] = useState<RealtimeCollectorCommandResult | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [output, setOutput] = useState<string[]>([]);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const initializedRef = useRef(false);
  const logDigestRef = useRef<string>("");

  function append(line: string) {
    setOutput((prev) => [...prev, `[${nowText()}] ${line}`].slice(-500));
  }

  async function refreshStatus() {
    const result = await fetchRealtimeCollectorStatus();
    setStatusResult(result);
    const text = `${result.stdout}\n${result.stderr}`;
    if (text.includes("[up]   stream services") && text.includes("[up]   frontend_bff:8003")) {
      setRunning("up");
    } else {
      setRunning("down");
    }
    return result;
  }

  async function refreshLogs() {
    const result = await fetchRealtimeCollectorLogs(120);
    const preferredOrder = ["start_services.log", "frontend_bff_8003.log"];
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

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    append("实时事件采集控制台已加载");

    refreshStatus()
      .then(async (result) => {
        const text = `${result.stdout}\n${result.stderr}`;
        if (text.includes("[up]   stream services")) {
          await refreshLogs();
        }
      })
      .catch(() => {
        setRunning("down");
      });
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshStatus().catch(() => undefined);
      if (running === "up") {
        refreshLogs().catch(() => undefined);
      }
    }, 8000);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    const panel = terminalRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [logs, output]);

  async function handleStart() {
    setBusy(true);
    if (running === "up") {
      append("实时采集链路已在运行，跳过重复启动");
      setBusy(false);
      return;
    }
    append("开始启动实时事件采集链路...");
    try {
      // 通过BFF接口触发启动时，不能restart BFF本身，否则会自杀式重启导致请求中断。
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
          append("启动超时后状态刷新失败，请确认BFF服务(8003)是否在线。");
        }
      } else {
        append(message.startsWith("启动失败:") ? message : `启动失败: ${message}`);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
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
      setBusy(false);
    }
  }

  async function handleRefresh() {
    setBusy(true);
    try {
      await refreshStatus();
      await refreshLogs();
      append("已刷新状态与日志");
    } catch (err) {
      const message = err instanceof Error ? err.message : "刷新失败";
      append(`刷新失败: ${message}`);
    } finally {
      setBusy(false);
    }
  }

  const mergedLogs = useMemo(() => [...output, ...logs], [output, logs]);

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
          <span className="metric-label section-title">控制面板</span>
          <div className="collection-debug-status">
            <div>
              <span className="metric-label">实时链路</span>
              <strong>{running === "up" ? "运行中" : running === "down" ? "未运行" : "检查中"}</strong>
            </div>
            <div>
              <span className="metric-label">执行状态</span>
              <strong>{busy ? "执行中" : "空闲"}</strong>
            </div>
            <div>
              <span className="metric-label">来源</span>
              <strong>status_realtime_stack.sh</strong>
            </div>
          </div>
          <div className="collection-action-row">
            <button type="button" className={`tag tag-button ${running === "down" ? "tag-active" : ""}`} onClick={handleStart} disabled={busy}>
              {busy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  处理中...
                </span>
              ) : (
                "启动实时采集"
              )}
            </button>
            <button type="button" className={`tag tag-button ${running === "up" ? "tag-active" : ""}`} onClick={handleStop} disabled={busy}>
              {busy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  处理中...
                </span>
              ) : (
                "停止实时采集"
              )}
            </button>
            <button type="button" className="tag tag-button" onClick={handleRefresh} disabled={busy}>
              {busy ? (
                <span className="screener-run-inline">
                  <span className="screener-spinner" />
                  处理中...
                </span>
              ) : (
                "刷新状态"
              )}
            </button>
            <span className="collection-status-indicator">
              {busy
                ? "⏳ 正在执行，请稍候..."
                : running === "up"
                  ? "🟢 采集运行中"
                  : running === "down"
                    ? "🔴 采集已停止"
                    : "⚪ 状态检查中"}
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
