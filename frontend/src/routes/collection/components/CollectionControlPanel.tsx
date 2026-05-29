/** P4-1A: 采集控制面板 — 纯展示 + 回调。使用原生 details 避免 antd Collapse 重挂载问题。 */
import { Button, Descriptions, Space, Switch, Tag } from "antd";
import type { JyhfCdpCollectorStatus, JyhfAuctionStatus, NewChainRealtimeStatus } from "../../../lib/api";

interface Props {
  status: {
    running: "unknown" | "up" | "down";
    stackStatus: NewChainRealtimeStatus | null;
    jyhfStatus: JyhfCdpCollectorStatus | null;
    auctionStatus: JyhfAuctionStatus | null;
  };
  busy: {
    mainBusy: boolean;
    jyhfBusy: boolean;
    auctionBusy: boolean;
  };
  toggles: {
    auctionEnabled: boolean;
    klineAlertsEnabled: boolean;
    w2sAlertsEnabled: boolean;
  };
  actions: {
    onStartRealtime: () => void;
    onStopRealtime: () => void;
    onRefreshRealtime: () => void;
    onStartDom: () => void;
    onStopDom: () => void;
    onRefreshDom: () => void;
    onToggleAuction: (v: boolean) => void;
    onToggleKlineAlerts: (v: boolean) => void;
    onToggleW2sAlerts: (v: boolean) => void;
  };
}

const sectionStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 8,
  padding: "12px 16px",
  marginBottom: 8,
};

const summaryStyle: React.CSSProperties = {
  cursor: "pointer",
  fontWeight: 600,
  fontSize: 14,
  padding: "4px 0",
  userSelect: "none",
};

export default function CollectionControlPanel(props: Props) {
  const { status, busy, toggles, actions } = props;
  const { stackStatus, jyhfStatus, auctionStatus } = status;

  return (
    <div>
      {/* 实时采集控制 */}
      <details open style={sectionStyle}>
        <summary style={summaryStyle}>
          <Space>
            <span>实时采集控制</span>
            {status.running === "up" ? <Tag color="green">运行中</Tag> : status.running === "down" ? <Tag color="red">已停止</Tag> : <Tag>检查中</Tag>}
          </Space>
        </summary>
        <div style={{ marginTop: 8 }}>
          <Space style={{ marginBottom: 8 }}>
            <Button type="primary" size="small" onClick={actions.onStartRealtime} disabled={busy.mainBusy} loading={busy.mainBusy && status.running === "unknown"}>
              启动实时采集
            </Button>
            <Button danger size="small" onClick={actions.onStopRealtime} disabled={busy.mainBusy}>
              停止实时采集
            </Button>
            <Button size="small" onClick={actions.onRefreshRealtime} disabled={busy.mainBusy}>
              刷新状态
            </Button>
          </Space>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="Run ID">{stackStatus?.run_id ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Profile">{stackStatus?.profile_version ?? "?"}/{stackStatus?.profile_status ?? "?"}</Descriptions.Item>
            <Descriptions.Item label="raw_news PID">{stackStatus?.raw_news_pid ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="decision PID">{stackStatus?.decision_pid ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Pending / DL">{stackStatus?.pending_count ?? "?"} / {stackStatus?.dead_letter_count ?? "?"}</Descriptions.Item>
            <Descriptions.Item label="LLM Mode">{stackStatus?.llm_judge_mode ?? "-"}</Descriptions.Item>
          </Descriptions>
        </div>
      </details>

      {/* JYHF DOM 采集 */}
      <details open style={sectionStyle}>
        <summary style={summaryStyle}>
          <Space>
            <span>JYHF DOM 采集</span>
            {jyhfStatus?.collector_running ? <Tag color="green">采集中</Tag> : <Tag>已停止</Tag>}
          </Space>
        </summary>
        <div style={{ marginTop: 8 }}>
          <Space style={{ marginBottom: 8 }}>
            <Button type="primary" size="small" onClick={actions.onStartDom} disabled={busy.jyhfBusy} loading={busy.jyhfBusy}>
              启动 DOM 采集
            </Button>
            <Button danger size="small" onClick={actions.onStopDom} disabled={busy.jyhfBusy}>
              停止 DOM 采集
            </Button>
            <Button size="small" onClick={actions.onRefreshDom} disabled={busy.jyhfBusy}>
              刷新 DOM 状态
            </Button>
          </Space>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="Owner">{jyhfStatus?.service_owner ?? "?"}</Descriptions.Item>
            <Descriptions.Item label="Service">{jyhfStatus?.service_running ? "运行中" : "已停止"}</Descriptions.Item>
            <Descriptions.Item label="CDP">{jyhfStatus?.cdp_connected ? "已连接" : "未连接"}</Descriptions.Item>
            <Descriptions.Item label="App">{jyhfStatus?.app_running ? "运行中" : "已停止"}</Descriptions.Item>
            <Descriptions.Item label="Tab">{jyhfStatus?.current_tab ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Last Capture">{jyhfStatus?.last_capture_at?.slice(11, 19) ?? "-"}</Descriptions.Item>
            <Descriptions.Item label="Captures">{jyhfStatus?.capture_count_total ?? 0}</Descriptions.Item>
            <Descriptions.Item label="New Events">{jyhfStatus?.new_event_count_total ?? 0}</Descriptions.Item>
          </Descriptions>
        </div>
      </details>

      {/* 开关设置 */}
      <details style={sectionStyle}>
        <summary style={summaryStyle}>开关设置</summary>
        <div style={{ marginTop: 8 }}>
          <Space direction="vertical">
            <div>
              <span style={{ marginRight: 8 }}>竞价采集</span>
              <Switch checked={toggles.auctionEnabled} onChange={actions.onToggleAuction} disabled={busy.auctionBusy} size="small" />
              {auctionStatus && (
                <Tag style={{ marginLeft: 8 }} color={auctionStatus.running ? "green" : "default"}>
                  {auctionStatus.state} rds={auctionStatus.rounds}
                </Tag>
              )}
            </div>
            <div>
              <span style={{ marginRight: 8 }}>K线告警 SSE</span>
              <Switch checked={toggles.klineAlertsEnabled} onChange={actions.onToggleKlineAlerts} size="small" />
            </div>
            <div>
              <span style={{ marginRight: 8 }}>W2S告警 SSE</span>
              <Switch checked={toggles.w2sAlertsEnabled} onChange={actions.onToggleW2sAlerts} size="small" />
            </div>
          </Space>
        </div>
      </details>
    </div>
  );
}
