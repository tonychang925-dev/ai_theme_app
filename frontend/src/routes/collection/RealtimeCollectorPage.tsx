import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchJyhfCdpCollectorLogs,
  fetchJyhfCdpCollectorStatus,
  startJyhfCdpCollector,
  stopJyhfCdpCollector,
  fetchNewChainRealtimeStatus,
  startNewChainRealtime,
  stopNewChainRealtime,
  fetchStatusBundle,
  startJyhfAuctionCollector,
  stopJyhfAuctionCollector,
  openKlineAlertsStream,
  openW2SAlertsStream,
  fetchReviewQueue,
  confirmReviewEvent,
  deleteReviewEvent,
  batchDeleteReviewEvents,
  fetchReviewQueueDetail,
  type JyhfCdpCollectorStatus,
  type JyhfAuctionStatus,
  type KlineAlertEvent,
  type W2SAlertEvent,
  type NewChainRealtimeStatus,
  type ReviewQueueItem,
  type StatusBundle,
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
  const [klineFilter, setKlineFilter] = useState<"all" | "critical" | "error" | "warning" | "info" | "auction" | "intraday">("warning");
  const [klineAlertsEnabled, setKlineAlertsEnabled] = useState(true);
  const klineEsRef = useRef<EventSource | null>(null);
  const [w2sAlerts, setW2sAlerts] = useState<W2SAlertEvent[]>([]);
  const [w2sFilter, setW2sFilter] = useState<"all" | "important" | "observe">("important");
  const [w2sAlertsEnabled, setW2sAlertsEnabled] = useState(true);
  const w2sEsRef = useRef<EventSource | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const initializedRef = useRef(false);

  // ── Review Queue state ──
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [reviewTotal, setReviewTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [detailItem, setDetailItem] = useState<ReviewQueueItem | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);

  function append(line: string) {
    setOutput((prev) => [...prev, `[${nowText()}] ${line}`].slice(-500));
  }

  // P0-C2: 统一状态获取 — 一次请求替代 new-chain + CDP + auction 三个独立轮询
  async function refreshBundledStatus() {
    try {
      const bundle = await fetchStatusBundle();

      // new-chain status
      const nc = bundle.new_chain as Record<string, unknown>;
      if (nc && typeof nc.running !== 'undefined') {
        setStackStatus(nc as unknown as NewChainRealtimeStatus);
        setRunning(nc.running ? "up" : "down");
        const streams = (nc.redis_streams as Record<string, {length: number}> | undefined) || {};
        const rawLen = streams["stream:news:raw"]?.length ?? 0;
        const structLen = streams["stream:events:structured"]?.length ?? 0;
        const decLen = streams["stream:events:decision"]?.length ?? 0;
        const qwenOk = nc.qwen_dedup_ready ? "Qwen✅" : "Qwen⚠️";
        append(
          `[采集] run=${nc.running ? "🟢" : "🔴"} ${qwenOk} ` +
          `raw=${rawLen > 999 ? Math.round(rawLen/1000) + "k" : rawLen} ` +
          `struct=${structLen > 999 ? Math.round(structLen/1000) + "k" : structLen} ` +
          `dec=${decLen > 999 ? Math.round(decLen/1000) + "k" : decLen} ` +
          `pending=${nc.pending_count} dl=${nc.dead_letter_count} ` +
          `LLM过滤=${nc.prefilter_skipped ?? 0} Feed通过=${nc.news_published_total ?? 0}` +
          (rawLen > 5000 ? " ⚠️积压" : "")
        );
      }
    } catch (err) {
      setRunning("down");
      if (err instanceof Error && err.message.includes("timeout")) {
        append("新链状态查询超时，SPS 可能未启动");
      }
    }

    // JYHF CDP status
    try {
      const cdp = bundle.jyhf_cdp as Record<string, unknown>;
      if (cdp && typeof cdp === 'object') {
        setJyhfStatus(cdp as unknown as JyhfCdpCollectorStatus);
        setJyhfError(null);
        append(`[诊断] cr=${cdp.collector_running} cdc=${cdp.cdp_connected} app=${cdp.app_running} owner=${cdp.service_owner} sr=${cdp.service_running} tab=${cdp.current_tab || '-'} cap=${cdp.last_capture_at || '-'}`);
      }
    } catch (err) {
      setJyhfError(err instanceof Error ? err.message : "JYHF-CDP 服务未连接");
    }

    // Auction status
    try {
      const auction = bundle.jyhf_auction as Record<string, unknown>;
      if (auction && typeof auction === 'object') {
        setAuctionStatus(auction as unknown as JyhfAuctionStatus);
      }
    } catch { /* silent */ }
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

    refreshBundledStatus().catch(() => {});
    refreshJyhfCdpLogs().catch(() => undefined);
  }, []);

  // P0-C2: 统一 8s 轮询替代原来的 3 个独立轮询
  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshBundledStatus().catch(() => {});
      refreshJyhfCdpLogs().catch(() => undefined);
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
    try {
      append("🖱️ 按钮点击已触发");
      setMainBusy(true);
      if (running === "up") {
        append("已在运行，跳过");
        setMainBusy(false);
        return;
      }
      append("[新链] 发送启动请求...");
      const result = await startNewChainRealtime();
      append(`[新链] ok=${result.ok}`);
      await refreshBundledStatus();
    } catch (err: any) {
      append(`❌ 启动失败: ${err?.message || err}`);
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
      await refreshBundledStatus();
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
      await refreshBundledStatus();
      append("已刷新新链状态");
    } catch (err) {
      const message = err instanceof Error ? err.message : "刷新失败";
      append(`刷新失败: ${message}`);
    } finally {
      setMainBusy(false);
    }
  }

  // ── Review Queue helpers ──
  async function refreshReviewQueue() {
    try {
      const data = await fetchReviewQueue({ page_size: 50, status: "waiting" });
      setReviewItems(data.items);
      setReviewTotal(data.total);
    } catch { /* silent */ }
  }
  async function handleConfirmReview(id: number) {
    setReviewBusy(true);
    try { await confirmReviewEvent(id); await refreshReviewQueue(); } catch { /* silent */ } finally { setReviewBusy(false); }
  }
  async function handleDeleteReview(id: number) {
    setReviewBusy(true);
    try { await deleteReviewEvent(id); await refreshReviewQueue(); } catch { /* silent */ } finally { setReviewBusy(false); }
  }
  async function handleBatchDelete() {
    if (selectedIds.size === 0) return;
    setReviewBusy(true);
    try { await batchDeleteReviewEvents([...selectedIds]); setSelectedIds(new Set()); await refreshReviewQueue(); } catch { /* silent */ } finally { setReviewBusy(false); }
  }
  async function openDetail(id: number) {
    try {
      const d = await fetchReviewQueueDetail(id);
      setDetailItem(d); setDetailOpen(true);
    } catch { /* silent */ }
  }
  function toggleSelect(id: number) {
    setSelectedIds(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  useEffect(() => { refreshReviewQueue(); const t = setInterval(refreshReviewQueue, 30000); return () => clearInterval(t); }, []);

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
        append(`竞价采集: state=${r.state} running=${r.running} trade=${r.trade_date} candidate=${r.candidate_date}`);
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
    // 实时采集日志
    if (stackStatus) {
      parts.push(
        `── 实时采集状态 ──`,
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

      <main className="collection-debug-grid" style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 12 }}>
        {/* ── 左列 ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <section className="workspace-card collection-debug-control">
          <span className="metric-label section-title">控制面板 · 实时采集</span>
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
            <button type="button" id="btn-start-realtime" className={`tag tag-button ${running === "down" ? "tag-active" : ""}`} onClick={handleStart} disabled={mainBusy}>
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
                  ? "🟢 实时采集运行中"
                  : running === "down"
                    ? "🔴 已停止"
                    : "⚪ 状态检查中"}
            </span>
          </div>
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
              <input type="checkbox" checked={klineAlertsEnabled} onChange={(e) => setKlineAlertsEnabled(e.target.checked)}
                style={{ width: 16, height: 16, cursor: "pointer" }} />
              <span style={{ fontWeight: 600, fontSize: 12 }}>支撑告警</span>
            </label>
            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", userSelect: "none" }}>
              <input type="checkbox" checked={w2sAlertsEnabled} onChange={(e) => setW2sAlertsEnabled(e.target.checked)}
                style={{ width: 16, height: 16, cursor: "pointer" }} />
              <span style={{ fontWeight: 600, fontSize: 12 }}>W2S告警</span>
            </label>
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
              {jyhfBusy ? "⏳ 等待中..."
                : jyhfError ? `⚠ ${jyhfError}`
                : jyhfStatus?.last_error ? `⚠ ${jyhfStatus.last_error}`
                : jyhfCollectorRunning ? "🟢 DOM采集运行中"
                : jyhfStatus?.service_running ? jyhfStage
                : "就绪"}
            </span>
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">Stream 健康监控</span>
          <div style={{ fontSize: 11, lineHeight: 1.6, marginTop: 4 }}>
            {/* Qwen 状态 */}
            <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
              <span style={{ color: "#94a3b8" }}>Qwen 去重</span>
              <span style={{ color: stackStatus?.qwen_dedup_ready ? "#22c55e" : "#f59e0b" }}>
                {stackStatus?.qwen_dedup_ready ? "✅ 就绪" : "⚠️ 规则模式"}
                {stackStatus?.qwen_dedup_calls ? ` (${stackStatus.qwen_dedup_calls}次)` : ""}
              </span>
            </div>
            {/* Stream 积压 */}
            {stackStatus?.redis_streams && Object.entries(stackStatus.redis_streams).map(([name, info]) => {
              const length = info?.length ?? 0;
              const color = length > 5000 ? "#ef4444" : length > 1000 ? "#f59e0b" : "#22c55e";
              const shortName = name.replace("stream:", "");
              return (
                <div key={name} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                  <span style={{ color: "#94a3b8" }}>{shortName}</span>
                  <span style={{ color }}>{length.toLocaleString()}</span>
                </div>
              );
            })}
            {/* LLM 过滤统计 */}
            <div style={{ marginTop: 4, paddingTop: 4, borderTop: "1px solid #334155" }}>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                <span style={{ color: "#94a3b8" }}>LLM低质量过滤</span>
                <span style={{ color: "#f59e0b" }}>{stackStatus?.prefilter_skipped ?? 0}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                <span style={{ color: "#94a3b8" }}>硬去重拦截</span>
                <span style={{ color: "#f59e0b" }}>{stackStatus?.news_dedup_skipped ?? 0}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                <span style={{ color: "#94a3b8" }}>白名单保护</span>
                <span style={{ color: "#22c55e" }}>{stackStatus?.hard_protect_count ?? 0}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0", fontWeight: 600 }}>
                <span style={{ color: "#cbd5e1" }}>✅ Feed通过</span>
                <span style={{ color: "#22c55e" }}>{stackStatus?.news_published_total ?? 0}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                <span style={{ color: "#94a3b8" }}>总拦截 (过滤+去重)</span>
                <span style={{ color: "#f97316" }}>{(stackStatus?.prefilter_skipped ?? 0) + (stackStatus?.news_dedup_skipped ?? 0)}</span>
              </div>
            </div>
            {/* Pending / DL / Review */}
            <div style={{ marginTop: 4, paddingTop: 4, borderTop: "1px solid #334155" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
              <span style={{ color: "#94a3b8" }}>Pending (弱信号)</span>
              <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ color: "#94a3b8" }}>{(stackStatus?.pending_count ?? 0).toLocaleString()}</span>
                <button type="button" className="tag tag-button"
                  style={{ fontSize: 9, padding: "1px 5px", color: "#f59e0b" }}
                  onClick={async () => {
                    if (!confirm("将 pending 事件导入复核队列？这可能需要一些时间。")) return;
                    append("⏳ 正在导入 pending → 复核队列...");
                    try {
                      const resp = await fetch("/api/v2/review-queue/import-pending", { method: "POST" });
                      const data = await resp.json();
                      append(`✅ 导入完成: ${data.imported || 0} 条, 已清空 ${data.cleared || 0} 条 pending`);
                      await refreshReviewQueue();
                    } catch (e: any) { append("❌ 导入失败: " + (e?.message || e)); }
                  }}>导入复核</button>
                <button type="button" className="tag tag-button"
                  style={{ fontSize: 9, padding: "1px 5px", color: "#ef4444" }}
                  onClick={async () => {
                    if (!confirm("确认清空所有 pending 弱信号事件？此操作不可撤销。")) return;
                    try {
                      await fetch("/api/v2/review-queue/clear-pending", { method: "POST" });
                      append("✅ pending 已清空");
                      await refreshBundledStatus();
                    } catch (e: any) { append("❌ 清空 pending 失败: " + (e?.message || e)); }
                  }}>清空</button>
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
              <span style={{ color: "#94a3b8" }}>死信</span>
              <span style={{ color: (stackStatus?.dead_letter_count ?? 0) > 10 ? "#ef4444" : "#94a3b8" }}>
                {(stackStatus?.dead_letter_count ?? 0).toLocaleString()}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
              <span style={{ color: "#94a3b8" }}>复核队列</span>
              <span style={{ color: "#94a3b8" }}>{(stackStatus?.review_queue_count ?? 0).toLocaleString()}</span>
            </div>
            {/* Processor PIDs */}
            <div style={{ marginTop: 4, padding: "4px 0", borderTop: "1px solid #334155" }}>
              <span style={{ color: "#64748b" }}>
                raw={stackStatus?.raw_news_pid ?? "-"} dec={stackStatus?.decision_pid ?? "-"}
                {" "}profile={stackStatus?.profile_version}/{stackStatus?.profile_status}
              </span>
            </div>
            </div>
          </div>
        </section>

        </div>{/* 左列结束 */}

        {/* ── 右列 ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <section className="workspace-card">
          <span className="metric-label section-title">弱转强观察</span>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4, marginBottom: 8, flexWrap: "wrap" }}>
            {(["all", "critical", "error", "warning", "info", "auction", "intraday"] as const).map(tag => (
              <button key={tag} type="button" className={`tag tag-button ${klineFilter === tag ? "tag-active" : ""}`}
                style={{ fontSize: 11, padding: "2px 10px" }} onClick={() => setKlineFilter(tag as typeof klineFilter)}>
                {tag === "all" ? "全部" : tag === "auction" ? "竞价" : tag === "intraday" ? "盘中" : tag.toUpperCase()}
              </button>
            ))}
            <button type="button" className="tag tag-button" style={{ fontSize: 11, padding: "2px 10px", marginLeft: "auto" }}
              onClick={() => { setKlineAlerts([]); setW2sAlerts([]); }}>清空</button>
          </div>
          <div className="collection-log-panel" style={{ maxHeight: 300, overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
            {(() => {
              const sevColors: Record<string, string> = { critical: "#ef4444", error: "#f97316", warning: "#eab308", info: "#94a3b8" };
              const lvlColor: Record<string, string> = { A: "#22c55e", B: "#f59e0b", C: "#94a3b8" };

              // 合并 kline + w2s 告警到统一列表
              type MergedAlert = { ts: string; source: string; line: React.ReactNode; severity: string };
              const merged: MergedAlert[] = [];

              // K线支撑告警
              for (const a of klineAlerts) {
                const ts = a.generated_at?.slice(11, 19) || "";
                const distSign = parseFloat(a.distance_pct) >= 0 ? "+" : "";
                const sev = a.severity || "info";
                if (klineFilter !== "all" && klineFilter !== "auction" && klineFilter !== "intraday" && sev !== klineFilter) continue;
                if (klineFilter === "auction" || klineFilter === "intraday") continue; // kline in "all" mode only
                merged.push({
                  ts, source: "支撑", severity: sev,
                  line: <span>
                    <span style={{ color: sevColors[sev] }}>[{a.alert_type?.replace(/_/g, " ")}]</span>{" "}
                    <strong>{a.stock_name || a.stock_id}</strong>{" "}
                    <span style={{ color: "#94a3b8" }}>C={parseFloat(a.current).toFixed(2)}</span>{" "}
                    <span style={{ color: parseFloat(a.distance_pct) < 0 ? "#ef4444" : "#22c55e" }}>({distSign}{a.distance_pct}%)</span>
                  </span>
                });
              }

              // W2S竞价告警
              for (const a of w2sAlerts) {
                const ts = a.generated_at?.slice(11, 19) || "";
                const sev = a.severity || "observe";
                if (klineFilter !== "all" && klineFilter !== "intraday" && klineFilter !== sev && klineFilter !== "auction") continue;
                merged.push({
                  ts, source: "竞价", severity: sev,
                  line: <span>
                    <strong style={{ color: lvlColor[a.confirm_level] || "#94a3b8" }}>[{a.confirm_level}]</strong>{" "}
                    <strong>{a.stock_name || a.stock_id}</strong>{" "}
                    <span style={{ color: "#94a3b8" }}>{a.theme_name}</span>{" "}
                    <span style={{ color: "#64748b" }}>score={a.confirm_score} open={a.auction_open_pct}% carry={a.carry_ratio}</span>
                  </span>
                });
              }

              merged.sort((a, b) => a.ts.localeCompare(b.ts));
              if (merged.length === 0) {
                return <div className="collection-log-line" style={{ color: "#64748b" }}>等待弱转强信号...</div>;
              }
              return merged.slice(-80).reverse().map((m, i) => (
                <div key={`w2su-${i}`} className="collection-log-line" style={{ color: "#cbd5e1", whiteSpace: "nowrap" }}>
                  <span style={{ color: "#64748b" }}>{m.ts}</span>{" "}
                  <span style={{ color: "#475569", fontSize: 10 }}>[{m.source}]</span>{" "}
                  {m.line}
                </div>
              ));
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
          <div style={{ marginTop: 8, padding: "6px 10px", background: "#1e293b", borderRadius: 4, fontSize: 11, display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ color: stackStatus?.running ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
              {stackStatus?.running ? "🟢 运行中" : "🔴 已停止"}
            </span>
            <span style={{ color: "#94a3b8" }}>
              Run: <span style={{ color: "#cbd5e1" }}>{stackStatus?.run_id?.slice(-8) || "-"}</span>
            </span>
            <span style={{ color: "#94a3b8" }}>
              原始新闻: <span style={{ color: stackStatus?.raw_news_pid ? "#22c55e" : "#ef4444" }}>{stackStatus?.raw_news_pid || "未启动"}</span>
            </span>
            <span style={{ color: "#94a3b8" }}>
              决策引擎: <span style={{ color: stackStatus?.decision_pid ? "#22c55e" : "#ef4444" }}>{stackStatus?.decision_pid || "未启动"}</span>
            </span>
            <span style={{ color: "#94a3b8" }}>
              待处理: <span style={{ color: (stackStatus?.pending_count ?? 0) > 100 ? "#f97316" : "#22c55e", fontWeight: 600 }}>{stackStatus?.pending_count ?? 0}</span>
            </span>
            <span style={{ color: "#94a3b8" }}>
              死信: <span style={{ color: (stackStatus?.dead_letter_count ?? 0) > 10 ? "#ef4444" : "#94a3b8" }}>{stackStatus?.dead_letter_count ?? 0}</span>
            </span>
            <span style={{ color: "#475569", marginLeft: "auto" }}>
              DOM: <span style={{ color: jyhfStatus?.last_capture_at ? "#22c55e" : "#94a3b8" }}>{jyhfStatus?.last_capture_at ? `${jyhfStatus.capture_count_total} 条` : "未采集"}</span>
            </span>
            <span style={{ color: "#475569" }}>
              Qwen: <span style={{ color: stackStatus?.qwen_dedup_ready ? "#22c55e" : "#f59e0b" }}>{stackStatus?.qwen_dedup_ready ? "✅" : "⚠️"}</span>
              {" "}过滤: <span style={{ color: "#cbd5e1" }}>{stackStatus?.prefilter_skipped ?? "-"}</span>
            </span>
          </div>
        </section>

        {/* ── 复核队列 (Phase 6A) ── */}
        <section className="workspace-card">
          <span className="metric-label section-title">
            复核队列{" "}
            <span style={{ color: "#f59e0b", fontWeight: 600 }}>{reviewTotal}</span>
            {" "}条待处理
          </span>
          <div style={{ display: "flex", gap: 6, marginTop: 4, flexWrap: "wrap", alignItems: "center" }}>
            <button type="button" className="tag tag-button" style={{ fontSize: 11, padding: "2px 8px" }}
              onClick={() => refreshReviewQueue()} disabled={reviewBusy}>刷新</button>
            <label style={{ fontSize: 11, color: "#94a3b8", cursor: "pointer", display: "flex", alignItems: "center", gap: 2 }}>
              <input type="checkbox"
                checked={reviewItems.length > 0 && selectedIds.size === reviewItems.length}
                onChange={() => {
                  if (selectedIds.size === reviewItems.length) {
                    setSelectedIds(new Set());
                  } else {
                    setSelectedIds(new Set(reviewItems.map(it => it.id)));
                  }
                }}
                style={{ margin: 0 }} />全选
            </label>
            <button type="button" className="tag tag-button" style={{ fontSize: 11, padding: "2px 8px", color: "#f97316" }}
              onClick={handleBatchDelete} disabled={reviewBusy || selectedIds.size === 0}>
              批量删除 ({selectedIds.size})
            </button>
            {reviewBusy && <span style={{ fontSize: 11, color: "#f59e0b" }}>⏳</span>}
          </div>
          <div className="collection-log-panel" style={{ maxHeight: 520, overflow: "auto", marginTop: 6, fontFamily: "monospace", fontSize: 11, lineHeight: 1.4 }}>
            {reviewItems.length === 0 ? (
              <div style={{ color: "#475569", padding: 8 }}>暂无待复核事件</div>
            ) : (
              reviewItems.map((item) => (
                <div key={item.id} style={{
                  display: "flex", alignItems: "flex-start", gap: 6, padding: "4px 4px",
                  borderBottom: "1px solid #1e293b", cursor: "pointer",
                  background: selectedIds.has(item.id) ? "rgba(59,130,246,0.12)" : "transparent",
                }}>
                  <input type="checkbox" checked={selectedIds.has(item.id)}
                    onChange={() => toggleSelect(item.id)}
                    style={{ marginTop: 2, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}
                    onClick={() => openDetail(item.id)}>
                    <div style={{ color: "#e2e8f0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {item.event_title || item.raw_title || `event #${item.event_id}`}
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 1 }}>
                      <span style={{ color: "#22c55e", fontSize: 10 }}>
                        {item.proposed_theme_name || "-"}
                      </span>
                      <span style={{ color: "#64748b", fontSize: 10 }}>
                        {(() => { const v = parseFloat(String(item.proposed_theme_confidence ?? "")); return Number.isFinite(v) ? v.toFixed(2) : "-"; })()}
                      </span>
                      <span style={{ color: "#475569", fontSize: 10 }}>
                        {(item.created_at || "").slice(0, 16).replace("T", " ")}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                    <button type="button" className="tag tag-button"
                      style={{ fontSize: 10, padding: "1px 6px", color: "#22c55e" }}
                      onClick={(e) => { e.stopPropagation(); handleConfirmReview(item.id); }}>确认</button>
                    <button type="button" className="tag tag-button"
                      style={{ fontSize: 10, padding: "1px 6px", color: "#ef4444" }}
                      onClick={(e) => { e.stopPropagation(); handleDeleteReview(item.id); }}>删除</button>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        </div>{/* 右列结束 */}
      </main>

      {/* ── 复核详情 Modal ── */}
      {detailOpen && detailItem && (
        <div className="collection-modal-backdrop" onClick={() => { setDetailOpen(false); setDetailItem(null); }}>
          <div className="screener-detail-modal" style={{ maxWidth: 640, maxHeight: "85vh" }}
            onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <strong style={{ color: "#e2e8f0", fontSize: 14 }}>复核详情 #{detailItem.id}</strong>
              <button type="button" className="tag tag-button" style={{ fontSize: 11 }}
                onClick={() => { setDetailOpen(false); setDetailItem(null); }}>✕ 关闭</button>
            </div>
            <div style={{ maxHeight: "65vh", overflow: "auto" }}>
              <section className="collection-section">
                <strong>事件信息</strong>
                <div className="collection-metric-card" style={{ marginTop: 4 }}>
                  <div><label className="collection-field">Event ID</label><span>{detailItem.event_id}</span></div>
                  <div><label className="collection-field">类型</label><span>{detailItem.event_type || "-"}</span></div>
                  <div><label className="collection-field">来源</label><span>{detailItem.source_channel}</span></div>
                  <div><label className="collection-field">创建时间</label><span>{detailItem.created_at?.slice(0, 19).replace("T", " ")}</span></div>
                </div>
              </section>
              <section className="collection-section" style={{ marginTop: 8 }}>
                <strong>标题</strong>
                <div className="workspace-note" style={{ marginTop: 2, color: "#e2e8f0" }}>
                  {detailItem.event_title || detailItem.raw_title || "-"}
                </div>
              </section>
              {(detailItem.event_summary || detailItem.raw_content) && (
                <section className="collection-section" style={{ marginTop: 8 }}>
                  <strong>摘要/内容</strong>
                  <div className="workspace-note" style={{ marginTop: 2, maxHeight: 200, overflow: "auto", color: "#94a3b8", whiteSpace: "pre-wrap", fontSize: 12 }}>
                    {(detailItem.event_summary || detailItem.raw_content || "").slice(0, 2000)}
                  </div>
                </section>
              )}
              <section className="collection-section" style={{ marginTop: 8 }}>
                <strong>复核信息</strong>
                <div className="collection-metric-card" style={{ marginTop: 4 }}>
                  <div><label className="collection-field">建议主题</label><span style={{ color: "#22c55e" }}>{detailItem.proposed_theme_name || "-"}</span></div>
                  <div><label className="collection-field">置信度</label><span>{(() => { const v = parseFloat(String(detailItem.proposed_theme_confidence ?? "")); return Number.isFinite(v) ? v.toFixed(4) : "-"; })()}</span></div>
                  <div><label className="collection-field">原因</label><span>{detailItem.reason || "-"}</span></div>
                  <div><label className="collection-field">状态</label><span style={{ color: detailItem.review_status === "waiting" ? "#f59e0b" : "#22c55e" }}>{detailItem.review_status}</span></div>
                  {detailItem.reviewed_by && <div><label className="collection-field">审核人</label><span>{detailItem.reviewed_by}</span></div>}
                  {detailItem.reviewed_at && <div><label className="collection-field">审核时间</label><span>{String(detailItem.reviewed_at).slice(0, 19).replace("T", " ")}</span></div>}
                  {detailItem.review_note && <div><label className="collection-field">备注</label><span>{detailItem.review_note}</span></div>}
                </div>
              </section>
            </div>
            <div className="collection-action-row" style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button type="button" className="tag tag-button tag-active"
                style={{ color: "#22c55e" }}
                disabled={reviewBusy}
                onClick={async () => {
                  const id = detailItem.id;
                  await handleConfirmReview(id);
                  setDetailOpen(false); setDetailItem(null);
                }}>
                {reviewBusy ? "处理中..." : "确认"}
              </button>
              <button type="button" className="tag tag-button"
                style={{ color: "#ef4444" }}
                disabled={reviewBusy}
                onClick={async () => {
                  const id = detailItem.id;
                  await handleDeleteReview(id);
                  setDetailOpen(false); setDetailItem(null);
                }}>
                {reviewBusy ? "处理中..." : "删除"}
              </button>
              <button type="button" className="tag tag-button"
                disabled={reviewBusy}
                onClick={() => { setDetailOpen(false); setDetailItem(null); }}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
