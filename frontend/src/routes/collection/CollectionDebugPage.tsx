import { useEffect, useRef, useState } from "react";
import {
  cancelCollection,
  fetchCollectionAvailability,
  fetchCollectionStatus,
  startCollection,
  type CollectionAvailability,
  type CollectionJobStatus,
} from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

const STORAGE_KEY = "collection:debug:job-id";

function nowText() {
  return new Date().toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function todayString() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function isHistoricalTradeDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && value < todayString();
}

function statusLabel(status?: string) {
  if (!status) return "idle";
  return status;
}

function loadJobId() {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function saveJobId(jobId?: string | null) {
  try {
    if (!jobId) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, jobId);
  } catch {
    // noop
  }
}

export function CollectionDebugPage() {
  const [tradeDate, setTradeDate] = useState(todayString());
  const [availability, setAvailability] = useState<CollectionAvailability | null>(null);
  const [job, setJob] = useState<CollectionJobStatus | null>(null);
  const [jobId, setJobId] = useState<string | null>(() => loadJobId());
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [autoBuildV2IfMissing, setAutoBuildV2IfMissing] = useState(true);
  const [f10Capital, setF10Capital] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  function appendLog(line: string) {
    setLogs((prev) => {
      const next = [...prev, `[${nowText()}] ${line}`];
      return next.slice(-400);
    });
  }

  useEffect(() => {
    appendLog("调试页已加载");
  }, []);

  useEffect(() => {
    fetchCollectionAvailability(tradeDate)
      .then((data) => {
        setAvailability(data);
      })
      .catch((err: Error) => {
        appendLog(`获取可用性失败: ${err.message}`);
      });
  }, [tradeDate]);

  useEffect(() => {
    if (!jobId) return;
    fetchCollectionStatus(jobId)
      .then((data) => {
        setJob(data);
        appendLog(`恢复任务成功: ${data.job_id} (${statusLabel(data.status)})`);
      })
      .catch((err: Error) => {
        appendLog(`恢复任务失败: ${err.message}`);
      });
  }, [jobId]);

  useEffect(() => {
    if (!job?.job_id) return;
    if (job.status !== "running") return;
    const timer = window.setInterval(() => {
      fetchCollectionStatus(job.job_id)
        .then((data) => {
          setJob(data);
        })
        .catch((err: Error) => {
          appendLog(`状态轮询失败: ${err.message}`);
        });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (!job) return;
    saveJobId(job.job_id);
  }, [job]);

  useEffect(() => {
    const panel = logRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [logs, job?.logs]);

  async function handleStart() {
    if (!isHistoricalTradeDate(tradeDate) && !availability?.allowed) {
      appendLog(`当前不可启动: ${availability?.message ?? "采集窗口未开放"}`);
      return;
    }
    setLoading(true);
    appendLog(`准备启动采集: trade_date=${tradeDate}`);
    try {
      const payload = await startCollection({
        trade_date: tradeDate,
        options: {
          jyhf: true,
          jyhf_history: false,
          tushare_kline: true,
          dragon_tiger: true,
          f10_capital: f10Capital,
          abnormal_signal: true,
          leader_llm: true,
          recap_snapshot: true,
          auto_build_v2_if_missing: autoBuildV2IfMissing,
        },
        tushare_pause_seconds: 0.1,
        abnormal_filters: {
          turnover_rate: true,
          main_net_inflow: true,
          hot_money_buy: true,
          institution_buy: true,
          tail_rush: false,
        },
        min_turnover_rate: 3,
        min_composite_score: 40,
      });
      setJob(payload);
      setJobId(payload.job_id);
      appendLog(`启动成功: job_id=${payload.job_id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "启动失败";
      appendLog(`启动失败: ${message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleStop() {
    if (!job?.job_id) {
      appendLog("无活动任务可停止");
      return;
    }
    appendLog(`请求停止任务: ${job.job_id}`);
    try {
      const payload = await cancelCollection(job.job_id);
      setJob(payload);
      appendLog(`停止完成: status=${payload.status}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "停止失败";
      appendLog(`停止失败: ${message}`);
    }
  }

  async function handleRefresh() {
    if (!job?.job_id) {
      appendLog("无任务可刷新");
      return;
    }
    try {
      const payload = await fetchCollectionStatus(job.job_id);
      setJob(payload);
      appendLog(`手动刷新成功: status=${payload.status}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "刷新失败";
      appendLog(`手动刷新失败: ${message}`);
    }
  }

  const mergedLogs = [...logs, ...(job?.logs ?? []).map((line) => `[job] ${line}`)];

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/collection")}>
          返回采集控制台
        </button>
        <div>
          <p className="eyebrow">Collection Debug Console</p>
          <h1>日采集终端调试页</h1>
          <p className="subtle">用于启动/停止日采集任务、实时查看任务日志和原始状态JSON。</p>
        </div>
      </header>

      <main className="collection-debug-grid">
        <section className="workspace-card collection-debug-control">
          <span className="metric-label section-title">控制面板</span>
          <label className="collection-field">
            <span>交易日</span>
            <input type="date" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} />
          </label>
          <div className="workspace-note">
            采集窗口: {availability?.allowed ? "OPEN" : "LOCKED"} / {availability?.message ?? "--"}
          </div>
          <label className="collection-check">
            <input
              type="checkbox"
              checked={autoBuildV2IfMissing}
              onChange={() => setAutoBuildV2IfMissing((s) => !s)}
            />
            <span>v2周期缺失时自动补建</span>
          </label>
          <label className="collection-check">
            <input
              type="checkbox"
              checked={f10Capital}
              onChange={() => setF10Capital((s) => !s)}
            />
            <span>F10资金动向采集</span>
          </label>
          <div className="workspace-note">
            顺序执行到该 step 时自动从当日复盘候选池提取股票，专项采集资金动向快照，不参与评分。
            如需自动解析候选池，请先执行能生成当日候选池的前置任务，例如股票快照/题材热度排名。
          </div>
          <div className="collection-action-row">
            <button
              type="button"
              className="tag tag-button tag-active"
              onClick={handleStart}
              disabled={loading}
            >
              启动采集
            </button>
            <button type="button" className="tag tag-button" onClick={handleStop}>
              停止采集
            </button>
            <button type="button" className="tag tag-button" onClick={handleRefresh}>
              刷新状态
            </button>
          </div>
          <div className="collection-debug-status">
            <div>
              <span className="metric-label">Job ID</span>
              <strong>{job?.job_id ?? "--"}</strong>
            </div>
            <div>
              <span className="metric-label">状态</span>
              <strong>{statusLabel(job?.status)}</strong>
            </div>
            <div>
              <span className="metric-label">进度</span>
              <strong>{job?.progress_percent ?? 0}%</strong>
            </div>
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">终端日志</span>
          <div className="collection-log-panel collection-debug-terminal" ref={logRef}>
            {(mergedLogs.length ? mergedLogs : ["[等待中] 尚未产生调试日志。"]).map((line, idx) => (
              <div className="collection-log-line" key={`terminal-${idx}`}>{line}</div>
            ))}
          </div>
        </section>

        <section className="workspace-card">
          <span className="metric-label section-title">任务原始JSON</span>
          <pre className="collection-debug-json">
            {job ? JSON.stringify(job, null, 2) : "{\n  \"job\": null\n}"}
          </pre>
        </section>
      </main>
    </div>
  );
}
