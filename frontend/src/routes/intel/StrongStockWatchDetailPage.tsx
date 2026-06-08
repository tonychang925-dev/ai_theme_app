import { useMemo } from "react";
import { fetchStrongStockWatch } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import { navigateTo } from "../../lib/navigation";

function qp() {
  return new URLSearchParams(window.location.search);
}

function fmtPct(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const num = Number(value);
  return `${num > 0 ? "+" : ""}${num.toFixed(2)}%`;
}

function fmtNum(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export function StrongStockWatchDetailPage() {
  const stockId = qp().get("stock_id") || "";
  const date = qp().get("date") || new Date().toISOString().slice(0, 10);
  const windowDaysRaw = Number(qp().get("window_days") || "7");
  const windowDays = Number.isFinite(windowDaysRaw) && windowDaysRaw > 0 ? windowDaysRaw : 7;

  const fetcher = useMemo(
    () => () =>
      fetchStrongStockWatch({
        stockId,
        date,
        windowDays,
        includeRemoved: true,
        latestPerStock: false,
        limit: 200,
      }),
    [stockId, date, windowDays],
  );
  const { data, loading, error } = useApi(fetcher, { immediate: true, deps: [stockId, date, windowDays] });
  const rows = data?.items ?? [];
  const latest = rows[0];

  return (
    <div className="workspace-page strong-watch-detail-page">
      <header className="workspace-header">
        <button
          type="button"
          className="back-button"
          onClick={() => navigateTo(`/intel/strong-stocks/watch?date=${date}&window_days=${windowDays}`)}
        >
          返回跟踪页
        </button>
        <h1>强势股跟踪详情</h1>
      </header>

      {loading && <div className="empty-state">加载详情中...</div>}
      {!loading && error && <div className="empty-state error">{error}</div>}
      {!loading && !error && !latest && <div className="empty-state">未找到该股票跟踪记录</div>}

      {!loading && !error && latest && (
        <>
          <section className="workspace-card">
            <span className="metric-label section-title">基础信息</span>
            <div className="strong-watch-detail-grid">
              <article className="collection-metric-card">
                <span>股票</span>
                <strong>{latest.stock_name || latest.stock_id || "--"}</strong>
              </article>
              <article className="collection-metric-card">
                <span>题材</span>
                <strong>{latest.theme_name || latest.subject_key || "--"}</strong>
                <p className="workspace-note">{latest.subject_key || "--"}</p>
              </article>
              <article className="collection-metric-card">
                <span>当前状态</span>
                <strong>{latest.watch_status}</strong>
                <p className="workspace-note">池内类型 {latest.pool_entry_type || "--"}</p>
              </article>
              <article className="collection-metric-card">
                <span>最新观察分</span>
                <strong>{fmtNum(latest.watch_score)}</strong>
                <p className="workspace-note">周期 {latest.cycle_state || "--"}</p>
              </article>
            </div>
            <div className="collection-action-row">
              <button type="button" className="tag tag-button" onClick={() => navigateTo(`/stocks/${latest.stock_id}`)}>
                打开个股工作台
              </button>
              {latest.subject_key && (
                <button type="button" className="tag tag-button" onClick={() => navigateTo(`/themes/${latest.subject_key}`)}>
                  打开题材工作台
                </button>
              )}
            </div>
          </section>

          <section className="workspace-card">
            <span className="metric-label section-title">跟踪轨迹</span>
            <div className="strong-watch-detail-table-wrap">
              <table className="strong-watch-table">
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>状态</th>
                    <th>池内类型</th>
                    <th>观察分</th>
                    <th>连板</th>
                    <th>涨幅</th>
                    <th>换手率</th>
                    <th>主力净流入</th>
                    <th>周期</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((item) => (
                    <tr key={`${item.trade_date}-${item.stock_id}-${item.watch_score}`}>
                      <td>{item.trade_date}</td>
                      <td>{item.watch_status}</td>
                      <td>{item.pool_entry_type || "--"}</td>
                      <td>{fmtNum(item.watch_score)}</td>
                      <td>{Number(item.current_flag || 0)}</td>
                      <td className={item.pct_chg && item.pct_chg > 0 ? "up" : "down"}>{fmtPct(item.pct_chg)}</td>
                      <td>{fmtPct(item.turnover_rate)}</td>
                      <td>{fmtNum(item.main_net_inflow)}</td>
                      <td>{item.cycle_state || "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
