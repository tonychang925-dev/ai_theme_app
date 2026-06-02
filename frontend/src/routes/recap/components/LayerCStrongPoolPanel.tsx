/** PR-14B: Layer C 强势股跟踪池 — 按主线分组，按 formal/observe/reject 分层。 */
import { Table, Tag } from "antd";
import type { PostMarketDecisionV2Review } from "../../../lib/api";

interface Props {
  review: PostMarketDecisionV2Review;
}

function rowKey(row: Record<string, unknown>): string {
  const stockId = String(row.stock_id || "").trim();
  if (stockId) return `stock_id:${stockId}`;
  return [
    "fallback",
    String(row.stock_name || "").trim() || "--",
    String(row.mainline_name || "").trim() || "--",
    String(row.theme_name || "").trim() || "--",
    String(row.relay_role || "").trim() || "--",
  ].join("|");
}

function displayMainlineName(row: Record<string, unknown>): string {
  return String(row.mainline_name || row.theme_name || "其他").trim() || "其他";
}

function translatePoolEntryType(value?: string | null): string {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    formal: "正式",
    observe_only: "观察",
    reject: "剔除",
    tracking_only: "跟踪",
    mainline_tracking: "主线跟踪",
    refresh: "刷新",
    strong_seed: "强势种子",
    decision_pool: "决策池",
    unknown: "未知",
  };
  return map[key] || key || "未知";
}

function translateWatchStatus(value?: string | null): string {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    active: "活跃",
    weakening: "转弱",
    removed: "移除",
    pending: "待定",
    unknown: "未知",
  };
  return map[key] || key || "未知";
}

function translateRelayRole(value?: string | null): string {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    dragon: "龙头",
    sub_dragon: "次龙头",
    leader: "龙头",
    focus: "重点关注",
    observe_only: "仅观察",
    unknown: "未知",
  };
  return map[key] || key || "未知";
}

function dedupeRows(rows: Record<string, unknown>[]): Record<string, unknown>[] {
  const best = new Map<string, Record<string, unknown>>();
  for (const row of rows) {
    const key = rowKey(row);
    const score = Number(row.watch_score || 0);
    const prev = best.get(key);
    if (!prev || score > Number(prev.watch_score || 0)) {
      best.set(key, row);
    }
  }
  return Array.from(best.values());
}

export default function LayerCStrongPoolPanel({ review }: Props) {
  const pool = dedupeRows((review.strong_stock_pool_reviews ?? []) as Record<string, unknown>[]);

  const byMainline: Record<string, Record<string, unknown>[]> = {};
  for (const r of pool) {
    const ml = displayMainlineName(r);
    if (!byMainline[ml]) byMainline[ml] = [];
    byMainline[ml].push(r);
  }

  const cols = [
    { title: "股票", dataIndex: "stock_name", key: "name", width: 110 },
    { title: "角色", dataIndex: "relay_role", key: "role", width: 76, render: (v: string) => translateRelayRole(v) },
    { title: "评分", dataIndex: "watch_score", key: "score", width: 62, render: (v: number) => v?.toFixed(0) },
    { title: "级别", dataIndex: "pool_entry_type", key: "level", width: 96, render: (v: string) => <Tag color={v === "formal" ? "green" : v === "observe_only" ? "orange" : v === "tracking_only" ? "blue" : "red"}>{translatePoolEntryType(v)}</Tag> },
    { title: "状态", dataIndex: "watch_status", key: "status", width: 72, render: (v: string) => translateWatchStatus(v) },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        强势股跟踪池
        <Tag style={{ marginLeft: 8 }}>{pool.length} 只</Tag>
      </h3>
      {Object.entries(byMainline).map(([ml, rows]) => (
        <details key={ml} open style={{ marginBottom: 10 }}>
          <summary style={{ color: "#8ddcff", fontWeight: 600, cursor: "pointer", marginBottom: 4 }}>
            {ml} ({rows.length})
          </summary>
          <div className="recap-table-shell">
            <Table
              dataSource={rows.map((r, i) => ({ ...r, key: (r.stock_id as string) || i }))}
              columns={cols}
              size="small"
              pagination={false}
              scroll={{ x: 520 }}
            />
          </div>
        </details>
      ))}
    </div>
  );
}
