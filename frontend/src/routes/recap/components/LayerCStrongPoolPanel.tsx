/** PR-14B: Layer C / 当天入围强股展示 — 按题材分组，按 role/candidate 分层。 */
import { Table, Tag } from "antd";
import type { PostMarketDecisionV2Review } from "../../../lib/api";

interface Props {
  review?: PostMarketDecisionV2Review;
  rows?: Record<string, unknown>[];
  title?: string;
}

function rowKey(row: Record<string, unknown>): string {
  const stockId = String(row.stock_id || "").trim();
  if (stockId) return `stock_id:${stockId}`;
  return [
    "fallback",
    String(row.stock_name || "").trim() || "--",
    String(row.mainline_name || row.theme_name || "").trim() || "--",
    String(row.theme_name || "").trim() || "--",
    String(row.relay_role || row.role_label || row.role || "").trim() || "--",
  ].join("|");
}

function displayGroupName(row: Record<string, unknown>): string {
  return String(row.mainline_name || row.theme_name || row.subject_key || "其他").trim() || "其他";
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

function translateRole(value?: string | null): string {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    dragon: "龙头",
    sub_dragon: "次龙头",
    leader: "龙头",
    sub_leader: "次龙头",
    switch_leader: "卡位",
    focus: "重点关注",
    watch: "观察",
    observe_only: "仅观察",
    reject: "淘汰",
    unknown: "未知",
    龙头: "龙头",
    次龙头: "次龙头",
    卡位: "卡位",
    观察: "观察",
    仅观察: "仅观察",
    淘汰: "淘汰",
    重点关注: "重点关注",
  };
  return map[key] || key || "未知";
}

function translateStatus(value?: string | null): string {
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

function isIncludedRow(row: Record<string, unknown>): boolean {
  const role = String(row.role || row.role_label || row.relay_role || "").trim().toLowerCase();
  const candidateLevel = String(row.candidate_level || row.pool_entry_type || "").trim().toLowerCase();
  const watchStatus = String(row.watch_status || "").trim().toLowerCase();
  if (role === "reject") return false;
  if (candidateLevel === "reject") return false;
  if (watchStatus === "removed") return false;
  return watchStatus === "active" || watchStatus === "weakening" || candidateLevel === "formal" || candidateLevel === "observe_only";
}

function dedupeRows(rows: Record<string, unknown>[]): Record<string, unknown>[] {
  const best = new Map<string, Record<string, unknown>>();
  for (const row of rows) {
    const key = rowKey(row);
    const score = Number(row.watch_score ?? row.composite_score ?? 0);
    const prev = best.get(key);
    if (!prev || score > Number(prev.watch_score ?? prev.composite_score ?? 0)) {
      best.set(key, row);
    }
  }
  return Array.from(best.values());
}

export default function LayerCStrongPoolPanel({ review, rows, title = "当天入围强势股" }: Props) {
  const sourceRows = rows ?? ((review?.strong_stock_pool_reviews ?? []) as Record<string, unknown>[]);
  const pool = dedupeRows(sourceRows).filter(isIncludedRow);

  const byMainline: Record<string, Record<string, unknown>[]> = {};
  for (const r of pool) {
    const ml = displayGroupName(r);
    if (!byMainline[ml]) byMainline[ml] = [];
    byMainline[ml].push(r);
  }

  const cols = [
    { title: "股票", dataIndex: "stock_name", key: "name", width: 110, render: (_: unknown, row: Record<string, unknown>) => <span>{String(row.stock_name || "--")}</span> },
    { title: "角色", dataIndex: "role_label", key: "role", width: 90, render: (v: string, row: Record<string, unknown>) => translateRole(v || String(row.relay_role || row.role || "")) },
    { title: "评分", dataIndex: "watch_score", key: "score", width: 62, render: (_: unknown, row: Record<string, unknown>) => Number(row.watch_score ?? row.composite_score ?? 0)?.toFixed(0) },
    { title: "级别", dataIndex: "candidate_level", key: "level", width: 96, render: (_: unknown, row: Record<string, unknown>) => {
      const value = String(row.pool_entry_type || row.candidate_level || "");
      return (
        <Tag color={value === "formal" ? "green" : value === "observe_only" ? "orange" : value === "tracking_only" ? "blue" : "red"}>
          {translatePoolEntryType(value)}
        </Tag>
      );
    } },
    { title: "状态", dataIndex: "watch_status", key: "status", width: 72, render: (v: string) => translateStatus(v) },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        {title}
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
