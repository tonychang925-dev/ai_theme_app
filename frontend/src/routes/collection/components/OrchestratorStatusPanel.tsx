/** P4-2B: Realtime Business Orchestrator 只读状态面板。 */
import { Badge, Card, Descriptions, Space, Tag } from "antd";
import type { OrchestratorStatus, OrchestratorServiceState } from "../../../lib/api";

interface Props {
  status: OrchestratorStatus | null;
  loading: boolean;
  error?: string | null;
  onRefresh: () => void;
}

function stateBadge(state: string): "success" | "warning" | "error" | "default" {
  if (state === "ready" || state === "running") return "success";
  if (state === "degraded") return "warning";
  if (state === "blocked" || state === "failed") return "error";
  return "default";
}

function stateLabel(state: string): string {
  const map: Record<string, string> = {
    ready: "就绪",
    running: "运行中",
    stopped: "已停止",
    blocked: "阻塞",
    degraded: "降级",
    failed: "失败",
    unknown: "未知",
  };
  return map[state] || state;
}

function serviceName(name: string): string {
  const map: Record<string, string> = {
    cdp_token: "CDP / Token",
    jyhf_market: "JYHF Market",
    jyhf_auction: "JYHF Auction",
    w2s_alert: "W2S Alert",
    support_alert: "Support Alert",
  };
  return map[name] || name;
}

function ServiceCard({ svc }: { svc: OrchestratorServiceState }) {
  return (
    <Card size="small" style={{ flex: 1, minWidth: 140 }}>
      <Space>
        <Badge status={stateBadge(svc.observed_state)} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>{serviceName(svc.name)}</span>
      </Space>
      <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}>
        <Tag>{stateLabel(svc.observed_state)}</Tag>
        {svc.desired_state === "wanted"
          ? <Tag color="blue">待启动</Tag>
          : <Tag color="default">非当前窗口</Tag>
        }
      </div>
      <div style={{ fontSize: 11, color: "#8c8c8c", marginTop: 2 }}>
        owner: {svc.owner}
      </div>
      {svc.blockers.length > 0 && (
        <div style={{ marginTop: 4 }}>
          {svc.blockers.slice(0, 2).map((b, i) => (
            <div key={i} style={{ fontSize: 10, color: "#ef4444", lineHeight: 1.4 }}>
              ⛔ {b}
            </div>
          ))}
          {svc.blockers.length > 2 && (
            <div style={{ fontSize: 10, color: "#64748b" }}>
              +{svc.blockers.length - 2} more...
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default function OrchestratorStatusPanel({ status, loading, error, onRefresh }: Props) {
  if (!status) {
    return (
      <Card size="small" style={{ marginTop: 12 }}>
        <div style={{ color: error ? "#ef4444" : "#64748b", textAlign: "center", padding: 20, fontSize: error ? 12 : 14 }}>
          {error ? `编排器不可用: ${error}` : (loading ? "加载编排器状态中..." : "编排器状态暂不可用")}
        </div>
      </Card>
    );
  }

  const svcList = ["cdp_token", "jyhf_market", "jyhf_auction", "w2s_alert", "support_alert"]
    .map((k) => status.services?.[k])
    .filter(Boolean) as OrchestratorServiceState[];

  return (
    <div style={{ marginTop: 12 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#e2e8f0" }}>自动编排</span>
        <Tag color={status.enabled ? "green" : "default"}>
          {status.enabled ? "诊断已启用" : "已禁用"}
        </Tag>
        {status.enabled && (
          <Tag color={status.actions_enabled ? "orange" : "default"}>
            {status.actions_enabled ? "动作: 允许执行" : "动作: 只读"}
          </Tag>
        )}
        <Tag color="blue">{status.phase_label}</Tag>
        {status.dry_run && <Tag>dry_run</Tag>}
        <span style={{ fontSize: 11, color: "#64748b", marginLeft: "auto" }}>
          seq={status.tick_seq}
          {status.tick_duration_ms ? ` ${status.tick_duration_ms}ms` : ""}
          {status.now_override ? ` sim:${status.now_override}` : ""}
          {!status.is_trade_day && " · 非交易日"}
        </span>
        <button
          style={{
            padding: "2px 10px", border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 4, background: "rgba(255,255,255,0.06)", color: "#94a3b8",
            cursor: "pointer", fontSize: 12,
          }}
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? "刷新中..." : "刷新"}
        </button>
      </div>

      {/* Executed Actions */}
      {status.executed_actions && status.executed_actions.length > 0 && (
        <Card size="small" style={{ marginBottom: 8 }} title={
          <span style={{ color: "#22c55e" }}>已执行动作 ({status.executed_actions.length})</span>
        }>
          {status.executed_actions.map((a: any, i: number) => (
            <div key={i} style={{ fontSize: 11, marginBottom: 2, color: "#e2e8f0" }}>
              <Tag color={a.result ? "green" : "red"}>{a.result ? "ok" : "fail"}</Tag>
              <span>{a.service}</span>
              {a.duration_ms != null && <span style={{ color: "#64748b", marginLeft: 8 }}>{a.duration_ms}ms</span>}
              {a.skipped && <span style={{ color: "#f59e0b", marginLeft: 8 }}>{a.skipped}</span>}
            </div>
          ))}
        </Card>
      )}

      {/* Service cards */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {svcList.map((svc) => (
          <ServiceCard key={svc.name} svc={svc} />
        ))}
      </div>

      {/* Planned Actions */}
      {status.planned_actions.length > 0 && (
        <Card size="small" style={{ marginTop: 8 }} title="Planned Actions">
          {status.planned_actions.map((a, i) => (
            <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>
              <Tag color="blue">{a.action}</Tag>
              <span style={{ color: "#e2e8f0" }}>{serviceName(a.service)}</span>
              <span style={{ color: "#64748b", marginLeft: 8 }}>{a.reason}</span>
            </div>
          ))}
        </Card>
      )}

      {/* Global Blockers */}
      {status.global_blockers.length > 0 && (
        <Card size="small" style={{ marginTop: 8 }} title={
          <span style={{ color: "#f59e0b" }}>Blockers ({status.global_blockers.length})</span>
        }>
          {status.global_blockers.slice(0, 10).map((b, i) => (
            <div key={i} style={{ fontSize: 11, color: "#ef4444", lineHeight: 1.5 }}>
              {b}
            </div>
          ))}
          {status.global_blockers.length > 10 && (
            <div style={{ fontSize: 11, color: "#64748b" }}>
              +{status.global_blockers.length - 10} more...
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
