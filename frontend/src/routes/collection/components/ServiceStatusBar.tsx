/** P4-3B: 紧凑全局状态栏 — 驾驶舱风格，8 个状态灯。 */
import { Badge } from "antd";
import type { JyhfCdpCollectorStatus, JyhfAuctionStatus, NewChainRealtimeStatus } from "../../../lib/api";

export type SseConnState = "disabled" | "connecting" | "connected" | "disconnected";

interface Props {
  stackStatus: NewChainRealtimeStatus | null;
  jyhfStatus: JyhfCdpCollectorStatus | null;
  auctionStatus: JyhfAuctionStatus | null;
  klineSseState: SseConnState;
  w2sSseState: SseConnState;
  klineAlertCount: number;
  w2sAlertCount: number;
  redisHealth?: { state?: string; redis_state?: string; stream_state?: string; dead_letter_state?: string; latency_ms?: number | null };
  dbHealth?: { state?: string; db_state?: string };
}

function dot(s: string | undefined): "success" | "warning" | "error" | "default" {
  if (s === "ready" || s === "connected" || s === "running") return "success";
  if (s === "degraded" || s === "warning") return "warning";
  if (s === "blocked" || s === "disconnected" || s === "error") return "error";
  return "default";
}

function dlqBadge(count: number): "success" | "warning" | "error" | "default" {
  if (count === 0) return "success";
  if (count < 100) return "warning";
  if (count < 1000) return "error";
  return "error"; // deep red for >=1000
}

function dlqLabel(count: number): string {
  if (count === 0) return "0";
  if (count < 100) return String(count);
  if (count < 1000) return `!${count}`;
  return `!!${count}`;
}

export default function ServiceStatusBar(props: Props) {
  const { stackStatus, jyhfStatus, auctionStatus, klineSseState, w2sSseState, klineAlertCount, w2sAlertCount, redisHealth, dbHealth } = props;

  const hasRaw = Boolean(stackStatus?.raw_news_pid); const hasDec = Boolean(stackStatus?.decision_pid);
  const rtState = hasRaw && hasDec ? "running" : hasRaw || hasDec ? "degraded" : "stopped";
  const domState = (jyhfStatus?.collector_running && jyhfStatus?.cdp_connected) ? "connected"
    : jyhfStatus?.service_running ? "warning" : "stopped";
  const aucState = auctionStatus?.running ? "running" : auctionStatus?.state === "finished" ? "stopped" : "stopped";
  const dlCount = stackStatus?.dead_letter_count ?? 0;

  const redisState = redisHealth?.redis_state || redisHealth?.state || "?";
  const streamState = redisHealth?.stream_state || "?";
  const dlState = dlCount >= 1000 ? "blocked" : dlCount >= 100 ? "degraded" : dlCount > 0 ? "warning" : "ready";

  const items = [
    { label: "Realtime", s: rtState, v: `${stackStatus?.raw_news_pid ?? "-"}/${stackStatus?.decision_pid ?? "-"}` },
    { label: "CDP", s: domState, v: jyhfStatus?.capture_count_total ? `x${jyhfStatus.capture_count_total}` : "-" },
    { label: "Auction", s: aucState, v: auctionStatus?.rounds ? `r${auctionStatus.rounds}` : "-" },
    { label: "Kline", s: klineSseState === "connected" ? "running" : "stopped", v: String(klineAlertCount) },
    { label: "W2S", s: w2sSseState === "connected" ? "running" : "stopped", v: String(w2sAlertCount) },
    { label: "Redis", s: redisState, v: redisHealth?.latency_ms != null ? `${redisHealth.latency_ms}ms` : "?" },
    { label: "Stream", s: streamState, v: "" },
    { label: "DB", s: dbHealth?.db_state || dbHealth?.state, v: "" },
  ];
  const dlItem = { label: "DLQ", s: dlState, v: dlqLabel(dlCount), badge: dlqBadge(dlCount) };

  return (
    <div style={{
      display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center",
      padding: "4px 8px", background: "rgba(255,255,255,0.03)", borderRadius: 6,
      border: "1px solid rgba(255,255,255,0.06)", marginBottom: 8,
    }}>
      {items.map((it) => (
        <div key={it.label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
          <Badge status={dot(it.s)} />
          <span style={{ color: "#94a3b8", fontWeight: 500 }}>{it.label}</span>
          {it.v ? <span style={{ color: "#e2e8f0", fontSize: 11 }}>{it.v}</span> : null}
        </div>
      ))}
      <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
        <Badge status={dlItem.badge} />
        <span style={{ color: "#94a3b8", fontWeight: 500 }}>{dlItem.label}</span>
        <span style={{ color: dlCount >= 100 ? "#f59e0b" : "#e2e8f0", fontSize: 11, fontWeight: dlCount >= 100 ? 600 : 400 }}>
          {dlItem.v}
        </span>
      </div>
    </div>
  );
}
