/** PR-14B: 主线状态总览 — 每主线一行：生命周期/强度/D1/focus/建议。 */
import { Table, Tag } from "antd";
import type { MainlineDailyStateReview } from "../../../lib/api";

interface Props {
  rows: MainlineDailyStateReview[];
  tradeDate?: string;
}

const STATE_COLORS: Record<string, string> = {
  start: "blue", fermentation: "green", acceleration: "cyan",
  divergence: "orange", repair: "geekblue",
  fade_watch: "volcano", fade_confirmed: "red",
  dead: "default", unknown: "default",
};

export default function MainlineStateBoard({ rows }: Props) {
  const columns = [
    { title: "主线", dataIndex: "mainline_name", key: "name", width: 110 },
    { title: "生命周期", dataIndex: "lifecycle_state", key: "state", width: 110, render: (v: string) => <Tag color={STATE_COLORS[v] || "default"}>{v}</Tag> },
    { title: "存活", dataIndex: "mainline_alive", key: "alive", width: 60, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "可交易", dataIndex: "mainline_trade_alive", key: "trade", width: 72, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "强度", dataIndex: "mainline_strength_score", key: "strength", width: 62, render: (v: number | null) => v != null ? v.toFixed(0) : "-" },
    { title: "强股池", dataIndex: "strong_pool_count", key: "pool", width: 72 },
    { title: "D1", dataIndex: "d1_count", key: "d1", width: 52 },
    { title: "focus", dataIndex: "focus_count", key: "focus", width: 60 },
    { title: "建议", dataIndex: "action_advice", key: "action", width: 150, render: (v: string) => <span style={{ color: "#8ddcff" }}>{v}</span> },
    { title: "结论", dataIndex: "conclusion", key: "conc", ellipsis: true },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">主线状态</h3>
      <Table
        dataSource={rows.map((r, i) => ({ ...r, key: r.mainline_id || i }))}
        columns={columns}
        size="small"
        pagination={false}
        scroll={{ x: 980 }}
      />
    </div>
  );
}
