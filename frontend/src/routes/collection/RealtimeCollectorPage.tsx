import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchJyhfCdpCollectorLogs,
  fetchJyhfCdpCollectorStatus,
  startJyhfCdpCollector,
  stopJyhfCdpCollector,
  startRealtimeCollector,
  stopRealtimeCollector,
  fetchStatusBundle,
  fetchOrchestratorStatus,
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
  type OrchestratorStatus,
} from "../../lib/api";
import { navigateTo } from "../../lib/navigation";
import { ConfigProvider, Tabs, theme } from "antd";
import realtimeIcon from "../../assets/intel-icons/实时采集.png";

// P4-1A: 展示组件
import ServiceStatusBar, { type SseConnState } from "./components/ServiceStatusBar";
import CollectionControlPanel from "./components/CollectionControlPanel";
import UnifiedAlertPanel, { type UnifiedAlertRow } from "./components/UnifiedAlertPanel";
import DiagnosticsTabs from "./components/DiagnosticsTabs";
import OrchestratorStatusPanel from "./components/OrchestratorStatusPanel";

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
  const [startBusy, setStartBusy] = useState(false);
  const [stopBusy, setStopBusy] = useState(false);
  const [refreshBusy, setRefreshBusy] = useState(false);
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
  const [klineAlertsEnabled, setKlineAlertsEnabled] = useState(false); // 默认关闭，按需开启
  const klineEsRef = useRef<EventSource | null>(null);
  const [w2sAlerts, setW2sAlerts] = useState<W2SAlertEvent[]>([]);
  const [w2sFilter, setW2sFilter] = useState<"all" | "important" | "observe">("important");
  const [w2sAlertsEnabled, setW2sAlertsEnabled] = useState(false); // 默认关闭，按需开启
  const w2sEsRef = useRef<EventSource | null>(null);
  // ── 操作日志 ──
  const [output, setOutput] = useState<string[]>([]);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const initializedRef = useRef(false);

  // ── 生命周期日志去重：只在 state/pid/source 变化时写入 ──
  const lastRealtimeSigRef = useRef<string>("");
  const lastJyhfSigRef = useRef<string>("");

  function buildRealtimeSig(nc: Record<string, unknown> | null | undefined): string {
    if (!nc) return "unknown";
    const verified = nc.running_verified ? "running" : "stopped";
    return [
      verified,
      nc.raw_news_pid || "-",
      nc.decision_pid || "-",
      nc.db_collector_pid || "-",
      nc.status_source || "-",
    ].join("|");
  }

  function buildJyhfSig(cdp: Record<string, unknown> | null | undefined): string {
    if (!cdp) return "unknown";
    return [
      cdp.collector_running ? "1" : "0",
      cdp.cdp_connected ? "1" : "0",
      cdp.app_running ? "1" : "0",
      cdp.service_running ? "1" : "0",
      cdp.current_tab || "-",
    ].join("|");
  }

  // P4-1A: SSE 连接状态（供 ServiceStatusBar 显示）
  const [klineSseState, setKlineSseState] = useState<SseConnState>("connecting");
  const [w2sSseState, setW2sSseState] = useState<SseConnState>("connecting");

  // ── Review Queue state ──
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [reviewTotal, setReviewTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [detailItem, setDetailItem] = useState<ReviewQueueItem | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);

  // ── P4-2B: Orchestrator read-only status（非阻塞诊断）──
  const [orchStatus, setOrchStatus] = useState<OrchestratorStatus | null>(null);
  const [orchLoading, setOrchLoading] = useState(false);
  const [orchError, setOrchError] = useState<string | null>(null);
  const orchInFlightRef = useRef(false);

  function append(line: string) {
    setOutput((prev) => [...prev, `[${nowText()}] ${line}`].slice(-500));
  }

  // P0-C2: 统一状态获取 — 一次请求替代 new-chain + CDP + auction 三个独立轮询
  async function refreshBundledStatus() {
    let bundle: StatusBundle | null = null;

    try {
      bundle = await fetchStatusBundle();
    } catch (err) {
      setRunning("down");
      if (err instanceof Error && err.message.includes("timeout")) {
        append("新链状态查询超时，SPS 可能未启动");
      }
      return;
    }

    // new-chain status
    try {
      const nc = bundle.new_chain as Record<string, unknown>;
      if (nc && typeof nc.running !== 'undefined') {
        const runningVerified = Boolean(nc.running_verified);
        const effectiveRunning = Boolean(nc.raw_news_pid || nc.decision_pid);
        const normalizedNc = { ...nc, running: effectiveRunning } as unknown as NewChainRealtimeStatus;
        setStackStatus(normalizedNc);
        setRunning(effectiveRunning ? "up" : "down");

        // 生命周期日志：只写一次，不每 8s 刷屏
        const sig = buildRealtimeSig(nc);
        if (sig !== lastRealtimeSigRef.current) {
          const stateLabel = effectiveRunning ? (runningVerified ? "running" : "degraded") : "stopped";
          const sourceLabel = nc.status_source || "?";
          const streams = (nc.redis_streams as Record<string, {length: number}> | undefined) || {};
          const rawLen = streams["stream:news:raw"]?.length ?? 0;
          const rawPid = nc.raw_news_pid ?? "-";
          const decPid = nc.decision_pid ?? "-";
          const dbPid = nc.db_collector_pid ?? "-";
          append(
            `[生命周期] realtime=${stateLabel} source=${sourceLabel} ` +
            `raw_pid=${rawPid} dec_pid=${decPid} db_pid=${dbPid}`
          );
          lastRealtimeSigRef.current = sig;
        }
      }
    } catch (err) {
      append(`新链状态解析失败：${err instanceof Error ? err.message : String(err)}`);
    }

    // JYHF CDP status — 也只写变化时的诊断日志
    try {
      const cdp = bundle.jyhf_cdp as Record<string, unknown>;
      if (cdp && typeof cdp === 'object') {
        setJyhfStatus(cdp as unknown as JyhfCdpCollectorStatus);
        setJyhfError(null);
        const sig = buildJyhfSig(cdp);
        if (sig !== lastJyhfSigRef.current) {
          append(`[诊断] cr=${cdp.collector_running} cdc=${cdp.cdp_connected} app=${cdp.app_running} owner=${cdp.service_owner} sr=${cdp.service_running} tab=${cdp.current_tab || '-'}`);
          lastJyhfSigRef.current = sig;
        }
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

  // P4-2B: Orchestrator 60s 低频轮询（非阻塞，失败不影响主控）
  async function refreshOrchestrator() {
    if (orchInFlightRef.current) return;
    orchInFlightRef.current = true;
    setOrchLoading(true);
    try {
      const status = await fetchOrchestratorStatus();
      setOrchStatus(status);
      setOrchError(null);
    } catch (err: any) {
      setOrchError(err?.message || String(err));
    } finally {
      orchInFlightRef.current = false;
      setOrchLoading(false);
    }
  }
  useEffect(() => {
    refreshOrchestrator();
    const timer = window.setInterval(() => refreshOrchestrator(), 15000);
    return () => window.clearInterval(timer);
  }, []);

  // P1-H: K线支撑告警 SSE
  useEffect(() => {
    if (!klineAlertsEnabled) {
      if (klineEsRef.current) { klineEsRef.current.close(); klineEsRef.current = null; }
      setKlineSseState("disabled");
      return;
    }
    // 强制单例：先关旧连接再开新连接
    if (klineEsRef.current) { klineEsRef.current.close(); klineEsRef.current = null; }
    setKlineSseState("connecting");
    const es = openKlineAlertsStream(
      (alert) => {
        setKlineSseState("connected");
        setKlineAlerts(prev => [...prev, alert].slice(-200));
        const ts = alert.generated_at?.slice(11, 19) || "";
        const distSign = parseFloat(alert.distance_pct) >= 0 ? "+" : "";
        append(`[${alert.severity.toUpperCase()}] ${alert.stock_name || alert.stock_id} ${alert.alert_type.replace(/_/g," ")} | C=${parseFloat(alert.current).toFixed(2)} S=${parseFloat(alert.support_level).toFixed(2)} (${distSign}${alert.distance_pct}%) conf=${alert.confidence} ${ts}`);
      },
      (err) => {
        setKlineSseState("disconnected");
        append(`[K线告警] SSE 断开: ${err.message}`);
      },
    );
    klineEsRef.current = es;
    return () => {
      es.close();
      if (klineEsRef.current === es) klineEsRef.current = null;
    };
  }, [klineAlertsEnabled]);

  // P1-I-1b: W2S 竞价弱转强告警 SSE
  useEffect(() => {
    if (!w2sAlertsEnabled) {
      if (w2sEsRef.current) { w2sEsRef.current.close(); w2sEsRef.current = null; }
      setW2sSseState("disabled");
      return;
    }
    // 强制单例
    if (w2sEsRef.current) { w2sEsRef.current.close(); w2sEsRef.current = null; }
    setW2sSseState("connecting");
    const es = openW2SAlertsStream(
      (alert) => {
        setW2sSseState("connected");
        setW2sAlerts(prev => [...prev, alert].slice(-100));
        const ts = alert.generated_at?.slice(11, 19) || "";
        const level = alert.confirm_level;
        append(`[W2S-${level}] ${alert.stock_name || alert.stock_id} ${alert.candidate_type || ""} | score=${alert.confirm_score} open=${alert.auction_open_pct}% carry=${alert.carry_ratio} ${ts}`);
      },
      (err) => {
        setW2sSseState("disconnected");
        append(`[W2S告警] SSE 断开: ${err.message}`);
      },
    );
    w2sEsRef.current = es;
    return () => {
      es.close();
      if (w2sEsRef.current === es) w2sEsRef.current = null;
    };
  }, [w2sAlertsEnabled]);

  useEffect(() => {
    const panel = terminalRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [jyhfLogs, output]);

  async function handleStart() {
    try {
      setStartBusy(true);
      append("[操作] 启动实时采集 — 请求 BFF → SPS...");
      const result = await startRealtimeCollector({});
      append(`[操作] start → ok=${result.ok} rc=${result.return_code}`);
      if (result.stdout?.trim()) append(result.stdout.trim());
      if (result.stderr?.trim()) append(`stderr: ${result.stderr.trim()}`);
      await new Promise((r) => setTimeout(r, 5000));
      await refreshBundledStatus();
    } catch (err: any) {
      append(`❌ 启动失败: ${err?.message || err}`);
    } finally {
      setStartBusy(false);
    }
  }

  async function handleStop() {
    setStopBusy(true);
    append("[操作] 停止实时 pipeline...");
    try {
      const result = await stopRealtimeCollector({});
      append(`[操作] stop → ok=${result.ok} rc=${result.return_code}`);
      if (result.stdout?.trim()) append(result.stdout.trim());
      if (result.stderr?.trim()) append(`stderr: ${result.stderr.trim()}`);
      await new Promise((r) => setTimeout(r, 1500));
      await refreshBundledStatus();
    } catch (err: any) {
      append(`❌ 停止异常: ${err?.message || err}`);
    } finally {
      setStopBusy(false);
    }
  }

  async function handleRefresh() {
    setRefreshBusy(true);
    try {
      await refreshBundledStatus();
      append("已刷新新链状态");
    } catch (err) {
      const message = err instanceof Error ? err.message : "刷新失败";
      append(`刷新失败: ${message}`);
    } finally {
      setRefreshBusy(false);
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
  function selectAll() {
    if (reviewItems.length > 0 && selectedIds.size === reviewItems.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(reviewItems.map((r) => r.id)));
    }
  }
  async function handleImportPending() {
    setReviewBusy(true);
    try {
      await fetch("/api/v2/review-queue/import-pending", { method: "POST" });
      append("已导入 Pending 到复核队列");
      await refreshReviewQueue();
    } catch (err: any) {
      append(`导入失败: ${err?.message || err}`);
    } finally { setReviewBusy(false); }
  }
  async function handleClearPending() {
    setReviewBusy(true);
    try {
      await fetch("/api/v2/review-queue/clear-pending", { method: "POST" });
      append("已清空 Pending");
      await refreshBundledStatus();
    } catch (err: any) {
      append(`清空失败: ${err?.message || err}`);
    } finally { setReviewBusy(false); }
  }
  function closeDetail() { setDetailOpen(false); setDetailItem(null); }
  useEffect(() => { refreshReviewQueue(); const t = setInterval(refreshReviewQueue, 30000); return () => clearInterval(t); }, []);

  async function handleStartJyhfCdp() {
    setJyhfBusy(true);
    setJyhfStatus(prev => ({ ...(prev ?? {} as JyhfCdpCollectorStatus), collector_running: false }));
    append("启动 JYHF DOM 采集器...");
    setKlineAlertsEnabled(true);
    setW2sAlertsEnabled(true);

    const startAuctionAfterDomReady = async () => {
      if (!auctionEnabled) return;
      setAuctionBusy(true);
      append("DOM 首次采集成功，启动竞价采集...");
      const now = new Date();
      const td = now.toISOString().slice(0, 10);
      const yesterday = new Date(now);
      yesterday.setDate(yesterday.getDate() - 1);
      const cd = yesterday.toISOString().slice(0, 10);
      try {
        const r = await startJyhfAuctionCollector(td, cd);
        setAuctionStatus(r);
        append(`竞价采集: state=${r.state} running=${r.running} trade=${r.trade_date} candidate=${r.candidate_date}`);
      } catch (err) {
        append(`竞价采集启动失败: ${err instanceof Error ? err.message : String(err)}`);
      } finally {
        setAuctionBusy(false);
      }
    };

    try {
      const result = await startJyhfCdpCollector();
      let domCaptured = Boolean(result.last_capture_at);
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
            domCaptured = true;
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
      if (domCaptured) {
        await startAuctionAfterDomReady();
      } else if (auctionEnabled) {
        append("DOM 未完成首次采集，跳过竞价采集启动");
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

    // ── 操作日志 ──
    parts.push("── 操作日志 ──", ...output.slice(-80), "");

    // ── 生命周期日志 ── (当前快照，不累计)
    if (stackStatus) {
      const streams = stackStatus.redis_streams;
      const rawLen = streams?.["stream:news:raw"]?.length ?? 0;
      const structLen = streams?.["stream:events:structured"]?.length ?? 0;
      const decLen = streams?.["stream:events:decision"]?.length ?? 0;
      parts.push(
        "── 生命周期状态 ──",
        `realtime: ${stackStatus.running ? (stackStatus.running_verified ? "running" : "degraded") : "stopped"}`,
        `verified: ${stackStatus.running_verified ?? "?"}  source: ${stackStatus.status_source ?? "?"}`,
        `run_id: ${stackStatus.run_id || "-"}`,
        `PID — raw: ${stackStatus.raw_news_pid ?? "-"}  dec: ${stackStatus.decision_pid ?? "-"}  db: ${stackStatus.db_collector_pid ?? "-"}`,
        `started_at: ${stackStatus.started_at ?? "-"}`,
        "",
      );

      // ── 诊断/Redis 指标 ──
      parts.push(
        "── Redis Stream 指标（历史数据，非运行状态）──",
        `raw_len=${rawLen > 999 ? Math.round(rawLen/1000) + "k" : rawLen} ` +
        `struct=${structLen > 999 ? Math.round(structLen/1000) + "k" : structLen} ` +
        `dec=${decLen > 999 ? Math.round(decLen/1000) + "k" : decLen}`,
        `pending=${stackStatus.pending_count}  dead_letter=${stackStatus.dead_letter_count}` +
        `  LLM过滤=${stackStatus.prefilter_skipped ?? 0}  Feed通过=${stackStatus.news_published_total ?? 0}` +
        (rawLen > 5000 ? "  ⚠️积压" : ""),
        `profile: ${stackStatus.profile_version}/${stackStatus.profile_status}  llm: ${stackStatus.llm_judge_mode || "-"}`,
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
    return parts;
  }, [output, jyhfLogs, stackStatus, jyhfCollectorRunning, jyhfStatus?.service_running, auctionEnabled, auctionStatus]);

  // P4-1A: 统一告警 view model — Kline + W2S 合并为 UnifiedAlertRow[]
  const unifiedAlerts = useMemo((): UnifiedAlertRow[] => {
    const rows: UnifiedAlertRow[] = [];

    for (const a of klineAlerts) {
      rows.push({
        id: `kline-${a.generated_at}-${a.stock_id}`,
        ts: new Date(a.generated_at || 0).getTime() || Date.now(),
        time: a.generated_at?.slice(11, 19) || "",
        kind: "support",
        level: a.severity || "info",
        stock: a.stock_name || a.stock_id,
        title: `[${a.alert_type?.replace(/_/g, " ")}] C=${parseFloat(a.current).toFixed(2)} dist=${a.distance_pct}%`,
        score: a.confidence,
        source: "支撑告警",
        raw: a,
      });
    }

    for (const a of w2sAlerts) {
      rows.push({
        id: `w2s-${a.generated_at}-${a.stock_id}`,
        ts: new Date(a.generated_at || 0).getTime() || Date.now(),
        time: a.generated_at?.slice(11, 19) || "",
        kind: "w2s",
        level: a.severity || a.confirm_level || "observe",
        stock: a.stock_name || a.stock_id,
        title: `${a.candidate_type || "弱转强"} score=${a.confirm_score} open=${a.auction_open_pct}% carry=${a.carry_ratio}`,
        score: a.confirm_score,
        source: a.source || "竞价告警",
        raw: a,
      });
    }

    rows.sort((a, b) => a.ts - b.ts);
    return rows;
  }, [klineAlerts, w2sAlerts]);

  // P4-1A: 固化 status/busy/toggles 引用，actions 直接内联（原生 details 不需要 memo）
  const controlStatus = useMemo(
    () => ({ running, stackStatus, jyhfStatus, auctionStatus }),
    [running, stackStatus, jyhfStatus, auctionStatus],
  );
  const controlBusy = useMemo(
    () => ({ startBusy, stopBusy, refreshBusy, jyhfBusy, auctionBusy }),
    [startBusy, stopBusy, refreshBusy, jyhfBusy, auctionBusy],
  );
  const controlToggles = useMemo(
    () => ({ auctionEnabled, klineAlertsEnabled, w2sAlertsEnabled }),
    [auctionEnabled, klineAlertsEnabled, w2sAlertsEnabled],
  );

  return (
    <div className="workspace-page">
      <section className="strong-watch-toolbar">
        <img src={realtimeIcon} alt="" style={{ height: 64, width: 64, flexShrink: 0 }} />
        <h1 className="strong-watch-title">实时采集</h1>
        <button className="back-button" type="button" style={{ marginLeft: "auto" }} onClick={() => navigateTo("/")}>
          返回
        </button>
      </section>

      {/* P4-3A: 标签页重组 */}
      <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <div className="realtime-ops-dashboard" style={{ padding: "0 12px" }}>

        {/* 全局状态栏 — 所有 Tab 可见 */}
        <ServiceStatusBar
          stackStatus={stackStatus}
          jyhfStatus={jyhfStatus}
          auctionStatus={auctionStatus}
          klineSseState={klineSseState}
          w2sSseState={w2sSseState}
          klineAlertCount={klineAlerts.length}
          w2sAlertCount={w2sAlerts.length}
          redisHealth={orchStatus?.runtime_dependencies?.redis as Record<string,any> | undefined}
          dbHealth={orchStatus?.runtime_dependencies?.database as Record<string,any> | undefined}
        />

        <Tabs
          defaultActiveKey="control"
          size="small"
          style={{ marginTop: 8 }}
          items={[
            {
              key: "control",
              label: "控制台",
              children: (
                <div style={{ display: "grid", gridTemplateColumns: "420px 1fr", gap: 12 }}>
                  <CollectionControlPanel
                    status={controlStatus}
                    busy={controlBusy}
                    toggles={controlToggles}
                    actions={{
                      onStartRealtime: handleStart, onStopRealtime: handleStop, onRefreshRealtime: handleRefresh,
                      onStartDom: handleStartJyhfCdp, onStopDom: handleStopJyhfCdp, onRefreshDom: handleRefreshJyhfCdp,
                      onToggleAuction: setAuctionEnabled, onToggleKlineAlerts: setKlineAlertsEnabled, onToggleW2sAlerts: setW2sAlertsEnabled,
                    }}
                  />
                  <UnifiedAlertPanel
                    alerts={unifiedAlerts}
                    onClear={() => { setKlineAlerts([]); setW2sAlerts([]); }}
                  />
                </div>
              ),
            },
            {
              key: "orchestrator",
              label: "自动编排",
              children: (
                <OrchestratorStatusPanel
                  status={orchStatus}
                  loading={orchLoading}
                  error={orchError}
                  onRefresh={refreshOrchestrator}
                />
              ),
            },
            {
              key: "health",
              label: "运行健康",
              children: (
                <Tabs size="small" defaultActiveKey="infra" items={[
                  {
                    key: "infra",
                    label: "基础设施",
                    children: (
                      <OrchestratorStatusPanel
                        status={orchStatus}
                        loading={orchLoading}
                        error={orchError}
                        onRefresh={refreshOrchestrator}
                      />
                    ),
                  },
                  {
                    key: "dataflow",
                    label: "数据流",
                    children: (
                      <DiagnosticsTabs
                        mergedLogs={[]} jyhfLogs={[]} stackStatus={stackStatus}
                        reviewItems={[]} reviewTotal={0} reviewBusy={false}
                        selectedIds={new Set()} onToggleSelect={()=>{}} onSelectAll={()=>{}}
                        onConfirm={async()=>{}} onDelete={async()=>{}} onBatchDelete={async()=>{}}
                        onImportPending={async()=>{}} onClearPending={async()=>{}}
                        onRefreshReview={async()=>{}} onOpenDetail={()=>{}}
                      />
                    ),
                  },
                  {
                    key: "logs",
                    label: "日志",
                    children: (
                      <div className="collection-log-panel" style={{ maxHeight: 400, overflow: "auto", fontFamily: "monospace", fontSize: 12, lineHeight: 1.6, color: "#94a3b8" }}>
                        {mergedLogs.length === 0 ? <div style={{ color: "#64748b" }}>暂无日志</div>
                          : mergedLogs.slice(-200).map((line, i) => <div key={i}>{line}</div>)}
                      </div>
                    ),
                  },
                  {
                    key: "review",
                    label: "Review Queue",
                    children: (
                      <DiagnosticsTabs
                        mergedLogs={[]} jyhfLogs={[]} stackStatus={null}
                        reviewItems={reviewItems} reviewTotal={reviewTotal}
                        reviewBusy={reviewBusy} selectedIds={selectedIds}
                        onToggleSelect={toggleSelect} onSelectAll={selectAll}
                        onConfirm={handleConfirmReview} onDelete={handleDeleteReview}
                        onBatchDelete={handleBatchDelete} onImportPending={handleImportPending}
                        onClearPending={handleClearPending} onRefreshReview={refreshReviewQueue}
                        onOpenDetail={(item: ReviewQueueItem) => openDetail(item.id)}
                      />
                    ),
                  },
                ]} />
              ),
            },
          ]}
        />

      </div>
      </ConfigProvider>

      {/* ── 复核详情 Modal (保留原有实现) ── */}
      {detailOpen && detailItem && (
        <div className="collection-modal-backdrop" onClick={closeDetail}>
          <div className="collection-modal" style={{ border: "1px solid #334155", padding: 20, borderRadius: 12, maxWidth: 700, maxHeight: "90vh", overflow: "auto" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <span className="section-title">复核详情 #{detailItem.id}</span>
              <span style={{ fontSize: 12, color: "#64748b" }}>{detailItem.review_status}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <section className="collection-section">
                <strong>事件信息</strong>
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
                  {detailItem.reviewed_at && <div><label className="collection-field">审核时间</label><span>{detailItem.reviewed_at}</span></div>}
                  {detailItem.review_note && <div><label className="collection-field">备注</label><span>{detailItem.review_note}</span></div>}
                </div>
              </section>
            </div>
            <div className="collection-action-row" style={{ marginTop: 16 }}>
              <button type="button" className="tag tag-button"
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
