/** P4-2B: Realtime Business Orchestrator 只读状态面板。 */
import { Badge, Card, Descriptions, Space, Tag, Table, Typography } from "antd";
import type { OrchestratorStatus, OrchestratorServiceState, RedisRuntimeHealth, RedisStreamHealth, DatabaseRuntimeHealth } from "../../../lib/api";

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
    <Card
      size="small"
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, fontSize: 14, color: "#e2e8f0" }}>自动编排</span>
          <Tag color={status.enabled ? "green" : "default"}>
            {status.enabled ? "诊断已启用" : "已禁用"}
          </Tag>
          {status.enabled && (
            <Tag color={status.actions_enabled ? "orange" : "default"}>
              {status.actions_enabled ? "动作: 允许" : "动作: 只读"}
            </Tag>
          )}
          <Tag color="blue" style={{ marginLeft: 4 }}>{status.phase_label}</Tag>
          <span style={{ fontSize: 10, color: "#64748b", marginLeft: "auto" }}>
            seq={status.tick_seq}{status.tick_duration_ms ? ` ${status.tick_duration_ms}ms` : ""}
            {status.now_override ? ` sim:${status.now_override}` : ""}
            {!status.is_trade_day && " · 非交易日"}
          </span>
          <button
            style={{
              padding: "1px 8px", border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 4, background: "rgba(255,255,255,0.06)", color: "#94a3b8",
              cursor: "pointer", fontSize: 11,
            }}
            onClick={onRefresh}
            disabled={loading}
          >
            {loading ? "..." : "刷新"}
          </button>
        </div>
      }
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 8,
      }}
    >
      {/* Executed Actions */}
      {status.executed_actions && status.executed_actions.length > 0 && (
        <div style={{ marginBottom: 8, padding: "4px 8px", background: "rgba(34,197,94,0.06)", borderRadius: 4 }}>
          {status.executed_actions.map((a: any, i: number) => (
            <span key={i} style={{ fontSize: 11, marginRight: 12, color: "#e2e8f0" }}>
              <Tag color={a.result ? "green" : "red"} style={{ fontSize: 10 }}>{a.result ? "ok" : "fail"}</Tag>
              {a.service}
              {a.duration_ms != null && <span style={{ color: "#64748b", marginLeft: 4 }}>{a.duration_ms}ms</span>}
              {a.skipped && <span style={{ color: "#f59e0b", marginLeft: 4 }}>{a.skipped}</span>}
            </span>
          ))}
        </div>
      )}

      {/* Service cards */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {svcList.map((svc) => (
          <ServiceCard key={svc.name} svc={svc} />
        ))}
      </div>

      {/* Runtime Health */}
      <RedisHealthSection redis={status.runtime_dependencies?.redis as RedisRuntimeHealth | undefined} />
      <DbHealthSection db={status.runtime_dependencies?.database as DatabaseRuntimeHealth | undefined} />

      {/* Planned Actions */}
      {status.planned_actions.length > 0 && (
        <div style={{
          marginTop: 8, padding: "4px 8px",
          background: "rgba(22,119,255,0.06)", borderRadius: 4,
        }}>
          {status.planned_actions.map((a, i) => (
            <div key={i} style={{ fontSize: 11, marginBottom: 2 }}>
              <Tag color="blue" style={{ fontSize: 10 }}>{a.action}</Tag>
              <span style={{ color: "#e2e8f0" }}>{serviceName(a.service)}</span>
              <span style={{ color: "#64748b", marginLeft: 6 }}>{a.reason}</span>
            </div>
          ))}
        </div>
      )}

      {/* Global Blockers */}
      {status.global_blockers.length > 0 && (
        <div style={{
          marginTop: 6, padding: "4px 8px",
          background: "rgba(245,158,11,0.05)", borderRadius: 4,
        }}>
          {status.global_blockers.slice(0, 6).map((b, i) => (
            <div key={i} style={{ fontSize: 10, color: "#ef4444", lineHeight: 1.5 }}>
              {b}
            </div>
          ))}
          {status.global_blockers.length > 6 && (
            <div style={{ fontSize: 10, color: "#64748b" }}>
              +{status.global_blockers.length - 6} more...
            </div>
          )}
        </div>
      )}
    </Card>
  );
}


function healthBadge(s: string | undefined): "success" | "warning" | "error" | "default" {
  if (s === "ready") return "success";
  if (s === "degraded") return "warning";
  if (s === "blocked") return "error";
  return "default";
}

function stateColor(s: string | undefined): string {
  if (s === "ready") return "#22c55e";
  if (s === "degraded") return "#f59e0b";
  if (s === "blocked") return "#ef4444";
  return "#64748b";
}

function RedisHealthSection({ redis }: { redis?: RedisRuntimeHealth }) {
  if (!redis) return null;

  const streams = redis.streams || {};
  const streamKeys = ["stream:w2s:alerts", "stream:kline:alerts", "stream:news:raw", "stream:events:structured", "stream:events:decision", "stream:dead:letter"];

  return (
    <Card size="small" style={{ marginTop: 8, background: "rgba(255,255,255,0.02)" }} title={
      <Space>
        <span style={{ fontWeight: 600, fontSize: 13 }}>Redis Health</span>
        <Badge status={healthBadge(redis.state)} />
        <span style={{ color: stateColor(redis.state), fontSize: 12 }}>{redis.state || "?"}</span>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          {redis.latency_ms != null ? `${redis.latency_ms}ms` : ""}
        </Typography.Text>
      </Space>
    }>
      <div style={{ display: "flex", gap: 8, marginBottom: 6, fontSize: 12, flexWrap: "wrap" }}>
        <span>Redis <b style={{ color: stateColor(redis.redis_state) }}>{redis.redis_state || "?"}</b></span>
        <span>· Stream <b style={{ color: stateColor(redis.stream_state) }}>{redis.stream_state || "?"}</b></span>
        <span>· DL <b style={{ color: stateColor(redis.dead_letter_state) }}>{redis.dead_letter_state || "?"}</b></span>
      </div>

      <Table<{ key: string; length?: number | null; state?: string }>
        size="small"
        pagination={false}
        dataSource={streamKeys.filter(k => streams[k]).map(k => ({ key: k, ...streams[k] }))}
        columns={[
          { title: "Stream", dataIndex: "key", key: "key", width: 130, render: (v: string) => <span style={{ fontSize: 12 }}>{v.replace("stream:","").replace("events:","").replace("alerts","").replace("news:","").replace("dead:letter","dead")}</span> },
          { title: "Len", dataIndex: "length", key: "length", width: 50, render: (v: number | null) => <span style={{ fontSize: 12 }}>{v != null && v > 999 ? Math.round(v/1000)+"k" : (v ?? "-")}</span> },
          { title: "State", dataIndex: "state", key: "state", width: 70, render: (v: string) => <Badge status={healthBadge(v)} text={v} /> },
        ]}
        locale={{ emptyText: "—" }}
      />

      <Typography.Text type="secondary" style={{ fontSize: 10, display: "block", marginTop: 4 }}>
        Stream length 为历史/积压指标，不代表服务正在运行。Dead Letter 积压不等于 Redis 不可用。
      </Typography.Text>
    </Card>
  );
}


function DbHealthSection({ db }: { db?: DatabaseRuntimeHealth }) {
  if (!db || !db.db_state) return null;

  const tables = db.tables || {};
  const tableKeys = Object.keys(tables);
  const samples = db.waiting_samples || [];

  return (
    <Card size="small" style={{ marginTop: 8, background: "rgba(255,255,255,0.02)" }} title={
      <Space>
        <span style={{ fontWeight: 600, fontSize: 13 }}>Database Health</span>
        <Badge status={healthBadge(db.state)} />
        <span style={{ color: stateColor(db.state), fontSize: 12 }}>{db.state || "?"}</span>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          {db.latency_ms != null ? `${db.latency_ms}ms` : ""} {db.write_db}
        </Typography.Text>
      </Space>
    }>
      <div style={{ display: "flex", gap: 8, marginBottom: 6, fontSize: 12, flexWrap: "wrap" }}>
        <span>DB <b style={{ color: stateColor(db.db_state) }}>{db.db_state || "?"}</b></span>
        <span>· Schema <b style={{ color: stateColor(db.schema_state) }}>{db.schema_state || "?"}</b></span>
        <span>· Fresh <b style={{ color: stateColor(db.freshness_state) }}>{db.freshness_state || "?"}</b></span>
        <span>· Lock <b style={{ color: stateColor(db.lock_state) }}>{db.lock_state || "?"}</b></span>
        {samples.length > 0 && <span style={{ color: "#64748b" }}>waiting={samples.length}</span>}
      </div>

      {tableKeys.length > 0 && (
        <Table<{ key: string; estimated_rows?: number | null; age_sec?: number | null; state?: string }>
          size="small"
          pagination={false}
          dataSource={tableKeys.map(k => ({ key: k, ...tables[k] }))}
          columns={[
            { title: "Table", dataIndex: "key", key: "key", width: 130, render: (v: string) => <span style={{ fontSize: 12 }}>{v}</span> },
            { title: "Rows", dataIndex: "estimated_rows", key: "rows", width: 55, render: (v: number | null) => <span style={{ fontSize: 12 }}>{v != null && v > 999 ? Math.round(v/1000)+"k" : (v ?? "-")}</span> },
            { title: "Age", dataIndex: "age_sec", key: "age", width: 60, render: (v: number | null) => <span style={{ fontSize: 12, color: v != null && v > 1800 ? "#f59e0b" : undefined }}>{v != null ? (v > 3600 ? Math.round(v/3600)+"h" : Math.round(v/60)+"m") : "?"}</span> },
            { title: "State", dataIndex: "state", key: "state", width: 70, render: (v: string) => <Badge status={healthBadge(v)} text={v} /> },
          ]}
          locale={{ emptyText: "—" }}
        />
      )}

      {samples.length > 0 && samples[0].wait_event === "ClientRead" && (
        <Typography.Text type="secondary" style={{ fontSize: 10 }}>
          ClientRead 为连接池空闲等待，非锁冲突。
        </Typography.Text>
      )}

      <Typography.Text type="secondary" style={{ fontSize: 10, display: "block", marginTop: 4 }}>
        数据新鲜度 degraded 不代表数据库不可用。
      </Typography.Text>
    </Card>
  );
}
