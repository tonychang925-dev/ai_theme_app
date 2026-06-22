/** M4h: Market Recap panel showing top themes + leaders from recap API. */

import type { FC } from "react";
import { useMarketRecap } from "../../../hooks/useMarketRecap";
import { navigateTo } from "../../../lib/navigation";

interface Props {
  tradeDate: string;
}

export const MarketRecapPanel: FC<Props> = ({ tradeDate }) => {
  const { data, loading, error } = useMarketRecap(tradeDate);

  if (loading) {
    return <div className="recap-panel"><span>加载复盘数据...</span></div>;
  }

  if (error || !data?.top_themes?.length) {
    return null; // silent — coexists with legacy recap
  }

  const { top_themes, market_summary, diagnostics } = data;

  return (
    <div className="recap-panel" style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>📊 题材强度</h3>
        {diagnostics?.degraded && (
          <span className="pill" style={{ background: "#fff3cd", color: "#856404", fontSize: 12 }}>
            部分数据降级
          </span>
        )}
        <span style={{ fontSize: 12, color: "#999" }}>
          {market_summary?.theme_count ?? 0}个题材 · {market_summary?.leader_count ?? 0}只龙头 · {market_summary?.evidence_source_count ?? 0}源证据
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
        {top_themes.slice(0, 8).map((theme) => (
          <div
            key={theme.theme_name}
            className="recap-card"
            style={{
              border: "1px solid #e0e0e0",
              borderRadius: 8,
              padding: 12,
              background: theme.rank === 1 ? "#f0f7ff" : "#fff",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <button
                type="button"
                className="recap-theme-link"
                onClick={() => navigateTo(`/themes/${encodeURIComponent(theme.theme_name)}`)}
                style={{ fontWeight: 700, fontSize: 15, border: "none", background: "none", cursor: "pointer", padding: 0 }}
              >
                #{theme.rank} {theme.theme_name}
              </button>
              <span style={{ fontWeight: 700, color: "#1a73e8", fontSize: 16 }}>
                {(theme.strength_score * 100).toFixed(0)}
              </span>
            </div>

            {/* Why strong */}
            <div style={{ marginBottom: 4 }}>
              {theme.why_strong?.map((reason: string) => (
                <span key={reason} className="tag" style={{ marginRight: 4, fontSize: 11 }}>
                  {reason}
                </span>
              ))}
            </div>

            {/* Catalyst event */}
            {theme.catalyst && (
              <div style={{ fontSize: 12, color: "#aaa", marginBottom: 6, lineHeight: 1.4 }}>
                {theme.catalyst}
              </div>
            )}

            {/* Leaders */}
            <div style={{ fontSize: 13 }}>
              {theme.leaders?.map((ld) => (
                <button
                  key={ld.stock_code}
                  type="button"
                  className="recap-theme-link"
                  onClick={() => navigateTo(`/stocks/${encodeURIComponent(ld.stock_code)}`)}
                  style={{ marginRight: 8, border: "none", background: "#f5f5f5", padding: "2px 8px", borderRadius: 4, cursor: "pointer" }}
                >
                  {ld.stock_name}
                  <span style={{ color: "#999", fontSize: 11, marginLeft: 4 }}>
                    {(ld.leader_score * 100).toFixed(0)}
                  </span>
                </button>
              ))}
            </div>

            {/* Stock/leader counts */}
            <div style={{ fontSize: 11, color: "#999", marginTop: 6 }}>
              {theme.stock_count}只成分股 · {theme.leader_count}只共振 · {theme.evidence_sources?.join(" + ")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
