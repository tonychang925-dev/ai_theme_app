import React, { useEffect, useState, useCallback } from "react";

// ── Types ──

interface Playbook {
  trade_date: string;
  subject_id: string;
  subject_name: string;
  ai_draft: boolean;
  analyst_reviewed: boolean;
  phase: string;
  phase_label: string;
  strategy: string;
  entry_condition: string;
  exit_condition: string;
  invalidation_condition: string;
  tomorrow_watchpoints: string[];
  key_risk: string;
  analyst_overrides: Record<string, { ai_value: string; analyst_value: string; reason: string }>;
  review?: {
    yesterday_prediction: string;
    today_actual: string;
    prediction_correct: boolean | null;
    prediction_delta: string;
  };
}

interface Props {
  tradeDate: string;
  subjectId: string;
  subjectName?: string;
  onClose: () => void;
}

// ── Helpers ──

type FieldStatus = "ai" | "confirmed" | "modified" | "rejected";

function statusColor(s: FieldStatus): string {
  return s === "ai" ? "#a0aec0" : s === "confirmed" ? "#38a169" : s === "modified" ? "#d69e2e" : "#e53e3e";
}

function statusBg(s: FieldStatus): string {
  return s === "ai" ? "#f7fafc" : s === "confirmed" ? "#f0fff4" : s === "modified" ? "#fffff0" : "#fff5f5";
}

const PHASE_BADGE: Record<string, string> = {
  start: "🚀 启动", fermentation: "🔥 发酵", divergence: "⚡ 分歧",
  repair: "🔧 修复", fade_watch: "⚠️ 退潮观察", fade_confirmed: "❌ 退潮确认",
};

// ── Component ──

export function PlaybookPanel({ tradeDate, subjectId, subjectName, onClose }: Props) {
  const [playbook, setPlaybook] = useState<Playbook | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [fieldStatuses, setFieldStatuses] = useState<Record<string, FieldStatus>>({});
  const [overrides, setOverrides] = useState<Record<string, { ai_value: string; analyst_value: string; reason: string }>>({});
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});

  const fetchPlaybook = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/v1/playbook/${tradeDate}/${encodeURIComponent(subjectId)}`);
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json();
      setPlaybook(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [tradeDate, subjectId]);

  useEffect(() => { fetchPlaybook(); }, [fetchPlaybook]);

  const handleFieldChange = (field: string, value: string) => {
    setDraftValues((prev) => ({ ...prev, [field]: value }));
  };

  const handleFieldConfirm = (field: string) => {
    const aiValue = (playbook as any)?.[field] || "";
    const newValue = draftValues[field] ?? aiValue;
    if (newValue !== aiValue) {
      setFieldStatuses((prev) => ({ ...prev, [field]: "modified" }));
      setOverrides((prev) => ({
        ...prev,
        [field]: { ai_value: typeof aiValue === "string" ? aiValue : JSON.stringify(aiValue), analyst_value: newValue, reason: "" },
      }));
    } else {
      setFieldStatuses((prev) => ({ ...prev, [field]: "confirmed" }));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const resp = await fetch(`/api/v1/playbook/${tradeDate}/${encodeURIComponent(subjectId)}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...playbook, ...Object.fromEntries(Object.entries(draftValues).map(([k, v]) => [k, v])), analyst_overrides: overrides }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch { /* ignore */ } finally { setSaving(false); }
  };

  if (loading) return <div style={{ padding: 24 }}>Loading playbook…</div>;
  if (error) return <div style={{ padding: 24, color: "#e53e3e" }}>Error: {error}</div>;
  if (!playbook) return <div style={{ padding: 24 }}>No data.</div>;

  const overrideCount = Object.keys(overrides).length;
  const getVal = (field: string) => draftValues[field] ?? (playbook as any)[field] ?? "";

  return (
    <div style={{ padding: 20, maxWidth: 680 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0 }}>📋 {playbook.subject_name || subjectName || subjectId}</h2>
          <span style={{ fontSize: 14, color: "#718096" }}>
            {PHASE_BADGE[playbook.phase] || playbook.phase} · {playbook.phase_label}
          </span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {overrideCount > 0 && (
            <span style={{ fontSize: 12, color: "#d69e2e", background: "#fefcbf", padding: "2px 8px", borderRadius: 4 }}>
              {overrideCount} override{overrideCount !== 1 ? "s" : ""}
            </span>
          )}
          <button onClick={onClose} style={{ padding: "4px 12px", cursor: "pointer" }}>✕ Close</button>
        </div>
      </div>

      {/* Review Panel */}
      {playbook.review && (
        <div style={{ marginBottom: 24, padding: 16, background: "#fffbeb", border: "1px solid #f6e05e", borderRadius: 8 }}>
          <h4 style={{ margin: "0 0 10px 0", fontSize: 14 }}>📊 Review — Prediction vs Actual</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 13 }}>
            <div>
              <div style={{ color: "#718096", marginBottom: 4 }}>Yesterday's View</div>
              <div style={{ background: "#fff", padding: 8, borderRadius: 4, border: "1px solid #e2e8f0" }}>
                {playbook.review.yesterday_prediction || "—"}
              </div>
            </div>
            <div>
              <div style={{ color: "#718096", marginBottom: 4 }}>Today's Actual</div>
              <div style={{ background: "#fff", padding: 8, borderRadius: 4, border: "1px solid #e2e8f0" }}>
                {playbook.review.today_actual || "—"}
              </div>
            </div>
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 12 }}>
            <span style={{ fontSize: 12, color: "#718096" }}>Analyst verdict:</span>
            {[true, false].map((verdict) => (
              <label key={String(verdict)} style={{ fontSize: 12, cursor: "pointer" }}>
                <input type="radio" name="prediction_correct"
                  checked={playbook.review?.prediction_correct === verdict}
                  onChange={() => {
                    setPlaybook((prev) => prev ? {
                      ...prev,
                      review: { ...prev.review!, prediction_correct: verdict },
                    } : prev);
                  }} />
                {" "}{verdict ? "✓ Correct" : "✗ Wrong"}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Strategy + Phase */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
        <Field label="Strategy" field="strategy" value={getVal("strategy")} status={fieldStatuses["strategy"] || "ai"}
          onChange={(v) => handleFieldChange("strategy", v)} onConfirm={() => handleFieldConfirm("strategy")} />
        <Field label="Key Risk" field="key_risk" value={getVal("key_risk")} status={fieldStatuses["key_risk"] || "ai"}
          onChange={(v) => handleFieldChange("key_risk", v)} onConfirm={() => handleFieldConfirm("key_risk")} />
      </div>

      {/* Conditions */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
        <Field label="Entry Condition" field="entry_condition" value={getVal("entry_condition")} status={fieldStatuses["entry_condition"] || "ai"}
          onChange={(v) => handleFieldChange("entry_condition", v)} onConfirm={() => handleFieldConfirm("entry_condition")} multiline />
        <Field label="Exit Condition" field="exit_condition" value={getVal("exit_condition")} status={fieldStatuses["exit_condition"] || "ai"}
          onChange={(v) => handleFieldChange("exit_condition", v)} onConfirm={() => handleFieldConfirm("exit_condition")} multiline />
        <Field label="Invalidation Condition" field="invalidation_condition" value={getVal("invalidation_condition")} status={fieldStatuses["invalidation_condition"] || "ai"}
          onChange={(v) => handleFieldChange("invalidation_condition", v)} onConfirm={() => handleFieldConfirm("invalidation_condition")} multiline />
      </div>

      {/* Watchpoints */}
      <div style={{ marginBottom: 20 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: "#4a5568", marginBottom: 8, display: "block" }}>
          Tomorrow's Watchpoints
        </label>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {playbook.tomorrow_watchpoints.map((wp, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, padding: "6px 10px", background: "#f7fafc", borderRadius: 4 }}>
              <span>{wp}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <button onClick={handleSave} disabled={saving}
          style={{ padding: "10px 24px", fontSize: 15, fontWeight: 600, background: saved ? "#38a169" : "#3182ce", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", opacity: saving ? 0.6 : 1 }}>
          {saved ? "Saved ✓" : saving ? "Saving…" : "Save Playbook"}
        </button>
        <button onClick={onClose} style={{ padding: "10px 16px", background: "#e2e8f0", border: "none", borderRadius: 6, cursor: "pointer" }}>Cancel</button>
      </div>
    </div>
  );
}

// ── Field sub-component ──

function Field({
  label, field, value, status, multiline,
  onChange, onConfirm,
}: {
  label: string; field: string; value: string; status: FieldStatus; multiline?: boolean;
  onChange: (v: string) => void; onConfirm: () => void;
}) {
  const [editing, setEditing] = useState(false);
  return (
    <div style={{ padding: 10, border: `1px solid ${statusColor(status)}`, borderRadius: 6, background: statusBg(status) }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: "#4a5568" }}>{label}</label>
        <span style={{ fontSize: 11, color: statusColor(status) }}>
          {status === "ai" ? "AI" : status === "confirmed" ? "✓" : status === "modified" ? "✎ modified" : "✗ rejected"}
        </span>
      </div>
      {editing ? (
        multiline ? (
          <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={3}
            style={{ width: "100%", padding: 6, fontSize: 14, borderRadius: 4, border: "1px solid #cbd5e0" }} />
        ) : (
          <input value={value} onChange={(e) => onChange(e.target.value)}
            style={{ width: "100%", padding: 6, fontSize: 14, borderRadius: 4, border: "1px solid #cbd5e0" }} />
        )
      ) : (
        <div style={{ fontSize: 14, whiteSpace: "pre-wrap", color: status === "ai" ? "#718096" : "#1a202c" }}>
          {value || <span style={{ color: "#cbd5e0" }}>empty</span>}
        </div>
      )}
      <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
        {editing ? (
          <>
            <button onClick={() => { onConfirm(); setEditing(false); }}
              style={{ fontSize: 12, padding: "2px 10px", background: "#38a169", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer" }}>Confirm</button>
            <button onClick={() => setEditing(false)}
              style={{ fontSize: 12, padding: "2px 10px", background: "#e2e8f0", border: "none", borderRadius: 3, cursor: "pointer" }}>Cancel</button>
          </>
        ) : (
          <button onClick={() => setEditing(true)}
            style={{ fontSize: 12, padding: "2px 10px", background: "#edf2f7", border: "1px solid #e2e8f0", borderRadius: 3, cursor: "pointer" }}>Edit</button>
        )}
      </div>
    </div>
  );
}
