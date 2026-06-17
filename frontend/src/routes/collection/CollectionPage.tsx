import { useEffect, useMemo, useRef, useState } from "react";
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
import collectionIcon from "../../assets/intel-icons/采集控制台.png";

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
      return "数据为空";
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
  const [lastPollAt, setLastPollAt] = useState<string>("--");
  const logPanelRef = useRef<HTMLDivElement | null>(null);

  const [options, setOptions] = useState({
    stockSnapshot: {
      enabled: true,
      provider: "jyhf" as "jyhf" | "tushare_join",
      onExisting: "skip" as "skip" | "upsert" | "replace",
    },
    subjectRank: {
      enabled: false,
      provider: "jyhf" as "jyhf" | "snapshot_agg",
      onExisting: "skip" as "skip" | "upsert" | "replace",
    },
    tushareDailyBasic: false,
    tushareKline: true,
    auction: false,
    f10Capital: false,
    dragonTiger: true,
    indexKline: true,
  });

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
          setLastPollAt(new Date().toLocaleTimeString("zh-CN"));
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

  useEffect(() => {
    const panel = logPanelRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [job?.logs]);

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
          stock_snapshot: options.stockSnapshot.enabled
            ? {
                provider: options.stockSnapshot.provider,
                on_existing: options.stockSnapshot.onExisting,
                force: false,
              }
            : false,
          subject_rank: options.subjectRank.enabled
            ? {
                provider: options.subjectRank.provider,
                on_existing: options.subjectRank.onExisting,
                force: false,
              }
            : false,
          jyhf_history: false,
          tushare_daily_basic: options.tushareDailyBasic,
          tushare_kline: options.tushareKline,
          auction: options.auction,
          f10_capital: options.f10Capital,
          dragon_tiger: options.dragonTiger,
          index_kline: options.indexKline,
          auto_build_v2_if_missing: false,
        },
        tushare_pause_seconds: 0.1,
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
      await cancelCollection(job.job_id);
      // 取消 = 完全停止 + 恢复初始状态（等同于重置）
      handleReset();
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
      if (payload.status === "running") {
        setJob(payload);
      } else {
        // 任务未进入运行状态（可能 can_continue=false），回退到重置
        setErrorState({
          step: "继续任务",
          message: "任务无法继续，请重置后重新开始",
          detail: "后端返回状态: " + (payload.status || "未知"),
        });
      }
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
      <section className="strong-watch-toolbar">
        <img src={collectionIcon} alt="" style={{ height: 64, width: 64, flexShrink: 0 }} />
        <h1 className="strong-watch-title">采集控制</h1>
        <button
          className="tag tag-button"
          type="button"
          style={{ fontSize: 16, padding: "8px 16px", marginLeft: "auto" }}
          onClick={handleReset}
          title="清除缓存并重置页面状态，用于从异常中恢复"
        >
          重置页面
        </button>
        <button className="back-button" type="button" onClick={() => navigateTo(`/?date=${tradeDate}`)}>
          返回
        </button>
      </section>

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

            {/* ── Tushare daily_basic 换手率采集 ── */}
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.tushareDailyBasic}
                onChange={() => setOptions((s) => ({ ...s, tushareDailyBasic: !s.tushareDailyBasic }))}
              />
              <span>Tushare daily_basic 换手率采集</span>
            </label>

            {/* ── Tushare 日K线（基础数据层，必须最先执行）── */}
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.tushareKline}
                onChange={() => setOptions((s) => ({ ...s, tushareKline: !s.tushareKline }))}
              />
              <span>Tushare 日K线</span>
            </label>

            {/* ── 盘前竞价采集（可选增强链路）── */}
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.auction}
                onChange={() => setOptions((s) => ({ ...s, auction: !s.auction }))}
              />
              <span>盘前竞价采集</span>
            </label>

            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.f10Capital}
                onChange={() => setOptions((s) => ({ ...s, f10Capital: !s.f10Capital }))}
              />
              <span>F10资金动向采集</span>
            </label>
            <div className="workspace-note">
              自动从当日复盘候选池提取股票，专项采集资金动向快照，不参与评分。
            </div>

            {/* ── 股票快照（可插拔数据源）── */}
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.stockSnapshot.enabled}
                onChange={() =>
                  setOptions((s) => ({
                    ...s,
                    stockSnapshot: { ...s.stockSnapshot, enabled: !s.stockSnapshot.enabled },
                  }))
                }
              />
              <span>股票快照</span>
            </label>

            {options.stockSnapshot.enabled && (
              <div className="collection-sub-group">
                {/* 第一层：数据源选择 */}
                <div className="collection-radio-group">
                  <span className="collection-sub-label">股票快照数据源</span>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="snapshot-provider"
                      value="jyhf"
                      checked={options.stockSnapshot.provider === "jyhf"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          stockSnapshot: { ...s.stockSnapshot, provider: "jyhf" },
                        }))
                      }
                    />
                    <span>久赢恒丰 API（默认）</span>
                  </label>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="snapshot-provider"
                      value="tushare_join"
                      checked={options.stockSnapshot.provider === "tushare_join"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          stockSnapshot: { ...s.stockSnapshot, provider: "tushare_join" },
                        }))
                      }
                    />
                    <span>Tushare 日K拼接</span>
                  </label>
                </div>

                {options.stockSnapshot.provider === "tushare_join" && (
                  <p className="collection-hint">
                    Tushare 拼接模式要求当日 stock_daily_snapshot 已存在。
                    如果不存在，请先执行 Tushare 日K线采集，或在后端启用 auto_run_daily_bar。
                  </p>
                )}

                {/* 第二层：已有数据处理策略 */}
                <div className="collection-radio-group">
                  <span className="collection-sub-label">重建策略</span>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="snapshot-on-existing"
                      value="skip"
                      checked={options.stockSnapshot.onExisting === "skip"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          stockSnapshot: { ...s.stockSnapshot, onExisting: "skip" },
                        }))
                      }
                    />
                    <span>跳过已有数据（默认）</span>
                  </label>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="snapshot-on-existing"
                      value="upsert"
                      checked={options.stockSnapshot.onExisting === "upsert"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          stockSnapshot: { ...s.stockSnapshot, onExisting: "upsert" },
                        }))
                      }
                    />
                    <span>覆盖已有行</span>
                  </label>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="snapshot-on-existing"
                      value="replace"
                      checked={options.stockSnapshot.onExisting === "replace"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          stockSnapshot: { ...s.stockSnapshot, onExisting: "replace" },
                        }))
                      }
                    />
                    <span>删除后重建</span>
                  </label>
                </div>
              </div>
            )}

            {/* ── 题材热度排名（可插拔数据源）── */}
            <label className="collection-check">
              <input
                type="checkbox"
                checked={options.subjectRank.enabled}
                onChange={() =>
                  setOptions((s) => ({
                    ...s,
                    subjectRank: { ...s.subjectRank, enabled: !s.subjectRank.enabled },
                  }))
                }
              />
              <span>题材热度排名</span>
            </label>

            {options.subjectRank.enabled && (
              <div className="collection-sub-group">
                <div className="collection-radio-group">
                  <span className="collection-sub-label">热度排名数据源</span>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="rank-provider"
                      value="jyhf"
                      checked={options.subjectRank.provider === "jyhf"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          subjectRank: { ...s.subjectRank, provider: "jyhf" },
                        }))
                      }
                    />
                    <span>久赢恒丰 API（默认）</span>
                  </label>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="rank-provider"
                      value="snapshot_agg"
                      checked={options.subjectRank.provider === "snapshot_agg"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          subjectRank: { ...s.subjectRank, provider: "snapshot_agg" },
                        }))
                      }
                    />
                    <span>快照聚合（从 subject_stock_daily_snapshot）</span>
                  </label>
                </div>

                {options.subjectRank.provider === "snapshot_agg" && (
                  <p className="collection-hint">
                    快照聚合模式要求当日 subject_stock_daily_snapshot 已存在。
                    请确保股票快照任务已先执行。
                  </p>
                )}

                <div className="collection-radio-group">
                  <span className="collection-sub-label">重建策略</span>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="rank-on-existing"
                      value="skip"
                      checked={options.subjectRank.onExisting === "skip"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          subjectRank: { ...s.subjectRank, onExisting: "skip" },
                        }))
                      }
                    />
                    <span>跳过已有数据（默认）</span>
                  </label>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="rank-on-existing"
                      value="upsert"
                      checked={options.subjectRank.onExisting === "upsert"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          subjectRank: { ...s.subjectRank, onExisting: "upsert" },
                        }))
                      }
                    />
                    <span>覆盖已有行</span>
                  </label>
                  <label className="collection-radio">
                    <input
                      type="radio"
                      name="rank-on-existing"
                      value="replace"
                      checked={options.subjectRank.onExisting === "replace"}
                      onChange={() =>
                        setOptions((s) => ({
                          ...s,
                          subjectRank: { ...s.subjectRank, onExisting: "replace" },
                        }))
                      }
                    />
                    <span>删除后重建</span>
                  </label>
                </div>
              </div>
            )}

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
                checked={options.indexKline}
                onChange={() => setOptions((s) => ({ ...s, indexKline: !s.indexKline }))}
              />
              <span>指数采集</span>
            </label>
          </div>

          <div className="collection-action-row">
            <button
              type="button"
              className="tag tag-button tag-active"
              onClick={handleStart}
              disabled={loading || job?.status === "running"}
            >
              开始采集
            </button>
            <button type="button" className="tag tag-button" onClick={() => navigateTo(`/recap?date=${tradeDate}&report_type=post_market`)}>
              前往当日复盘 →
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
              {(job?.tasks ?? []).filter((task: any) => {
                const key = String(task.key || task.title || "").toLowerCase();
                const forbidden = ["recap", "daily_review", "post_market", "strong_stock", "derived", "snapshot_generate"];
                return !forbidden.some((p) => key.includes(p));
              }).map((task) => (
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
            <span style={{marginLeft:12,fontSize:11,color:lastPollAt==="--"?"#e67e22":"#27ae60"}}>
              上次轮询: {lastPollAt}
            </span>
            <div className="collection-log-panel collection-debug-terminal" ref={logPanelRef}>
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
