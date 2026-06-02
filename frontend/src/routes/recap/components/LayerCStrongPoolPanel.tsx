/** PR-14B: Layer C 强势股跟踪池 — 按主线分组，按 formal/observe/reject 分层。 */
import { Table, Tag } from "antd";
import type { PostMarketDecisionV2Review } from "../../../lib/api";

interface Props {
  review: PostMarketDecisionV2Review;
}

export default function LayerCStrongPoolPanel({ review }: Props) {
  const pool = (review.strong_stock_pool_reviews ?? []) as Record<string, unknown>[];

  const byMainline: Record<string, Record<string, unknown>[]> = {};
  for (const r of pool) {
    const ml = (r.mainline_id || r.theme_name || "其他") as string;
    if (!byMainline[ml]) byMainline[ml] = [];
    byMainline[ml].push(r);
  }

  const cols = [
    { title: "股票", dataIndex: "stock_name", key: "name", width: 70 },
    { title: "角色", dataIndex: "relay_role", key: "role", width: 56 },
    { title: "评分", dataIndex: "watch_score", key: "score", width: 48, render: (v: number) => v?.toFixed(0) },
    { title: "级别", dataIndex: "pool_entry_type", key: "level", width: 60, render: (v: string) => <Tag color={v === "formal" ? "green" : v === "observe_only" ? "orange" : "red"}>{v}</Tag> },
    { title: "状态", dataIndex: "watch_status", key: "status", width: 50 },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 style={{ margin: "0 0 10px", color: "#e2e8f0", fontSize: 15 }}>
        Layer C 强势股跟踪池
        <Tag style={{ marginLeft: 8 }}>{pool.length} 只</Tag>
      </h3>
      {Object.entries(byMainline).map(([ml, rows]) => (
        <details key={ml} open style={{ marginBottom: 10 }}>
          <summary style={{ color: "#cbd5e1", fontWeight: 600, cursor: "pointer", marginBottom: 4 }}>
            {ml} ({rows.length})
          </summary>
          <Table
            dataSource={rows.map((r, i) => ({ ...r, key: (r.stock_id as string) || i }))}
            columns={cols}
            size="small"
            pagination={false}
          />
        </details>
      ))}
    </div>
  );
}
