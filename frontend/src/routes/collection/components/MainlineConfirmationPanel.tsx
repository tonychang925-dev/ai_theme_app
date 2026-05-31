import React, { useState, useCallback, useEffect } from "react";
import {
  fetchMainlineReviewQueue,
  fetchConfirmedMainlines,
  submitMainlineReviewDecision,
  importMainlineReviewCandidates,
  MainlineReviewItem,
  ConfirmedMainlineItem,
} from "../../../lib/api";

function fmt(v: unknown): string {
  if (v == null) return "--";
  return String(v);
}
function n(v: number | null | undefined): string {
  return v != null ? String(Math.round(v)) : "--";
}

const TAB_STYLE: Record<string, React.CSSProperties> = {
  active: { background: "#1a2a4a", color: "#e0e8ff", border: "1px solid #2a4a8a" },
  inactive: { background: "transparent", color: "#8899bb" },
};

// ── MainlineConfirmationPanel ──

export const MainlineConfirmationPanel: React.FC = () => {
  const [tab, setTab] = useState<"pending" | "confirmed">("pending");
  const [items, setItems] = useState<MainlineReviewItem[]>([]);
  const [confirmed, setConfirmed] = useState<ConfirmedMainlineItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<MainlineReviewItem | null>(null);
  const [importing, setImporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        fetchMainlineReviewQueue({ limit: 200 }),
        fetchConfirmedMainlines({ limit: 100 }),
      ]);
      setItems(r1.items ?? []);
      setConfirmed(r2.items ?? []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleImport = async () => {
    setImporting(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await importMainlineReviewCandidates(today);
      await load();
    } catch { /* ignore */ }
    setImporting(false);
  };

  const handleDecision = async (reviewId: string, decision: string) => {
    await submitMainlineReviewDecision(reviewId, { human_decision: decision });
    await load();
  };

  const handleConfirm = async (reviewId: string) => {
    const item = items.find((i) => i.review_id === reviewId);
    if (!item) return;
    const name = prompt("主线名称:", item.theme_name ?? item.subject_key ?? "");
    if (!name) return;
    const csk = prompt("canonical subject_key:", item.subject_key ?? "");
    if (!csk) return;
    await submitMainlineReviewDecision(reviewId, {
      human_decision: "confirm_mainline",
      canonical_subject_key: csk,
      mainline_name: name,
    });
    await load();
  };

  const handleMerge = async (reviewId: string) => {
    const item = items.find((i) => i.review_id === reviewId);
    if (!item) return;
    const target = prompt("合并到已有主线 mainline_id:", "");
    if (!target) return;
    await submitMainlineReviewDecision(reviewId, {
      human_decision: "merge_into_existing_mainline",
      merge_target_mainline_id: target,
      related_subject_keys: [item.subject_key],
    });
    await load();
  };

  const pending = items.filter((i) => i.review_status === "pending" || !i.human_decision);
  const fast = pending.filter((i) => i.machine_state === "machine_fast_candidate").length;
  const slow = pending.filter((i) => i.machine_state === "machine_slow_candidate").length;

  return (
    <div style={{ padding: "12px 0" }}>
      {/* ── Stats cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        <div style={{ background: "#1a1a2e", padding: "10px 14px", borderRadius: 6, border: "1px solid #2a2a4e" }}>
          <span style={{ color: "#888", fontSize: 12 }}>待确认</span>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#ffaa33" }}>{pending.length}</div>
        </div>
        <div style={{ background: "#1a1a2e", padding: "10px 14px", borderRadius: 6, border: "1px solid #2a2a4e" }}>
          <span style={{ color: "#888", fontSize: 12 }}>已确认</span>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#44cc88" }}>{confirmed.length}</div>
        </div>
        <div style={{ background: "#1a1a2e", padding: "10px 14px", borderRadius: 6, border: "1px solid #2a2a4e" }}>
          <span style={{ color: "#888", fontSize: 12 }}>快线/慢线</span>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#88aaff" }}>{fast}/{slow}</div>
        </div>
        <div style={{ background: "#1a1a2e", padding: "10px 14px", borderRadius: 6, border: "1px solid #2a2a4e" }}>
          <span style={{ color: "#888", fontSize: 12 }}>操作</span>
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <button onClick={handleImport} disabled={importing}
              style={{ background: "#2a4a6a", color: "#ddeeff", border: "none", borderRadius: 4, padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>
              {importing ? "导入中..." : "导入候选"}</button>
            <button onClick={load} disabled={loading}
              style={{ background: "#333", color: "#aaa", border: "none", borderRadius: 4, padding: "4px 10px", cursor: "pointer", fontSize: 12 }}>
              刷新</button>
          </div>
        </div>
      </div>

      {/* ── Tab toggle ── */}
      <div style={{ display: "flex", gap: 0, marginBottom: 12 }}>
        <button onClick={() => setTab("pending")}
          style={{ ...TAB_STYLE[tab === "pending" ? "active" : "inactive"], padding: "8px 20px", border: "1px solid #2a4a8a", borderRadius: "4px 0 0 4px", cursor: "pointer", fontWeight: 500, fontSize: 13 }}>
          待确认 {pending.length > 0 && `(${pending.length})`}
        </button>
        <button onClick={() => setTab("confirmed")}
          style={{ ...TAB_STYLE[tab === "confirmed" ? "active" : "inactive"], padding: "8px 20px", border: "1px solid #2a4a8a", borderRadius: "0 4px 4px 0", cursor: "pointer", fontWeight: 500, fontSize: 13 }}>
          已确认 {confirmed.length > 0 && `(${confirmed.length})`}
        </button>
      </div>

      {/* ── Pending table ── */}
      {tab === "pending" && (
        <div style={{ overflow: "auto", maxHeight: "calc(100vh - 350px)", background: "#111827", borderRadius: 6, border: "1px solid #1e293b" }}>
          {pending.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "#666" }}>暂无待确认主线候选</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, color: "#c4c9d4" }}>
              <thead>
                <tr style={{ background: "#1a2236", color: "#8899bb", fontSize: 11, textTransform: "uppercase" }}>
                  <th style={th}>优先</th><th style={th}>题材</th><th style={th}>状态</th><th style={th}>类型</th>
                  <th style={th}>逻辑分</th><th style={th}>市场分</th><th style={th}>重大事件</th>
                  <th style={th}>原因</th><th style={th}>建议</th><th style={th}>操作</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((item) => (
                  <tr key={item.review_id} style={{ borderBottom: "1px solid #1e293b" }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#1a2a44"; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
                    <td style={td}>{n(item.review_priority)}</td>
                    <td style={td}><span style={{ color: "#88ccff", maxWidth: 200, display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={item.theme_name ?? ""}>{item.theme_name ?? item.subject_key}</span></td>
                    <td style={td}><StatusBadge state={item.machine_state} /></td>
                    <td style={td}>{item.mainline_type ?? "--"}</td>
                    <td style={td}>{n((item.scores_json as any)?.hybrid_logic_score)}</td>
                    <td style={td}>{n((item.scores_json as any)?.market_acceptance_score)}</td>
                    <td style={td}>{n((item.scores_json as any)?.major_event_score)}</td>
                    <td style={td}><span style={{ maxWidth: 180, display: "inline-block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={item.review_reason ?? ""}>{item.review_reason ?? "--"}</span></td>
                    <td style={td}>{item.suggested_human_decision ?? "--"}</td>
                    <td style={td}>
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        <OpBtn label="确认" color="#22c55e" onClick={() => handleConfirm(item.review_id)} />
                        <OpBtn label="观察" color="#f59e0b" onClick={() => handleDecision(item.review_id, "watch")} />
                        <OpBtn label="拒绝" color="#ef4444" onClick={() => handleDecision(item.review_id, "reject")} />
                        <OpBtn label="合并" color="#8b5cf6" onClick={() => handleMerge(item.review_id)} />
                        <OpBtn label="详情" color="#3b82f6" onClick={() => setSelected(item)} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Confirmed table ── */}
      {tab === "confirmed" && (
        <div style={{ overflow: "auto", maxHeight: "calc(100vh - 350px)", background: "#111827", borderRadius: 6, border: "1px solid #1e293b" }}>
          {confirmed.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "#666" }}>暂无已确认主线</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, color: "#c4c9d4" }}>
              <thead>
                <tr style={{ background: "#1a2236", color: "#8899bb", fontSize: 11, textTransform: "uppercase" }}>
                  <th style={th}>主线 ID</th><th style={th}>名称</th><th style={th}>canonical SK</th>
                  <th style={th}>类型</th><th style={th}>状态</th><th style={th}>生效日期</th><th style={th}>审核人</th>
                </tr>
              </thead>
              <tbody>
                {confirmed.map((item) => (
                  <tr key={item.mainline_id} style={{ borderBottom: "1px solid #1e293b" }}>
                    <td style={td}><span style={{ color: "#88ccff", fontSize: 11 }}>{item.mainline_id}</span></td>
                    <td style={td}><strong>{item.mainline_name}</strong></td>
                    <td style={td}><code style={{ fontSize: 10, color: "#aaa" }}>{item.canonical_subject_key}</code></td>
                    <td style={td}>{item.mainline_type ?? "--"}</td>
                    <td style={td}><StatusBadge state={item.identity_status} /></td>
                    <td style={td}>{item.valid_from}</td>
                    <td style={td}>{item.human_reviewer ?? "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Detail Drawer ── */}
      {selected && (
        <DetailDrawer item={selected} onClose={() => setSelected(null)} onConfirm={handleConfirm} onMerge={handleMerge}
          onDecision={handleDecision} />
      )}
    </div>
  );
};

// ── Detail Drawer ──

const DetailDrawer: React.FC<{
  item: MainlineReviewItem;
  onClose: () => void;
  onConfirm: (id: string) => void;
  onMerge: (id: string) => void;
  onDecision: (id: string, dec: string) => void;
}> = ({ item, onClose, onConfirm, onMerge, onDecision }) => {
  const scores = (item.scores_json ?? {}) as Record<string, unknown>;
  const evidence = (item.evidence_json ?? {}) as Record<string, unknown>;
  const risks = (item.risk_flags_json ?? {}) as Record<string, unknown>;
  return (
    <div style={{ position: "fixed", top: 0, right: 0, width: 480, height: "100vh", background: "#0f172a", borderLeft: "1px solid #1e293b", zIndex: 100, overflow: "auto", padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ margin: 0, color: "#e0e8ff", fontSize: 16 }}>{item.theme_name ?? item.subject_key}</h3>
        <button onClick={onClose} style={{ background: "none", border: "none", color: "#888", fontSize: 20, cursor: "pointer" }}>✕</button>
      </div>
      {/* Machine summary */}
      <Section title="机器判断摘要">
        <Row label="状态" value={item.machine_state} />
        <Row label="类型" value={item.mainline_type ?? "--"} />
        <Row label="路径" value={item.confirmation_path ?? "--"} />
        <Row label="原因" value={item.review_reason ?? "--"} />
        <Row label="建议" value={item.suggested_human_decision ?? "--"} />
      </Section>
      {/* Scores */}
      <Section title="评分">
        {[
          ["逻辑分", scores.hybrid_logic_score],
          ["规则逻辑", scores.rule_logic_score],
          ["LLM叙事", scores.llm_narrative_score],
          ["市场接受度", scores.market_acceptance_score],
          ["重大事件", scores.major_event_score],
          ["快线分", scores.fast_line_score],
          ["慢线分", scores.slow_line_score],
        ].map(([label, val]) => (
          <Row key={String(label)} label={String(label)} value={n(val as number | null | undefined)} />
        ))}
      </Section>
      {/* Risk */}
      {Object.keys(risks).length > 0 && (
        <Section title="风险标记">
          {Object.entries(risks).map(([k, v]) => {
            const vv: unknown = v;
            return (
              <div key={k} style={{ marginBottom: 4, fontSize: 12 }}>
                <span style={{ color: "#888" }}>{k}: </span>
                <span style={{ color: vv ? "#ff6666" : "#aaa" }}>{Array.isArray(vv) ? (vv as string[]).join(", ") : String(vv)}</span>
              </div>
            );
          })}
        </Section>
      )}
      {/* Evidence */}
      {evidence.event_chain ? (
        <Section title="事件链">
          <pre style={{ fontSize: 11, color: "#8899bb", whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>
            {JSON.stringify(evidence.event_chain, null, 2)}
          </pre>
        </Section>
      ) : null}
      {/* Actions */}
      <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
        <button onClick={() => onConfirm(item.review_id)} style={btnStyle("#22c55e")}>确认主线</button>
        <button onClick={() => onDecision(item.review_id, "watch")} style={btnStyle("#f59e0b")}>观察</button>
        <button onClick={() => onDecision(item.review_id, "reject")} style={btnStyle("#ef4444")}>拒绝</button>
        <button onClick={() => onMerge(item.review_id)} style={btnStyle("#8b5cf6")}>合并到已有主线</button>
      </div>
    </div>
  );
};

// ── helpers ──

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div style={{ marginBottom: 16, padding: 12, background: "#111827", borderRadius: 6, border: "1px solid #1e293b" }}>
    <div style={{ color: "#8899bb", fontSize: 12, fontWeight: 600, marginBottom: 8, textTransform: "uppercase" }}>{title}</div>
    {children}
  </div>
);

const Row: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12 }}>
    <span style={{ color: "#667" }}>{label}</span>
    <span style={{ color: "#c4c9d4", fontWeight: 500 }}>{value}</span>
  </div>
);

const StatusBadge: React.FC<{ state: string }> = ({ state }) => {
  const m: Record<string, string> = {
    machine_fast_candidate: "#22c55e", machine_slow_candidate: "#3b82f6",
    confirmed: "#44cc88", pending: "#f59e0b", rejected: "#ef4444",
  };
  return <span style={{ background: m[state] ?? "#333", color: "#fff", borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 500 }}>{state}</span>;
};

const OpBtn: React.FC<{ label: string; color: string; onClick: () => void }> = ({ label, color, onClick }) => (
  <button onClick={onClick} style={{ background: color, color: "#fff", border: "none", borderRadius: 3, padding: "3px 8px", cursor: "pointer", fontSize: 11, fontWeight: 500 }}>
    {label}
  </button>
);

const th: React.CSSProperties = { padding: "8px 10px", textAlign: "left", borderBottom: "2px solid #2a3a5a", whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "7px 10px", whiteSpace: "nowrap" };

const btnStyle = (color: string): React.CSSProperties => ({
  background: color, color: "#fff", border: "none", borderRadius: 4, padding: "8px 14px", cursor: "pointer", fontSize: 12, fontWeight: 500,
});
