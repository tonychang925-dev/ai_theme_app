/** PR-14B: D1 次日观察面板 — formal / observe_only / focus。 */
import { Alert, Table, Tag } from "antd";
import type { PostMarketDecisionV2Review } from "../../../lib/api";

interface Props {
  review: PostMarketDecisionV2Review;
}

export default function D1NextDayWatchPanel({ review }: Props) {
  const d1 = (review.weak_to_strong_d1_reviews ?? []) as Record<string, unknown>[];
  const focus = (review.next_day_focus_stocks ?? []) as Record<string, unknown>[];
  const tp = review.trading_permission ?? {};
  const allowTrade = Boolean(tp.allow_trade);

  const formal = d1.filter((r) => r.candidate_level === "formal");
  const observe = d1.filter((r) => r.candidate_level !== "formal");

  const cols = [
    { title: "股票", dataIndex: "stock_name", key: "name", width: 110 },
    { title: "主线", dataIndex: "theme_name", key: "theme", width: 110, ellipsis: true },
    { title: "角色", dataIndex: "relay_role", key: "role", width: 70 },
    { title: "级别", dataIndex: "candidate_level", key: "level", width: 74, render: (v: string) => <Tag color={v === "formal" ? "green" : "orange"}>{v}</Tag> },
    { title: "评分", dataIndex: "candidate_score", key: "score", width: 62, render: (v: number) => v?.toFixed(0) },
    { title: "买入条件", dataIndex: "buy_condition", key: "buy", width: 260, render: (v: unknown) => Array.isArray(v) ? (v as string[]).join("；") : String(v ?? "-") },
    { title: "失效条件", dataIndex: "invalid_condition", key: "invalid", width: 260, render: (v: unknown) => Array.isArray(v) ? (v as string[]).join("；") : String(v ?? "-") },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        次日观察 (D1)
        <Tag style={{ marginLeft: 8 }}>formal {formal.length}</Tag>
        <Tag color="orange">observe {observe.length}</Tag>
        <Tag>focus {focus.length}</Tag>
      </h3>

      {!allowTrade && (
        <Alert type="warning" showIcon message="当前市场不交易，所有 D1 仅观察，不生成正式买点" style={{ marginBottom: 10 }} />
      )}

      {d1.length === 0 ? (
        <div style={{ color: "#8ddcff", padding: 8 }}>暂无 D1 候选</div>
      ) : (
        <Table dataSource={d1.map((r, i) => ({ ...r, key: (r.stock_id as string) || i }))} columns={cols} size="small" pagination={{ pageSize: 10 }} scroll={{ x: 1100 }} />
      )}
    </div>
  );
}
