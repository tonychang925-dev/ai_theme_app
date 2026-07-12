import React from "react";

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

interface Props {
  document: ReviewDocument | null | undefined;
  mode: ReviewDocumentMode;
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

export function ReviewDocumentView({ document, mode }: Props) {
  if (!document) {
    return (
      <div style={{ padding: 24, color: colors.muted, background: "#0c1118" }}>
        暂无复盘报告
      </div>
    );
  }

  const metadata = document.metadata || {};
  const quality = document.quality || {};
  const sections = (quality.sections || {}) as Record<string, any>;
  const themes = Array.isArray(document.themes) ? document.themes : [];
  const stocks = Array.isArray(document.stocks) ? document.stocks : [];
  const capital = document.capital || {};
  const institution = Array.isArray(capital.institution) ? capital.institution : [];
  const hotMoney = Array.isArray(capital.hot_money) ? capital.hot_money : [];
  const plan = document.plan || {};

  return (
    <div style={{ color: colors.text, background: "#0c1118", minHeight: "100%" }}>
      <div style={{ padding: "14px 18px", borderBottom: `1px solid ${colors.border}`, background: colors.band, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 18, color: colors.accent, letterSpacing: 0 }}>统一复盘报告</h2>
        <Badge tone={quality.overall === "READY" ? "good" : "warn"}>{String(quality.overall || "UNKNOWN")}</Badge>
        <Badge>{mode === "editable" ? "编辑态" : "只读"}</Badge>
        <span style={{ marginLeft: "auto", fontSize: 12, color: colors.muted }}>
          {String(metadata.trade_date || "")} · {String(metadata.document_schema_version || "")} · {String(metadata.assembler_version || "")}
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
                ["题材", (row) => nameValue(row.name) || text(row.theme_name)],
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
                ["题材", (row) => text(row.theme_name || row.subject_key)],
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
            <ActionList label="允许" items={plan.allowed_actions} tone="good" />
            <ActionList label="禁止" items={plan.forbidden_actions} tone="bad" />
            <ActionList label="关注" items={plan.watch_themes} tone="watch" />
          </Section>

          <Section title="风险控制" quality={sections.risk}>
            <KeyValue label="等级" value={text(document.risk?.risk_level)} strong />
            <ActionList label="风险" items={document.risk?.top_risks} tone="bad" />
          </Section>
        </aside>
      </div>
    </div>
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

function CompactTable({ rows, columns }: { rows: any[]; columns: Array<[string, (row: any) => string]> }) {
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
                <td key={label} style={{ padding: "7px 8px", overflowWrap: "anywhere" }}>{render(row) || "-"}</td>
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
