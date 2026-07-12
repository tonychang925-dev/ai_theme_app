import React, { useState } from "react";
import {
  OverrideEditor,
  fieldPathLabel,
  type ReviewOverride,
} from "./OverrideEditor";

export type ReviewDocumentMode = "editable" | "readonly";

export interface ReviewDocument {
  metadata?: Record<string, any>;
  summary?: Record<string, any>;
  market?: Record<string, any>;
  emotion?: Record<string, any>;
  themes?: Array<Record<string, any>>;
  stocks?: Array<Record<string, any>>;
  capital?: Record<string, any>;
  limit_up?: Record<string, any>;
  plan?: Record<string, any>;
  risk?: Record<string, any>;
  quality?: Record<string, any>;
  field_provenance?: Record<string, any>;
  audit?: Record<string, any>;
}

/** Context needed to render the OverrideEditor for a specific field. */
interface EditingContext {
  fieldPath: string;
  fieldClass: "IDENTITY" | "ASSESSMENT" | "PLAN";
  aiValue: any;
  analystValue: any;
  reason: string;
}

interface Props {
  document: ReviewDocument | null | undefined;
  mode: ReviewDocumentMode;
  /** Current overrides (used only for display, actual state managed by parent) */
  overrides?: ReviewOverride[];
  /** Called when user saves an override from the editor */
  onOverridesChange?: (overrides: ReviewOverride[]) => void;
  /** Called to persist overrides to backend */
  onSave?: () => void;
  saving?: boolean;
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

export function ReviewDocumentView({
  document,
  mode,
  overrides,
  onOverridesChange,
  onSave,
  saving,
}: Props) {
  const [editingContext, setEditingContext] = useState<EditingContext | null>(null);

  if (!document) {
    return (
      <div style={{ padding: 24, color: colors.muted, background: "#0c1118" }}>
        暂无复盘报告
      </div>
    );
  }

  const isEditable = !!(mode === "editable" && onOverridesChange);

  const metadata = document.metadata || {};
  const quality = document.quality || {};
  const sections = (quality.sections || {}) as Record<string, any>;
  const themes = Array.isArray(document.themes) ? document.themes : [];
  const stocks = Array.isArray(document.stocks) ? document.stocks : [];
  const capital = document.capital || {};
  const institution = Array.isArray(capital.institution) ? capital.institution : [];
  const hotMoney = Array.isArray(capital.hot_money) ? capital.hot_money : [];
  const plan = document.plan || {};

  const handleOverrideSave = (override: ReviewOverride) => {
    if (!onOverridesChange) return;

    // Merge with existing overrides: replace any override for the same field_path
    const existing = overrides || [];
    const merged = existing.filter((o) => o.field_path !== override.field_path);
    merged.push(override);
    onOverridesChange(merged);
    setEditingContext(null);
  };

  /** Build editing context for a theme name field. */
  const openThemeNameEditor = (theme: Record<string, any>, idx: number) => {
    const nameObj = theme.name || {};
    const themeKey = theme.theme_key || theme.subject_key || String(idx);
    const fieldPath = `themes[${themeKey}].name`;

    // Look up existing override for this field
    const existing = (overrides || []).find((o) => o.field_path === fieldPath);

    setEditingContext({
      fieldPath,
      fieldClass: "IDENTITY",
      aiValue: existing?.ai_value ?? (nameObj.ai_value || nameValue(theme.name)),
      analystValue: existing?.analyst_value ?? (nameObj.analyst_value || ""),
      reason: existing?.reason ?? (nameObj.reason || ""),
    });
  };

  /** Build editing context for a stock theme_name field. */
  const openStockThemeEditor = (stock: Record<string, any>, idx: number) => {
    const stockCode = stock.stock_code || stock.stock_id || String(idx);
    const currentName = stock.theme_name || stock.subject_key || "";
    const fieldPath = `stocks[${stockCode}].theme_name`;

    const existing = (overrides || []).find((o) => o.field_path === fieldPath);

    setEditingContext({
      fieldPath,
      fieldClass: "IDENTITY",
      aiValue: existing?.ai_value ?? nameValue(currentName),
      analystValue: existing?.analyst_value ?? "",
      reason: existing?.reason ?? "",
    });
  };

  /** Build editing context for a plan field. */
  const openPlanEditor = (field: string, currentValue: any) => {
    const fieldPath = `plan.${field}`;
    const existing = (overrides || []).find((o) => o.field_path === fieldPath);
    const currentText = Array.isArray(currentValue) ? currentValue.join("\n") : String(currentValue || "");

    setEditingContext({
      fieldPath,
      fieldClass: "PLAN",
      aiValue: existing?.ai_value ?? currentText,
      analystValue: existing?.analyst_value ?? "",
      reason: existing?.reason ?? "",
    });
  };

  // ── Look up overrides for display ──
  const overrideMap = new Map<string, ReviewOverride>();
  for (const o of overrides || []) {
    overrideMap.set(o.field_path, o);
  }

  return (
    <div style={{ color: colors.text, background: "#0c1118", minHeight: "100%" }}>
      {/* Header */}
      <div style={{ padding: "14px 18px", borderBottom: `1px solid ${colors.border}`, background: colors.band, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 18, color: colors.accent, letterSpacing: 0 }}>统一复盘报告</h2>
        <Badge tone={quality.overall === "READY" ? "good" : "warn"}>{String(quality.overall || "UNKNOWN")}</Badge>
        <Badge>{mode === "editable" ? "编辑态" : "只读"}</Badge>
        {isEditable && onSave && (
          <button
            onClick={onSave}
            disabled={saving}
            style={{
              fontSize: 12,
              padding: "4px 12px",
              background: saving ? "#1a3a5c" : "#38a169",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: saving ? "not-allowed" : "pointer",
              marginLeft: 8,
            }}
          >
            {saving ? "保存中…" : "保存修正"}
          </button>
        )}
        <span style={{ marginLeft: "auto", fontSize: 12, color: colors.muted }}>
          {String(metadata.trade_date || "")} · {String(metadata.document_schema_version || "")} · {String(metadata.assembler_version || "")}
          {(overrides || []).length > 0 && (
            <span style={{ marginLeft: 8, color: colors.yellow }}>{overrides!.length} 项修正</span>
          )}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.15fr) minmax(320px, 0.85fr)", gap: 0 }}>
        <main style={{ minWidth: 0 }}>
          <Section title="核心结论" quality={sections.summary}>
            <KeyValue label="主线题材" value={nameValue(document.summary?.primary_theme)} strong />
            <KeyValue label="市场结论" value={text(document.summary?.market_conclusion)} />
            <KeyValue label="主线叙事" value={text(document.summary?.main_story)} />
          </Section>

          <Section title="市场状态" quality={sections.market}>
            <MetricGrid
              items={[
                ["涨停", document.market?.limit_up_count],
                ["跌停", document.market?.limit_down_count],
                ["上涨", document.market?.up_count],
                ["下跌", document.market?.down_count],
                ["活跃资金", formatYi(document.market?.active_capital_yi)],
                ["最高板", document.market?.max_board_height],
              ]}
            />
          </Section>

          <Section title="情绪周期" quality={sections.emotion}>
            <MetricGrid
              items={[
                ["阶段", document.emotion?.phase],
                ["分数", document.emotion?.score],
                ["风险", document.emotion?.risk_level],
                ["置信度", formatPercent(document.emotion?.confidence)],
              ]}
            />
            <KeyValue label="策略" value={text(document.emotion?.strategy)} />
          </Section>

          <Section title="题材结构" quality={sections.themes}>
            <CompactTable
              rows={themes.slice(0, 12)}
              columns={[
                [
                  "题材",
                  (row, idx) => {
                    const themeKey = row.theme_key || row.subject_key || String(idx);
                    const fieldPath = `themes[${themeKey}].name`;
                    const ov = overrideMap.get(fieldPath);
                    const display = ov?.final_value ?? nameValue(row.name);
                    const hasOverride = !!ov;
                    return (
                      <span
                        onClick={isEditable ? () => openThemeNameEditor(row, idx) : undefined}
                        style={{
                          cursor: isEditable ? "pointer" : "default",
                          color: hasOverride ? colors.green : colors.text,
                          borderBottom: isEditable ? `1px dashed ${colors.muted}` : "none",
                          padding: "1px 2px",
                          borderRadius: 2,
                        }}
                        title={isEditable ? "点击修正题材名称" : undefined}
                      >
                        {display || "-"}
                        {isEditable && <span style={{ marginLeft: 4, fontSize: 10, color: colors.muted, opacity: 0.5 }}>✎</span>}
                      </span>
                    );
                  },
                ],
                ["角色", (row) => text(row.role)],
                ["阶段", (row) => text(row.stage)],
                ["强度", (row) => text(row.strength_score)],
              ]}
            />
          </Section>

          <Section title="强势股票池" quality={sections.stocks}>
            <CompactTable
              rows={stocks.slice(0, 12)}
              columns={[
                ["代码", (row) => text(row.stock_code || row.stock_id)],
                ["名称", (row) => text(row.stock_name)],
                [
                  "题材",
                  (row, idx) => {
                    const stockCode = row.stock_code || row.stock_id || String(idx);
                    const fieldPath = `stocks[${stockCode}].theme_name`;
                    const ov = overrideMap.get(fieldPath);
                    const display = ov?.final_value ?? text(row.theme_name || row.subject_key);
                    const hasOverride = !!ov;
                    return (
                      <span
                        onClick={isEditable ? () => openStockThemeEditor(row, idx) : undefined}
                        style={{
                          cursor: isEditable ? "pointer" : "default",
                          color: hasOverride ? colors.green : colors.text,
                          borderBottom: isEditable ? `1px dashed ${colors.muted}` : "none",
                          padding: "1px 2px",
                          borderRadius: 2,
                        }}
                        title={isEditable ? "点击修正股票所属题材" : undefined}
                      >
                        {display || "-"}
                        {isEditable && <span style={{ marginLeft: 4, fontSize: 10, color: colors.muted, opacity: 0.5 }}>✎</span>}
                      </span>
                    );
                  },
                ],
                ["角色", (row) => text(row.role || row.watch_status)],
                ["高度", (row) => text(row.board_height || row.board_count)],
              ]}
            />
          </Section>
        </main>

        <aside style={{ minWidth: 0, borderLeft: `1px solid ${colors.border}` }}>
          <Section title="资金证据" quality={sections.capital}>
            <MiniList title="机构方向" rows={institution.slice(0, 8)} />
            <MiniList title="游资方向" rows={hotMoney.slice(0, 8)} />
          </Section>

          <Section title="涨停分类" quality={sections.limit_up}>
            <KeyValue label="总数" value={text(document.limit_up?.total)} strong />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              {(Array.isArray(document.limit_up?.categories) ? document.limit_up?.categories : []).slice(0, 18).map((item: any, idx: number) => (
                <span key={`${text(item.theme_key)}-${idx}`} style={{ fontSize: 12, color: colors.text, border: `1px solid ${colors.border}`, borderRadius: 4, padding: "3px 7px", background: "#101a24" }}>
                  {text(item.name)}
                </span>
              ))}
            </div>
          </Section>

          <Section title="明日计划" quality={sections.plan}>
            <KeyValue label="场景" value={text(plan.scenario)} strong />

            {/* Allowed actions */}
            <EditableList
              label="允许"
              items={plan.allowed_actions}
              tone="good"
              editable={isEditable}
              field="allowed_actions"
              overrideMap={overrideMap}
              onEdit={(field, current) => openPlanEditor(field, current)}
            />

            {/* Forbidden actions */}
            <EditableList
              label="禁止"
              items={plan.forbidden_actions}
              tone="bad"
              editable={isEditable}
              field="forbidden_actions"
              overrideMap={overrideMap}
              onEdit={(field, current) => openPlanEditor(field, current)}
            />

            {/* Watch themes */}
            {isEditable ? (
              <EditableList
                label="关注"
                items={plan.watch_themes}
                tone="watch"
                editable={isEditable}
                field="watch_themes"
                overrideMap={overrideMap}
                onEdit={(field, current) => openPlanEditor(field, current)}
              />
            ) : (
              <ActionList label="关注" items={plan.watch_themes} tone="watch" />
            )}
          </Section>

          <Section title="风险控制" quality={sections.risk}>
            <KeyValue label="等级" value={text(document.risk?.risk_level)} strong />
            <ActionList label="风险" items={document.risk?.top_risks} tone="bad" />
          </Section>
        </aside>
      </div>

      {/* ── Override Editor Modal ── */}
      {editingContext && (
        <OverrideEditor
          fieldPath={editingContext.fieldPath}
          fieldLabel={fieldPathLabel(editingContext.fieldPath)}
          fieldClass={editingContext.fieldClass}
          aiValue={editingContext.aiValue}
          currentAnalystValue={editingContext.analystValue}
          currentReason={editingContext.reason}
          onSave={handleOverrideSave}
          onCancel={() => setEditingContext(null)}
        />
      )}
    </div>
  );
}

// ── Editable List component for plan arrays ──

function EditableList({
  label,
  items,
  tone,
  editable,
  field,
  overrideMap,
  onEdit,
}: {
  label: string;
  items: any;
  tone: "good" | "bad" | "watch";
  editable: boolean;
  field: string;
  overrideMap: Map<string, ReviewOverride>;
  onEdit: (field: string, currentValue: any) => void;
}) {
  const list = Array.isArray(items) ? items : [];
  const color = tone === "good" ? colors.green : tone === "bad" ? colors.red : colors.yellow;
  const fieldPath = `plan.${field}`;
  const ov = overrideMap.get(fieldPath);

  // If there's an override, show the overridden items (comma-separated from analyst_value)
  const displayItems: string[] = ov?.analyst_value
    ? ov.analyst_value.split("\n").filter(Boolean)
    : list.map((item: any) => text(item.theme_name || item.stock_name || item));

  if (!displayItems.length && !editable) return null;

  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={{ color, fontSize: 12, fontWeight: 700 }}>{label}</span>
        {editable && (
          <button
            onClick={() => onEdit(field, items)}
            style={{
              fontSize: 10,
              padding: "1px 8px",
              background: ov ? `${colors.green}20` : "transparent",
              color: ov ? colors.green : colors.muted,
              border: `1px solid ${ov ? colors.green : colors.border}`,
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            {ov ? "已修正" : "修正"}
          </button>
        )}
      </div>
      {displayItems.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18, color: ov ? colors.green : colors.text, fontSize: 13, lineHeight: 1.7 }}>
          {displayItems.slice(0, 8).map((item: string, idx: number) => (
            <li key={idx}>{item}</li>
          ))}
        </ul>
      ) : (
        <div style={{ color: colors.muted, fontSize: 13 }}>暂无数据</div>
      )}
    </div>
  );
}

// ── Shared sub-components ──

function Section({ title, quality, children }: { title: string; quality?: any; children: React.ReactNode }) {
  return (
    <section style={{ borderBottom: `1px solid ${colors.border}`, padding: "14px 18px", background: colors.panel }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <h3 className="recap-panel-title" style={{ margin: 0, fontSize: 15, color: colors.yellow }}>{title}</h3>
        {quality?.status && <Badge tone={quality.status === "READY" ? "good" : quality.status === "BLOCKED" ? "bad" : "warn"}>{quality.status}</Badge>}
      </div>
      {children}
    </section>
  );
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const color = tone === "good" ? colors.green : tone === "bad" ? colors.red : tone === "warn" ? colors.yellow : colors.muted;
  return (
    <span style={{ fontSize: 11, lineHeight: "18px", color, border: `1px solid ${color}55`, borderRadius: 4, padding: "0 6px", background: `${color}14` }}>
      {children}
    </span>
  );
}

function MetricGrid({ items }: { items: Array<[string, any]> }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8 }}>
      {items.map(([label, value]) => (
        <div key={label} style={{ border: `1px solid ${colors.border}`, borderRadius: 6, padding: "8px 10px", background: "#0c141d", minHeight: 56 }}>
          <div style={{ color: colors.muted, fontSize: 11, marginBottom: 4 }}>{label}</div>
          <div style={{ color: colors.text, fontSize: 18, fontWeight: 700, overflowWrap: "anywhere" }}>{text(value) || "-"}</div>
        </div>
      ))}
    </div>
  );
}

function KeyValue({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  if (!value) return null;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "82px minmax(0, 1fr)", gap: 10, padding: "5px 0", fontSize: 13 }}>
      <span style={{ color: colors.muted }}>{label}</span>
      <span style={{ color: strong ? colors.yellow : colors.text, fontWeight: strong ? 700 : 400, overflowWrap: "anywhere" }}>{value}</span>
    </div>
  );
}

function CompactTable({ rows, columns }: { rows: any[]; columns: Array<[string, (row: any, idx: number) => any]> }) {
  if (!rows.length) {
    return <div style={{ color: colors.muted, fontSize: 13 }}>暂无数据</div>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="recap-table" style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed", fontSize: 12 }}>
        <thead>
          <tr>
            {columns.map(([label]) => <th key={label} style={{ textAlign: "left", padding: "7px 8px" }}>{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
              {columns.map(([label, render]) => (
                <td key={label} style={{ padding: "7px 8px", overflowWrap: "anywhere" }}>{render(row, idx) || "-"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MiniList({ title, rows }: { title: string; rows: any[] }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ color: colors.accent, fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{title}</div>
      {rows.length ? rows.map((row, idx) => (
        <div key={idx} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 8, borderTop: `1px solid ${colors.border}`, padding: "7px 0", fontSize: 12 }}>
          <span style={{ overflowWrap: "anywhere" }}>{text(row.theme_name || row.subject_key || row.stock_name)}</span>
          <span style={{ color: colors.muted }}>{text(row.role_label || row.money_flow_tier || row.composite_score)}</span>
        </div>
      )) : <div style={{ color: colors.muted, fontSize: 13 }}>暂无数据</div>}
    </div>
  );
}

function ActionList({ label, items, tone }: { label: string; items: any; tone: "good" | "bad" | "watch" }) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return null;
  const color = tone === "good" ? colors.green : tone === "bad" ? colors.red : colors.yellow;
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ color, fontSize: 12, fontWeight: 700, marginBottom: 6 }}>{label}</div>
      <ul style={{ margin: 0, paddingLeft: 18, color: colors.text, fontSize: 13, lineHeight: 1.7 }}>
        {list.slice(0, 8).map((item: any, idx: number) => (
          <li key={idx}>{text(item.theme_name || item.stock_name || item)}</li>
        ))}
      </ul>
    </div>
  );
}

function text(value: any): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") {
    if ("final_value" in value) return text(value.final_value);
    if ("theme_name" in value) return text(value.theme_name);
    if ("stock_name" in value) return text(value.stock_name);
  }
  return String(value);
}

function nameValue(value: any): string {
  if (!value) return "";
  if (typeof value === "object") return text(value.final_value || value.analyst_value || value.ai_value);
  return text(value);
}

function formatPercent(value: any): string {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return text(value);
  return `${Math.round((n <= 1 ? n * 100 : n) * 10) / 10}%`;
}

function formatYi(value: any): string {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (!Number.isFinite(n)) return text(value);
  return `${Math.round(n * 10) / 10}亿`;
}
