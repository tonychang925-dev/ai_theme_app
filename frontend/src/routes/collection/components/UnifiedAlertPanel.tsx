/** P4-1A: 统一事件告警窗口 — K线支撑 + W2S 合并展示。纯展示，不接触 SSE 或原始状态。 */
import { useState, useMemo } from "react";
import { Badge, Button, Segmented, Space, Table, Tag } from "antd";
import type { KlineAlertEvent, W2SAlertEvent } from "../../../lib/api";

export interface UnifiedAlertRow {
  id: string;
  ts: number;
  time: string;
  kind: "support" | "w2s";
  level: string;
  stock: string;
  title: string;
  score?: string | number;
  source: string;
  raw: KlineAlertEvent | W2SAlertEvent;
}

interface Props {
  alerts: UnifiedAlertRow[];
  onClear: () => void;
}

const KIND_OPTIONS: { label: string; value: string }[] = [
  { label: "全部", value: "all" },
  { label: "支撑", value: "support" },
  { label: "W2S", value: "w2s" },
];

const LEVEL_OPTIONS: { label: string; value: string }[] = [
  { label: "全部级别", value: "all" },
  { label: "Alert", value: "alert" },
  { label: "Watch", value: "watch" },
  { label: "Warning", value: "warning" },
  { label: "Info", value: "info" },
];

function levelColor(level: string): string {
  if (level === "alert" || level === "critical") return "red";
  if (level === "warning") return "gold";
  if (level === "watch" || level === "important") return "orange";
  if (level === "info") return "default";
  return "default";
}

export default function UnifiedAlertPanel({ alerts, onClear }: Props) {
  const [kindFilter, setKindFilter] = useState<string>("all");
  const [levelFilter, setLevelFilter] = useState<string>("all");

  const filtered = useMemo(() => {
    return alerts.filter((a) => {
      if (kindFilter !== "all" && a.kind !== kindFilter) return false;
      if (levelFilter !== "all" && a.level !== levelFilter) return false;
      return true;
    });
  }, [alerts, kindFilter, levelFilter]);

  const columns = [
    {
      title: "时间",
      dataIndex: "time",
      key: "time",
      width: 80,
      render: (v: string) => <span style={{ fontFamily: "monospace", fontSize: 11 }}>{v}</span>,
    },
    {
      title: "类型",
      dataIndex: "kind",
      key: "kind",
      width: 60,
      render: (v: string) => (
        <Tag color={v === "support" ? "blue" : "purple"}>{v === "support" ? "支撑" : "W2S"}</Tag>
      ),
    },
    {
      title: "级别",
      dataIndex: "level",
      key: "level",
      width: 60,
      render: (v: string) => <Badge status={levelColor(v) as any} text={v} />,
    },
    {
      title: "股票",
      dataIndex: "stock",
      key: "stock",
      width: 90,
      render: (v: string) => <strong>{v}</strong>,
    },
    {
      title: "事件",
      dataIndex: "title",
      key: "title",
      ellipsis: true,
    },
    {
      title: "分数",
      dataIndex: "score",
      key: "score",
      width: 60,
      render: (v: any) => (v != null ? <span style={{ fontFamily: "monospace" }}>{v}</span> : "-"),
    },
    {
      title: "来源",
      dataIndex: "source",
      key: "source",
      width: 70,
      render: (v: string) => <span style={{ fontSize: 11, color: "#8c8c8c" }}>{v}</span>,
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Space>
          <Segmented options={KIND_OPTIONS} value={kindFilter} onChange={(v) => setKindFilter(v as string)} size="small" />
          <Segmented options={LEVEL_OPTIONS} value={levelFilter} onChange={(v) => setLevelFilter(v as string)} size="small" />
        </Space>
        <Space>
          <span style={{ fontSize: 12, color: "#8c8c8c" }}>{filtered.length} / {alerts.length} 条</span>
          <Button size="small" onClick={onClear}>清空</Button>
        </Space>
      </div>
      <Table
        dataSource={filtered.slice(0, 200)}
        columns={columns}
        rowKey="id"
        size="small"
        pagination={false}
        scroll={{ y: 400 }}
        locale={{ emptyText: "等待告警信号..." }}
      />
    </div>
  );
}
