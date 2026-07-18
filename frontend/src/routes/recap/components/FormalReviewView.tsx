import type { ReactNode } from "react";
import type { FormalReviewProjection, WorkbenchApproval } from "../../../lib/api";

type Props = {
  formalReview?: FormalReviewProjection | null;
  approval?: WorkbenchApproval | null;
};

function text(value: unknown, fallback = "--"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : fallback;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.map((item) => text(item, "")).filter(Boolean).join("、") || fallback;
  if (typeof value === "object") return fallback;
  return String(value);
}

function amount(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return text(value);
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)}万`;
  return value.toFixed(0);
}

function yiAmount(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return text(value);
  return `${value.toFixed(2).replace(/\.00$/, "")}亿`;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function dict(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function chip(value: unknown, tone = "") {
  const label = text(value, "");
  if (!label) return null;
  return <span className={`recap-chip ${tone}`}>{label}</span>;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginBottom: 16, padding: 14, border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, background: "rgba(255,255,255,0.03)" }}>
      <h3 className="section-title recap-panel-title" style={{ marginBottom: 12 }}>{title}</h3>
      {children}
    </section>
  );
}

function KeyValueGrid({ rows }: { rows: Array<[string, unknown, string?]> }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
      {rows.map(([label, value, tone]) => (
        <div key={label} style={{ padding: "8px 10px", borderRadius: 6, background: "#0c1118" }}>
          <div style={{ fontSize: 11, color: "#789", marginBottom: 4 }}>{label}</div>
          <div style={{ fontSize: 15, color: tone || "#dbeafe", fontWeight: 700 }}>{text(value)}</div>
        </div>
      ))}
    </div>
  );
}

function SmallList({ items }: { items: unknown[] }) {
  if (!items.length) return <span className="workspace-note">--</span>;
  return (
    <div className="recap-tag-stack" style={{ gap: 6 }}>
      {items.slice(0, 10).map((item, idx) => (
        <span key={`${text(item)}-${idx}`} className="recap-chip is-status">{text(item)}</span>
      ))}
    </div>
  );
}

function ExecutiveSummary({ summary }: { summary: Record<string, unknown> }) {
  return (
    <Section title="今日结论">
      <div style={{ display: "grid", gap: 10 }}>
        <KeyValueGrid rows={[
          ["市场结论", summary.market_conclusion || summary.summary],
          ["主线方向", summary.primary_theme],
          ["交易模式", summary.trade_mode],
          ["风险等级", summary.risk_level, "#ffd85e"],
        ]} />
        {text(summary.main_story, "") && (
          <p style={{ margin: 0, color: "#cbd5e1", lineHeight: 1.7 }}>{text(summary.main_story)}</p>
        )}
        <SmallList items={list(summary.top_risks)} />
      </div>
    </Section>
  );
}

function MarketState({ marketState }: { marketState: Record<string, unknown> }) {
  const facts = dict(marketState.facts);
  const regime = dict(marketState.regime);
  const relay = dict(marketState.relay_summary);
  const emotion = dict(marketState.emotion);
  return (
    <Section title="市场状态">
      <KeyValueGrid rows={[
        ["上涨/下跌", `${text(facts.up_count)} / ${text(facts.down_count)}`],
        ["涨停/跌停", `${text(facts.limit_up_total)} / ${text(facts.limit_down_total)}`],
        ["成交额", facts.total_amount_yi != null ? yiAmount(facts.total_amount_yi) : amount(facts.total_amount)],
        ["市场健康度", marketState.market_health_score],
        ["情绪分", marketState.emotion_score],
        ["情绪节点", emotion.emotion_node || emotion.emotion_label],
        ["最高板", relay.max_board_height],
        ["梯队形态", relay.ladder_shape],
        ["交易模式", regime.trade_mode],
        ["仓位约束", regime.position_limit],
      ]} />
    </Section>
  );
}

function ThemeStructure({ themeStructure }: { themeStructure: NonNullable<FormalReviewProjection["theme_structure"]> }) {
  const themes = themeStructure.themes || [];
  return (
    <Section title="主线题材">
      {text(themeStructure.summary?.mainline_narrative, "") && (
        <p style={{ marginTop: 0, color: "#cbd5e1", lineHeight: 1.7 }}>{text(themeStructure.summary?.mainline_narrative)}</p>
      )}
      <div className="recap-table-wrap">
        <table className="recap-table">
          <thead><tr><th>题材</th><th>角色</th><th>阶段</th><th>状态演化</th><th>分析师修正</th></tr></thead>
          <tbody>
            {themes.slice(0, 12).map((theme, idx) => {
              const analyst = dict(theme.analyst_view);
              const overrides = list(analyst.overrides);
              return (
                <tr key={`${text(theme.subject_key)}-${idx}`}>
                  <td className="recap-cell-wrap"><strong>{text(theme.theme_name || theme.subject_key)}</strong></td>
                  <td>{chip(theme.role, theme.role === "MAINLINE" ? "is-pass" : "is-status")}</td>
                  <td>{text(theme.stage)}</td>
                  <td className="recap-cell-wrap">{text(dict(theme.state_evolution).conclusion || dict(theme.state_evolution).action_advice)}</td>
                  <td className="recap-cell-wrap">
                    {overrides.length ? overrides.slice(0, 2).map((item, i) => {
                      const row = dict(item);
                      return <div key={i}>{text(row.field)}: <strong>{text(row.final_value)}</strong></div>;
                    }) : <span className="workspace-note">--</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function StockStructure({ stockStructure }: { stockStructure: NonNullable<FormalReviewProjection["stock_structure"]> }) {
  const stocks = stockStructure.stocks || [];
  return (
    <Section title="强势股结构">
      <div className="recap-table-wrap">
        <table className="recap-table">
          <thead><tr><th>股票</th><th>题材</th><th>今日角色</th><th>综合</th><th>状态</th></tr></thead>
          <tbody>
            {stocks.slice(0, 12).map((stock, idx) => (
              <tr key={`${text(stock.stock_code || stock.stock_name)}-${idx}`}>
                <td><strong>{text(stock.stock_name || stock.stock_code)}</strong></td>
                <td>{text(stock.theme_name || stock.subject_key)}</td>
                <td>{chip(stock.today_role, stock.today_role === "LEADER" ? "is-pass" : "is-status")}</td>
                <td>{text(dict(stock.scores).composite)}</td>
                <td className="recap-cell-wrap">{text(stock.today_status || stock.rationale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function CapitalEvidence({ capital }: { capital: NonNullable<FormalReviewProjection["capital_evidence"]> }) {
  const market = capital.market || {};
  const stocks = capital.stocks || [];
  return (
    <Section title="资金证据">
      <KeyValueGrid rows={[
        ["活跃资金", market.active_amount_yi != null ? yiAmount(market.active_amount_yi) : yiAmount(market.active_amount)],
        ["资金状态", market.state],
        ["游资净买", amount(market.hot_money_net_buy)],
        ["机构净买", amount(market.institution_net_buy)],
        ["证据数量", market.evidence_count],
      ]} />
      <div className="recap-table-wrap" style={{ marginTop: 12 }}>
        <table className="recap-table">
          <thead><tr><th>股票</th><th>事实资金</th><th>资金判断</th><th>龙虎榜</th><th>异动</th></tr></thead>
          <tbody>
            {stocks.slice(0, 10).map((stock, idx) => {
              const capitalBlocks = dict(stock.capital);
              const fact = dict(capitalBlocks.fact);
              const assessment = dict(capitalBlocks.assessment);
              return (
                <tr key={`${text(stock.stock_code || stock.stock_name)}-${idx}`}>
                  <td><strong>{text(stock.stock_name || stock.stock_code)}</strong></td>
                  <td>{amount(fact.main_net_inflow)}</td>
                  <td>{text(assessment.money_flow_tier || assessment.conclusion || assessment.role_enhanced)}</td>
                  <td>{text(dict(stock.dragon_tiger).side_summary || dict(stock.dragon_tiger).seat_type)}</td>
                  <td>{text(dict(list(stock.abnormal_signals)[0]).conclusion)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function NextDayPlan({ plan }: { plan: NonNullable<FormalReviewProjection["next_day_plan"]> }) {
  return (
    <Section title="明日计划">
      <div style={{ display: "grid", gap: 12 }}>
        {text(plan.scenario, "") && <p style={{ margin: 0, color: "#dbeafe", lineHeight: 1.7 }}>{plan.scenario}</p>}
        <KeyValueGrid rows={[
          ["观察题材", (plan.watch_themes || []).map((item) => text(item.theme_name || item.subject_key, ""))],
          ["确认信号", plan.confirmation_signals || []],
          ["失效信号", plan.invalidation_signals || []],
          ["禁止动作", plan.forbidden_actions || [], "#fca5a5"],
        ]} />
        <div className="recap-table-wrap">
          <table className="recap-table">
            <thead><tr><th>股票</th><th>题材</th><th>标签</th><th>动作</th><th>确认条件</th></tr></thead>
            <tbody>
              {(plan.watch_stocks || []).slice(0, 12).map((stock, idx) => (
                <tr key={`${text(stock.stock_code || stock.stock_name)}-${idx}`}>
                  <td><strong>{text(stock.stock_name || stock.stock_code)}</strong></td>
                  <td>{text(stock.theme_name || stock.subject_key)}</td>
                  <td><SmallList items={list(stock.tags)} /></td>
                  <td className="recap-cell-wrap">{text(stock.action || stock.reason)}</td>
                  <td className="recap-cell-wrap">{text(list(stock.confirmation_signals))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  );
}

export default function FormalReviewView({ formalReview, approval }: Props) {
  if (!formalReview) return null;
  const isFormal = approval?.mode === "formal" || approval?.mode === "published";
  return (
    <div data-testid="formal-review-view" style={{ marginBottom: 18 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
        <div>
          <span className="metric-label section-title">正式复盘</span>
          <p className="workspace-note" style={{ marginTop: 4 }}>v{formalReview.version || "1.0"}</p>
        </div>
        <span className={`recap-chip ${isFormal ? "is-pass" : "is-watch"}`}>
          {isFormal ? "Approved Snapshot" : "Preview"}
        </span>
      </div>
      <ExecutiveSummary summary={formalReview.executive_summary || {}} />
      <MarketState marketState={formalReview.market_state || {}} />
      {formalReview.theme_structure && <ThemeStructure themeStructure={formalReview.theme_structure} />}
      {formalReview.stock_structure && <StockStructure stockStructure={formalReview.stock_structure} />}
      {formalReview.capital_evidence && <CapitalEvidence capital={formalReview.capital_evidence} />}
      {formalReview.next_day_plan && <NextDayPlan plan={formalReview.next_day_plan} />}
    </div>
  );
}
