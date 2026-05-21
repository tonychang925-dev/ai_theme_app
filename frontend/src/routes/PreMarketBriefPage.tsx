import { useEffect, useMemo, useState } from "react";
import {
  fetchPreMarketBrief,
  publishPreMarketBriefToNotion,
  type PreMarketAlert,
  type PreMarketBriefEvent,
  type PreMarketBriefTheme,
  type PreMarketBriefView,
  type PreMarketOpportunity,
  type PreMarketOpportunityStock,
} from "../lib/api";
import { navigateTo } from "../lib/navigation";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function text(value: unknown, fallback = "--"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return fallback;
  }
}

function score(value: unknown): string {
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  return num.toFixed(num >= 10 ? 1 : 2);
}

function statusClass(status?: string): string {
  const normalized = String(status || "missing").toLowerCase();
  if (normalized === "final") return "is-pass";
  if (normalized === "draft") return "is-watch";
  if (normalized === "partial" || normalized === "stale") return "is-risk";
  return "is-pending";
}

function eventKey(event: PreMarketBriefEvent, idx: number): string {
  return String(event.event_id ?? event.item_id ?? `${event.title || "event"}-${idx}`);
}

function SectionShell({ title, children, empty }: { title: string; children: React.ReactNode; empty?: boolean }) {
  return (
    <section className="workspace-card pre-market-section">
      <span className="metric-label section-title">{title}</span>
      {empty ? <div className="empty-state compact">暂无数据</div> : children}
    </section>
  );
}

function EventList({ events, mode = "normal" }: { events: PreMarketBriefEvent[]; mode?: "normal" | "review" | "unknown" }) {
  if (!events.length) return null;
  return (
    <div className="pre-market-event-list">
      {events.map((event, idx) => (
        <article className={`pre-market-event is-${mode}`} key={eventKey(event, idx)}>
          <div className="pre-market-event-head">
            <strong>{event.title || "未命名事件"}</strong>
            <span className="recap-chip is-status">{score(event.impact_score)}</span>
          </div>
          <p className="workspace-note">{event.summary || event.reason || "暂无摘要"}</p>
          <div className="recap-tag-stack">
            {event.theme_name && <span className="recap-chip is-basis">{event.theme_name}</span>}
            {event.confidence !== undefined && <span className="recap-chip is-watch">置信度 {score(event.confidence)}</span>}
            {event.source_channel && <span className="recap-chip">{event.source_channel}</span>}
          </div>
        </article>
      ))}
    </div>
  );
}

function ThemeTable({ themes }: { themes: PreMarketBriefTheme[] }) {
  if (!themes.length) return null;
  return (
    <div className="recap-table-wrap">
      <table className="recap-table pre-market-theme-table">
        <thead>
          <tr>
            <th>题材</th>
            <th>事件数</th>
            <th>置信度</th>
            <th>影响分</th>
            <th>最新事件</th>
          </tr>
        </thead>
        <tbody>
          {themes.map((theme, idx) => (
            <tr key={`${theme.subject_key || theme.theme_name || "theme"}-${idx}`}>
              <td>
                {theme.subject_key ? (
                  <button className="recap-theme-link" type="button" onClick={() => navigateTo(`/themes/${encodeURIComponent(theme.subject_key || "")}`)}>
                    {theme.theme_name || "未命名题材"}
                  </button>
                ) : (
                  theme.theme_name || "未命名题材"
                )}
              </td>
              <td>{theme.event_count ?? 0}</td>
              <td>{score(theme.confidence)}</td>
              <td>{score(theme.impact_score)}</td>
              <td className="recap-cell-wrap">{theme.latest_event_title || "--"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpportunityStockRow({ stock }: { stock: PreMarketOpportunityStock }) {
  return (
    <tr>
      <td>
        {stock.stock_id ? (
          <button className="recap-theme-link recap-stock-highlight" type="button" onClick={() => navigateTo(`/stocks/${encodeURIComponent(stock.stock_id || "")}`)}>
            {stock.stock_name || stock.stock_id}
          </button>
        ) : (
          stock.stock_name || "--"
        )}
      </td>
      <td><span className={`recap-chip ${stock.level === "A" ? "is-pass" : stock.level === "B" ? "is-watch" : "is-pending"}`}>{stock.level || "C"}</span></td>
      <td>{score(stock.score)}</td>
      <td className="recap-cell-wrap">{stock.reason || "--"}</td>
      <td className="recap-cell-wrap">{stock.risk || "--"}</td>
    </tr>
  );
}

function OpportunityCard({ item }: { item: PreMarketOpportunity }) {
  const tierOrder = ["A", "B", "C"];
  const tiers = item.tiers || {};
  const fallbackStocks = item.stocks || [];
  return (
    <article className="recap-table-card pre-market-opportunity">
      <div className="recap-table-head">
        <div>
          <strong>{item.theme_name || "未命名题材"}</strong>
          <p className="workspace-note">{item.latest_event_title || "暂无最新事件标题"}</p>
        </div>
        <div className="recap-tag-stack">
          <span className="recap-chip is-status">事件 {item.event_count ?? 0}</span>
          <span className="recap-chip is-watch">置信度 {score(item.theme_confidence)}</span>
        </div>
      </div>
      {tierOrder.some((tier) => (tiers[tier] || []).length > 0) ? (
        <div className="pre-market-tier-stack">
          {tierOrder.map((tier) => {
            const stocks = tiers[tier] || [];
            if (!stocks.length) return null;
            return (
              <div className="pre-market-tier" key={`${item.subject_key}-${tier}`}>
                <span className={`recap-chip ${tier === "A" ? "is-pass" : tier === "B" ? "is-watch" : "is-pending"}`}>{tier}档</span>
                <div className="recap-table-wrap">
                  <table className="recap-table pre-market-stock-table">
                    <thead>
                      <tr>
                        <th>股票</th>
                        <th>档位</th>
                        <th>分数</th>
                        <th>理由</th>
                        <th>风险</th>
                      </tr>
                    </thead>
                    <tbody>{stocks.map((stock, idx) => <OpportunityStockRow stock={stock} key={`${stock.stock_id || "stock"}-${idx}`} />)}</tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="recap-table-wrap">
          <table className="recap-table pre-market-stock-table">
            <thead>
              <tr>
                <th>股票</th>
                <th>档位</th>
                <th>分数</th>
                <th>理由</th>
                <th>风险</th>
              </tr>
            </thead>
            <tbody>{fallbackStocks.map((stock, idx) => <OpportunityStockRow stock={stock} key={`${stock.stock_id || "stock"}-${idx}`} />)}</tbody>
          </table>
        </div>
      )}
    </article>
  );
}

function alertLevelClass(level?: string): string {
  const l = (level || "").toLowerCase();
  if (l === "critical") return "is-risk";
  if (l === "important") return "is-watch";
  return "is-basis";
}

function RiskAlertCard({ alert }: { alert: PreMarketAlert }) {
  return (
    <article className={`pre-market-risk ${alertLevelClass(alert.alert_level)}`}>
      <div className="pre-market-risk-head">
        <span className={`recap-chip ${alertLevelClass(alert.alert_level)}`}>
          {alert.alert_level?.toUpperCase() || "?"}
        </span>
        <strong>{alert.title || "风险提示"}</strong>
        <span className="recap-chip is-status">S{score(alert.alert_score)}</span>
      </div>
      <p className="workspace-note">{alert.reason || alert.summary || ""}</p>
      <div className="recap-tag-stack">
        {alert.stock_name && <span className="recap-chip">{alert.stock_name}({alert.stock_code})</span>}
        {alert.reason_code && <span className="recap-chip is-watch">{alert.reason_code}</span>}
        {alert.publish_time && <span className="recap-chip">{String(alert.publish_time).slice(0, 16)}</span>}
      </div>
    </article>
  );
}

function OpportunityAlertCard({ alert }: { alert: PreMarketAlert }) {
  return (
    <article className="pre-market-opportunity">
      <div className="pre-market-opp-head">
        <span className={`recap-chip ${alertLevelClass(alert.alert_level)}`}>
          {alert.alert_level?.toUpperCase() || "?"}
        </span>
        <strong>{alert.title || "机会提醒"}</strong>
        <span className="recap-chip is-status">S{score(alert.alert_score)}</span>
      </div>
      <p className="workspace-note">{alert.reason || alert.summary || ""}</p>
      <div className="recap-tag-stack">
        {alert.stock_name && <span className="recap-chip">{alert.stock_name}({alert.stock_code})</span>}
        {alert.amount && <span className="recap-chip is-basis">{alert.amount}</span>}
        {alert.reason_code && <span className="recap-chip is-watch">{alert.reason_code}</span>}
      </div>
    </article>
  );
}

function DiagnosticsPanel({ payload }: { payload: PreMarketBriefView }) {
  const diagnostics = payload.payload?.diagnostics || payload.diagnostics || {};
  return (
    <details className="workspace-card pre-market-diagnostics">
      <summary>📊 diagnostics（点击展开）</summary>
      <pre>{JSON.stringify(diagnostics, null, 2)}</pre>
    </details>
  );
}

export function PreMarketBriefPage() {
  const initialDate = useMemo(() => new URLSearchParams(window.location.search).get("trade_date") || new URLSearchParams(window.location.search).get("date") || todayIso(), []);
  const [tradeDate, setTradeDate] = useState(initialDate);
  const [payload, setPayload] = useState<PreMarketBriefView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchPreMarketBrief(tradeDate)
      .then((res) => {
        if (!active) return;
        setPayload(res);
        const query = new URLSearchParams({ trade_date: tradeDate });
        window.history.replaceState(null, "", `/pre-market-brief?${query.toString()}`);
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tradeDate, refreshNonce]);

  const sections = payload?.payload?.sections || {};
  const status = payload?.status || payload?.payload?.status || "missing";
  const majorEvents = sections.major_events || [];
  const matchedThemes = sections.matched_themes || [];
  const opportunities = sections.event_driven_opportunities || [];
  const reviewEvents = sections.review_events || [];
  const unknownEvents = sections.unknown_watch || [];
  const riskAlerts = sections.risk_alerts || [];
  const opportunityAlerts = sections.opportunity_alerts || [];
  const announcementsRaw = sections.company_announcements_raw || [];
  const partial = Boolean(payload?.diagnostics?.partial || payload?.payload?.diagnostics?.partial);

  return (
    <div className="workspace-page pre-market-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/intel")}>
          返回情报台
        </button>
        <div>
          <p className="eyebrow">Pre-Market Brief</p>
          <h1>盘前必读</h1>
          <p className="subtle">只读 pre_market_brief_snapshot 快照，展示事件驱动机会报告。</p>
        </div>
      </header>

      <section className="workspace-card pre-market-toolbar">
        <label className="recap-toolbar-date">
          <span>交易日</span>
          <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
        </label>
        <div className="recap-tag-stack">
          <span className={`recap-chip ${statusClass(status)}`}>{status}</span>
          {partial && <span className="recap-chip is-risk">partial</span>}
          <span className="recap-chip">updated {text(payload?.updated_at || payload?.generated_at)}</span>
        </div>
        <button className="tag tag-button" type="button" onClick={() => setRefreshNonce((prev) => prev + 1)}>
          刷新
        </button>
        <button
          className="tag tag-button is-pass"
          type="button"
          disabled={publishing}
          onClick={async () => {
            setPublishing(true);
            try {
              const result = await publishPreMarketBriefToNotion(tradeDate);
              alert(`已发布到 Notion: ${result.page_url || result.action}`);
            } catch (err: any) {
              alert(`发布失败: ${err.message}`);
            } finally {
              setPublishing(false);
            }
          }}
        >
          {publishing ? "发布中..." : "发布到 Notion"}
        </button>
      </section>

      {loading && <div className="empty-state">正在加载盘前必读...</div>}
      {error && <div className="empty-state error">{error}</div>}

      {!loading && !error && payload && (
        <main className="workspace-layout single">
          <section className="workspace-column">
            <div className="pre-market-summary-grid">
              <div className="workspace-card">
                <span className="metric-label">重大事件</span>
                <strong>{majorEvents.length}</strong>
              </div>
              <div className="workspace-card">
                <span className="metric-label">匹配题材</span>
                <strong>{matchedThemes.length}</strong>
              </div>
              <div className="workspace-card">
                <span className="metric-label">公告</span>
                <strong>{announcementsRaw.length}</strong>
              </div>
              <div className="workspace-card is-risk">
                <span className="metric-label">风险预警</span>
                <strong>{riskAlerts.length}</strong>
              </div>
              <div className="workspace-card is-basis">
                <span className="metric-label">机会提醒</span>
                <strong>{opportunityAlerts.length}</strong>
              </div>
              <div className="workspace-card">
                <span className="metric-label">待复核</span>
                <strong>{reviewEvents.length + unknownEvents.length}</strong>
              </div>
            </div>

            <SectionShell title="一、隔夜重大事件" empty={majorEvents.length === 0}>
              <EventList events={majorEvents} />
            </SectionShell>

            <SectionShell title="二、今日重点题材" empty={matchedThemes.length === 0}>
              <ThemeTable themes={matchedThemes} />
            </SectionShell>

            <SectionShell title="三、事件驱动机会" empty={opportunities.length === 0}>
              <div className="recap-table-stack">
                {opportunities.map((item, idx) => <OpportunityCard item={item} key={`${item.subject_key || item.theme_name || "opportunity"}-${idx}`} />)}
              </div>
            </SectionShell>

            <SectionShell title="四、弱转强观察" empty={(sections.weak_to_strong_watch || []).length === 0}>
              <pre className="pre-market-json-block">{JSON.stringify(sections.weak_to_strong_watch, null, 2)}</pre>
            </SectionShell>

            <SectionShell title="四、公告机会" empty={opportunityAlerts.length === 0}>
              <div className="pre-market-alert-list">
                {opportunityAlerts.map((alert, idx) => (
                  <OpportunityAlertCard alert={alert as PreMarketAlert} key={alert.dedupe_key || `opp-${idx}`} />
                ))}
              </div>
            </SectionShell>

            <SectionShell title="五、风险预警" empty={riskAlerts.length === 0}>
              <div className="pre-market-alert-list">
                {riskAlerts.map((alert, idx) => (
                  <RiskAlertCard alert={alert as PreMarketAlert} key={alert.dedupe_key || `risk-${idx}`} />
                ))}
              </div>
            </SectionShell>

            <SectionShell title="六、待复核事件" empty={reviewEvents.length + unknownEvents.length === 0}>
              <EventList events={reviewEvents} mode="review" />
              <EventList events={unknownEvents} mode="unknown" />
            </SectionShell>

            <DiagnosticsPanel payload={payload} />
          </section>
        </main>
      )}
    </div>
  );
}
