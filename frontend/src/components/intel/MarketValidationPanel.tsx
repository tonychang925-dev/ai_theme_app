import type { MarketValidationView } from "../../lib/api";

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    start: "启动", fermentation: "发酵", divergence: "分歧",
    rebound: "弱转强", climax: "高潮", fade: "退潮",
    fade_watch: "退潮观察", fade_confirmed: "退潮确认", repair: "修复",
  };
  return map[stage] ?? stage;
}

interface Props {
  data: MarketValidationView | null;
  loading?: boolean;
  error?: string | null;
}

export function MarketValidationPanel({ data, loading, error }: Props) {
  const tv = data?.theme_validation;

  return (
    <aside className="theme-radar-panel" style={{ borderRight: "none", borderLeft: "1px solid #1d2a3d" }}>
      <div className="theme-radar-head">
        <span className="metric-label section-title">市场验证</span>
      </div>

      {loading && <div className="empty-state compact">加载中...</div>}
      {error && <div className="empty-state compact error">{error}</div>}

      {!loading && !error && (
        <div style={{ padding: "6px 14px", display: "grid", gap: 10 }}>

          {/* 池统计 */}
          {data && (
            <div className="workspace-card" style={{ padding: "10px 12px" }}>
              <span className="metric-label">池状态</span>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 6 }}>
                <div>
                  <strong style={{ color: "#f7d45a", fontSize: 20 }}>{data.strong_watch_count}</strong>
                  <p className="workspace-note">强势池</p>
                </div>
                <div>
                  <strong style={{ color: "#78a9ff", fontSize: 20 }}>{data.w2s_candidate_count}</strong>
                  <p className="workspace-note">弱转强候选</p>
                </div>
              </div>
            </div>
          )}

          {/* 主题验证 */}
          {tv && (
            <div className="workspace-card" style={{ padding: "10px 12px" }}>
              <span className="metric-label">
                {tv.theme_name || data?.subject_key || "选中主题"}
              </span>
              <div style={{ marginTop: 6, display: "grid", gap: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span className="workspace-note">周期阶段</span>
                  <span className="recap-chip is-watch">{stageLabel(tv.cycle_stage || "--")}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span className="workspace-note">主线强度</span>
                  <strong style={{ color: "#f7d45a" }}>{(tv.mainline_strength ?? 0).toFixed(2)}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span className="workspace-note">退潮风险</span>
                  <strong style={{ color: "#ffb0b0" }}>{(tv.fade_risk ?? 0).toFixed(2)}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span className="workspace-note">主线存活</span>
                  <span>{tv.mainline_alive ? "是" : "否"}</span>
                </div>
              </div>
              {tv.leader_stocks && tv.leader_stocks.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <span className="workspace-note">龙头股票</span>
                  <div style={{ display: "grid", gap: 3, marginTop: 4 }}>
                    {tv.leader_stocks.slice(0, 5).map((ls, i) => (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                        <span>{ls.name || "--"}</span>
                        <span style={{ color: "#78a9ff" }}>
                          {ls.pct_chg != null ? `${Number(ls.pct_chg) > 0 ? "+" : ""}${Number(ls.pct_chg).toFixed(2)}%` : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 无选中主题时显示默认提示 */}
          {!tv && data && (
            <div className="workspace-card" style={{ padding: "10px 12px" }}>
              <span className="metric-label">候选级别</span>
              <div style={{ marginTop: 4 }}>
                <span className="recap-chip is-watch">{data.candidate_level || "observe"}</span>
              </div>
              <p className="workspace-note" style={{ marginTop: 4 }}>
                支撑类型: {data.support_type || "--"}
              </p>
              {data.support_score != null && (
                <p className="workspace-note">支撑分数: {data.support_score.toFixed(2)}</p>
              )}
            </div>
          )}

          {/* 拒绝原因 */}
          {data && data.reject_reasons.length > 0 && (
            <div className="workspace-card" style={{ padding: "10px 12px", borderColor: "#5d3540" }}>
              <span className="metric-label" style={{ color: "#ffb0b0" }}>拒绝原因</span>
              <ul className="workspace-list" style={{ marginTop: 4 }}>
                {data.reject_reasons.map((r, i) => (
                  <li key={i} className="workspace-note" style={{ color: "#ffb0b0" }}>{r}</li>
                ))}
              </ul>
            </div>
          )}

        </div>
      )}

      {!loading && !error && !data && (
        <div className="empty-state compact">暂无验证数据</div>
      )}
    </aside>
  );
}
