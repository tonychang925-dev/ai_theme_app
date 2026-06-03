import { Tag } from "antd";
import type { MarketHotspotNarrative } from "../../../lib/api";
import { navigateTo } from "../../../lib/navigation";

interface Props {
  narrative?: MarketHotspotNarrative | null;
  tradeDate?: string;
}

function translateAction(value?: string | null) {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    "主线参与": "主线参与",
    "主线分歧": "主线分歧",
    "轮动跟随": "轮动跟随",
    "轮动观察": "轮动观察",
    "观察": "观察",
    "回避": "回避",
    "谨慎": "谨慎",
  };
  return map[key] || key || "--";
}

function renderThemeTag(theme: MarketHotspotNarrative["strongest_themes"][number], tradeDate?: string) {
  const href = theme.subject_key ? `/themes/${encodeURIComponent(theme.subject_key)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}` : "";
  return (
    <button type="button" className="recap-theme-link" onClick={() => href && navigateTo(href)}>
      {theme.theme_name || "--"}
    </button>
  );
}

export default function MarketHotspotNarrativePanel({ narrative, tradeDate }: Props) {
  if (!narrative) return null;

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        行情概览
        <Tag color="gold" style={{ marginLeft: 8 }}>热点总结</Tag>
        {narrative.source && <Tag color={narrative.source === "engine_template" ? "green" : "blue"}>{narrative.source}</Tag>}
      </h3>

      <div style={{ background: "rgba(255,214,102,0.08)", border: "1px solid rgba(255,214,102,0.18)", borderRadius: 8, padding: 14, marginBottom: 12 }}>
        <div className="workspace-note" style={{ marginBottom: 6 }}>今日热点结论</div>
        <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.6 }}>{narrative.headline}</div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">核心要点</div>
        <ul className="workspace-list">
          {narrative.core_points.map((point, idx) => (
            <li key={`hotspot-point-${idx}`}>
              <p className="workspace-note">{point}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">最强热点</div>
        <div className="recap-tag-stack">
          {narrative.strongest_themes.length > 0 ? (
            narrative.strongest_themes.map((theme, idx) => (
              <div key={`strongest-${theme.subject_key || theme.theme_name || idx}`} className="recap-tag-stack" style={{ gap: 4, alignItems: "flex-start" }}>
                <div>
                  {renderThemeTag(theme, tradeDate)}
                </div>
                <div className="recap-tag-stack" style={{ gap: 4, flexWrap: "wrap" }}>
                  <Tag color="blue">{theme.limit_up_count ?? 0} 涨停</Tag>
                  {theme.active_mainline ? <Tag color="green">主线</Tag> : <Tag color="default">轮动</Tag>}
                  {theme.lifecycle_state && <Tag color="purple">{theme.lifecycle_state}</Tag>}
                  {theme.trade_action && <Tag color="orange">{translateAction(theme.trade_action)}</Tag>}
                </div>
              </div>
            ))
          ) : (
            <span className="workspace-note">暂无热点数据</span>
          )}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">轮动观察</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {narrative.rotation_themes.length > 0 ? narrative.rotation_themes.map((item) => <Tag key={item}>{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">风险主题</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {narrative.risk_themes.length > 0 ? narrative.risk_themes.map((item) => <Tag key={item} color="red">{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">热点总结</div>
        <p className="workspace-note">{narrative.market_heat_summary}</p>
      </div>

      <div className="workspace-card">
        <div className="metric-label section-title">明日聚焦</div>
        <p className="workspace-note">{narrative.next_day_focus}</p>
      </div>
    </div>
  );
}
