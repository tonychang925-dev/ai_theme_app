import React, { useEffect, useState, useCallback } from "react";

// ── Types ──

interface CognitionCard {
  trade_date: string;
  subject_id: string;
  subject_name: string;
  ai_draft: boolean;
  analyst_reviewed: boolean;
  trading_style: string;
  market_phase: string;
  phase_raw: string;
  event_stimuli: string[];
  current_leaders: string[];
  potential_leaders: string[];
  bull_pool: string[];
  bear_pool: string[];
  yesterday_view: string;
  today_actual: string;
  tomorrow_view: string;
  analyst_notes: string;
  analyst_overrides: Record<string, OverrideChange>;
  evidence_refs: string[];
}

interface OverrideChange {
  ai_value: string;
  analyst_value: string;
  reason: string;
}

// ── Props ──

interface Props {
  tradeDate: string;
  subjectId: string;
  subjectName?: string;
  onClose: () => void;
}

// ── Status colors ──

type FieldStatus = "ai" | "confirmed" | "modified" | "rejected";

function statusColor(s: FieldStatus): string {
  return s === "ai" ? "#a0aec0" : s === "confirmed" ? "#38a169" : s === "modified" ? "#d69e2e" : "#e53e3e";
}

function statusBg(s: FieldStatus): string {
  return s === "ai" ? "#f7fafc" : s === "confirmed" ? "#f0fff4" : s === "modified" ? "#fffff0" : "#fff5f5";
}

// ── Component ──

export function CognitionWorkspace({ tradeDate, subjectId, subjectName, onClose }: Props) {
  const [card, setCard] = useState<CognitionCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Track which fields have been modified by analyst
  const [fieldStatuses, setFieldStatuses] = useState<Record<string, FieldStatus>>({});
  const [overrides, setOverrides] = useState<Record<string, OverrideChange>>({});
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});

  const fetchCard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`http://127.0.0.1:8090/api/v1/cognition/${tradeDate}/${encodeURIComponent(subjectId)}`);
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json();
      setCard(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [tradeDate, subjectId]);

  useEffect(() => {
    fetchCard();
  }, [fetchCard]);

  // ── Field edit handler ──
  const handleFieldChange = (field: string, value: string) => {
    setDraftValues((prev) => ({ ...prev, [field]: value }));
  };

  const handleFieldConfirm = (field: string) => {
    const aiValue = getCardValue(field);
    const newValue = draftValues[field] ?? aiValue;

    if (newValue !== aiValue) {
      setFieldStatuses((prev) => ({ ...prev, [field]: "modified" }));
      setOverrides((prev) => ({
        ...prev,
        [field]: { ai_value: aiValue, analyst_value: newValue, reason: "" },
      }));
    } else {
      setFieldStatuses((prev) => ({ ...prev, [field]: "confirmed" }));
      setOverrides((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const handleFieldReject = (field: string) => {
    setFieldStatuses((prev) => ({ ...prev, [field]: "rejected" }));
    setOverrides((prev) => ({
      ...prev,
      [field]: {
        ai_value: getCardValue(field),
        analyst_value: "[REJECTED]",
        reason: "Analyst rejected AI value",
      },
    }));
  };

  const getCardValue = (field: string): string => {
    if (!card) return "";
    // Handle array fields
    if (["event_stimuli", "current_leaders", "potential_leaders", "bull_pool", "bear_pool"].includes(field)) {
      const arr = (card as any)[field] || [];
      return arr.join("\n");
    }
    return (card as any)[field] || "";
  };

  const getDisplayValue = (field: string): string => {
    if (field in draftValues) return draftValues[field];
    return getCardValue(field);
  };

  // ── Save handler ──
  const handleSave = async () => {
    setSaving(true);
    try {
      const resp = await fetch(`http://127.0.0.1:8090/api/v1/cognition/${tradeDate}/${encodeURIComponent(subjectId)}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...card,
          ...Object.fromEntries(
            Object.entries(draftValues).map(([k, v]) => [k, v])
          ),
          analyst_overrides: overrides,
        }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div style={{ padding: 24 }}>Loading cognition card…</div>;
  if (error) return <div style={{ padding: 24, color: "#e53e3e" }}>Error: {error} <button onClick={fetchCard}>Retry</button></div>;
  if (!card) return <div style={{ padding: 24 }}>No data available.</div>;

  const overrideCount = Object.keys(overrides).length;

  return (
    <div style={{ padding: 20, maxWidth: 680 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0 }}>{card.subject_name || subjectName || subjectId}</h2>
          <span style={{ fontSize: 13, color: "#718096" }}>
            {tradeDate} · {card.phase_raw} · {card.ai_draft ? "AI Draft" : "Analyst Reviewed"}
          </span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {overrideCount > 0 && (
            <span style={{ fontSize: 12, color: "#d69e2e", background: "#fefcbf", padding: "2px 8px", borderRadius: 4 }}>
              {overrideCount} override{overrideCount !== 1 ? "s" : ""}
            </span>
          )}
          <button onClick={onClose} style={{ padding: "4px 12px", cursor: "pointer" }}>✕ Close</button>
        </div>
      </div>

      {/* Fields */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <EditableField label="Trading Style" field="trading_style" card={card}
          value={getDisplayValue("trading_style")} status={fieldStatuses["trading_style"] || "ai"}
          onChange={(v) => handleFieldChange("trading_style", v)}
          onConfirm={() => handleFieldConfirm("trading_style")}
          onReject={() => handleFieldReject("trading_style")} />

        <EditableField label="Market Phase" field="market_phase" card={card}
          value={getDisplayValue("market_phase")} status={fieldStatuses["market_phase"] || "ai"}
          onChange={(v) => handleFieldChange("market_phase", v)}
          onConfirm={() => handleFieldConfirm("market_phase")}
          onReject={() => handleFieldReject("market_phase")} />

        <EditableField label="Event Stimuli" field="event_stimuli" card={card} multiline
          value={getDisplayValue("event_stimuli")} status={fieldStatuses["event_stimuli"] || "ai"}
          onChange={(v) => handleFieldChange("event_stimuli", v)}
          onConfirm={() => handleFieldConfirm("event_stimuli")}
          onReject={() => handleFieldReject("event_stimuli")} />

        <EditableField label="Current Leaders" field="current_leaders" card={card} multiline
          value={getDisplayValue("current_leaders")} status={fieldStatuses["current_leaders"] || "ai"}
          onChange={(v) => handleFieldChange("current_leaders", v)}
          onConfirm={() => handleFieldConfirm("current_leaders")}
          onReject={() => handleFieldReject("current_leaders")} />

        <EditableField label="Potential Leaders" field="potential_leaders" card={card} multiline
          value={getDisplayValue("potential_leaders")} status={fieldStatuses["potential_leaders"] || "ai"}
          onChange={(v) => handleFieldChange("potential_leaders", v)}
          onConfirm={() => handleFieldConfirm("potential_leaders")}
          onReject={() => handleFieldReject("potential_leaders")} />

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <EditableField label="Bull Pool" field="bull_pool" card={card} multiline small
            value={getDisplayValue("bull_pool")} status={fieldStatuses["bull_pool"] || "ai"}
            onChange={(v) => handleFieldChange("bull_pool", v)}
            onConfirm={() => handleFieldConfirm("bull_pool")}
            onReject={() => handleFieldReject("bull_pool")} />
          <EditableField label="Bear Pool" field="bear_pool" card={card} multiline small
            value={getDisplayValue("bear_pool")} status={fieldStatuses["bear_pool"] || "ai"}
            onChange={(v) => handleFieldChange("bear_pool", v)}
            onConfirm={() => handleFieldConfirm("bear_pool")}
            onReject={() => handleFieldReject("bear_pool")} />
        </div>

        <EditableField label="Yesterday View" field="yesterday_view" card={card}
          value={getDisplayValue("yesterday_view")} status={fieldStatuses["yesterday_view"] || "ai"}
          onChange={(v) => handleFieldChange("yesterday_view", v)}
          onConfirm={() => handleFieldConfirm("yesterday_view")}
          onReject={() => handleFieldReject("yesterday_view")} />

        <EditableField label="Today Actual" field="today_actual" card={card}
          value={getDisplayValue("today_actual")} status={fieldStatuses["today_actual"] || "ai"}
          onChange={(v) => handleFieldChange("today_actual", v)}
          onConfirm={() => handleFieldConfirm("today_actual")}
          onReject={() => handleFieldReject("today_actual")} />

        <EditableField label="Tomorrow View" field="tomorrow_view" card={card}
          value={getDisplayValue("tomorrow_view")} status={fieldStatuses["tomorrow_view"] || "ai"}
          onChange={(v) => handleFieldChange("tomorrow_view", v)}
          onConfirm={() => handleFieldConfirm("tomorrow_view")}
          onReject={() => handleFieldReject("tomorrow_view")} />

        <EditableField label="Analyst Notes" field="analyst_notes" card={card} multiline
          value={getDisplayValue("analyst_notes")} status={fieldStatuses["analyst_notes"] || "ai"}
          onChange={(v) => handleFieldChange("analyst_notes", v)}
          onConfirm={() => handleFieldConfirm("analyst_notes")}
          onReject={() => handleFieldReject("analyst_notes")} />
      </div>

      {/* Actions */}
      <div style={{ marginTop: 24, display: "flex", gap: 12, alignItems: "center" }}>
        <button onClick={handleSave} disabled={saving}
          style={{
            padding: "10px 24px", fontSize: 15, fontWeight: 600,
            background: saved ? "#38a169" : "#3182ce", color: "#fff",
            border: "none", borderRadius: 6, cursor: "pointer",
            opacity: saving ? 0.6 : 1,
          }}>
          {saved ? "Saved ✓" : saving ? "Saving…" : "Save Cognition Card"}
        </button>
        <button onClick={onClose}
          style={{ padding: "10px 16px", fontSize: 14, background: "#e2e8f0", border: "none", borderRadius: 6, cursor: "pointer" }}>
          Cancel
        </button>
        {overrideCount > 0 && (
          <span style={{ fontSize: 12, color: "#d69e2e" }}>
            {overrideCount} field{overrideCount !== 1 ? "s" : ""} modified — will be logged to OverrideLog
          </span>
        )}
      </div>
    </div>
  );
}

// ── EditableField sub-component ──

function EditableField({
  label, field, value, status, multiline, small,
  onChange, onConfirm, onReject,
}: {
  label: string;
  field: string;
  card: CognitionCard;
  value: string;
  status: FieldStatus;
  multiline?: boolean;
  small?: boolean;
  onChange: (v: string) => void;
  onConfirm: () => void;
  onReject: () => void;
}) {
  const [editing, setEditing] = useState(false);

  return (
    <div style={{
      padding: 10,
      border: `1px solid ${statusColor(status)}`,
      borderRadius: 6,
      background: statusBg(status),
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <label style={{ fontSize: 13, fontWeight: 600, color: "#4a5568" }}>{label}</label>
        <div style={{ display: "flex", gap: 4 }}>
          {status === "modified" && <span style={{ fontSize: 11, color: "#d69e2e" }}>modified</span>}
          {status === "confirmed" && <span style={{ fontSize: 11, color: "#38a169" }}>confirmed</span>}
          {status === "rejected" && <span style={{ fontSize: 11, color: "#e53e3e" }}>rejected</span>}
          {status === "ai" && <span style={{ fontSize: 11, color: "#a0aec0" }}>AI draft</span>}
        </div>
      </div>

      {editing ? (
        multiline ? (
          <textarea value={value} onChange={(e) => onChange(e.target.value)}
            rows={small ? 3 : 4}
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
              style={{ fontSize: 12, padding: "2px 10px", background: "#38a169", color: "#fff", border: "none", borderRadius: 3, cursor: "pointer" }}>
              Confirm
            </button>
            <button onClick={() => setEditing(false)}
              style={{ fontSize: 12, padding: "2px 10px", background: "#e2e8f0", border: "none", borderRadius: 3, cursor: "pointer" }}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <button onClick={() => setEditing(true)}
              style={{ fontSize: 12, padding: "2px 10px", background: "#edf2f7", border: "1px solid #e2e8f0", borderRadius: 3, cursor: "pointer" }}>
              Edit
            </button>
            {status !== "confirmed" && (
              <button onClick={onConfirm}
                style={{ fontSize: 12, padding: "2px 10px", background: "#f0fff4", border: "1px solid #38a169", borderRadius: 3, color: "#38a169", cursor: "pointer" }}>
                ✓ Confirm
              </button>
            )}
            {status !== "rejected" && (
              <button onClick={onReject}
                style={{ fontSize: 12, padding: "2px 10px", background: "#fff5f5", border: "1px solid #e53e3e", borderRadius: 3, color: "#e53e3e", cursor: "pointer" }}>
                ✗ Reject
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
