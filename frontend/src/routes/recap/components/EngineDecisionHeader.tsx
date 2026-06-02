/** PR-14B: 复盘引擎交易结论总览 — 替代旧"今日交易原则"卡片。 */
import { Descriptions, Tag } from "antd";
import type { EngineSummary, EngineMarketRegimeReview } from "../../../lib/api";

interface Props {
  engineSummary: EngineSummary;
  marketRegime?: EngineMarketRegimeReview | null;
}

export default function EngineDecisionHeader({ engineSummary, marketRegime }: Props) {
  const allow = engineSummary.allow_trade;
  const mode = engineSummary.trade_mode;
  const modeColor =
    allow ? (mode === "ultra_short_only" ? "orange" : mode === "mainline_core_only" ? "blue" : "green") : "red";

  return (
    <div style={{ background: allow ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)", border: `1px solid ${allow ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`, borderRadius: 8, padding: 16, marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <Tag color={modeColor} style={{ fontSize: 14, padding: "4px 12px" }}>
          {allow ? (mode === "ultra_short_only" ? "超短防守" : mode === "mainline_core_only" ? "主线核心" : "正常交易") : "不交易"}
        </Tag>
        <span style={{ fontSize: 16, fontWeight: 700, color: "#8ddcff" }}>
          {engineSummary.conclusion || (allow ? "允许交易" : "不允许交易")}
        </span>
      </div>

      <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }}>
        <Descriptions.Item label="交易模式">{engineSummary.trade_mode}</Descriptions.Item>
        <Descriptions.Item label="仓位上限">{engineSummary.position_limit != null ? `${(engineSummary.position_limit * 100).toFixed(0)}%` : "-"}</Descriptions.Item>
        <Descriptions.Item label="主阻断规则">
          <span style={{ color: "#66d9ef" }}>{engineSummary.no_trade_blocking_rule || "-"}</span>
        </Descriptions.Item>
        {(engineSummary.no_trade_reasons?.length ?? 0) > 0 && (
          <Descriptions.Item label="不交易原因" span={3}>
            {engineSummary.no_trade_reasons?.join("；")}
          </Descriptions.Item>
        )}
        {engineSummary.next_day_strategy && (
          <Descriptions.Item label="明日策略" span={3}>
            <span style={{ color: "#8ddcff" }}>{engineSummary.next_day_strategy}</span>
          </Descriptions.Item>
        )}
        {(engineSummary.risk_notes?.length ?? 0) > 0 && (
          <Descriptions.Item label="风险提示" span={3}>
            {engineSummary.risk_notes?.join("；")}
          </Descriptions.Item>
        )}
      </Descriptions>
    </div>
  );
}
