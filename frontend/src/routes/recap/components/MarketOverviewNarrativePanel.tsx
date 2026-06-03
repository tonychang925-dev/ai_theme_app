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

function filterTradeTips(points: string[]) {
  const duplicateMarkers = [
    "市场状态：",
    "市场状态",
    "短线情绪：",
    "短线情绪",
    "主线环境：",
    "主线环境",
    "交易模式：",
    "交易模式",
    "当前允许交易",
    "市场定性",
    "操作倾向",
    "上证指数",
    "沪深300",
    "中证1000",
    "指数环境",
    "支撑",
    "压力",
  ];
  return points.filter((point) => !duplicateMarkers.some((marker) => point.includes(marker)));
}

function titleTone(title: string) {
  const map: Record<string, string> = {
    "市场状态判断": "green",
    "指数环境总结": "blue",
    "短线情绪总结": "orange",
    "核心要点": "gold",
    "风险提示": "red",
    "明日策略": "purple",
  };
  return map[title] || "default";
}

function TitleTag({ children }: { children: string }) {
  return <Tag color={titleTone(children)} className="recap-title-tag">{children}</Tag>;
}

function isWarningSentence(text: string) {
  return text.includes("市场信号尚不充分") || text.includes("先观察主线修复与确认");
}

function TextBlock({ value }: { value: string }) {
  const warning = isWarningSentence(value);
  return <div className={`recap-body-text ${warning ? "recap-warning-text" : ""}`}>{value}</div>;
}

function HeadlineBlock({ value }: { value: string }) {
  const warning = isWarningSentence(value);
  return warning ? (
    <div className="recap-body-text recap-warning-text">{value}</div>
  ) : (
    <div className="recap-hero-text">{value}</div>
  );
}

export default function MarketOverviewNarrativePanel({ narrative, engineSummary, marketRegime }: Props) {
  const view = narrative ?? buildFallbackNarrative(engineSummary, marketRegime);
  if (!view) return null;
  const tradeTips = filterTradeTips(view.core_points || []);

  return (
    <div className="market-overview-narrative" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, padding: 16, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        市场总览
        <Tag color="gold" style={{ marginLeft: 8 }}>复盘开篇总结</Tag>
        {view.source && <Tag color={view.source === "engine_template" ? "green" : "blue"}>{view.source}</Tag>}
      </h3>

      <div style={{ background: "rgba(141,220,255,0.08)", border: "1px solid rgba(141,220,255,0.18)", borderRadius: 8, padding: 14, marginBottom: 12 }}>
        <Tag color="green" className="recap-title-tag" style={{ marginBottom: 6 }}>今日核心结论</Tag>
        <HeadlineBlock value={view.headline} />
      </div>

      <div className="market-summary-grid">
        <section className="workspace-card market-summary-card">
          <div className="workspace-summary-block">
            <div className="workspace-note" style={{ marginBottom: 6 }}><TitleTag>市场状态判断</TitleTag></div>
            <TextBlock value={view.market_state_summary} />
          </div>
          <div className="workspace-summary-block">
            <div className="workspace-note" style={{ marginBottom: 6 }}><TitleTag>指数环境总结</TitleTag></div>
            <TextBlock value={view.index_summary} />
          </div>
          <div className="workspace-summary-block">
            <div className="workspace-note" style={{ marginBottom: 6 }}><TitleTag>短线情绪总结</TitleTag></div>
            <TextBlock value={view.sentiment_summary} />
          </div>
        </section>

        <section className="workspace-card market-summary-card">
          <div className="workspace-summary-block">
            <div className="workspace-note" style={{ marginBottom: 6 }}><TitleTag>核心要点</TitleTag></div>
            <ul className="workspace-list">
              {tradeTips.length > 0 ? tradeTips.map((point, idx) => (
                <li key={`market-overview-point-${idx}`}>
                  <TextBlock value={point} />
                </li>
              )) : <li><TextBlock value="--" /></li>}
            </ul>
          </div>
          <div className="workspace-summary-block">
            <div className="workspace-note" style={{ marginBottom: 6 }}><TitleTag>风险提示</TitleTag></div>
            <TextBlock value={view.risk_warning} />
          </div>
          <div className="workspace-summary-block">
            <div className="workspace-note" style={{ marginBottom: 6 }}><TitleTag>明日策略</TitleTag></div>
            <TextBlock value={view.next_day_strategy} />
          </div>
        </section>
      </div>
    </div>
  );
}
