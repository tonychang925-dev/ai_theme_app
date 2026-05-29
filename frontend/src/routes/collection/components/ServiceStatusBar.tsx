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
  redisHealth?: { state?: string; redis_state?: string; dead_letter_state?: string; latency_ms?: number | null };
  dbHealth?: { state?: string; db_state?: string };
}

function dot(s: string | undefined): "success" | "warning" | "error" | "default" {
  if (s === "ready" || s === "connected" || s === "running") return "success";
  if (s === "degraded" || s === "warning") return "warning";
  if (s === "blocked" || s === "disconnected" || s === "error") return "error";
  return "default";
}

export default function ServiceStatusBar(props: Props) {
  const { stackStatus, jyhfStatus, auctionStatus, klineSseState, w2sSseState, klineAlertCount, w2sAlertCount, redisHealth, dbHealth } = props;

  const hasRaw = Boolean(stackStatus?.raw_news_pid); const hasDec = Boolean(stackStatus?.decision_pid);
  const rtState = hasRaw && hasDec ? "running" : hasRaw || hasDec ? "degraded" : "stopped";
  const domState = (jyhfStatus?.collector_running && jyhfStatus?.cdp_connected) ? "connected"
    : jyhfStatus?.service_running ? "warning" : "stopped";
  const aucState = auctionStatus?.running ? "running" : auctionStatus?.state === "finished" ? "stopped" : "stopped";
  const dlCount = stackStatus?.dead_letter_count ?? 0;

  const items = [
    { label: "实时采集", s: rtState, v: `${stackStatus?.raw_news_pid ?? "-"}/${stackStatus?.decision_pid ?? "-"}` },
    { label: "DOM", s: domState, v: jyhfStatus?.capture_count_total ? `cap=${jyhfStatus.capture_count_total}` : "-" },
    { label: "Auction", s: aucState, v: auctionStatus?.rounds ? `rds=${auctionStatus.rounds}` : "-" },
    { label: "Kline", s: klineSseState === "connected" ? "running" : "stopped", v: String(klineAlertCount) },
    { label: "W2S", s: w2sSseState === "connected" ? "running" : "stopped", v: String(w2sAlertCount) },
    { label: "Redis", s: redisHealth?.redis_state || redisHealth?.state, v: redisHealth?.latency_ms != null ? `${redisHealth.latency_ms}ms` : "?" },
    { label: "DB", s: dbHealth?.db_state || dbHealth?.state, v: dbHealth?.db_state || "?" },
    { label: "DLQ", s: dlCount > 100 ? "degraded" : dlCount > 1000 ? "blocked" : "ready", v: String(dlCount) },
  ];

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
          <span style={{ color: "#e2e8f0", fontSize: 11 }}>{it.v}</span>
        </div>
      ))}
    </div>
  );
}
