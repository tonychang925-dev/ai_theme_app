/** P4-3C: 采集控制面板 — 按 Owner 分组。 */
import { Tag, Descriptions } from "antd";
import type { JyhfCdpCollectorStatus, JyhfAuctionStatus, NewChainRealtimeStatus, IndexCollectResult } from "../../../lib/api";

interface Props {
  status: {
    running: "unknown" | "up" | "down";
    stackStatus: NewChainRealtimeStatus | null;
    jyhfStatus: JyhfCdpCollectorStatus | null;
    auctionStatus: JyhfAuctionStatus | null;
    indexStatus: IndexCollectResult | null;
    indexBusy: boolean;
  };
  busy: {
    startBusy: boolean; stopBusy: boolean; refreshBusy: boolean;
    jyhfBusy: boolean; auctionBusy: boolean;
  };
  toggles: {
    auctionEnabled: boolean; klineAlertsEnabled: boolean; w2sAlertsEnabled: boolean;
  };
  actions: {
    onStartRealtime: () => void; onStopRealtime: () => void; onRefreshRealtime: () => void;
    onStartDom: () => void; onStopDom: () => void; onRefreshDom: () => void;
    onToggleAuction: (v: boolean) => void; onToggleKlineAlerts: (v: boolean) => void; onToggleW2sAlerts: (v: boolean) => void;
    onCollectIndex: () => void;
  };
}

const s: Record<string, React.CSSProperties> = {
  section: { background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: "10px 14px", marginBottom: 6 },
  owner: { fontSize: 10, color: "#64748b", marginBottom: 4, fontWeight: 500 },
  btn: { padding: "3px 10px", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 4, background: "rgba(255,255,255,0.08)", color: "#e2e8f0", cursor: "pointer", fontSize: 12, marginRight: 4 },
  primary: { background: "#1677ff", border: "1px solid #1677ff" },
  danger: { background: "rgba(255,77,79,0.15)", border: "1px solid #ff4d4f", color: "#ff4d4f" },
  disabled: { opacity: 0.4, cursor: "not-allowed" },
  chk: { marginRight: 4 },
};

export default function CollectionControlPanel(props: Props) {
  const { status, busy, toggles, actions } = props;
  const { stackStatus, jyhfStatus, auctionStatus } = status;
  const b = (v: boolean) => v ? { ...s.btn, ...s.disabled } : s.btn;

  const hasRaw = Boolean(stackStatus?.raw_news_pid);
  const hasDec = Boolean(stackStatus?.decision_pid);
  const rtTag = hasRaw && hasDec ? { t: "运行中", c: "green" } : hasRaw || hasDec ? { t: "降级", c: "orange" } : { t: "已停止", c: "red" };

  return (
    <div>
      {/* Realtime Pipeline — SPS */}
      <div style={s.section}>
        <div style={s.owner}>owner: SPS RealtimeStackManager</div>
        <Tag color={rtTag.c}>{rtTag.t}</Tag>
        {stackStatus?.status_source === "bff_sps_unreachable" && <Tag color="red">SPS不可达</Tag>}
        <div style={{ marginTop: 6 }}>
          <button style={busy.startBusy ? b(true) : { ...s.btn, ...s.primary }} onClick={actions.onStartRealtime} disabled={busy.startBusy}>{busy.startBusy ? "启动中..." : "启动"}</button>
          <button style={busy.stopBusy ? b(true) : { ...s.btn, ...s.danger }} onClick={actions.onStopRealtime} disabled={busy.stopBusy}>{busy.stopBusy ? "停止中..." : "停止"}</button>
          <button style={busy.refreshBusy ? b(true) : s.btn} onClick={actions.onRefreshRealtime} disabled={busy.refreshBusy}>{busy.refreshBusy ? "刷新中..." : "刷新"}</button>
        </div>
        <Descriptions size="small" column={2} style={{ marginTop: 4 }}>
          <Descriptions.Item label="Run ID">{stackStatus?.run_id ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="Verified">{stackStatus?.running_verified ? "是" : "否"}</Descriptions.Item>
          <Descriptions.Item label="raw PID">{stackStatus?.raw_news_pid ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="dec PID">{stackStatus?.decision_pid ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="db PID">{stackStatus?.db_collector_pid ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="Source">{stackStatus?.status_source ?? "-"}</Descriptions.Item>
        </Descriptions>
      </div>

      {/* DOM/CDP — BFF CDP Manager */}
      <div style={s.section}>
        <div style={s.owner}>owner: BFF JyhfCdpManager</div>
        {jyhfStatus?.collector_running ? <Tag color="green">采集中</Tag> : <Tag>已停止</Tag>}
        <div style={{ marginTop: 6 }}>
          <button style={busy.jyhfBusy ? b(true) : { ...s.btn, ...s.primary }} onClick={actions.onStartDom} disabled={busy.jyhfBusy}>{busy.jyhfBusy ? "处理中..." : "启动"}</button>
          <button style={busy.jyhfBusy ? b(true) : { ...s.btn, ...s.danger }} onClick={actions.onStopDom} disabled={busy.jyhfBusy}>停止</button>
          <button style={busy.jyhfBusy ? b(true) : s.btn} onClick={actions.onRefreshDom} disabled={busy.jyhfBusy}>刷新</button>
        </div>
        <Descriptions size="small" column={2} style={{ marginTop: 4 }}>
          <Descriptions.Item label="Service">{jyhfStatus?.service_running ? "运行中" : "已停止"}</Descriptions.Item>
          <Descriptions.Item label="CDP">{jyhfStatus?.cdp_connected ? "已连接" : "未连接"}</Descriptions.Item>
          <Descriptions.Item label="Captures">{jyhfStatus?.capture_count_total ?? 0}</Descriptions.Item>
          <Descriptions.Item label="Tab">{jyhfStatus?.current_tab ?? "-"}</Descriptions.Item>
        </Descriptions>
      </div>

      {/* Auction — BFF AuctionManager */}
      <div style={s.section}>
        <div style={s.owner}>owner: BFF JyhfAuctionManager</div>
        {auctionStatus?.running ? <Tag color="green">运行中 rds={auctionStatus.rounds}</Tag> : <Tag>空闲</Tag>}
        {auctionStatus?.state === "finished" && <Tag color="default">已结束</Tag>}
        <div style={{ marginTop: 4 }}>
          <label style={{ fontSize: 12, color: "#94a3b8", userSelect: "none" }}>
            <input type="checkbox" checked={toggles.auctionEnabled} onChange={e => actions.onToggleAuction(e.target.checked)} disabled={busy.auctionBusy} style={s.chk} />
            竞价采集
          </label>
        </div>
      </div>

      {/* Index Collection — SPS IndexKlineCollectJob */}
      <div style={s.section}>
        <div style={s.owner}>owner: SPS IndexKlineCollectJob</div>
        {status.indexStatus?.success ? <Tag color="green">已采集 {status.indexStatus.collected_count ?? 0}/{status.indexStatus.total_count ?? 6}</Tag> : <Tag color="orange">未采集</Tag>}
        {status.indexBusy && <Tag color="processing">采集中...</Tag>}
        <div style={{ marginTop: 6 }}>
          <button style={status.indexBusy ? b(true) : { ...s.btn, ...s.primary }} onClick={actions.onCollectIndex} disabled={status.indexBusy}>
            {status.indexBusy ? "采集中..." : "采集指数"}
          </button>
        </div>
        <Descriptions size="small" column={2} style={{ marginTop: 4 }}>
          <Descriptions.Item label="已采集">{status.indexStatus?.success ? `${status.indexStatus.collected_count}/${status.indexStatus.total_count}` : "-"}</Descriptions.Item>
          <Descriptions.Item label="交易日">{status.indexStatus?.trade_date ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="技术分析">{status.indexStatus?.success ? `${status.indexStatus.technical_count}/${status.indexStatus.collected_count}` : "-"}</Descriptions.Item>
          <Descriptions.Item label="来源">{status.indexStatus?.source ?? "-"}</Descriptions.Item>
        </Descriptions>
      </div>

      {/* Alert Streams — SPS SSE / Frontend EventSource */}
      <div style={s.section}>
        <div style={s.owner}>owner: SPS Alert Stream / Frontend EventSource</div>
        <div style={{ display: "flex", gap: 12 }}>
          <label style={{ fontSize: 12, color: "#94a3b8", userSelect: "none" }}>
            <input type="checkbox" checked={toggles.klineAlertsEnabled} onChange={e => actions.onToggleKlineAlerts(e.target.checked)} style={s.chk} />
            K线告警 SSE
          </label>
          <label style={{ fontSize: 12, color: "#94a3b8", userSelect: "none" }}>
            <input type="checkbox" checked={toggles.w2sAlertsEnabled} onChange={e => actions.onToggleW2sAlerts(e.target.checked)} style={s.chk} />
            W2S告警 SSE
          </label>
        </div>
      </div>
    </div>
  );
}
