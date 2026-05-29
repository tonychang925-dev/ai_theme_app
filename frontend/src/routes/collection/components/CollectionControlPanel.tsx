/** P4-1A: 采集控制面板 — 纯展示 + 回调。使用原生 button/checkbox 替代 antd 交互组件，排除按钮点击失效问题。 */
import { Tag, Descriptions } from "antd";
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
  color: "#e2e8f0",
};

const btnStyle: React.CSSProperties = {
  padding: "4px 12px",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: 4,
  background: "rgba(255,255,255,0.08)",
  color: "#e2e8f0",
  cursor: "pointer",
  fontSize: 13,
  marginRight: 6,
};

const btnPrimaryStyle: React.CSSProperties = {
  ...btnStyle,
  background: "#1677ff",
  border: "1px solid #1677ff",
};

const btnDangerStyle: React.CSSProperties = {
  ...btnStyle,
  background: "rgba(255,77,79,0.15)",
  border: "1px solid #ff4d4f",
  color: "#ff4d4f",
};

const btnDisabledStyle: React.CSSProperties = {
  ...btnStyle,
  opacity: 0.4,
  cursor: "not-allowed",
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#94a3b8",
  marginRight: 8,
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
          <span style={{ marginRight: 8 }}>实时采集控制</span>
          {status.running === "up" ? <Tag color="green">运行中</Tag> : status.running === "down" ? <Tag color="red">已停止</Tag> : <Tag>检查中</Tag>}
        </summary>
        <div style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 8 }}>
            <button
              style={busy.mainBusy ? btnDisabledStyle : btnPrimaryStyle}
              onClick={actions.onStartRealtime}
              disabled={busy.mainBusy}
            >
              {busy.mainBusy && status.running === "unknown" ? "处理中..." : "启动实时采集"}
            </button>
            <button
              style={btnDangerStyle}
              onClick={actions.onStopRealtime}
            >
              停止实时采集
            </button>
            <button
              style={busy.mainBusy ? btnDisabledStyle : btnStyle}
              onClick={actions.onRefreshRealtime}
              disabled={busy.mainBusy}
            >
              刷新状态
            </button>
          </div>
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
          <span style={{ marginRight: 8 }}>JYHF DOM 采集</span>
          {jyhfStatus?.collector_running ? <Tag color="green">采集中</Tag> : <Tag>已停止</Tag>}
        </summary>
        <div style={{ marginTop: 8 }}>
          <div style={{ marginBottom: 8 }}>
            <button
              style={busy.jyhfBusy ? btnDisabledStyle : btnPrimaryStyle}
              onClick={actions.onStartDom}
              disabled={busy.jyhfBusy}
            >
              {busy.jyhfBusy ? "处理中..." : "启动 DOM 采集"}
            </button>
            <button
              style={busy.jyhfBusy ? btnDisabledStyle : btnDangerStyle}
              onClick={actions.onStopDom}
              disabled={busy.jyhfBusy}
            >
              停止 DOM 采集
            </button>
            <button
              style={busy.jyhfBusy ? btnDisabledStyle : btnStyle}
              onClick={actions.onRefreshDom}
              disabled={busy.jyhfBusy}
            >
              刷新 DOM 状态
            </button>
          </div>
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
          <div style={{ marginBottom: 6 }}>
            <label style={labelStyle}>
              <input
                type="checkbox"
                checked={toggles.auctionEnabled}
                onChange={(e) => actions.onToggleAuction(e.target.checked)}
                disabled={busy.auctionBusy}
                style={{ marginRight: 4 }}
              />
              竞价采集
            </label>
            {auctionStatus && (
              <Tag style={{ marginLeft: 4 }} color={auctionStatus.running ? "green" : "default"}>
                {auctionStatus.state} rds={auctionStatus.rounds}
              </Tag>
            )}
          </div>
          <div style={{ marginBottom: 6 }}>
            <label style={labelStyle}>
              <input
                type="checkbox"
                checked={toggles.klineAlertsEnabled}
                onChange={(e) => actions.onToggleKlineAlerts(e.target.checked)}
                style={{ marginRight: 4 }}
              />
              K线告警 SSE
            </label>
          </div>
          <div>
            <label style={labelStyle}>
              <input
                type="checkbox"
                checked={toggles.w2sAlertsEnabled}
                onChange={(e) => actions.onToggleW2sAlerts(e.target.checked)}
                style={{ marginRight: 4 }}
              />
              W2S告警 SSE
            </label>
          </div>
        </div>
      </details>
    </div>
  );
}
