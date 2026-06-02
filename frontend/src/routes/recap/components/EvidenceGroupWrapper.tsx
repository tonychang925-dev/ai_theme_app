/** PR-14C.2: 证据层分组包装器 — 按引擎上下文对旧栏目分组。 */
import { Alert } from "antd";
import type { EvidenceAlignmentIndex } from "../../../lib/api";

type AlignRow = Record<string, unknown>;

interface Props {
  title: string;
  rows: AlignRow[];
  stockIdKey?: string;
  alignmentIndex?: EvidenceAlignmentIndex | null;
  groups: { key: string; label: string; type: "info" | "warning" | "error" | "success"; filter: (al: AlignRow) => boolean }[];
  children: (rows: AlignRow[], groupKey: string, alignments: Record<string, AlignRow>) => React.ReactNode;
}

export default function EvidenceGroupWrapper({ title, rows, stockIdKey = "stock_id", alignmentIndex, groups, children }: Props) {
  const byStock = alignmentIndex?.by_stock ?? {};
  const indexedCount = rows.filter(r => {
    const sid = String(r[stockIdKey] ?? "");
    return sid && (byStock as Record<string, unknown>)[sid];
  }).length;

  const grouped: Record<string, AlignRow[]> = {};
  const ungrouped: AlignRow[] = [];
  const groupAlignments: Record<string, Record<string, AlignRow>> = {};

  for (const grp of groups) {
    grouped[grp.key] = [];
    groupAlignments[grp.key] = {};
  }

  for (const row of rows) {
    const sid = String(row[stockIdKey] ?? "");
    const al = sid ? (byStock as Record<string, AlignRow>)[sid] ?? null : null;
    let matched = false;
    for (const grp of groups) {
      if (al && grp.filter(al)) {
        grouped[grp.key].push(row);
        if (al) groupAlignments[grp.key][sid] = al;
        matched = true;
        break;
      }
    }
    if (!matched) ungrouped.push(row);
  }

  const nonMainlineCount = ungrouped.length;

  return (
    <div style={{ marginBottom: 14 }}>
      <Alert type="info" showIcon style={{ marginBottom: 8 }}
        message={`${title}：已对齐 ${indexedCount}/${rows.length} 条，非主线 ${nonMainlineCount} 条。本模块仅作为引擎结论证据，不单独生成交易计划。`} />

      {groups.map(grp => {
        const grpRows = grouped[grp.key];
        if (grpRows.length === 0) return null;
        return (
          <details key={grp.key} open style={{ marginBottom: 8 }}>
            <summary style={{ color: "#cbd5e1", fontWeight: 600, cursor: "pointer", fontSize: 13, padding: "4px 0" }}>
              {grp.label} ({grpRows.length})
            </summary>
            <div style={{ paddingLeft: 4 }}>
              {children(grpRows, grp.key, groupAlignments[grp.key])}
            </div>
          </details>
        );
      })}

      {ungrouped.length > 0 && (
        <details style={{ marginBottom: 8, opacity: 0.6 }}>
          <summary style={{ color: "#64748b", fontWeight: 500, cursor: "pointer", fontSize: 12, padding: "4px 0" }}>
            非主线 ({ungrouped.length})
          </summary>
          <div style={{ paddingLeft: 4 }}>{children(ungrouped, "non_mainline", {})}</div>
        </details>
      )}
    </div>
  );
}

