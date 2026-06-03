import { Tag } from "antd";
import type { EngineMarketRegimeReview, EngineSummary, MarketOverviewNarrative } from "../../../lib/api";

interface Props {
  narrative?: MarketOverviewNarrative | null;
  engineSummary?: EngineSummary | null;
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

function buildFallbackNarrative(
  engineSummary?: EngineSummary | null,
  marketRegime?: EngineMarketRegimeReview | null,
): MarketOverviewNarrative | null {
  if (!engineSummary && !marketRegime) return null;
  const allowTrade = Boolean(engineSummary?.allow_trade);
  const tradeMode = String(engineSummary?.trade_mode || marketRegime?.trade_mode || "no_trade");
  const headline = engineSummary?.conclusion
    || (allowTrade ? "市场环境可参与，但需要结合主线节奏执行。" : "市场环境偏弱，当前不支持主动交易，以观察为主。");
  const riskWarning = engineSummary?.no_trade_reasons?.join("；")
    || engineSummary?.no_trade_blocking_rule
    || marketRegime?.no_trade_blocking_rule
    || engineSummary?.risk_notes?.join("；")
    || "当前以观察为主，注意盘中修复失败和热点切换。";
  const nextDayStrategy = engineSummary?.next_day_strategy
    || (allowTrade
      ? "按主线修复节奏执行，优先观察确认强度再决定参与方式。"
      : "不做新开仓，只观察主线是否修复，D1 候选仅进入观察池。");
  return {
    headline,
    core_points: [
      `交易模式：${translateTradeMode(tradeMode)}；交易权限：${allowTrade ? "允许交易" : "不支持主动交易"}`,
      `主线环境：${String(marketRegime?.mainline_environment || "--")}`,
      `短线情绪：${String(marketRegime?.short_term_sentiment || "--")}`,
      `风险提示：${riskWarning}`,
    ],
    market_state_summary: `市场状态：${String(marketRegime?.broad_market_regime || "--")}，交易模式 ${translateTradeMode(tradeMode)}。`,
    index_summary: marketRegime?.index_data_ready ? "指数数据已就绪，详细状态见下方大盘环境面板。" : "指数数据暂未就绪，详细信息请参考下方大盘环境面板。",
    sentiment_summary: `短线情绪：${String(marketRegime?.short_term_sentiment || "--")}，主线环境：${String(marketRegime?.mainline_environment || "--")}。`,
    hotspot_summary: "热点概览请结合下方主线与行情概览面板继续查看。",
    risk_warning: String(riskWarning || "--"),
    next_day_strategy: String(nextDayStrategy || "--"),
    source: "engine_summary_fallback",
    diagnostics: {
      allow_trade: allowTrade,
      trade_mode: tradeMode,
      fallback: true,
    },
  };
}

export default function MarketOverviewNarrativePanel({ narrative, engineSummary, marketRegime }: Props) {
  const view = narrative ?? buildFallbackNarrative(engineSummary, marketRegime);
  if (!view) return null;

  return (
    <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, padding: 16, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        市场总览
        <Tag color="gold" style={{ marginLeft: 8 }}>复盘开篇总结</Tag>
        {view.source && <Tag color={view.source === "engine_template" ? "green" : "blue"}>{view.source}</Tag>}
      </h3>

      <div style={{ background: "rgba(141,220,255,0.08)", border: "1px solid rgba(141,220,255,0.18)", borderRadius: 8, padding: 14, marginBottom: 12 }}>
        <div className="workspace-note" style={{ marginBottom: 6 }}>今日核心结论</div>
        <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.6 }}>
          {view.headline}
        </div>
      </div>

      <div className="recap-narrative-grid">
        <section className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="metric-label section-title">核心要点</div>
          <ul className="workspace-list">
            {view.core_points.map((point, idx) => (
              <li key={`market-overview-point-${idx}`}>
                <p className="workspace-note">{point}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="metric-label section-title">市场状态判断</div>
          <p className="workspace-note">{view.market_state_summary}</p>
        </section>

        <section className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="metric-label section-title">指数环境总结</div>
          <p className="workspace-note">{view.index_summary}</p>
        </section>

        <section className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="metric-label section-title">短线情绪总结</div>
          <p className="workspace-note">{view.sentiment_summary}</p>
        </section>

        <section className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="metric-label section-title">热点行情概览</div>
          <p className="workspace-note">{view.hotspot_summary}</p>
        </section>

        <section className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="metric-label section-title">风险提示</div>
          <p className="workspace-note">{view.risk_warning}</p>
        </section>

        <section className="workspace-card">
          <div className="metric-label section-title">明日策略</div>
          <p className="workspace-note">{view.next_day_strategy}</p>
        </section>
      </div>
    </div>
  );
}
