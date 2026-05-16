import { useEffect, useMemo, useState } from "react";
import {
  cancelCollection,
  continueCollection,
  fetchCollectionAvailability,
  fetchCollectionStatus,
  startCollection,
  type CollectionAvailability,
  type CollectionJobStatus,
  type CollectionTaskItem,
} from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

const COLLECTION_JOB_STORAGE_KEY = "collection:latest-job";

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

function timeText(value: string) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function statusLabel(status: CollectionTaskItem["status"] | CollectionJobStatus["status"]) {
  switch (status) {
    case "running":
      return "运行中";
    case "success":
      return "成功";
    case "skipped":
      return "已跳过";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
    case "paused":
      return "暂停";
    default:
      return "等待中";
  }
}

function loadPersistedJob(): CollectionJobStatus | null {
  try {
    const raw = window.localStorage.getItem(COLLECTION_JOB_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as CollectionJobStatus;
  } catch {
    return null;
  }
}

function persistJob(job: CollectionJobStatus | null) {
  try {
    if (!job) {
      window.localStorage.removeItem(COLLECTION_JOB_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(COLLECTION_JOB_STORAGE_KEY, JSON.stringify(job));
  } catch {
    // Ignore storage failures so collection UI still works in restricted browsers.
  }
}

export function CollectionPage() {
  const [tradeDate, setTradeDate] = useState(todayString());
  const [availability, setAvailability] = useState<CollectionAvailability | null>(null);
  const [job, setJob] = useState<CollectionJobStatus | null>(() => loadPersistedJob());
  const [errorState, setErrorState] = useState<{ step: string; message: string; detail: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const [options, setOptions] = useState({
    jyhf: true,
    jyhfHistory: false,
    tushareKline: true,
    dragonTiger: true,
    abnormalSignal: true,
    strongStockWatch: true,
    leaderLlm: true,
    recapSnapshot: true,
    autoBuildV2IfMissing: true,
  });
  const [abnormalFilters, setAbnormalFilters] = useState({
    turnoverRate: true,
    mainNetInflow: true,
    hotMoneyBuy: true,
    institutionBuy: true,
    tailRush: false,
  });
  const [minTurnoverRate, setMinTurnoverRate] = useState("3.0");
  const [minCompositeScore, setMinCompositeScore] = useState("40");

  const totalSteps = job?.total_steps ?? 0;
  const completedSteps = job?.completed_steps ?? 0;
  const failedSteps = useMemo(
    () => (job?.tasks ?? []).filter((item) => item.status === "failed").length,
    [job],
  );
  const progressPercent = job?.progress_percent ?? 0;

  useEffect(() => {
    fetchCollectionAvailability(tradeDate)
      .then(setAvailability)
      .catch((err: Error) =>
        setErrorState({
          step: "可用性检查",
          message: err.message,
          detail: "无法获取采集窗口状态，请稍后重试。",
        }),
      );
  }, [tradeDate]);

  useEffect(() => {
    persistJob(job);
  }, [job]);

  useEffect(() => {
    const persisted = loadPersistedJob();
    if (!persisted?.job_id) return;
    fetchCollectionStatus(persisted.job_id)
      .then((data) => {
        setJob(data);
        if (data.last_error) {
          setErrorState({
            step: data.last_error.step,
            message: data.last_error.message,
            detail: data.last_error.detail || "",
          });
        }
      })
      .catch((err: Error) => {
        setJob(null);
        persistJob(null);
        const message = err.message.includes("404") ? "历史任务已失效" : err.message;
        setErrorState({
          step: "恢复任务状态",
          message,
          detail: err.message.includes("404") ? "后台任务已不存在，本地缓存已清理。" : "无法恢复上次任务状态，请检查 BFF 服务。",
        });
      });
  }, []);

  useEffect(() => {
    if (!job?.job_id || job.status !== "running") return;
    const timer = window.setInterval(() => {
      fetchCollectionStatus(job.job_id)
        .then((data) => {
          setJob(data);
          if (data.last_error) {
            setErrorState({
              step: data.last_error.step,
              message: data.last_error.message,
              detail: data.last_error.detail || "",
            });
          }
        })
        .catch((err: Error) =>
          setErrorState({
            step: "状态轮询",
            message: err.message,
            detail: "无法获取任务状态，请检查 BFF 服务。",
          }),
        );
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  async function handleStart() {
    if (!isHistoricalTradeDate(tradeDate) && !availability?.allowed) {
      setErrorState({
        step: "启动前校验",
        message: availability?.message || "当前交易日暂不可采集",
        detail: "历史交易日可直接补采；仅当天数据受 16:30 时间窗口限制。",
      });
      return;
    }
    setLoading(true);
    setErrorState(null);
    try {
      const payload = await startCollection({
        trade_date: tradeDate,
        options: {
          jyhf: options.jyhf,
          jyhf_history: options.jyhfHistory,
          tushare_kline: options.tushareKline,
          dragon_tiger: options.dragonTiger,
          abnormal_signal: options.abnormalSignal,
          strong_stock_watch: options.strongStockWatch,
          leader_llm: options.leaderLlm,
          recap_snapshot: options.recapSnapshot,
          auto_build_v2_if_missing: options.autoBuildV2IfMissing,
        },
        tushare_pause_seconds: 0.1,
        abnormal_filters: {
          turnover_rate: abnormalFilters.turnoverRate,
          main_net_inflow: abnormalFilters.mainNetInflow,
          hot_money_buy: abnormalFilters.hotMoneyBuy,
          institution_buy: abnormalFilters.institutionBuy,
          tail_rush: abnormalFilters.tailRush,
        },
        min_turnover_rate: Number(minTurnoverRate),
        min_composite_score: Number(minCompositeScore),
      });
      setJob(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "启动采集失败";
      setErrorState({
        step: "启动采集",
        message,
        detail: "请检查服务端日志或确认当前采集时段是否可用。",
      });
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    window.localStorage.removeItem(COLLECTION_JOB_STORAGE_KEY);
    setJob(null);
    setErrorState(null);
    // 重新检查采集窗口状态
    fetchCollectionAvailability(tradeDate)
      .then(setAvailability)
      .catch(() => {});
  }

  async function handleCancel() {
    if (!job?.job_id) return;
    try {
      const payload = await cancelCollection(job.job_id);
      setJob(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "取消失败";
      setErrorState({
        step: "取消任务",
        message,
        detail: "任务取消请求未成功提交。",
      });
    }
  }

  async function handleContinue() {
    if (!job?.job_id) return;
    setErrorState(null);
    try {
      const payload = await continueCollection(job.job_id);
      setJob(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "继续失败";
      setErrorState({
        step: "继续任务",
        message,
        detail: "任务恢复请求未成功提交。",
      });
    }
  }

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo(`/?date=${tradeDate}`)}>
          返回情报台
        </button>
        <div>
          <p className="eyebrow">Collection Workspace</p>
          <h1>日采集控制台</h1>
          <p className="subtle">16:30后执行日采集与盘后复盘更新。当前页面已接入后台任务状态机。</p>
          <div className="collection-action-row">
            <button className="tag tag-button" type="button" onClick={() => navigateTo("/realtime-collector")}>
              打开实时采集控制台
            </button>
            <button className="tag tag-button" type="button" onClick={() => navigateTo("/collection-debug")}>
              打开终端调试页
            </button>
            <button
              className="tag tag-button"
              type="button"
              onClick={handleReset}
              title="清除缓存并重置页面状态，用于从异常中恢复"
            >
              重置页面
            </button>
          </div>
        </div>
      </header>

      <section className={`workspace-card collection-guard ${availability?.allowed ? "is-open" : "is-locked"}`}>
        <div>
          <span className="metric-label section-title">采集窗口状态</span>
          <strong>{availability?.allowed ? "可启动日采集" : "未到采集时段"}</strong>
          <p className="workspace-note">
            当前时间 {availability ? timeText(availability.server_time) : "--"}，
            {availability?.message ?? "正在检查采集窗口状态..."}
          </p>
        </div>
        <span className={`collection-status-chip ${availability?.allowed ? "is-open" : "is-locked"}`}>
          {availability?.allowed ? "OPEN" : "LOCKED"}
        </span>
      </section>

      <main className="collection-grid">
        <section className="workspace-card collection-config-card">
          <span className="metric-label section-title">采集配置</span>

          <label className="recap-toolbar-date">
            <span>交易日</span>
            <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
          </label>

          <div className="collection-section">
            <strong>数据源</strong>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.jyhf}
                onChange={() => setOptions((s) => ({ ...s, jyhf: !s.jyhf }))}
              />
              <span>股票快照</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.jyhfHistory}
                onChange={() => setOptions((s) => ({ ...s, jyhfHistory: !s.jyhfHistory }))}
              />
              <span>题材事件集中采集</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.tushareKline}
                onChange={() => setOptions((s) => ({ ...s, tushareKline: !s.tushareKline }))}
              />
              <span>Tushare 日K线（含盘前竞价采集）</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.dragonTiger}
                onChange={() => setOptions((s) => ({ ...s, dragonTiger: !s.dragonTiger }))}
              />
              <span>龙虎榜</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.abnormalSignal}
                onChange={() => setOptions((s) => ({ ...s, abnormalSignal: !s.abnormalSignal }))}
              />
              <span>异动股票数据</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.strongStockWatch}
                onChange={() => setOptions((s) => ({ ...s, strongStockWatch: !s.strongStockWatch }))}
              />
              <span>强势股跟踪池</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.leaderLlm}
                onChange={() => setOptions((s) => ({ ...s, leaderLlm: !s.leaderLlm }))}
              />
              <span>龙头候选LLM裁决</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.recapSnapshot}
                onChange={() => setOptions((s) => ({ ...s, recapSnapshot: !s.recapSnapshot }))}
              />
              <span>盘后复盘快照生成</span>
            </label>
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.autoBuildV2IfMissing}
                onChange={() => setOptions((s) => ({ ...s, autoBuildV2IfMissing: !s.autoBuildV2IfMissing }))}
              />
              <span>v2周期缺失时自动补建</span>
            </label>
          </div>

          <div className="collection-section">
            <strong>异动过滤</strong>
            <div className="collection-check-grid">
              <label className="collection-check">
                <input
                  type="checkbox"
                  checked={abnormalFilters.turnoverRate}
                  onChange={() => setAbnormalFilters((s) => ({ ...s, turnoverRate: !s.turnoverRate }))}
                />
                <span>换手率</span>
              </label>
              <label className="collection-check">
                <input
                  type="checkbox"
                  checked={abnormalFilters.mainNetInflow}
                  onChange={() => setAbnormalFilters((s) => ({ ...s, mainNetInflow: !s.mainNetInflow }))}
                />
                <span>资金流入</span>
              </label>
              <label className="collection-check">
                <input
                  type="checkbox"
                  checked={abnormalFilters.hotMoneyBuy}
                  onChange={() => setAbnormalFilters((s) => ({ ...s, hotMoneyBuy: !s.hotMoneyBuy }))}
                />
                <span>游资买入</span>
              </label>
              <label className="collection-check">
                <input
                  type="checkbox"
                  checked={abnormalFilters.institutionBuy}
                  onChange={() => setAbnormalFilters((s) => ({ ...s, institutionBuy: !s.institutionBuy }))}
                />
                <span>机构买入</span>
              </label>
              <label className="collection-check">
                <input
                  type="checkbox"
                  checked={abnormalFilters.tailRush}
                  onChange={() => setAbnormalFilters((s) => ({ ...s, tailRush: !s.tailRush }))}
                />
                <span>尾盘抢筹</span>
              </label>
            </div>
          </div>

          <div className="collection-parameter-grid">
            <label className="collection-field">
              <span>最小换手率</span>
              <input value={minTurnoverRate} onChange={(e) => setMinTurnoverRate(e.target.value)} />
            </label>
            <label className="collection-field">
              <span>最小综合分</span>
              <input value={minCompositeScore} onChange={(e) => setMinCompositeScore(e.target.value)} />
            </label>
          </div>

          <div className="collection-action-row">
            <button type="button" className="tag tag-button tag-active" onClick={handleStart} disabled={loading || job?.status === "running"}>
              开始采集
            </button>
            <button type="button" className="tag tag-button" onClick={handleCancel} disabled={!job?.can_cancel}>
              取消
            </button>
            <button type="button" className="tag tag-button" onClick={handleContinue} disabled={!job?.can_continue}>
              继续
            </button>
          </div>
        </section>

        <section className="collection-main-column">
          <section className="workspace-card collection-summary-card">
            <span className="metric-label section-title">执行总览</span>
            <div className="collection-summary-grid">
              <article className="collection-metric-card">
                <span>总任务数</span>
                <strong>{totalSteps}</strong>
              </article>
              <article className="collection-metric-card">
                <span>已完成</span>
                <strong>{completedSteps}</strong>
              </article>
              <article className="collection-metric-card">
                <span>失败数</span>
                <strong>{failedSteps}</strong>
              </article>
              <article className="collection-metric-card">
                <span>当前状态</span>
                <strong>{statusLabel(job?.status ?? "idle")}</strong>
              </article>
            </div>
            <div className="collection-progress-panel">
              <div className="collection-progress-head">
                <strong>总进度</strong>
                <span>{progressPercent}%</span>
              </div>
              <div className="collection-progress-bar">
                <span style={{ width: `${progressPercent}%` }} />
              </div>
            </div>
          </section>

          <section className="workspace-card">
            <span className="metric-label section-title">任务进度</span>
            <div className="collection-task-list">
              {(job?.tasks ?? []).map((task) => (
                <article className="collection-task-card" key={task.key} data-status={task.status}>
                  <div className="collection-task-head">
                    <div>
                      <strong>{task.title}</strong>
                      <p className="workspace-note">{task.current_label || "--"}</p>
                    </div>
                    <span className={`collection-task-chip is-${task.status}`}>{statusLabel(task.status)}</span>
                  </div>
                  <div className="collection-progress-bar compact">
                    <span style={{ width: `${task.progress_percent}%` }} />
                  </div>
                  <div className="collection-task-foot">
                    <span>{task.error_message || "--"}</span>
                    <span>{task.progress_percent}%</span>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="workspace-card">
            <span className="metric-label section-title">运行日志</span>
            <div className="collection-log-panel">
              {(job?.logs ?? ["[等待中] 尚未启动采集任务。"]).map((line, idx) => (
                <div className="collection-log-line" key={`log-${idx}`}>{line}</div>
              ))}
            </div>
          </section>
        </section>
      </main>

      {errorState && (
        <div className="collection-modal-backdrop">
          <div className="collection-modal">
            <span className="metric-label section-title">采集执行异常</span>
            <h3>{errorState.step}</h3>
            <p>{errorState.message}</p>
            <p className="workspace-note">{errorState.detail}</p>
            {!job?.can_cancel && !job?.can_continue && (
              <p className="workspace-note" style={{marginTop:8, color:"var(--color-warning, #e67e22)"}}>
                当前任务无法取消也無法繼續，请点击 "重置页面" 清除缓存后重新开始。
              </p>
            )}
            <div className="collection-action-row">
              {job?.can_cancel && (
                <button type="button" className="tag tag-button" onClick={handleCancel}>
                  取消任务
                </button>
              )}
              {job?.can_continue && (
                <button type="button" className="tag tag-button tag-active" onClick={handleContinue}>
                  从失败处继续
                </button>
              )}
              <button type="button" className="tag tag-button" onClick={() => setErrorState(null)}>
                关闭
              </button>
              <button
                type="button"
                className="tag tag-button"
                style={{borderColor:"var(--color-warning, #e67e22)", color:"var(--color-warning, #e67e22)"}}
                onClick={handleReset}
              >
                重置页面
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
