import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchJyhfCdpCollectorLogs,
  fetchJyhfCdpCollectorStatus,
  startJyhfCdpCollector,
  stopJyhfCdpCollector,
  fetchNewChainRealtimeStatus,
  startNewChainRealtime,
  stopNewChainRealtime,
  fetchJyhfAuctionStatus,
  startJyhfAuctionCollector,
  stopJyhfAuctionCollector,
  openKlineAlertsStream,
  openW2SAlertsStream,
  type JyhfCdpCollectorStatus,
  type JyhfAuctionStatus,
  type KlineAlertEvent,
  type W2SAlertEvent,
  type NewChainRealtimeStatus,
} from "../../lib/api";
import { navigateTo } from "../../lib/navigation";
import realtimeIcon from "../../assets/intel-icons/实时采集.png";

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
  const [stackStatus, setStackStatus] = useState<NewChainRealtimeStatus | null>(null);
  const [jyhfStatus, setJyhfStatus] = useState<JyhfCdpCollectorStatus | null>(null);
  const [jyhfError, setJyhfError] = useState<string | null>(null);
  const [jyhfLogs, setJyhfLogs] = useState<string[]>([]);
  const [auctionEnabled, setAuctionEnabled] = useState(true);
  const [auctionStatus, setAuctionStatus] = useState<JyhfAuctionStatus | null>(null);
  const [auctionBusy, setAuctionBusy] = useState(false);
  const [klineAlerts, setKlineAlerts] = useState<KlineAlertEvent[]>([]);
  const [klineFilter, setKlineFilter] = useState<"all" | "critical" | "error" | "warning" | "info">("warning");
  const [klineAlertsEnabled, setKlineAlertsEnabled] = useState(true);
  const klineEsRef = useRef<EventSource | null>(null);
  const [w2sAlerts, setW2sAlerts] = useState<W2SAlertEvent[]>([]);
  const [w2sFilter, setW2sFilter] = useState<"all" | "important" | "observe">("important");
  const [w2sAlertsEnabled, setW2sAlertsEnabled] = useState(true);
  const w2sEsRef = useRef<EventSource | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const initializedRef = useRef(false);

  function append(line: string) {
    setOutput((prev) => [...prev, `[${nowText()}] ${line}`].slice(-500));
  }

  async function refreshStatus() {
    try {
      const status = await fetchNewChainRealtimeStatus();
      setStackStatus(status);
      setRunning(status.running ? "up" : "down");
      append(
        `[新链] running=${status.running} akshare_pid=${status.akshare_pid ?? "-"} ` +
        `raw_pid=${status.raw_news_pid ?? "-"} dec_pid=${status.decision_pid ?? "-"} ` +
        `rebuild_pid=${status.rebuild_pid ?? "-"} v2=${status.profile_version}/${status.profile_status} ` +
        `pending=${status.pending_count} review=${status.review_queue_count ?? "-"} dl=${status.dead_letter_count}`
      );
    } catch (err) {
      setRunning("down");
      if (err instanceof Error && err.message.includes("timeout")) {
        append("新链状态查询超时，SPS 可能未启动");
      }
    }
  }

  async function refreshJyhfCdpStatus() {
    const result = await fetchJyhfCdpCollectorStatus();
    setJyhfStatus(result);
    setJyhfError(null);
    append(`[诊断] cr=${result.collector_running} cdc=${result.cdp_connected} app=${result.app_running} owner=${result.service_owner} sr=${result.service_running} tab=${result.current_tab || '-'} cap=${result.last_capture_at || '-'}`);
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
	    append(`[页面来源] href=${location.href} origin=${location.origin} port=${location.port}`);

    refreshStatus().catch(() => {
        setRunning("down");
      });
    refreshJyhfCdpStatus().catch((err) => {
      setJyhfError(err instanceof Error ? err.message : "JYHF-CDP 服务未连接");
    });
    refreshJyhfCdpLogs().catch(() => undefined);
  }, []);

  const statusErrorNotifiedRef = useRef(false);
  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshStatus().catch((err) => {
        setRunning("down");
        if (!statusErrorNotifiedRef.current) {
          const msg = err instanceof Error ? err.message : "状态检查失败";
          append(`状态轮询失败：${msg}`);
          statusErrorNotifiedRef.current = true;
        }
      });
    }, 8000);
    return () => window.clearInterval(timer);
  }, []);

  // JYHF CDP 独立轮询，不依赖主采集器状态
  useEffect(() => {
    refreshJyhfCdpStatus().catch(() => {});
    refreshJyhfCdpLogs().catch(() => {});
    fetchJyhfAuctionStatus().then(setAuctionStatus).catch(() => {});
    const timer = window.setInterval(() => {
      refreshJyhfCdpStatus().catch((err) => {
        setJyhfError(err instanceof Error ? err.message : "JYHF-CDP 服务未连接");
      });
      refreshJyhfCdpLogs().catch(() => undefined);
      fetchJyhfAuctionStatus().then(setAuctionStatus).catch(() => {});
    }, 8000);
    return () => window.clearInterval(timer);
  }, []);

  // P1-H: K线支撑告警 SSE
  useEffect(() => {
    if (!klineAlertsEnabled) {
      if (klineEsRef.current) { klineEsRef.current.close(); klineEsRef.current = null; }
      append("[K线告警] 已关闭");
      return;
    }
    const es = openKlineAlertsStream(
      (alert) => {
        setKlineAlerts(prev => [...prev, alert].slice(-200));
        const ts = alert.generated_at?.slice(11, 19) || "";
        const distSign = parseFloat(alert.distance_pct) >= 0 ? "+" : "";
        append(`[${alert.severity.toUpperCase()}] ${alert.stock_name || alert.stock_id} ${alert.alert_type.replace(/_/g," ")} | C=${parseFloat(alert.current).toFixed(2)} S=${parseFloat(alert.support_level).toFixed(2)} (${distSign}${alert.distance_pct}%) conf=${alert.confidence} ${ts}`);
      },
      (err) => {
        append(`[K线告警] SSE 断开: ${err.message}`);
      },
    );
    klineEsRef.current = es;
    append("[K线告警] SSE 已连接");
    return () => { es.close(); };
  }, [klineAlertsEnabled]);

  // P1-I-1b: W2S 竞价弱转强告警 SSE
  useEffect(() => {
    if (!w2sAlertsEnabled) {
      if (w2sEsRef.current) { w2sEsRef.current.close(); w2sEsRef.current = null; }
      return;
    }
    const es = openW2SAlertsStream(
      (alert) => {
        setW2sAlerts(prev => [...prev, alert].slice(-100));
        const ts = alert.generated_at?.slice(11, 19) || "";
        const level = alert.confirm_level;
        append(`[W2S-${level}] ${alert.stock_name || alert.stock_id} ${alert.candidate_type || ""} | score=${alert.confirm_score} open=${alert.auction_open_pct}% carry=${alert.carry_ratio} ${ts}`);
      },
      (err) => { append(`[W2S告警] SSE 断开: ${err.message}`); },
    );
    w2sEsRef.current = es;
    append("[W2S告警] SSE 已连接");
    return () => { es.close(); };
  }, [w2sAlertsEnabled]);

  useEffect(() => {
    if (running === "up") {
      statusErrorNotifiedRef.current = false;
    }
  }, [running]);

  useEffect(() => {
    const panel = terminalRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [jyhfLogs, output]);

  async function handleStart() {
    setMainBusy(true);
    if (running === "up") {
      append("新链实时采集已在运行，跳过重复启动");
      setMainBusy(false);
      return;
    }
    append("[新链] 启动基础数据采集...");
    try {
      const result = await startNewChainRealtime();
      append(`[新链] 启动完成: ok=${result.ok} status=${result.status}`);
      await refreshStatus();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "启动失败";
      append(`[新链] 启动失败: ${msg}`);
    } finally {
      setMainBusy(false);
    }
  }

  async function handleStop() {
    setMainBusy(true);
    append("[新链] 停止实时采集...");
    try {
      const result = await stopNewChainRealtime();
      append(`[新链] 停止完成: ok=${result.ok} status=${result.status}`);
      await refreshStatus();
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
      append("已刷新新链状态");
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
    setKlineAlertsEnabled(true);
    setW2sAlertsEnabled(true);

    // 竞价采集（独立线程，不阻塞 DOM 启动）
    if (auctionEnabled) {
      setAuctionBusy(true);
      append("同时启动竞价采集...");
      const now = new Date();
      const td = now.toISOString().slice(0, 10);
      const yesterday = new Date(now);
      yesterday.setDate(yesterday.getDate() - 1);
      const cd = yesterday.toISOString().slice(0, 10);
      startJyhfAuctionCollector(td, cd).then((r) => {
        setAuctionStatus(r);
        setAuctionBusy(false);
        append(`竞价采集: ok=${r.ok} state=${r.state} trade=${r.trade_date} candidate=${r.candidate_date}`);
      }).catch((err) => {
        setAuctionBusy(false);
        append(`竞价采集启动失败: ${err instanceof Error ? err.message : String(err)}`);
      });
    }

    try {
      const result = await startJyhfCdpCollector();
      // Merge result into jyhfStatus immediately so UI reflects current state
      setJyhfStatus(prev => ({
        ...(prev ?? {} as JyhfCdpCollectorStatus),
        // merge result fields (service_running, collector_running, service_owner, etc.)
        service_running: result.service_running,
        service_owner: result.service_owner,
        collector_running: result.collector_running,
        service_pid: result.service_pid,
        service_port: result.service_port,
        cdp_connected: result.cdp_connected,
        cdp_port: result.cdp_port,
        app_running: result.app_running,
        last_capture_at: result.last_capture_at,
        last_event_at: result.last_event_at,
        capture_count_total: result.capture_count_total,
        new_event_count_total: result.new_event_count_total,
        duplicate_count_total: result.duplicate_count_total,
        parse_error_count_total: result.parse_error_count_total,
        pushed_to_stream_count_total: result.pushed_to_stream_count_total,
        pushed_to_intel_count_total: result.pushed_to_intel_count_total,
        review_queue_count_total: result.review_queue_count_total,
        last_error: result.last_error,
        current_tab: result.current_tab,
        current_route: result.current_route,
      } as JyhfCdpCollectorStatus));

      // Only hard-fail when BOTH ok=false AND service is not running
      if (!result.ok && !result.service_running) {
        append(`启动失败: ${result.message}`);
        setJyhfBusy(false);
        return;
      }

      append(`[START_RESULT] ${JSON.stringify(result)}`);
      append(result.message || "启动请求已提交，等待状态确认...");

      // Poll /status with layered readiness checks
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try {
          const st = await fetchJyhfCdpCollectorStatus();
          setJyhfStatus(st);
          append(`[STATUS_RESULT ${i + 1}s] ${JSON.stringify(st)}`);

          // Layered readiness: wait for actual data, not just collector_running
          if (st.last_capture_at) {
            append(`采集正常，最近采集=${st.last_capture_at} (count=${st.capture_count_total})`);
            break;
          }
          if (st.cdp_connected) {
            if (i % 5 === 0) append("已连接9223，等待首次DOM采集...");
            continue;
          }
          if (st.collector_running) {
            if (i % 5 === 0) append("采集任务已启动，等待连接久赢恒丰9223...");
            continue;
          }
          if (st.service_running) {
            if (i % 5 === 0) append(`等待中... CDP服务已启动，采集任务未运行 (${i + 1}s)`);
            continue;
          }
          if (i % 5 === 0) append(`等待 CDP 服务启动... (${i + 1}s)`);
        } catch { append(`[轮询 ${i + 1}s] 请求失败，重试中...`); }
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
    setKlineAlertsEnabled(false);
    setW2sAlertsEnabled(false);

    // 同时停止竞价采集
    if (auctionStatus?.running) {
      append("同时停止竞价采集...");
      stopJyhfAuctionCollector().then((r) => {
        setAuctionStatus(r);
        append(`竞价采集已停止: state=${r.state}`);
      }).catch((err) => {
        append(`竞价采集停止失败: ${err instanceof Error ? err.message : String(err)}`);
      });
    }

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

  const [buildInfo, setBuildInfo] = useState<string>("");

  // Load build-info.json for diagnostics
  useEffect(() => {
    fetch("/build-info.json", { cache: "no-store" })
      .then(r => r.json())
      .then(d => setBuildInfo(`build: ${d.entry_asset || '?'} @ ${d.built_at || '?'}`))
      .catch(() => setBuildInfo("build-info.json not found"));
  }, []);

  const jyhfCollectorRunning = Boolean(jyhfStatus?.collector_running);

  function getJyhfStage(status: JyhfCdpCollectorStatus | null): string {
    if (!status?.service_running) return "CDP服务未启动";
    if (!status.collector_running) return "CDP服务已启动，采集任务未运行";
    if (!status.cdp_connected) return "采集任务已启动，等待连接久赢恒丰9223";
    if (!status.last_capture_at) return "已连接9223，等待首次DOM采集";
    return "采集正常";
  }

  const jyhfStage = getJyhfStage(jyhfStatus);

  const mergedLogs = useMemo(() => {
    const parts: string[] = [];
    // 基础数据采集日志
    if (stackStatus) {
      parts.push(
        `── 基础数据采集状态 ──`,
        `running: ${stackStatus.running}`,
        `run_id: ${stackStatus.run_id || "-"}`,
        `raw_news_pid: ${stackStatus.raw_news_pid ?? "-"}`,
        `decision_pid: ${stackStatus.decision_pid ?? "-"}`,
        `profile: ${stackStatus.profile_version}/${stackStatus.profile_status}`,
        `pending: ${stackStatus.pending_count}  dead_letter: ${stackStatus.dead_letter_count}`,
        `started_at: ${stackStatus.started_at ?? "-"}`,
        "",
      );
    }
    if (jyhfLogs.length) {
      if (jyhfCollectorRunning || jyhfStatus?.service_running) {
        parts.push("── JYHF DOM 采集日志 (运行中) ──", ...jyhfLogs, "");
      } else {
        parts.push("── JYHF DOM 采集日志 (已停止，以下为历史记录) ──", ...jyhfLogs, "");
      }
    }
    if (auctionEnabled && auctionStatus) {
      parts.push(
        `── JYHF 竞价采集 ──`,
        `running: ${auctionStatus.running}  state: ${auctionStatus.state}`,
        `trade_date: ${auctionStatus.trade_date ?? "-"}  candidate_date: ${auctionStatus.candidate_date ?? "-"}`,
        `rounds: ${auctionStatus.rounds}  points: ${auctionStatus.points}`,
        auctionStatus.last_error ? `last_error: ${auctionStatus.last_error}` : "",
        "",
      );
    }
    return [...output, ...parts];
  }, [output, jyhfLogs, stackStatus, jyhfCollectorRunning, jyhfStatus?.service_running, auctionEnabled, auctionStatus]);

  return (
    <div className="workspace-page">
      <section className="strong-watch-toolbar">
        <img src={realtimeIcon} alt="" style={{ height: 64, width: 64, flexShrink: 0 }} />
        <h1 className="strong-watch-title">实时采集</h1>
        <button className="back-button" type="button" style={{ marginLeft: "auto" }} onClick={() => navigateTo("/")}>
          返回
        </button>
      </section>

      <main className="collection-debug-grid">
        <section className="workspace-card collection-debug-control">
          <span className="metric-label section-title">日采集控制台 · 基础数据采集</span>
          <p className="subtle" style={{marginTop:4,marginBottom:12}}>
            raw_news + ThemeProcessor + DecisionExecutor → 盘前必读
          </p>
          <div className="collection-debug-status">
            <div>
              <span className="metric-label">新链状态</span>
              <strong>{running === "up" ? "🟢 运行中" : running === "down" ? "🔴 已停止" : "⚪ 检查中"}</strong>
            </div>
            {stackStatus?.run_id && (
              <div>
                <span className="metric-label">Run ID</span>
                <strong>{stackStatus.run_id}</strong>
              </div>
            )}
            <div>
              <span className="metric-label">Profile</span>
              <strong>{stackStatus?.profile_version ?? "?"}/{stackStatus?.profile_status ?? "?"}</strong>
            </div>
            <div>
              <span className="metric-label">raw_news PID</span>
              <strong>{stackStatus?.raw_news_pid ?? "-"}</strong>
            </div>
            <div>
              <span className="metric-label">decision PID</span>
              <strong>{stackStatus?.decision_pid ?? "-"}</strong>
            </div>
            <div>
              <span className="metric-label">Pending / DL</span>
              <strong>{stackStatus?.pending_count ?? "?"} / {stackStatus?.dead_letter_count ?? "?"}</strong>
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
                ? "⏳ 正在执行..."
                : running === "up"
                  ? "🟢 基础数据采集运行中"
                  : running === "down"
                    ? "🔴 已停止"
                    : "⚪ 状态检查中"}
            </span>
            <button className="tag" type="button"
              style={{ marginLeft: 12 }}
              onClick={() => navigateTo(`/recap?date=${new Date().toISOString().slice(0, 10)}&report_type=post_market`)}>
              前往当日复盘 →
            </button>
          </div>
          <p className="workspace-note" style={{ marginTop: 8 }}>
            基础数据采集完成后，请到「当日复盘」页面生成动态复盘数据与复盘报告。
          </p>
        </section>

        <section className="workspace-card collection-debug-control">
          <span className="metric-label section-title">JYHF DOM 采集源</span>
          <div className="collection-debug-status">
            <div>
              <span className="metric-label">采集器</span>
              <strong>{jyhfStage}</strong>
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
            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", userSelect: "none" }}>
              <input
                type="checkbox"
                checked={auctionEnabled}
                onChange={(e) => setAuctionEnabled(e.target.checked)}
                style={{ width: 16, height: 16, cursor: "pointer" }}
              />
              <span style={{ fontWeight: 600 }}>竞价采集</span>
              {auctionEnabled && auctionStatus && (
                <span style={{ fontSize: 12, color: auctionStatus.running ? "#22c55e" : auctionStatus.state === "error" ? "#ef4444" : "#94a3b8" }}>
                  {auctionStatus.running ? "运行中" : auctionStatus.state === "finished" ? "已完成" : auctionStatus.state === "idle" ? "待启动" : auctionStatus.state}
                </span>
              )}
              {auctionEnabled && auctionBusy && (
                <span style={{ fontSize: 12, color: "#f59e0b" }}>⏳ 启动中...</span>
              )}
            </label>
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
                    : jyhfStatus?.last_capture_at
                      ? `采集运行中，捕获 ${jyhfStatus.capture_count_total} 条，数据写入 stream:event:feed`
                      : jyhfStatus?.service_running
                        ? jyhfStage
                        : "就绪，点击启动开始采集 JYHF DOM 数据"}
            </span>
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">K线支撑告警</span>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", userSelect: "none", marginLeft: 12 }}>
            <input
              type="checkbox"
              checked={klineAlertsEnabled}
              onChange={(e) => setKlineAlertsEnabled(e.target.checked)}
              style={{ width: 16, height: 16, cursor: "pointer" }}
            />
            <span style={{ fontWeight: 600, fontSize: 13 }}>启用</span>
          </label>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4, marginBottom: 8 }}>
            {(["all", "critical", "error", "warning", "info"] as const).map(level => (
              <button
                key={level}
                type="button"
                className={`tag tag-button ${klineFilter === level ? "tag-active" : ""}`}
                style={{ fontSize: 11, padding: "2px 10px" }}
                onClick={() => setKlineFilter(level)}
              >
                {level === "all" ? "全部" : level.toUpperCase()}
              </button>
            ))}
            <button
              type="button"
              className="tag tag-button"
              style={{ fontSize: 11, padding: "2px 10px", marginLeft: "auto" }}
              onClick={() => setKlineAlerts([])}
            >
              清空
            </button>
          </div>
          <div className="collection-log-panel" style={{ maxHeight: 240, overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
            {(() => {
              const sevOrder: Record<string, number> = { critical: 0, error: 1, warning: 2, info: 3 };
              const sevColors: Record<string, string> = { critical: "#ef4444", error: "#f97316", warning: "#eab308", info: "#94a3b8" };
              const filtered = klineFilter === "all"
                ? klineAlerts
                : klineAlerts.filter(a => sevOrder[a.severity] <= (sevOrder[klineFilter] ?? 9));
              if (filtered.length === 0) {
                return <div className="collection-log-line" style={{ color: "#64748b" }}>等待告警...</div>;
              }
              return filtered.slice(-50).reverse().map((a, i) => {
                const ts = a.generated_at?.slice(11, 19) || "--:--:--";
                const distSign = parseFloat(a.distance_pct) >= 0 ? "+" : "";
                return (
                  <div key={`ka-${i}`} className="collection-log-line" style={{ color: sevColors[a.severity] || "#94a3b8", whiteSpace: "nowrap" }}>
                    <span style={{ color: "#64748b" }}>{ts}</span>
                    {" "}
                    <strong>{a.stock_name || a.stock_id}</strong>
                    {" "}
                    <span style={{ color: sevColors[a.severity] }}>[{a.alert_type.replace(/_/g, " ")}]</span>
                    {" "}
                    C={parseFloat(a.current).toFixed(2)} S={parseFloat(a.support_level).toFixed(2)}
                    {" "}
                    <span style={{ color: parseFloat(a.distance_pct) < 0 ? "#ef4444" : "#22c55e" }}>
                      ({distSign}{a.distance_pct}%)
                    </span>
                    {" "}
                    <span style={{ color: "#64748b", fontSize: 10 }}>conf={a.confidence}</span>
                  </div>
                );
              });
            })()}
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">弱转强竞价告警</span>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", userSelect: "none", marginLeft: 12 }}>
            <input type="checkbox" checked={w2sAlertsEnabled} onChange={(e) => setW2sAlertsEnabled(e.target.checked)} style={{ width: 16, height: 16, cursor: "pointer" }} />
            <span style={{ fontWeight: 600, fontSize: 13 }}>启用</span>
          </label>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4, marginBottom: 8 }}>
            {(["all", "important", "observe"] as const).map(level => (
              <button key={level} type="button" className={`tag tag-button ${w2sFilter === level ? "tag-active" : ""}`}
                style={{ fontSize: 11, padding: "2px 10px" }} onClick={() => setW2sFilter(level)}>
                {level === "all" ? "全部" : level === "important" ? "A/B级" : "C级"}
              </button>
            ))}
            <button type="button" className="tag tag-button" style={{ fontSize: 11, padding: "2px 10px", marginLeft: "auto" }}
              onClick={() => setW2sAlerts([])}>清空</button>
          </div>
          <div className="collection-log-panel" style={{ maxHeight: 200, overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
            {(() => {
              const filtered = w2sFilter === "all" ? w2sAlerts : w2sAlerts.filter(a => a.severity === w2sFilter);
              if (filtered.length === 0) return <div className="collection-log-line" style={{ color: "#64748b" }}>等待竞价确认...</div>;
              return filtered.slice(-50).reverse().map((a, i) => {
                const ts = a.generated_at?.slice(11, 19) || "--:--:--";
                const lvlColor: Record<string, string> = { A: "#22c55e", B: "#f59e0b", C: "#94a3b8" };
                return (
                  <div key={`w2s-${i}`} className="collection-log-line" style={{ color: "#cbd5e1", whiteSpace: "nowrap" }}>
                    <span style={{ color: "#64748b" }}>{ts}</span>{" "}
                    <strong style={{ color: lvlColor[a.confirm_level] || "#94a3b8" }}>[{a.confirm_level}]</strong>{" "}
                    <strong>{a.stock_name || a.stock_id}</strong>{" "}
                    <span style={{ color: "#94a3b8" }}>{a.theme_name}</span>{" "}
                    <span>{a.candidate_type?.replace(/_/g, " ")}</span>{" "}
                    <span style={{ color: "#64748b" }}>score={a.confirm_score} open={a.auction_open_pct}% carry={a.carry_ratio}</span>
                  </div>
                );
              });
            })()}
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">终端调试输出</span>
          <button type="button" className="tag tag-button" style={{marginLeft:12}} onClick={async () => {
            const text = mergedLogs.join('\n');
            try {
              await navigator.clipboard.writeText(text);
              append('✓ 终端输出已复制到剪贴板 (' + mergedLogs.length + ' 行)');
            } catch {
              // Fallback for non-HTTPS or clipboard permission denied
              const ta = document.createElement('textarea');
              ta.value = text;
              ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
              document.body.appendChild(ta);
              ta.select();
              document.execCommand('copy');
              document.body.removeChild(ta);
              append('✓ 终端输出已复制到剪贴板 (' + mergedLogs.length + ' 行)');
            }
          }}>📋 复制终端输出</button>
          <div className="collection-log-panel collection-debug-terminal" ref={terminalRef}>
            {(mergedLogs.length ? mergedLogs : ["[等待中] 尚未产生调试日志。"]).map((line, idx) => (
              <div className="collection-log-line" key={`realtime-terminal-${idx}`}>
                {line}
              </div>
            ))}
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">新链组件状态</span>
          <pre className="collection-debug-json">
            {stackStatus
              ? JSON.stringify({
                  running: stackStatus.running,
                  run_id: stackStatus.run_id,
                  started_at: stackStatus.started_at,
                  profile: `${stackStatus.profile_version}/${stackStatus.profile_status}`,
                  raw_news_pid: stackStatus.raw_news_pid,
                  decision_pid: stackStatus.decision_pid,
                  pending_count: stackStatus.pending_count,
                  dead_letter_count: stackStatus.dead_letter_count,
                }, null, 2)
              : "暂无状态"}
          </pre>
        </section>
      </main>
    </div>
  );
}
