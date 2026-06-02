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

const STATE_LABELS: Record<string, string> = {
  start: "启动",
  fermentation: "发酵",
  acceleration: "加速",
  divergence: "分歧",
  repair: "修复",
  fade_watch: "退潮观察",
  fade_confirmed: "退潮确认",
  dead: "衰竭",
  unknown: "未知",
};

export default function MainlineStateBoard({ rows }: Props) {
  const columns = [
    { title: "主线", dataIndex: "mainline_name", key: "name", width: 110 },
    { title: "生命周期", dataIndex: "lifecycle_state", key: "state", width: 110, render: (v: string) => <Tag color={STATE_COLORS[v] || "default"}>{STATE_LABELS[v] || v || "未知"}</Tag> },
    { title: "存活", dataIndex: "mainline_alive", key: "alive", width: 60, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "可交易", dataIndex: "mainline_trade_alive", key: "trade", width: 72, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "强度", dataIndex: "mainline_strength_score", key: "strength", width: 62, render: (v: number | null) => v != null ? v.toFixed(0) : "-" },
    { title: "强股池", dataIndex: "strong_pool_count", key: "pool", width: 72 },
    { title: "次日观察", dataIndex: "d1_count", key: "d1", width: 72 },
    { title: "重点关注", dataIndex: "focus_count", key: "focus", width: 72 },
    { title: "建议", dataIndex: "action_advice", key: "action", width: 150, render: (v: string) => <span style={{ color: "#8ddcff" }}>{v}</span> },
    { title: "结论", dataIndex: "conclusion", key: "conc", ellipsis: true },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">主线状态</h3>
      <div className="recap-table-shell">
        <Table
          dataSource={rows.map((r, i) => ({ ...r, key: r.mainline_id || i }))}
          columns={columns}
          size="small"
          pagination={false}
          scroll={{ x: 920 }}
        />
      </div>
    </div>
  );
}
