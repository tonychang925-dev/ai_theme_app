import { useEffect, useState } from "react";
import type { ThemeWorkspaceView } from "../../lib/api";
import { fetchThemeWorkspace } from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

interface Props {
  subjectKey: string;
}

export function ThemeWorkspacePage({ subjectKey }: Props) {
  const [payload, setPayload] = useState<ThemeWorkspaceView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchThemeWorkspace(subjectKey)
      .then((data) => {
        if (active) setPayload(data);
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
  }, [subjectKey]);

  const historyItems = Array.isArray(payload?.history) ? payload.history : [];
  const childItems = Array.isArray(payload?.children) ? payload.children : [];
  const stockItems = Array.isArray(payload?.stocks) ? payload.stocks : [];
  const themeName = typeof payload?.detail?.theme_name === "string" ? payload.detail.theme_name : subjectKey;
  const summary = typeof payload?.detail?.summary === "string" ? payload.detail.summary : "";

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/intel")}>
          返回情报台
        </button>
        <div>
          <p className="eyebrow">Theme Workspace</p>
          <h1>{themeName}</h1>
          <p className="subtle">{summary || "暂无题材摘要"}</p>
        </div>
      </header>

      {loading && <div className="empty-state">正在加载题材工作台...</div>}
      {error && <div className="empty-state error">{error}</div>}

      {!loading && !error && payload && (
        <main className="workspace-layout">
          <section className="workspace-column">
            <div className="workspace-card">
              <span className="metric-label">题材详情</span>
              <strong>{themeName}</strong>
              <p className="workspace-note">subject_key: {payload.subject_key}</p>
              <p className="workspace-note">状态: {String(payload.detail.binding_status ?? "--")}</p>
            </div>

            <div className="workspace-card">
              <span className="metric-label">历史驱动</span>
              {historyItems.length > 0 ? (
                <ul className="workspace-list">
                  {historyItems.slice(0, 10).map((item, idx) => (
                    <li key={`${item.source_ref ?? idx}`}>
                      <strong>{String(item.rank_date ?? "--")}</strong>
                      <span>{String(item.description ?? item.theme_name ?? "--")}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="workspace-note">暂无历史驱动</p>
              )}
            </div>
          </section>

          <section className="workspace-column">
            <div className="workspace-card">
              <span className="metric-label">子题材</span>
              {childItems.length > 0 ? (
                <div className="tag-row">
                  {childItems.map((item, idx) => (
                    <span className="tag" key={`${item.child_subject_key ?? idx}`}>
                      {String(item.child_name ?? item.child_subject_key ?? "--")}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="workspace-note">暂无子题材</p>
              )}
            </div>

            <div className="workspace-card">
              <span className="metric-label">股票池</span>
              {stockItems.length > 0 ? (
                <div className="tag-row">
                  {stockItems.map((item, idx) => (
                    <button
                      key={`${item.stock_id ?? idx}`}
                      type="button"
                      className="tag tag-button"
                      onClick={() => navigateTo(`/stocks/${String(item.stock_id ?? "")}`)}
                    >
                      {String(item.stock_name ?? item.stock_id ?? "--")}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="workspace-note">暂无股票池</p>
              )}
            </div>
          </section>
        </main>
      )}
    </div>
  );
}

