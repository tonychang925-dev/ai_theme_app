import React from "react";

interface Props {
  candidates: any[];
  loading: boolean;
  tradeDate: string;
  onRefresh: () => void;
}

export function AIDirectionDraftPanel({ candidates, loading, tradeDate, onRefresh }: Props) {
  const [actionLoading, setActionLoading] = React.useState<Record<string, boolean>>({});

  if (loading) {
    return <div style={{ padding: "8px 16px", fontSize: 12, color: "#5a7a8a" }}>加载AI方向草案…</div>;
  }
  if (!candidates || candidates.length === 0) return null;

  const drafts = candidates.filter((c: any) => c.status === 'DRAFT');

  const handleReview = async (candidateKey: string, action: string, extra?: Record<string, any>) => {
    setActionLoading(prev => ({ ...prev, [candidateKey]: true }));
    try {
      const resp = await fetch(`/api/v1/analyst-workspace/${tradeDate}/direction-candidates/${candidateKey}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...(extra || {}) }),
      });
      if (resp.ok) onRefresh();
    } catch { /* non-fatal */ }
    finally { setActionLoading(prev => ({ ...prev, [candidateKey]: false })); }
  };

  const spStars = (score: number) =>
    score >= 0.9 ? "★★★★★" : score >= 0.7 ? "★★★★☆" : score >= 0.5 ? "★★★☆☆" : score >= 0.3 ? "★★☆☆☆" : "★☆☆☆☆";

  return (
    <div style={{ padding: "10px 16px", borderBottom: "1px solid #243040", background: "#0c1118" }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", fontSize: 14, marginBottom: 8 }}>
        今日AI观察方向草案
      </div>
      {drafts.map((c: any) => {
        const sp = c.style_profile || {};
        const themes = (c.theme_bindings || []).map((t: any) => t.theme_name || t.subject_key).join(" · ");
        const loadingThis = actionLoading[c.candidate_key];

        return (
          <div key={c.candidate_key} style={{
            padding: "8px 10px", marginBottom: 6, background: "#111720",
            borderRadius: 4, border: "1px solid #243040", fontSize: 12,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <div>
                <span style={{ color: "#d8e6ef", fontWeight: 600 }}>{c.candidate_name}</span>
                <span style={{ color: "#6f8898", marginLeft: 8 }}>
                  置信度 {Math.round((c.confidence || 0) * 100)}%
                </span>
              </div>
              <span style={{ color: "#d69e2e", fontSize: 10, flexShrink: 0 }}>AI</span>
            </div>

            <div style={{ display: "flex", gap: 12, marginBottom: 4, fontSize: 11 }}>
              <span style={{ color: "#6f8898" }}>
                机构: <span style={{ color: "#66d9ef" }}>{spStars(sp.institution?.score || 0)}</span>
              </span>
              <span style={{ color: "#6f8898" }}>
                游资: <span style={{ color: "#dd6b20" }}>{spStars(sp.hot_money?.score || 0)}</span>
              </span>
              <span style={{ color: "#6f8898" }}>
                事件: <span style={{ color: "#805ad5" }}>{spStars(sp.event?.score || 0)}</span>
              </span>
            </div>

            {c.rationale && <div style={{ color: "#5a7a8a", fontSize: 11, marginBottom: 4 }}>{c.rationale}</div>}
            {themes && <div style={{ color: "#3a5a6a", fontSize: 10, marginBottom: 6 }}>涉及: {themes}</div>}

            <div style={{ display: "flex", gap: 6 }}>
              <button disabled={loadingThis} onClick={() => handleReview(c.candidate_key, "ACCEPT")}
                style={{ fontSize: 11, padding: "3px 10px", borderRadius: 3, cursor: "pointer",
                  background: "#1a3a2c", color: "#39ff14", border: "1px solid #2a5a3c" }}>
                接受
              </button>
              <button disabled={loadingThis} onClick={() => handleReview(c.candidate_key, "REJECT_OTHER", { notes: "分析师主动拒绝" })}
                style={{ fontSize: 11, padding: "3px 10px", borderRadius: 3, cursor: "pointer",
                  background: "#3a1a1a", color: "#e53e3e", border: "1px solid #5a2a2a" }}>
                拒绝
              </button>
              {loadingThis && <span style={{ color: "#5a7a8a", fontSize: 11 }}>处理中…</span>}
            </div>
          </div>
        );
      })}
      {drafts.length === 0 && (
        <div style={{ color: "#5a7a8a", fontSize: 12 }}>暂无AI方向草案 — 运行采集后自动生成</div>
      )}
    </div>
  );
}
