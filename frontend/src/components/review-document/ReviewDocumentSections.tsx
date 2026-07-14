import React from "react";
import type { ReviewDocument } from "./ReviewDocumentView";

// ── Shared helpers (same patterns as ReviewDocumentView) ──

const colors = {
  border: "#243040",
  panel: "#0f1722",
  text: "#d8e6ef",
  muted: "#6f8898",
  accent: "#66d9ef",
  green: "#39ff14",
  yellow: "#ffd85e",
  red: "#ff8a65",
};

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
  if (typeof value === "object" && value !== null) {
    return text(value.final_value) || text(value.ai_value) || "";
  }
  return text(value);
}

function stockThemeNames(row: any): string {
  const themes = Array.isArray(row?.themes) ? row.themes : [];
  return themes
    .map((theme: any) => nameValue(theme?.name))
    .filter(Boolean)
    .join(" / ");
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const color = tone === "good" ? colors.green : tone === "bad" ? colors.red : tone === "warn" ? colors.yellow : colors.muted;
  return (
    <span style={{ fontSize: 11, lineHeight: "18px", color, border: `1px solid ${color}55`, borderRadius: 4, padding: "0 6px", background: `${color}14` }}>
      {children}
    </span>
  );
}

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

// ── Main Component ──

export function ReviewDocumentSections({ document }: { document: ReviewDocument | null | undefined }) {
  if (!document) return null;

  const themes = Array.isArray(document.themes) ? document.themes : [];
  const stocks = Array.isArray(document.stocks) ? document.stocks : [];
  const limitUp = document.limit_up || {};
  const plan = document.plan || {};
  const risk = document.risk || {};
  const quality = document.quality || {};
  const sections: Record<string, any> = quality.sections || {};

  return (
    <div style={{ color: colors.text, background: "#0c1118" }}>
      {/* 题材结构 */}
      <Section title="题材结构" quality={sections.themes}>
        <CompactTable
          rows={themes.slice(0, 12)}
          columns={[
            ["题材", (row) => (
              <span style={{ color: colors.text }}>{nameValue(row.name) || text(row.theme_key) || "-"}</span>
            )],
            ["角色", (row) => text(row.role)],
            ["阶段", (row) => text(row.stage)],
            ["强度", (row) => typeof row.strength_score === "number" ? row.strength_score.toFixed(1) : text(row.strength_score)],
          ]}
        />
      </Section>

      {/* 强势股票池 */}
      <Section title="强势股票池" quality={sections.stocks}>
        <CompactTable
          rows={stocks.slice(0, 12)}
          columns={[
            ["代码", (row) => text(row.code)],
            ["名称", (row) => text(row.name)],
            ["题材", (row) => stockThemeNames(row)],
            ["角色", (row) => text(row.role)],
            ["高度", (row) => text(row.height)],
          ]}
        />
      </Section>

      {/* 涨停分类 */}
      <Section title="涨停分类" quality={sections.limit_up}>
        <div style={{ fontSize: 16, fontWeight: 700, color: colors.yellow, marginBottom: 10 }}>
          总数 {text(limitUp.total) || "-"}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {(Array.isArray(limitUp.categories) ? limitUp.categories : []).slice(0, 18).map((item: any, idx: number) => (
            <span key={`${text(item.theme_key)}-${idx}`} style={{
              fontSize: 12, color: colors.text, border: `1px solid ${colors.border}`,
              borderRadius: 4, padding: "3px 7px", background: "#101a24",
            }}>
              {nameValue(item.name) || text(item.theme_key)}
            </span>
          ))}
        </div>
      </Section>

      {/* 明日计划 */}
      <Section title="明日计划" quality={sections.plan}>
        <div style={{ fontSize: 14, fontWeight: 700, color: colors.yellow, marginBottom: 10 }}>
          场景 {text(plan.scenario) || "-"}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <ActionList label="允许" items={plan.allowed_actions} tone="good" />
          <ActionList label="禁止" items={plan.forbidden_actions} tone="bad" />
          <ActionList label="关注" items={plan.watch_themes} tone="watch" />
        </div>
      </Section>

      {/* 机构资金审美方向 */}
      <Section title="机构资金审美方向" quality={sections.capital}>
        <DirectionList rows={(document.capital || {}).institution_style || []} />
      </Section>

      {/* 游资情绪方向 */}
      <Section title="游资情绪方向" quality={{ status: "READY" }}>
        <DirectionList rows={(document.capital || {}).hot_money_style || []} isHotMoney />
      </Section>

      {/* 风险控制 */}
      <Section title="风险控制" quality={sections.risk}>
        <div style={{ fontSize: 16, fontWeight: 700, color: colors.red, marginBottom: 10 }}>
          等级 {text(risk.risk_level) || "-"}
        </div>
        <ActionList label="风险" items={risk.top_risks} tone="bad" />
      </Section>
    </div>
  );
}

function DirectionList({ rows, isHotMoney }: { rows: any[]; isHotMoney?: boolean }) {
  if (!rows.length) {
    return <div style={{ color: colors.muted, fontSize: 13 }}>暂无数据</div>;
  }
  const topRows = rows.slice(0, 6);
  return (
    <div>
      {topRows.map((row: any, idx: number) => {
        const name = text(row.direction_name || row.theme_name || row.subject_key);
        const score = row.score != null ? row.score : 0;
        const stars = score >= 80 ? "★★★★★" : score >= 65 ? "★★★★☆" : score >= 50 ? "★★★☆☆" : score >= 35 ? "★★☆☆☆" : "★☆☆☆☆";
        const stage = stageLabel(row.lifecycle_stage || row.attack_stage);
        const conf = row.confidence != null ? `${Math.round(row.confidence * 100)}%` : "";
        const signals = Array.isArray(row.top_signals) ? row.top_signals.slice(0, 3) : [];
        const relation = isHotMoney ? row.institution_hot_relation : null;
        return (
          <div key={idx} style={{ borderTop: `1px solid ${colors.border}`, padding: "10px 0", display: "flex", gap: 12, alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: colors.text }}>{name}</span>
                {relation && relation !== "HOT_MONEY_ONLY" && (
                  <span style={{ fontSize: 10, color: colors.muted, border: `1px solid ${colors.border}`, borderRadius: 3, padding: "1px 5px" }}>{relation === "BOTH" ? "机构+游资" : relation === "DIVERGENCE" ? "背离" : ""}</span>
                )}
              </div>
              <div style={{ fontSize: 12, color: colors.muted, marginBottom: 4 }}>
                <span style={{ color: colors.accent }}>{stars}</span>
                <span style={{ marginLeft: 8 }}>{score.toFixed(0)}分</span>
                {conf && <span style={{ marginLeft: 8 }}>{conf}</span>}
                {stage && <span style={{ marginLeft: 8, color: colors.yellow }}>{stage}</span>}
              </div>
              {signals.length > 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {signals.map((s: string, si: number) => (
                    <span key={si} style={{ fontSize: 11, color: colors.muted, background: "#101a24", padding: "2px 6px", borderRadius: 3 }}>{text(s)}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// PR4.2.37b: stage Chinese labels
const STAGE_LABELS: Record<string, string> = {
  "fermentation": "发酵", "Fermentation": "发酵", "FERMENTATION": "发酵",
  "divergence": "分歧", "Divergence": "分歧", "DIVERGENCE": "分歧",
  "start": "启动", "Start": "启动", "START": "启动",
  "incubation": "孵化", "Incubation": "孵化",
  "diffusion": "扩散", "Diffusion": "扩散",
  "peak": "高潮", "Peak": "高潮",
  "distribution": "退潮", "decay": "衰退",
  "fade_watch": "退潮观察", "fade_confirmed": "确认退潮",
  "FIRST_WAVE": "首波", "CONTINUING": "持续", "CLIMAX": "高潮", "RETREATING": "退却",
};
function stageLabel(s: string): string { return STAGE_LABELS[s] || s || ""; }

function ActionList({ label, items, tone }: { label: string; items: any; tone: "good" | "bad" | "watch" }) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return null;
  const color = tone === "good" ? colors.green : tone === "bad" ? colors.red : colors.yellow;
  return (
    <div>
      <div style={{ color, fontSize: 12, fontWeight: 700, marginBottom: 6 }}>{label}</div>
      <ul style={{ margin: 0, paddingLeft: 18, color: colors.text, fontSize: 13, lineHeight: 1.7 }}>
        {list.slice(0, 8).map((item: any, idx: number) => (
          <li key={idx}>{text(item.theme_name || item.stock_name || item)}</li>
        ))}
      </ul>
    </div>
  );
}
