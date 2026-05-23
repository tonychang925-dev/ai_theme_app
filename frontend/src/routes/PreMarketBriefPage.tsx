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
import premarketIcon from "../assets/intel-icons/盘前必读.png";

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

function EventTable({ events, mode = "normal" }: { events: PreMarketBriefEvent[]; mode?: "normal" | "review" | "unknown" }) {
  if (!events.length) return null;
  const isReviewMode = mode !== "normal";
  return (
    <div className="recap-table-wrap">
      <table className="recap-table pre-market-event-table">
        <thead>
          <tr>
            {isReviewMode && <th>类型</th>}
            <th>标题</th>
            <th>题材</th>
            <th>影响分</th>
            <th>置信度</th>
            <th>来源</th>
            <th>摘要</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event, idx) => (
            <tr key={eventKey(event, idx)} className={isReviewMode ? `row-${mode}` : ""}>
              {isReviewMode && (
                <td>
                  <span className={`recap-chip ${mode === "review" ? "is-watch" : "is-risk"}`}>
                    {mode === "review" ? "待复核" : "未匹配"}
                  </span>
                </td>
              )}
              <td className="recap-cell-wrap"><strong>{event.title || "未命名事件"}</strong></td>
              <td>{event.theme_name ? <span className="recap-chip is-basis">{event.theme_name}</span> : "--"}</td>
              <td>{score(event.impact_score)}</td>
              <td>{event.confidence !== undefined ? score(event.confidence) : "--"}</td>
              <td>{event.source_channel ? <span className="recap-chip">{event.source_channel}</span> : "--"}</td>
              <td className="recap-cell-wrap">{event.summary || event.reason || "--"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnnouncementTable({ announcements }: { announcements: any[] }) {
  if (!announcements.length) return null;
  // 展平分组结构为单层列表
  const flat: any[] = [];
  for (const group of announcements) {
    for (const a of group.announcements || []) {
      flat.push({ ...a, _stock_code: group.stock_code, _stock_name: group.stock_name });
    }
  }
  return (
    <div className="recap-table-wrap">
      <table className="recap-table pre-market-announcement-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>公告标题</th>
            <th>级别</th>
            <th>发布时间</th>
            <th>PDF</th>
            <th>摘要</th>
          </tr>
        </thead>
        <tbody>
          {flat.map((a: any, idx: number) => (
            <tr key={`${a.event_id || idx}`}>
              <td style={{ whiteSpace: "nowrap" }}>
                <span className="recap-chip">{a._stock_code}</span>{" "}
                <strong>{a._stock_name || ""}</strong>
              </td>
              <td className="recap-cell-wrap">{a.title}</td>
              <td>
                {a.event_level === "important" ? (
                  <span className="recap-chip is-risk">重要</span>
                ) : (
                  <span className="recap-chip is-pending">{a.event_level || "普通"}</span>
                )}
              </td>
              <td style={{ whiteSpace: "nowrap" }}>
                {a.publish_time ? String(a.publish_time).replace("T", " ").slice(0, 16) : "--"}
              </td>
              <td>
                {a.pdf_url ? (
                  <a href={a.pdf_url} target="_blank" rel="noopener noreferrer"
                     style={{ fontSize: 11, color: "#78a9ff", whiteSpace: "nowrap", textDecoration: "none" }}>
                    PDF &#8599;
                  </a>
                ) : "--"}
              </td>
              <td className="recap-cell-wrap">{a.summary || "--"}</td>
            </tr>
          ))}
        </tbody>
      </table>
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

  const renderStockTable = (stocks: PreMarketOpportunityStock[]) => (
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
  );

  return (
    <div className="pre-market-opportunity">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <strong style={{ color: "#ffd85e" }}>{item.theme_name || "未命名题材"}</strong>
        <div className="recap-tag-stack">
          <span className="recap-chip is-status">事件 {item.event_count ?? 0}</span>
          <span className="recap-chip is-watch">置信度 {score(item.theme_confidence)}</span>
        </div>
      </div>
      {item.latest_event_title && (
        <p className="workspace-note" style={{ marginBottom: 8 }}>{item.latest_event_title}</p>
      )}
      {tierOrder.some((tier) => (tiers[tier] || []).length > 0) ? (
        <div className="pre-market-tier-stack">
          {tierOrder.map((tier) => {
            const stocks = tiers[tier] || [];
            if (!stocks.length) return null;
            return (
              <div className="pre-market-tier" key={`${item.subject_key}-${tier}`}>
                <span className={`recap-chip ${tier === "A" ? "is-pass" : tier === "B" ? "is-watch" : "is-pending"}`}>{tier}档</span>
                {renderStockTable(stocks)}
              </div>
            );
          })}
        </div>
      ) : (
        renderStockTable(fallbackStocks)
      )}
    </div>
  );
}

function alertLevelClass(level?: string): string {
  const l = (level || "").toLowerCase();
  if (l === "critical") return "is-risk";
  if (l === "important") return "is-watch";
  return "is-basis";
}

function RiskAlertTable({ alerts }: { alerts: PreMarketAlert[] }) {
  if (!alerts.length) return null;
  return (
    <div className="recap-table-wrap">
      <table className="recap-table pre-market-risk-table">
        <thead>
          <tr>
            <th>级别</th>
            <th>原因 / 标题</th>
            <th>股票</th>
            <th>原因代码</th>
            <th>发布时间</th>
            <th>关联事件</th>
            <th>摘要</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert, idx) => {
            const subCount = ((alert as any).events || []).length;
            return (
              <tr key={alert.dedupe_key || `risk-${idx}`}>
                <td>
                  <span className={`recap-chip ${alertLevelClass(alert.alert_level)}`}>
                    {alert.alert_level?.toUpperCase() || "!"}
                  </span>
                </td>
                <td className="recap-cell-wrap"><strong>{alert.title || alert.reason || "风险提示"}</strong></td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {alert.stock_name ? `${alert.stock_name}(${alert.stock_code})` : "--"}
                </td>
                <td>
                  {alert.reason_code ? (
                    <span className="recap-chip is-watch">{alert.reason_code}</span>
                  ) : "--"}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {alert.publish_time ? String(alert.publish_time).slice(0, 16) : "--"}
                </td>
                <td>
                  {subCount > 0 ? (
                    <span className="recap-chip is-status" title={(alert as any).events?.map((e: any) => e.title).join("\n")}>
                      {subCount} 条
                    </span>
                  ) : "--"}
                </td>
                <td className="recap-cell-wrap">{alert.summary || alert.message || "--"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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
  const announcementsMatched = sections.company_announcements_matched || [];
  // 只展示有交易机会的公告（与 opportunity_alerts 一致）
  const opportunityEventIds = new Set(
    (sections.opportunity_alerts || []).map((a: any) => a.source_event_id).filter(Boolean)
  );
  const announcementsWithOpportunity = announcementsMatched
    .map((g: any) => ({
      ...g,
      announcements: (g.announcements || []).filter((a: any) => opportunityEventIds.has(a.event_id))
    }))
    .filter((g: any) => g.announcements.length > 0);
  const partial = Boolean(payload?.diagnostics?.partial || payload?.payload?.diagnostics?.partial);

  return (
    <div className="workspace-page pre-market-page">
      <section className="strong-watch-toolbar">
        <img src={premarketIcon} alt="" style={{ height: 64, width: 64, flexShrink: 0 }} />
        <h1 className="strong-watch-title">盘前必读</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#9f9f9f" }}>交易日</span>
            <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)}
              style={{ border: "1px solid #2a2a2a", borderRadius: 6, background: "#1a1a1a", color: "#f5f5f5", padding: "4px 8px" }} />
          </label>
          <div className="recap-tag-stack">
            <span className={`recap-chip ${statusClass(status)}`}>{status}</span>
            {partial && <span className="recap-chip is-risk">partial</span>}
            <span className="recap-chip">updated {text(payload?.updated_at || payload?.generated_at)}</span>
          </div>
          <button className="tag tag-button" type="button" style={{ fontSize: 16, padding: "8px 16px" }} onClick={() => setRefreshNonce((prev) => prev + 1)}>
            刷新
          </button>
          <button
            className="tag tag-button is-pass"
            style={{ fontSize: 16, padding: "8px 16px" }}
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
        </div>
        <button className="back-button" type="button" onClick={() => navigateTo("/intel")}>
          返回
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
                <strong>{announcementsWithOpportunity.length}</strong>
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
              <EventTable events={majorEvents} />
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

            <SectionShell title="四、公告机会" empty={announcementsWithOpportunity.length === 0}>
              <AnnouncementTable announcements={announcementsWithOpportunity} />
            </SectionShell>

            <SectionShell title="五、风险预警" empty={riskAlerts.length === 0}>
              <RiskAlertTable alerts={riskAlerts} />
            </SectionShell>

            <SectionShell title="六、待复核事件" empty={reviewEvents.length + unknownEvents.length === 0}>
              <EventTable events={reviewEvents} mode="review" />
              <EventTable events={unknownEvents} mode="unknown" />
            </SectionShell>

            <DiagnosticsPanel payload={payload} />
          </section>
        </main>
      )}
    </div>
  );
}
