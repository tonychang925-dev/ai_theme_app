/** P4-1A: 诊断详情 Tab 面板 — 日志/DOM/Stream/Review Queue。 */
import { Button, Descriptions, Space, Table, Tabs, Tag } from "antd";
import type { NewChainRealtimeStatus, ReviewQueueItem } from "../../../lib/api";

interface Props {
  mergedLogs: string[];
  jyhfLogs: string[];
  stackStatus: NewChainRealtimeStatus | null;
  reviewItems: ReviewQueueItem[];
  reviewTotal: number;
  reviewBusy: boolean;
  selectedIds: Set<number>;
  onToggleSelect: (id: number) => void;
  onSelectAll: () => void;
  onSetSelectedKeys: (keys: Set<number>) => void;
  onConfirm: (id: number) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onBatchDelete: () => Promise<void>;
  onImportPending: () => Promise<void>;
  onClearPending: () => Promise<void>;
  onRefreshReview: () => Promise<void>;
  onOpenDetail: (item: ReviewQueueItem) => void;
}

export default function DiagnosticsTabs(props: Props) {
  const {
    mergedLogs, jyhfLogs, stackStatus, reviewItems, reviewTotal, reviewBusy,
    selectedIds, onToggleSelect, onSelectAll, onSetSelectedKeys, onConfirm, onDelete,
    onBatchDelete, onImportPending, onClearPending, onRefreshReview, onOpenDetail,
  } = props;

  const streams = stackStatus?.redis_streams ?? {};

  const tabItems = [
    {
      key: "run-log",
      label: "运行日志",
      children: (
        <div className="collection-log-panel" style={{ maxHeight: 360, overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
          {mergedLogs.length === 0 ? (
            <div className="collection-log-line" style={{ color: "#64748b" }}>暂无运行日志...</div>
          ) : (
            mergedLogs.slice(-200).map((line, i) => (
              <div key={`rl-${i}`} className="collection-log-line">{line}</div>
            ))
          )}
        </div>
      ),
    },
    {
      key: "dom-log",
      label: "DOM日志",
      children: (
        <div className="collection-log-panel" style={{ maxHeight: 360, overflow: "auto", fontFamily: "monospace", fontSize: 11, lineHeight: 1.5 }}>
          {jyhfLogs.length === 0 ? (
            <div className="collection-log-line" style={{ color: "#64748b" }}>暂无 DOM 日志...</div>
          ) : (
            jyhfLogs.slice(-200).map((line, i) => (
              <div key={`dl-${i}`} className="collection-log-line">{line}</div>
            ))
          )}
        </div>
      ),
    },
    {
      key: "redis-stream",
      label: "Redis Stream",
      children: (() => {
          const pendingCount = stackStatus?.pending_count ?? 0;
          const reviewCount = stackStatus?.review_queue_count ?? 0;
          const deadCount = stackStatus?.dead_letter_count ?? 0;
          const decisionCount = stackStatus?.decision_stream_count ?? 0;
          return (
        <div>
          {/* ── 关键数据流指标 ── */}
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
            gap: 8, marginBottom: 10,
          }}>
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: pendingCount > 0 ? "rgba(245,158,11,0.08)" : "rgba(255,255,255,0.03)",
              border: pendingCount > 0 ? "1px solid rgba(245,158,11,0.3)" : "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ fontSize: 10, color: "#64748b" }}>📥 Pending</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: pendingCount > 0 ? "#f59e0b" : "#e2e8f0" }}>
                {stackStatus ? pendingCount : "?"}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>待导入</div>
            </div>
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: reviewCount > 0 ? "rgba(59,130,246,0.08)" : "rgba(255,255,255,0.03)",
              border: reviewCount > 0 ? "1px solid rgba(59,130,246,0.3)" : "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ fontSize: 10, color: "#64748b" }}>📋 待复核</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: reviewCount > 0 ? "#3b82f6" : "#e2e8f0" }}>
                {stackStatus ? reviewCount : "?"}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>DB waiting</div>
            </div>
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: deadCount > 0 ? "rgba(239,68,68,0.08)" : "rgba(255,255,255,0.03)",
              border: deadCount > 0 ? "1px solid rgba(239,68,68,0.3)" : "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ fontSize: 10, color: "#64748b" }}>💀 Dead Letter</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: deadCount > 0 ? "#ef4444" : "#e2e8f0" }}>
                {stackStatus ? deadCount : "?"}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>死信</div>
            </div>
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.06)",
            }}>
              <div style={{ fontSize: 10, color: "#64748b" }}>📊 Decision</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0" }}>
                {stackStatus ? (decisionCount >= 0 ? decisionCount : "?") : "?"}
              </div>
              <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>流长度</div>
            </div>
          </div>

          <Descriptions size="small" column={2}>
            <Descriptions.Item label="Qwen Dedup">
              {stackStatus?.qwen_dedup_ready ? <Tag color="green">就绪</Tag> : <Tag>未就绪</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="Qwen Calls">{stackStatus?.qwen_dedup_calls ?? 0}</Descriptions.Item>
            <Descriptions.Item label="Prefilter Skipped">{stackStatus?.prefilter_skipped ?? 0}</Descriptions.Item>
            <Descriptions.Item label="Dedup Skipped">{stackStatus?.news_dedup_skipped ?? 0}</Descriptions.Item>
            <Descriptions.Item label="Hard Protect">{stackStatus?.hard_protect_count ?? 0}</Descriptions.Item>
            <Descriptions.Item label="News Published">{stackStatus?.news_published_total ?? 0}</Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: 8 }}>
            <span className="metric-label section-title">Stream 长度</span>
            {Object.keys(streams).length === 0 ? (
              <div style={{ color: "#64748b", fontSize: 12 }}>暂无数据</div>
            ) : (
              Object.entries(streams).map(([name, info]) => {
                const len = info?.length ?? 0;
                const color = len > 5000 ? "#ef4444" : len > 1000 ? "#eab308" : "#22c55e";
                return (
                  <div key={name} style={{ fontSize: 12, marginBottom: 2 }}>
                    <span style={{ color: "#64748b" }}>{name}</span>
                    {" "}<strong style={{ color }}>{len}</strong>
                    {" groups="}<span style={{ color: "#94a3b8" }}>{info?.groups ?? 0}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>
          );
        }}(),
    },
    {
      key: "review-queue",
      label: `Review Queue (${reviewTotal})`,
      children: (
        <div>
          <Space style={{ marginBottom: 8 }}>
            <Button size="small" onClick={onRefreshReview} loading={reviewBusy}>刷新</Button>
            <Button size="small" onClick={onImportPending} disabled={reviewBusy}>导入 Pending</Button>
            <Button size="small" onClick={onClearPending} disabled={reviewBusy}>清空 Pending</Button>
            {selectedIds.size > 0 && (
              <Button size="small" danger onClick={onBatchDelete}>删除选中 ({selectedIds.size})</Button>
            )}
            <Button size="small" onClick={onSelectAll}>
              {selectedIds.size === reviewItems.length && reviewItems.length > 0 ? "取消全选" : "全选"}
            </Button>
          </Space>
          <Table
            dataSource={reviewItems}
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ y: "calc(100vh - 400px)" }}
            rowSelection={{
              selectedRowKeys: Array.from(selectedIds),
              onChange: (selectedRowKeys) => {
                onSetSelectedKeys(new Set(selectedRowKeys as number[]));
              },
              onSelect: (record) => onToggleSelect(record.id),
            }}
            columns={[
              { title: "ID", dataIndex: "id", width: 65 },
              {
                title: "Title", dataIndex: "event_title", ellipsis: true,
                render: (v: string | null, r: ReviewQueueItem) => (
                  <a onClick={() => onOpenDetail(r)} style={{ cursor: "pointer" }}>{v || r.raw_title || "(无标题)"}</a>
                ),
              },
              {
                title: "Theme", dataIndex: "proposed_theme_name", width: 100,
                render: (v: string | null) => v || "-",
              },
              {
                title: "Conf", dataIndex: "proposed_theme_confidence", width: 50,
                render: (v: number | null) => v != null ? v.toFixed(2) : "-",
              },
              { title: "时间", dataIndex: "created_at", width: 80, render: (v: string) => v?.slice(11, 19) ?? "-" },
              {
                title: "操作", key: "actions", width: 120,
                render: (_: any, r: ReviewQueueItem) => (
                  <Space size="small">
                    <Button size="small" type="link" onClick={() => onConfirm(r.id)}>确认</Button>
                    <Button size="small" type="link" danger onClick={() => onDelete(r.id)}>删除</Button>
                  </Space>
                ),
              },
            ]}
            locale={{ emptyText: "暂无待复核事件" }}
          />
        </div>
      ),
    },
  ];

  return <Tabs items={tabItems} size="small" />;
}
