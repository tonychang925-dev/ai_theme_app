import { Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { EvidenceItem, EvidenceLayerReview } from "../../../lib/api";

interface Props {
  evidenceLayerReview?: EvidenceLayerReview | null;
}

function displayLifecycle(value?: string | null) {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    divergence: "分歧",
    repair: "修复",
    start: "启动",
    fermentation: "发酵",
    watch: "观察",
    fade_watch: "退潮观察",
    fade_confirmed: "退潮确认",
    fade: "退潮",
  };
  return map[key] || key || "--";
}

function formatAmount(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const abs = Math.abs(Number(value));
  if (abs >= 1e8) return `${(Number(value) / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(Number(value) / 1e4).toFixed(2)}万`;
  return String(Math.round(Number(value)));
}

function evidenceTypeLabel(value: EvidenceItem["evidence_type"]) {
  const map: Record<string, string> = {
    abnormal: "异动",
    money_flow: "资金",
    dragon_tiger: "龙虎榜",
    stock_capital: "个股资金",
  };
  return map[value] || value || "--";
}

function renderTags(tags: string[]) {
  if (!tags || tags.length === 0) return <span className="workspace-note">--</span>;
  const classForTag = (tag: string) => {
    if (tag.includes("换手")) return "is-abnormal-turnover";
    if (tag.includes("倍量") || tag.includes("放量")) return "is-abnormal-volume";
    if (tag.includes("尾盘")) return "is-abnormal-tail";
    if (tag.includes("游资")) return "is-role";
    if (tag.includes("机构")) return "is-status";
    if (tag.includes("主力")) return "is-basis";
    if (tag.includes("观察") || tag.includes("试错")) return "is-status";
    if (tag.includes("异动")) return "is-basis";
    return "is-basis";
  };
  return (
    <div className="recap-tag-stack" style={{ gap: 4, flexWrap: "wrap" }}>
      {tags.slice(0, 6).map((tag, idx) => (
        <span key={`${tag}-${idx}`} className={`recap-chip ${classForTag(tag)}`}>
          {tag}
        </span>
      ))}
    </div>
  );
}

function sectionColumns(): ColumnsType<EvidenceItem & { key: string }> {
  return [
    {
      title: "股票",
      dataIndex: "stock_name",
      key: "stock_name",
      width: 120,
      render: (_: unknown, row: EvidenceItem) => (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span>{row.stock_name || row.stock_id || "--"}</span>
          {row.stock_code && row.stock_code !== row.stock_name && <span className="workspace-note">{row.stock_code}</span>}
        </div>
      ),
    },
    {
      title: "题材",
      dataIndex: "theme_name",
      key: "theme_name",
      width: 120,
      render: (_: unknown, row: EvidenceItem) => <span>{row.theme_name || row.subject_key || "--"}</span>,
    },
    {
      title: "主线",
      key: "mainline_name",
      width: 120,
      render: (_: unknown, row: EvidenceItem) => <Tag color={row.active_mainline ? "green" : "default"}>{row.mainline_name || (row.active_mainline ? "主线" : "--")}</Tag>,
    },
    {
      title: "生命周期",
      key: "lifecycle_state",
      width: 110,
      render: (_: unknown, row: EvidenceItem) => <Tag color={row.active_mainline ? "blue" : "default"}>{displayLifecycle(row.lifecycle_state)}</Tag>,
    },
    {
      title: "Layer C",
      key: "layer_c",
      width: 84,
      render: (_: unknown, row: EvidenceItem) => <Tag color={row.in_layer_c ? "green" : "default"}>{row.in_layer_c ? "是" : "否"}</Tag>,
    },
    {
      title: "D1",
      key: "d1",
      width: 72,
      render: (_: unknown, row: EvidenceItem) => <Tag color={row.is_d1_candidate ? "blue" : "default"}>{row.is_d1_candidate ? "是" : "否"}</Tag>,
    },
    {
      title: "Focus",
      key: "focus",
      width: 72,
      render: (_: unknown, row: EvidenceItem) => <Tag color={row.is_focus_stock ? "green" : "default"}>{row.is_focus_stock ? "是" : "否"}</Tag>,
    },
    {
      title: "评分",
      key: "score",
      width: 84,
      render: (_: unknown, row: EvidenceItem) => <span>{row.score != null ? Number(row.score).toFixed(1) : "--"}</span>,
    },
    {
      title: "金额",
      key: "amount",
      width: 108,
      render: (_: unknown, row: EvidenceItem) => <span>{formatAmount(row.amount ?? null)}</span>,
    },
    {
      title: "证据描述",
      dataIndex: "description",
      key: "description",
      width: 300,
      ellipsis: true,
      render: (_: unknown, row: EvidenceItem) => <span>{row.description || row.title || "--"}</span>,
    },
    {
      title: "动作",
      dataIndex: "trade_action",
      key: "trade_action",
      width: 110,
      render: (_: unknown, row: EvidenceItem) => <span>{row.trade_action || "--"}</span>,
    },
    {
      title: "标签",
      key: "tags",
      width: 240,
      render: (_: unknown, row: EvidenceItem) => renderTags(row.tags || []),
    },
  ];
}

function renderSection(title: string, items: EvidenceItem[]) {
  const rows = [...items].sort(
    (left, right) =>
      (left.rank_order ?? 9999) - (right.rank_order ?? 9999) ||
      (Number(right.score ?? 0) - Number(left.score ?? 0)) ||
      (Number(right.amount ?? 0) - Number(left.amount ?? 0)) ||
      String(left.stock_name || left.stock_id || "").localeCompare(String(right.stock_name || right.stock_id || "")),
  );

  return (
    <div className="workspace-card" style={{ marginBottom: 12 }}>
      <div className="metric-label section-title" style={{ marginBottom: 8 }}>
        {title}
        <Tag color="blue" style={{ marginLeft: 8 }}>
          {rows.length}
        </Tag>
      </div>
      {rows.length > 0 ? (
        <div style={{ overflowX: "auto" }}>
          <Table
            className="recap-table"
            dataSource={rows.map((row, index) => ({ ...row, key: `${row.stock_id || row.stock_code || index}-${index}` }))}
            columns={sectionColumns()}
            size="small"
            pagination={false}
            scroll={{ x: 1450 }}
            rowClassName={(row) => (row.active_mainline ? "recap-row-focus" : "")}
          />
        </div>
      ) : (
        <span className="workspace-note">暂无结构化证据</span>
      )}
    </div>
  );
}

export default function EvidenceLayerPanel({ evidenceLayerReview }: Props) {
  if (!evidenceLayerReview) return null;

  const groups = [...(evidenceLayerReview.evidence_groups || [])];
  const nonMainlineEvidence = [
    ...(evidenceLayerReview.abnormal_evidence || []),
    ...(evidenceLayerReview.money_flow_evidence || []),
    ...(evidenceLayerReview.dragon_tiger_evidence || []),
    ...(evidenceLayerReview.stock_capital_evidence || []),
  ]
    .filter((item) => !item.active_mainline)
    .sort(
      (left, right) =>
        (left.rank_order ?? 9999) - (right.rank_order ?? 9999) ||
        (Number(right.score ?? 0) - Number(left.score ?? 0)) ||
        (Number(right.amount ?? 0) - Number(left.amount ?? 0)) ||
        String(left.stock_name || left.stock_id || "").localeCompare(String(right.stock_name || right.stock_id || "")),
    );

  return (
    <div className="recap-evidence-layer" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        证据层
        <Tag color="cyan" style={{ marginLeft: 8 }}>
          交易证据
        </Tag>
        {evidenceLayerReview.source && (
          <Tag color={evidenceLayerReview.source === "structured" ? "green" : "blue"}>{evidenceLayerReview.source}</Tag>
        )}
      </h3>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title" style={{ marginBottom: 8 }}>
          证据摘要 / 非主线证据
          <Tag color="blue" style={{ marginLeft: 8 }}>
            {nonMainlineEvidence.length}
          </Tag>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12 }}>
          <div className="recap-form-label">证据摘要</div>
          <div className="recap-form-label">非主线证据</div>
          <div className="recap-form-label">Top 股票</div>
          <div className="recap-form-label">关联主线</div>

          <div className="workspace-note" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
            {evidenceLayerReview.summary}
          </div>
          <div className="workspace-note" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
            {nonMainlineEvidence.length > 0
              ? `主要来自 ${nonMainlineEvidence.slice(0, 3).map((item) => item.stock_name || item.stock_id || "--").filter(Boolean).join("、") || "--"}。`
              : "暂无非主线证据"}
          </div>
          <div className="workspace-note" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
            {nonMainlineEvidence.length > 0 ? nonMainlineEvidence.slice(0, 5).map((item) => item.stock_name || item.stock_id || "--").filter(Boolean).join("、") : "--"}
          </div>
          <div className="workspace-note" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
            {nonMainlineEvidence.length > 0
              ? Array.from(new Set(nonMainlineEvidence.flatMap((item) => (item.mainline_name ? [item.mainline_name] : [])))).slice(0, 5).join("、") || "--"
              : "--"}
          </div>
        </div>
      </div>

      {renderSection("异动证据", evidenceLayerReview.abnormal_evidence || [])}
      {renderSection("资金证据", evidenceLayerReview.money_flow_evidence || [])}
      {renderSection("龙虎榜证据", evidenceLayerReview.dragon_tiger_evidence || [])}
      {renderSection("个股资金证据", evidenceLayerReview.stock_capital_evidence || [])}

      {evidenceLayerReview.diagnostics && (
        <div className="workspace-note">
          诊断：异动 {String(evidenceLayerReview.diagnostics.abnormal_count ?? "--")}，资金 {String(evidenceLayerReview.diagnostics.money_flow_count ?? "--")}，龙虎榜 {String(evidenceLayerReview.diagnostics.dragon_tiger_count ?? "--")}，个股资金 {String(evidenceLayerReview.diagnostics.stock_capital_count ?? "--")}
        </div>
      )}
    </div>
  );
}
