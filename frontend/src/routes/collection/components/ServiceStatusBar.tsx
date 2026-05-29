/** P4-1A: 顶部服务状态总览栏 — 纯展示组件。 */
import { Badge, Card, Space, Statistic } from "antd";
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
}

function sseBadge(state: SseConnState): "success" | "warning" | "error" | "default" {
  if (state === "connected") return "success";
  if (state === "connecting") return "warning";
  if (state === "disconnected") return "error";
  return "default";
}

function sseLabel(state: SseConnState): string {
  if (state === "connected") return "已连接";
  if (state === "connecting") return "连接中";
  if (state === "disconnected") return "已断开";
  return "已禁用";
}

export default function ServiceStatusBar(props: Props) {
  const { stackStatus, jyhfStatus, auctionStatus, klineSseState, w2sSseState, klineAlertCount, w2sAlertCount } = props;

  // Redis
  const redisError = stackStatus?.redis_error;
  const redisStreams = stackStatus?.redis_streams;
  const rawLen = redisStreams?.["stream:news:raw"]?.length ?? 0;
  let redisBadge: "success" | "warning" | "error" | "default" = "default";
  let redisLabel = "未确认";
  if (redisError) { redisBadge = "error"; redisLabel = "异常"; }
  else if (Object.keys(redisStreams || {}).length > 0) {
    redisBadge = rawLen > 5000 ? "warning" : "success";
    redisLabel = rawLen > 5000 ? "积压" : "正常";
  }

  // 实时采集：只根据 SPS live-PID-verified 状态判断
  let rtBadge: "success" | "warning" | "error" | "default" = "default";
  let rtLabel = "已停止";
  const hasRawPid = Boolean(stackStatus?.raw_news_pid);
  const hasDecPid = Boolean(stackStatus?.decision_pid);
  const rtHasBoth = hasRawPid && hasDecPid;
  const rtHasOne = hasRawPid || hasDecPid;
  if (rtHasBoth) { rtBadge = "success"; rtLabel = "运行中"; }
  else if (rtHasOne) { rtBadge = "warning"; rtLabel = "降级"; }
  if (stackStatus?.status_source === "bff_sps_unreachable") { rtBadge = "error"; rtLabel = "SPS不可达"; }
  if (stackStatus?.last_error) { rtBadge = "error"; rtLabel = "异常"; }

  // DOM：需 collector_running + cdp_connected + 最近有采集才确认采集中
  let domBadge: "success" | "warning" | "error" | "default" = "default";
  let domLabel = "未启动";
  const domActive = jyhfStatus?.collector_running && jyhfStatus?.cdp_connected;
  const domHasData = !!(jyhfStatus?.last_capture_at || jyhfStatus?.capture_count_total);
  if (domActive && domHasData) { domBadge = "success"; domLabel = "采集中"; }
  else if (domActive && !domHasData) { domBadge = "warning"; domLabel = "等待数据"; }
  else if (jyhfStatus?.service_running) { domBadge = "warning"; domLabel = "服务运行"; }
  if (jyhfStatus?.last_error) { domBadge = "error"; domLabel = "异常"; }

  // 竞价
  let aucBadge: "success" | "warning" | "error" | "default" = "default";
  let aucLabel = "空闲";
  if (auctionStatus?.running) { aucBadge = "success"; aucLabel = "采集中"; }
  if (auctionStatus?.state === "error") { aucBadge = "error"; aucLabel = "异常"; }
  if (auctionStatus?.state === "finished") { aucBadge = "default"; aucLabel = "已结束"; }

  // DLQ
  const dlCount = stackStatus?.dead_letter_count ?? 0;
  let dlBadge: "success" | "warning" | "error" | "default" = "success";
  let dlLabel = "0";
  if (dlCount > 0) { dlBadge = dlCount >= 10 ? "error" : "warning"; dlLabel = String(dlCount); }

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
      <Card size="small" style={{ flex: 1, minWidth: 120 }}>
        <Space><Badge status={redisBadge} /><span style={{ fontWeight: 600 }}>Redis</span></Space>
        <Statistic value={redisLabel} valueStyle={{ fontSize: 14 }} />
        <div style={{ fontSize: 11, color: "#8c8c8c" }}>raw={rawLen} DL={dlCount}</div>
      </Card>

      <Card size="small" style={{ flex: 1, minWidth: 120 }}>
        <Space><Badge status={rtBadge} /><span style={{ fontWeight: 600 }}>实时采集</span></Space>
        <Statistic value={rtLabel} valueStyle={{ fontSize: 14 }} />
        <div style={{ fontSize: 11, color: "#8c8c8c" }}>
          raw={stackStatus?.raw_news_pid ?? "-"} dec={stackStatus?.decision_pid ?? "-"} db={stackStatus?.db_collector_pid ?? "-"}
        </div>
      </Card>

      <Card size="small" style={{ flex: 1, minWidth: 120 }}>
        <Space><Badge status={domBadge} /><span style={{ fontWeight: 600 }}>DOM采集</span></Space>
        <Statistic value={domLabel} valueStyle={{ fontSize: 14 }} />
        <div style={{ fontSize: 11, color: "#8c8c8c" }}>
          {jyhfStatus?.service_owner ?? "?"} cap={jyhfStatus?.capture_count_total ?? 0}
        </div>
      </Card>

      <Card size="small" style={{ flex: 1, minWidth: 120 }}>
        <Space><Badge status={aucBadge} /><span style={{ fontWeight: 600 }}>竞价</span></Space>
        <Statistic value={aucLabel} valueStyle={{ fontSize: 14 }} />
        <div style={{ fontSize: 11, color: "#8c8c8c" }}>
          rds={auctionStatus?.rounds ?? 0} pts={auctionStatus?.points ?? 0}
        </div>
      </Card>

      <Card size="small" style={{ flex: 1, minWidth: 120 }}>
        <Space><Badge status={sseBadge(klineSseState)} /><span style={{ fontWeight: 600 }}>K线告警</span></Space>
        <Statistic value={sseLabel(klineSseState)} valueStyle={{ fontSize: 14 }} />
        <div style={{ fontSize: 11, color: "#8c8c8c" }}>alerts={klineAlertCount}</div>
      </Card>

      <Card size="small" style={{ flex: 1, minWidth: 120 }}>
        <Space><Badge status={sseBadge(w2sSseState)} /><span style={{ fontWeight: 600 }}>W2S告警</span></Space>
        <Statistic value={sseLabel(w2sSseState)} valueStyle={{ fontSize: 14 }} />
        <div style={{ fontSize: 11, color: "#8c8c8c" }}>alerts={w2sAlertCount}</div>
      </Card>

      <Card size="small" style={{ flex: 1, minWidth: 100 }}>
        <Space><Badge status={dlBadge} /><span style={{ fontWeight: 600 }}>DLQ</span></Space>
        <Statistic value={dlLabel} valueStyle={{ fontSize: 14 }} />
        <div style={{ fontSize: 11, color: "#8c8c8c" }}>Pending={stackStatus?.pending_count ?? 0}</div>
      </Card>
    </div>
  );
}
