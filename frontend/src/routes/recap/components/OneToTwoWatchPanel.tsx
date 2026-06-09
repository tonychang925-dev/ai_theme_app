/** F1: OneToTwo 明日观察清单 — 只读 recap_doc.post_market_setup_plan，fail-closed. */
import { Tag } from "antd";
import type { PostMarketDailyReviewV2 } from "../../../lib/api";

interface Props {
  dailyReviewV2?: PostMarketDailyReviewV2 | null;
  tradeDate?: string;
}

interface OneToTwoItem {
  setup_type: string;
  trade_date: string;
  watch_date: string;
  stock_id: string;
  stock_name: string;
  subject_key: string;
  subject_name: string;
  decision: string;
  plan_status: string;
  rank_no?: number;
  rank_reason?: string;
  final_score?: number | null;
  technical_structure_score?: number | null;
  theme_authenticity_score?: number | null;
  board_breadth_score?: number | null;
  risk_flags?: string[];
  veto_reasons?: string[];
}

interface OneToTwoSummary {
  trade_date?: string;
  watch_date?: string;
  rule_version?: string;
  focus_count: number;
  observe_only_count: number;
  pending_review_only_count: number;
  reject_count: number;
}

function decisionLabel(d: string): string {
  const map: Record<string, string> = {
    focus: "重点观察",
    observe_only: "谨慎观察",
    pending_review_only: "待人工复核",
    reject: "剔除",
  };
  return map[d] || d;
}

function decisionColor(d: string): string {
  const map: Record<string, string> = {
    focus: "red",
    observe_only: "orange",
    pending_review_only: "default",
    reject: "default",
  };
  return map[d] || "default";
}

/** Extract OneToTwo payload from the dailyReviewV2 object.
 *  Fallback order: recap_doc.post_market_setup_plan → watchlists.one_to_two → fail-closed. */
function extractOneToTwoPayload(
  dailyReviewV2?: PostMarketDailyReviewV2 | null,
): { summary: OneToTwoSummary; items: OneToTwoItem[] } | null {
  if (!dailyReviewV2) return null;

  // Path 1: recap_doc.post_market_setup_plan
  const recapDoc = (dailyReviewV2 as Record<string, unknown>).recap_doc as Record<string, unknown> | undefined;
  const fromRecap = recapDoc?.post_market_setup_plan as Record<string, unknown> | undefined;
  if (fromRecap && typeof fromRecap.summary === "object" && Array.isArray(fromRecap.items)) {
    return fromRecap as unknown as { summary: OneToTwoSummary; items: OneToTwoItem[] };
  }

  // Path 2: watchlists.one_to_two
  const watchlists = (dailyReviewV2 as Record<string, unknown>).watchlists as Record<string, unknown> | undefined;
  const fromWatchlists = watchlists?.one_to_two as Record<string, unknown> | undefined;
  if (fromWatchlists && typeof fromWatchlists.summary === "object" && Array.isArray(fromWatchlists.items)) {
    return fromWatchlists as unknown as { summary: OneToTwoSummary; items: OneToTwoItem[] };
  }

  // Path 3: fail-closed — no data
  return null;
}

function hasValidSummary(payload: { summary: OneToTwoSummary }): boolean {
  const s = payload.summary;
  return (
    typeof s.focus_count === "number" ||
    typeof s.observe_only_count === "number" ||
    typeof s.pending_review_only_count === "number"
  );
}

export default function OneToTwoWatchPanel({ dailyReviewV2, tradeDate }: Props) {
  const payload = extractOneToTwoPayload(dailyReviewV2);

  // fail-closed: no payload or missing SUMMARY
  if (!payload || !hasValidSummary(payload)) {
    return (
      <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
        <h3 className="section-title recap-panel-title">
          明日观察：1进2观察清单
          <Tag style={{ marginLeft: 8 }} color="default">未生成</Tag>
        </h3>
        <p style={{ color: "rgba(255,255,255,0.45)", margin: "8px 0 0" }}>
          观察清单未生成 — 可能原因：当日无首板候选、市场环境 no_trade、或 OneToTwo 引擎未执行。
        </p>
      </div>
    );
  }

  const { summary, items } = payload;

  const visibleItems = items.filter((it) => it.decision !== "reject");
  const rejectItems = items.filter((it) => it.decision === "reject");

  const grouped: Record<string, OneToTwoItem[]> = { focus: [], observe_only: [], pending_review_only: [] };
  for (const it of visibleItems) {
    const d = it.decision || "observe_only";
    if (grouped[d]) grouped[d].push(it);
  }

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      {/* ── Header + summary ── */}
      <h3 className="section-title recap-panel-title">
        明日观察：1进2观察清单
        <Tag style={{ marginLeft: 8 }}>{visibleItems.length} 只</Tag>
        {summary.watch_date && (
          <span style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", marginLeft: 8 }}>
            观察日 {summary.watch_date}
          </span>
        )}
      </h3>

      {/* ── Count bar ── */}
      <div style={{ display: "flex", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
        <Tag color="red">重点观察 {summary.focus_count}</Tag>
        <Tag color="orange">谨慎观察 {summary.observe_only_count}</Tag>
        <Tag color="default">待复核 {summary.pending_review_only_count}</Tag>
        <Tag color="default" style={{ opacity: 0.6 }}>剔除 {summary.reject_count}</Tag>
      </div>

      {/* ── Visible tiers: focus → observe_only → pending_review_only ── */}
      {(["focus", "observe_only", "pending_review_only"] as const).map((tier) => {
        const tierItems = grouped[tier];
        if (!tierItems.length) return null;
        return (
          <details key={tier} open={tier === "focus"} style={{ marginBottom: 10 }}>
            <summary style={{ color: decisionColor(tier) === "red" ? "#ff7875" : decisionColor(tier) === "orange" ? "#ffc069" : "rgba(255,255,255,0.65)", fontWeight: 600, cursor: "pointer", marginBottom: 4 }}>
              {decisionLabel(tier)} ({tierItems.length})
            </summary>
            <div className="recap-table-shell" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                    <th style={{ padding: "4px 8px", textAlign: "left", color: "rgba(255,255,255,0.5)" }}>排名</th>
                    <th style={{ padding: "4px 8px", textAlign: "left", color: "rgba(255,255,255,0.5)" }}>股票</th>
                    <th style={{ padding: "4px 8px", textAlign: "left", color: "rgba(255,255,255,0.5)" }}>题材</th>
                    <th style={{ padding: "4px 8px", textAlign: "right", color: "rgba(255,255,255,0.5)" }}>综合分</th>
                    <th style={{ padding: "4px 8px", textAlign: "right", color: "rgba(255,255,255,0.5)" }}>技术分</th>
                    <th style={{ padding: "4px 8px", textAlign: "right", color: "rgba(255,255,255,0.5)" }}>题材分</th>
                    <th style={{ padding: "4px 8px", textAlign: "right", color: "rgba(255,255,255,0.5)" }}>板块分</th>
                    <th style={{ padding: "4px 8px", textAlign: "left", color: "rgba(255,255,255,0.5)" }}>风险/否决</th>
                  </tr>
                </thead>
                <tbody>
                  {tierItems.map((it) => (
                    <tr key={`${it.stock_id}|${it.subject_key}`} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                      <td style={{ padding: "4px 8px", color: "rgba(255,255,255,0.55)" }}>{it.rank_no ?? "-"}</td>
                      <td style={{ padding: "4px 8px", fontWeight: 500 }}>{it.stock_name || it.stock_id}</td>
                      <td style={{ padding: "4px 8px", color: "rgba(255,255,255,0.7)" }}>{it.subject_name || it.subject_key}</td>
                      <td style={{ padding: "4px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {it.final_score != null ? it.final_score.toFixed(1) : "-"}
                      </td>
                      <td style={{ padding: "4px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {it.technical_structure_score != null ? it.technical_structure_score.toFixed(1) : "-"}
                      </td>
                      <td style={{ padding: "4px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {it.theme_authenticity_score != null ? it.theme_authenticity_score.toFixed(1) : "-"}
                      </td>
                      <td style={{ padding: "4px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {it.board_breadth_score != null ? it.board_breadth_score.toFixed(1) : "-"}
                      </td>
                      <td style={{ padding: "4px 8px", maxWidth: 200 }}>
                        {(it.risk_flags ?? []).slice(0, 2).map((f, i) => (
                          <Tag key={i} color="orange" style={{ marginBottom: 2, fontSize: 11 }}>{f}</Tag>
                        ))}
                        {(it.veto_reasons ?? []).slice(0, 1).map((f, i) => (
                          <Tag key={`v${i}`} color="red" style={{ marginBottom: 2, fontSize: 11 }}>{f}</Tag>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        );
      })}

      {/* ── Reject (collapsed by default) ── */}
      {rejectItems.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ color: "rgba(255,255,255,0.35)", cursor: "pointer", fontSize: 12 }}>
            审计详情 — 剔除 {rejectItems.length} 只
          </summary>
          <div className="recap-table-shell" style={{ overflowX: "auto", marginTop: 4 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                  <th style={{ padding: "2px 6px", textAlign: "left", color: "rgba(255,255,255,0.35)" }}>股票</th>
                  <th style={{ padding: "2px 6px", textAlign: "left", color: "rgba(255,255,255,0.35)" }}>否决原因</th>
                </tr>
              </thead>
              <tbody>
                {rejectItems.map((it) => (
                  <tr key={`reject-${it.stock_id}|${it.subject_key}`}>
                    <td style={{ padding: "2px 6px", color: "rgba(255,255,255,0.35)" }}>{it.stock_name || it.stock_id}</td>
                    <td style={{ padding: "2px 6px", color: "rgba(255,255,255,0.35)" }}>{(it.veto_reasons ?? []).join("；") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
