/** PR-14B: 复盘引擎交易结论总览 — 替代旧"今日交易原则"卡片。 */
import { Tag } from "antd";
import type { EngineSummary, EngineMarketRegimeReview } from "../../../lib/api";

interface Props {
  engineSummary: EngineSummary;
  marketRegime?: EngineMarketRegimeReview | null;
}

function translateTradeMode(value?: string | null) {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    no_trade: "不交易",
    ultra_short_only: "仅超短",
    mainline_core_only: "主线核心",
    mainline_tradable: "主线可交易",
    observe_only: "仅观察",
    normal: "正常交易",
  };
  return map[key] || key || "未知";
}

function translateBlockingRule(value?: string | null) {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    broad_market_regime_bearish_adverse: "大盘弱势不利",
    mainline_risk_high: "主线风险过高",
    no_base_data: "基础数据缺失",
    no_signal: "无有效信号",
    unknown: "未知",
  };
  return map[key] || key || "未知";
}

export default function EngineDecisionHeader({ engineSummary, marketRegime }: Props) {
  const allow = engineSummary.allow_trade;
  const mode = engineSummary.trade_mode;
  const modeColor =
    allow ? (mode === "ultra_short_only" ? "orange" : mode === "mainline_core_only" ? "blue" : "green") : "red";

  return (
    <div className="workspace-card recap-engine-panel recap-decision-header">
      <div className="recap-decision-header__top">
        <Tag color={modeColor}>{allow ? translateTradeMode(mode) : "不交易"}</Tag>
        <span className="recap-decision-header__headline">
          {engineSummary.conclusion || (allow ? "允许交易" : "不允许交易")}
        </span>
      </div>

      <div className="recap-decision-header__grid">
        <div className="recap-decision-header__item">
          <span className="recap-decision-header__label">交易模式</span>
          <span className="recap-decision-header__value">{translateTradeMode(engineSummary.trade_mode)}</span>
        </div>
        <div className="recap-decision-header__item">
          <span className="recap-decision-header__label">仓位上限</span>
          <span className="recap-decision-header__value">{engineSummary.position_limit != null ? `${(engineSummary.position_limit * 100).toFixed(0)}%` : "-"}</span>
        </div>
        <div className="recap-decision-header__item">
          <span className="recap-decision-header__label">主阻断规则</span>
          <span className="recap-decision-header__value">{translateBlockingRule(engineSummary.no_trade_blocking_rule)}</span>
        </div>
        {(engineSummary.no_trade_reasons?.length ?? 0) > 0 && (
          <div className="recap-decision-header__item recap-decision-header__item--full">
            <span className="recap-decision-header__label">不交易原因</span>
            <span className="recap-decision-header__value">{engineSummary.no_trade_reasons?.join("；")}</span>
          </div>
        )}
        {engineSummary.next_day_strategy && (
          <div className="recap-decision-header__item recap-decision-header__item--full">
            <span className="recap-decision-header__label">明日策略</span>
            <span className="recap-decision-header__value">{engineSummary.next_day_strategy}</span>
          </div>
        )}
        {(engineSummary.risk_notes?.length ?? 0) > 0 && (
          <div className="recap-decision-header__item recap-decision-header__item--full">
            <span className="recap-decision-header__label">风险提示</span>
            <span className="recap-decision-header__value">{engineSummary.risk_notes?.join("；")}</span>
          </div>
        )}
      </div>
    </div>
  );
}
