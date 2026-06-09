/** F1+F5+P3F: OneToTwo 明日观察清单 — fail-closed payload, detail cards per stock. */
import { Tag } from "antd";
import type { PostMarketDailyReviewV2 } from "../../../lib/api";

interface Props {
  dailyReviewV2?: PostMarketDailyReviewV2 | null;
  tradeDate?: string;
}

interface OneToTwoItem {
  setup_type: string; trade_date: string; watch_date: string;
  stock_id: string; stock_name: string;
  subject_key: string; subject_name: string;
  decision: string; plan_status: string;
  rank_no?: number; rank_reason?: string;
  final_score?: number | null;
  technical_structure_score?: number | null;
  theme_authenticity_score?: number | null;
  board_breadth_score?: number | null;
  risk_flags?: string[]; veto_reasons?: string[];
  // P3 explanation fields
  observation_reason?: string[];
  event_logic?: Record<string, unknown>;
  subject_logic?: Record<string, unknown>;
  technical_summary?: Record<string, unknown>;
  key_parameters?: Record<string, unknown>;
  tomorrow_plan?: Record<string, unknown>;
  give_up_conditions?: string[];
}

interface OneToTwoSummary {
  trade_date?: string; watch_date?: string; rule_version?: string;
  focus_count: number; observe_only_count: number;
  pending_review_only_count: number; reject_count: number;
}

function decisionLabel(d: string): string {
  const m: Record<string, string> = { focus: "重点观察", observe_only: "谨慎观察", pending_review_only: "待人工复核", reject: "剔除" };
  return m[d] || d;
}
function decisionColor(d: string): string {
  const m: Record<string, string> = { focus: "red", observe_only: "orange", pending_review_only: "default", reject: "default" };
  return m[d] || "default";
}

type PayloadSource = "recap_doc" | "watchlists_fallback" | null;

function extractOneToTwoPayload(dailyReviewV2?: PostMarketDailyReviewV2 | null) {
  if (!dailyReviewV2) return null;
  const raw = dailyReviewV2 as Record<string, unknown>;

  // Path 1: dailyReviewV2.post_market_setup_plan (composer puts it at top level)
  const plan = raw.post_market_setup_plan as Record<string, unknown> | undefined;
  if (plan && typeof plan.summary === "object" && Array.isArray(plan.items))
    return { payload: plan as unknown as { summary: OneToTwoSummary; items: OneToTwoItem[] }, source: "recap_doc" as PayloadSource };

  // Path 2: watchlists.one_to_two
  const watchlists = raw.watchlists as Record<string, unknown> | undefined;
  const fromWl = watchlists?.one_to_two as Record<string, unknown> | undefined;
  if (fromWl && typeof fromWl.summary === "object" && Array.isArray(fromWl.items))
    return { payload: fromWl as unknown as { summary: OneToTwoSummary; items: OneToTwoItem[] }, source: "watchlists_fallback" as PayloadSource };

  return null;
}

function hasValidSummary(p: { summary: OneToTwoSummary; items: OneToTwoItem[] }): boolean {
  const s = p.summary;
  const counts = [s.focus_count, s.observe_only_count, s.pending_review_only_count, s.reject_count];
  if (!counts.every((v) => Number.isFinite(v) && v >= 0)) return false;
  // items only contains non-reject (rejects are continue'd in the engine)
  return p.items.length === s.focus_count + s.observe_only_count + s.pending_review_only_count;
}

function matchesTradeDate(p: { summary: OneToTwoSummary; items: OneToTwoItem[] }, td?: string): boolean {
  if (!td) return false;
  const t = String(td).slice(0, 10);
  const sd = String(p.summary.trade_date || "").slice(0, 10);
  if (sd && sd !== t) return false;
  return p.items.every((it) => { const d = String(it.trade_date || "").slice(0, 10); return !d || d === t; });
}

function filterIndependent(items: OneToTwoItem[]) {
  const safe: OneToTwoItem[] = []; let n = 0;
  for (const it of items) { if (String(it.subject_key || "").trim() === "__independent__") { n++; } else safe.push(it); }
  if (n) console.warn("OneToTwoWatchPanel: filtered %d __independent__ items", n);
  return { safe, filtered: n };
}

function sourceLabel(s: PayloadSource) { return s === "recap_doc" ? "数据源：recap snapshot" : s === "watchlists_fallback" ? "数据源：watchlists fallback" : ""; }

function fNum(v: unknown, d = 1): string { if (v == null) return "-"; const n = Number(v); return Number.isFinite(n) ? n.toFixed(d) : "-"; }

const cardStyle: React.CSSProperties = {
  border: "1px solid rgba(255,255,255,0.06)", borderRadius: 6, padding: "6px 10px", marginBottom: 6,
  background: "rgba(255,255,255,0.02)",
};
const sectionLabel: React.CSSProperties = { color: "rgba(255,255,255,0.45)", fontSize: 11, marginBottom: 2, marginTop: 6 };
const sectionText: React.CSSProperties = { color: "rgba(255,255,255,0.75)", fontSize: 12, lineHeight: 1.5 };

// ── Stock detail card ──

function StockDetailCard({ it }: { it: OneToTwoItem }) {
  const tp = (it.tomorrow_plan ?? {}) as Record<string, unknown>;
  const ts = (it.technical_summary ?? {}) as Record<string, unknown>;
  const sl = (it.subject_logic ?? {}) as Record<string, unknown>;
  const el = (it.event_logic ?? {}) as Record<string, unknown>;
  const kp = (it.key_parameters ?? {}) as Record<string, unknown>;
  const auth = (sl.stock_subject_authenticity ?? {}) as Record<string, unknown>;

  return (
    <div style={{ padding: "4px 0" }}>
      {/* 1. 入选原因 */}
      <div style={sectionLabel}>入选原因</div>
      <div style={sectionText}>
        {(it.observation_reason ?? []).length > 0
          ? (it.observation_reason ?? []).map((r, i) => <div key={i}>• {r}</div>)
          : <span style={{ color: "rgba(255,255,255,0.35)" }}>暂无入选原因</span>}
      </div>

      {/* 2. 重大事件 */}
      <div style={sectionLabel}>重大事件</div>
      <div style={sectionText}>
        {el.summary ? <div>{String(el.summary)}</div> : <span style={{ color: "rgba(255,255,255,0.35)" }}>暂无直接事件证据</span>}
        {(el.evidence as unknown[])?.length > 0 && <Tag style={{ marginTop: 2 }} color={el.evidence_level === "strong" ? "green" : "default"}>证据等级: {String(el.evidence_level)}</Tag>}
      </div>

      {/* 3. 题材逻辑 */}
      <div style={sectionLabel}>题材逻辑</div>
      <div style={sectionText}>
        <div>题材: {String(sl.subject_name || it.subject_name)} · 阶段: {String(sl.lifecycle_state || "-")}</div>
        <div>涨停 {kp.same_subject_limit_count ?? "-"} 只 · 强势 {kp.same_subject_strong_count ?? "-"} 只</div>
        <div>个股正宗度: {String(auth.level || "-")} ({(auth.score != null ? fNum(auth.score, 1) : "-")})</div>
      </div>

      {/* 4. 技术形态 */}
      <div style={sectionLabel}>技术形态</div>
      <div style={sectionText}>
        <div>{ts.label ? String(ts.label) : "-"}{ts.score != null ? <> · 评分 {fNum(ts.score)}</> : null}</div>
        {(ts.highlights as string[])?.length > 0 && (ts.highlights as string[]).map((h, i) => <div key={i} style={{ color: "rgba(255,255,255,0.55)" }}>+ {h}</div>)}
        {(ts.risks as string[])?.length > 0 && (ts.risks as string[]).map((r, i) => <div key={i} style={{ color: "rgba(255,200,100,0.7)" }}>! {r}</div>)}
      </div>

      {/* 5. 关键参数 */}
      <div style={sectionLabel}>关键参数</div>
      <div style={{ ...sectionText, display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
        <span>首板: {String(kp.first_board_type || "-")}</span>
        <span>换手: {kp.turnover_rate != null ? `${(Number(kp.turnover_rate) * 100).toFixed(1)}%` : "-"}</span>
        <span>一字板: {kp.is_one_word_board ? "是" : "否"}</span>
        <span>尾盘: {kp.is_late_seal ? "是" : "否"}</span>
        <span>封板时间: {String(kp.first_limit_time || "-")}</span>
        <span>涨停: {kp.same_subject_limit_count ?? "-"}只</span>
        <span>强势: {kp.same_subject_strong_count ?? "-"}只</span>
      </div>

      {/* 6. 明日观察计划 */}
      <div style={sectionLabel}>明日观察计划</div>
      <div style={sectionText}>
        <div>{String(tp.expected_behavior || "-")}</div>
        {(tp.auction_watch as string[])?.length > 0 && (
          <div style={{ marginTop: 2 }}>
            <span style={{ color: "rgba(255,255,255,0.45)" }}>竞价:</span>
            {(tp.auction_watch as string[]).map((s, i) => <div key={i} style={{ color: "rgba(255,255,255,0.55)", paddingLeft: 8 }}>· {s}</div>)}
          </div>
        )}
        {(tp.confirmation_triggers as string[])?.length > 0 && (
          <div style={{ marginTop: 2 }}>
            <span style={{ color: "rgba(255,255,255,0.45)" }}>确认条件:</span>
            {(tp.confirmation_triggers as string[]).map((s, i) => <div key={i} style={{ color: "rgba(255,255,255,0.55)", paddingLeft: 8 }}>· {s}</div>)}
          </div>
        )}
      </div>

      {/* 7. 放弃条件 */}
      <div style={sectionLabel}>放弃条件</div>
      <div style={sectionText}>
        {(it.give_up_conditions ?? []).length > 0
          ? (it.give_up_conditions ?? []).map((c, i) => <div key={i} style={{ color: "rgba(255,180,140,0.7)" }}>✕ {c}</div>)
          : <span style={{ color: "rgba(255,255,255,0.35)" }}>-</span>}
      </div>
    </div>
  );
}

// ── Main component ──

export default function OneToTwoWatchPanel({ dailyReviewV2, tradeDate }: Props) {
  const ext = extractOneToTwoPayload(dailyReviewV2);

  if (!ext) return <FailCard reason="观察清单未生成 — 可能原因：当日无首板候选、市场环境 no_trade、或 OneToTwo 引擎未执行。" />;
  const { payload, source } = ext;
  if (!hasValidSummary(payload)) return <FailCard reason="观察清单未生成 — summary 合同不完整或计数不一致。" />;
  if (!matchesTradeDate(payload, tradeDate)) return <FailCard reason="观察清单未生成 — 日期不匹配。" />;

  const { summary } = payload;
  const { safe: items, filtered: indepFiltered } = filterIndependent(payload.items);
  const visibleItems = items.filter((it) => it.decision !== "reject");
  const rejectItems = items.filter((it) => it.decision === "reject");
  const grouped: Record<string, OneToTwoItem[]> = { focus: [], observe_only: [], pending_review_only: [] };
  for (const it of visibleItems) { const d = it.decision || "observe_only"; if (grouped[d]) grouped[d].push(it); }

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        明日观察：1进2观察清单
        <Tag style={{ marginLeft: 8 }}>{visibleItems.length} 只</Tag>
        {summary.watch_date && <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", marginLeft: 8 }}>观察日 {summary.watch_date}</span>}
        <span style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", marginLeft: 8 }}>{sourceLabel(source)}</span>
        {indepFiltered > 0 && <Tag style={{ marginLeft: 8 }} color="warning">前端已拦截 {indepFiltered} 条</Tag>}
      </h3>

      <div style={{ display: "flex", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
        <Tag color="red">重点观察 {summary.focus_count}</Tag>
        <Tag color="orange">谨慎观察 {summary.observe_only_count}</Tag>
        <Tag color="default">待复核 {summary.pending_review_only_count}</Tag>
        <Tag color="default" style={{ opacity: 0.6 }}>剔除 {summary.reject_count}</Tag>
      </div>

      {(["focus", "observe_only", "pending_review_only"] as const).map((tier) => {
        const tierItems = grouped[tier];
        if (!tierItems.length) return null;
        return (
          <details key={tier} open={tier === "focus"} style={{ marginBottom: 8 }}>
            <summary style={{ color: decisionColor(tier) === "red" ? "#ff7875" : decisionColor(tier) === "orange" ? "#ffc069" : "rgba(255,255,255,0.65)", fontWeight: 600, cursor: "pointer", marginBottom: 4 }}>
              {decisionLabel(tier)} ({tierItems.length})
            </summary>
            {tierItems.map((it) => (
              <details key={`${it.stock_id}|${it.subject_key}`} style={cardStyle}>
                <summary style={{ cursor: "pointer", color: "#8ddcff", fontWeight: 500, fontSize: 13 }}>
                  <Tag color={decisionColor(it.decision)} style={{ marginRight: 6 }}>{decisionLabel(it.decision)}</Tag>
                  {it.stock_name || it.stock_id}
                  <span style={{ color: "rgba(255,255,255,0.5)", marginLeft: 8 }}>{it.subject_name || it.subject_key}</span>
                  <span style={{ float: "right", color: "rgba(255,255,255,0.45)", fontSize: 12 }}>
                    综合 {fNum(it.final_score)} · 技术 {fNum(it.technical_structure_score)} · 排名 {it.rank_no ?? "-"}
                  </span>
                </summary>
                <StockDetailCard it={it} />
              </details>
            ))}
          </details>
        );
      })}

      {rejectItems.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ color: "rgba(255,255,255,0.35)", cursor: "pointer", fontSize: 12 }}>审计详情 — 剔除 {rejectItems.length} 只</summary>
          <div style={{ marginTop: 4 }}>
            {rejectItems.map((it) => (
              <div key={`rej-${it.stock_id}|${it.subject_key}`} style={{ color: "rgba(255,255,255,0.3)", fontSize: 11, padding: "1px 0" }}>
                {it.stock_name || it.stock_id}: {(it.veto_reasons ?? []).join("；") || "-"}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function FailCard({ reason }: { reason: string }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">明日观察：1进2观察清单<Tag style={{ marginLeft: 8 }} color="default">未生成</Tag></h3>
      <p style={{ color: "rgba(255,255,255,0.45)", margin: "8px 0 0" }}>{reason}</p>
    </div>
  );
}
