import React, { useState, useEffect, useRef } from "react";

export interface ReviewOverride {
  field_path: string;
  field_class: "IDENTITY" | "ASSESSMENT" | "PLAN";
  ai_value: any;
  analyst_value: any;
  final_value: any;
  reason: string;
  author?: string;
  timestamp?: string;
}

interface OverrideEditorProps {
  fieldPath: string;
  fieldLabel: string;
  fieldClass: "IDENTITY" | "ASSESSMENT" | "PLAN";
  aiValue: any;
  currentAnalystValue: any;
  currentReason: string;
  onSave: (override: ReviewOverride) => void;
  onCancel: () => void;
  /** Optional: for array-type plan fields, pass the full array */
  arrayValue?: any[];
  /** Optional: index in array when editing a single plan item */
  arrayIndex?: number;
}

const colors = {
  border: "#243040",
  panel: "#0f1722",
  band: "#111b26",
  text: "#d8e6ef",
  muted: "#6f8898",
  accent: "#66d9ef",
  green: "#39ff14",
  yellow: "#ffd85e",
  red: "#ff8a65",
};

function fmt(value: any): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export function OverrideEditor({
  fieldPath,
  fieldLabel,
  fieldClass,
  aiValue,
  currentAnalystValue,
  currentReason,
  onSave,
  onCancel,
}: OverrideEditorProps) {
  const [analystValue, setAnalystValue] = useState<string>(fmt(currentAnalystValue));
  const [reason, setReason] = useState<string>(currentReason || "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSave = () => {
    const finalValue = analystValue.trim();
    if (!finalValue) return;
    onSave({
      field_path: fieldPath,
      field_class: fieldClass,
      ai_value: aiValue,
      analyst_value: finalValue,
      final_value: finalValue,
      reason: reason.trim(),
      author: "analyst",
      timestamp: new Date().toISOString(),
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSave();
    } else if (e.key === "Escape") {
      onCancel();
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        zIndex: 9998,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onCancel}
    >
      <div
        style={{
          background: "#162230",
          border: `1px solid ${colors.accent}`,
          borderRadius: 10,
          padding: 22,
          width: 420,
          maxWidth: "92vw",
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: colors.muted, marginBottom: 2, textTransform: "uppercase", letterSpacing: 1 }}>
            {fieldClass} · 分析师修正
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: colors.yellow }}>
            {fieldLabel}
          </div>
          <div style={{ fontSize: 10, color: colors.muted, marginTop: 2, fontFamily: "monospace" }}>
            {fieldPath}
          </div>
        </div>

        {/* AI value (readonly) */}
        <div style={{ marginBottom: 14 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: colors.muted, display: "block", marginBottom: 4 }}>
            AI 判断
          </label>
          <div style={{
            padding: "8px 10px",
            background: "#0c1118",
            border: `1px solid ${colors.border}`,
            borderRadius: 5,
            fontSize: 14,
            color: colors.text,
            minHeight: 24,
          }}>
            {fmt(aiValue) || <span style={{ color: colors.muted, fontStyle: "italic" }}>(无)</span>}
          </div>
        </div>

        {/* Analyst value (editable) */}
        <div style={{ marginBottom: 14 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: colors.yellow, display: "block", marginBottom: 4 }}>
            分析师修改
          </label>
          <input
            ref={inputRef}
            type="text"
            value={analystValue}
            onChange={(e) => setAnalystValue(e.target.value)}
            placeholder="输入修正后的值…"
            style={{
              width: "100%",
              padding: "8px 10px",
              fontSize: 14,
              borderRadius: 5,
              border: `1px solid ${colors.yellow}55`,
              background: "#0c1118",
              color: colors.green,
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>

        {/* Reason */}
        <div style={{ marginBottom: 18 }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: colors.muted, display: "block", marginBottom: 4 }}>
            修改原因
          </label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="例如：资金从高位题材切换到PCB容量方向"
            style={{
              width: "100%",
              padding: "8px 10px",
              fontSize: 13,
              borderRadius: 5,
              border: `1px solid ${colors.border}`,
              background: "#0c1118",
              color: colors.text,
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>

        {/* Final preview */}
        {analystValue.trim() && analystValue.trim() !== fmt(aiValue) && (
          <div style={{
            marginBottom: 14,
            padding: "8px 12px",
            background: `${colors.green}10`,
            border: `1px solid ${colors.green}30`,
            borderRadius: 5,
            fontSize: 12,
          }}>
            <span style={{ color: colors.muted }}>最终显示：</span>
            <span style={{ color: colors.green, fontWeight: 700, marginLeft: 4 }}>{analystValue.trim()}</span>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            style={{
              padding: "8px 18px",
              background: "transparent",
              color: colors.muted,
              border: `1px solid ${colors.border}`,
              borderRadius: 5,
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={!analystValue.trim()}
            style={{
              padding: "8px 18px",
              background: !analystValue.trim() ? "#1a3a5c" : "#3182ce",
              color: !analystValue.trim() ? colors.muted : "#fff",
              border: "none",
              borderRadius: 5,
              cursor: analystValue.trim() ? "pointer" : "not-allowed",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            保存 (⌘↵)
          </button>
        </div>
      </div>
    </div>
  );
}

/** Build a human-readable label from a ReviewDocument field path. */
export function fieldPathLabel(fieldPath: string): string {
  if (fieldPath.startsWith("themes[")) {
    const match = fieldPath.match(/^themes\[(.+?)\]\.(.+)$/);
    if (match) {
      const entity = match[1];
      const field = match[2];
      const fieldNames: Record<string, string> = { name: "题材名称" };
      return `题材 [${entity}] · ${fieldNames[field] || field}`;
    }
  }
  if (fieldPath.startsWith("stocks[")) {
    const match = fieldPath.match(/^stocks\[(.+?)\]\.(.+)$/);
    if (match) {
      const entity = match[1];
      const field = match[2];
      const fieldNames: Record<string, string> = {
        theme_name: "所属题材",
        subject_key: "题材Key",
      };
      return `股票 [${entity}] · ${fieldNames[field] || field}`;
    }
  }
  if (fieldPath.startsWith("plan.")) {
    const field = fieldPath.replace("plan.", "");
    const fieldNames: Record<string, string> = {
      allowed_actions: "允许操作",
      forbidden_actions: "禁止操作",
      watch_themes: "关注题材",
      scenario: "场景",
    };
    return `明日计划 · ${fieldNames[field] || field}`;
  }
  return fieldPath;
}
