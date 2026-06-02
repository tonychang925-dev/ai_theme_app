/** PR-14B: 大盘环境面板 — 指数技术分析 + 市场总闸门。 */
import { Descriptions, Table, Tag } from "antd";
import type { EngineMarketRegimeReview, IndexTechnicalReview } from "../../../lib/api";

interface Props {
  marketRegime?: EngineMarketRegimeReview | null;
  indexReviews?: IndexTechnicalReview[];
  tradeDate?: string;
}

const TREND_COLORS: Record<string, string> = {
  bullish_trend: "green", bearish_trend: "red", downtrend_rebound: "orange",
  neutral_box: "default",
};

const TREND_LABELS: Record<string, string> = {
  bullish_trend: "上升趋势",
  bearish_trend: "下降趋势",
  downtrend_rebound: "下跌反弹",
  neutral_box: "震荡箱体",
};

const MACD_LABELS: Record<string, string> = {
  above_zero_strong: "零轴上方走强",
  above_zero_weakening: "零轴上方走弱",
  below_zero_recovering: "零轴下方修复",
  below_zero_weakening: "零轴下方走弱",
  crossover_bullish: "金叉",
  crossover_bearish: "死叉",
  neutral: "中性",
};

const VOLUME_LABELS: Record<string, string> = {
  normal: "正常",
  rising: "放量",
  shrinking: "缩量",
  abnormal: "异常",
  weak: "偏弱",
  strong: "偏强",
};

const REGIME_LABELS: Record<string, string> = {
  bullish_friendly: "偏多有利",
  bearish_adverse: "弱势不利",
  neutral: "中性",
  strong_mainline: "主线偏强",
  weak_mainline: "主线偏弱",
};

const MAINLINE_ENV_LABELS: Record<string, string> = {
  mainline_tradable: "主线可交易",
  mainline_core_only: "主线核心",
  observe_only: "仅观察",
  no_mainline: "无主线",
  unknown: "未知",
};

const SENTIMENT_LABELS: Record<string, string> = {
  hot: "活跃",
  strong: "强势",
  neutral: "中性",
  weak: "偏弱",
  dead: "衰竭",
};

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

function translateText(value?: string | null, map?: Record<string, string>) {
  const key = String(value || "").trim();
  if (!key) return "--";
  return (map && map[key]) || key;
}

export default function MarketRegimePanel({ marketRegime, indexReviews }: Props) {
  if (!marketRegime) return null;
  const allow = marketRegime.allow_trade;
  const idxReviews = indexReviews ?? marketRegime.index_technical_reviews ?? [];

  const formatPrice = (value?: number | null) => (value == null || Number.isNaN(Number(value)) ? "--" : Number(value).toFixed(0));
  const formatPct = (value?: number | null) => {
    if (value == null || Number.isNaN(Number(value))) return "--";
    const sign = value > 0 ? "+" : "";
    return `${sign}${Number(value).toFixed(2)}%`;
  };
  const formatStatus = (value?: string | null) => {
    if (!value || value === "unknown") return "--";
    if (value === "support_available" || value === "resistance_available") return "有效";
    if (value === "near_support" || value === "near_resistance") return "临近";
    if (value === "support_broken" || value === "resistance_broken") return "失守";
    if (value === "touch_or_break") return "触及/突破";
    return value;
  };

  const columns = [
    { title: "指数", dataIndex: "index_name", key: "name", width: 88 },
    { title: "趋势", dataIndex: "trend_state", key: "trend", width: 104, render: (v: string) => <Tag color={TREND_COLORS[v] || "default"}>{translateText(v, TREND_LABELS)}</Tag> },
    { title: "评分", dataIndex: "trend_score", key: "score", width: 62 },
    { title: "MA5", dataIndex: "above_ma5", key: "ma5", width: 56, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "MA10", dataIndex: "above_ma10", key: "ma10", width: 56, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "MA20", dataIndex: "above_ma20", key: "ma20", width: 56, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "MACD", dataIndex: "macd_state", key: "macd", width: 132, ellipsis: true, render: (v: string) => translateText(v, MACD_LABELS) },
    { title: "量能", dataIndex: "volume_pattern", key: "vol", width: 88, render: (v: string) => translateText(v, VOLUME_LABELS) },
    { title: "支撑", dataIndex: "nearest_support_level", key: "sup", width: 78, render: (_: unknown, row: IndexTechnicalReview) => formatPrice(row.nearest_support_level ?? row.support_level) },
    { title: "距支撑", dataIndex: "support_distance_pct", key: "supd", width: 86, render: (v: number) => formatPct(v) },
    { title: "压力", dataIndex: "nearest_resistance_level", key: "res", width: 78, render: (_: unknown, row: IndexTechnicalReview) => formatPrice(row.nearest_resistance_level ?? row.resistance_level) },
    { title: "距压力", dataIndex: "resistance_distance_pct", key: "resd", width: 86, render: (v: number) => formatPct(v) },
    {
      title: "支撑/压力",
      key: "support_status",
      width: 156,
      render: (_: unknown, row: IndexTechnicalReview) => (
        <div className="recap-market-regime-status">
          <div>
            <span className="recap-market-regime-label">支撑</span>
            <span>{formatStatus(row.support_status)}</span>
          </div>
          <div>
            <span className="recap-market-regime-label">压力</span>
            <span>{formatStatus(row.resistance_status)}</span>
          </div>
        </div>
      ),
    },
    {
      title: "提示",
      key: "hint",
      width: 220,
      ellipsis: true,
      render: (_: unknown, row: IndexTechnicalReview) => (
        <div className="recap-market-regime-hint" title={row.index_trade_hint || "--"}>
          <span className="recap-market-regime-label">{translateText(row.warning_level, { normal: "正常", warn: "警示", danger: "风险", high: "高风险" })}</span>
          <span>{row.index_trade_hint || "--"}</span>
        </div>
      ),
    },
    { title: "风险", dataIndex: "risk_flags", key: "risk", width: 220, render: (v: string[]) => v?.map((f: string) => <Tag key={f} color="red">{translateText(f, { overheat: "过热", weakness: "偏弱", warning: "警示", danger: "风险", liquidity_risk: "流动性风险" })}</Tag>) },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        大盘环境
        <Tag color={allow ? "green" : "red"} style={{ marginLeft: 8 }}>
          {allow ? translateTradeMode(marketRegime.trade_mode) : "不交易"}
        </Tag>
        {marketRegime.index_data_ready ? <Tag color="green">指数就绪</Tag> : <Tag color="orange">指数缺失</Tag>}
      </h3>

      <Descriptions size="small" column={3} style={{ marginBottom: 10 }}>
        <Descriptions.Item label="大盘环境">{translateText(marketRegime.broad_market_regime, REGIME_LABELS)}</Descriptions.Item>
        <Descriptions.Item label="短线情绪">{translateText(marketRegime.short_term_sentiment, SENTIMENT_LABELS)}</Descriptions.Item>
        <Descriptions.Item label="主线环境">{translateText(marketRegime.mainline_environment, MAINLINE_ENV_LABELS)}</Descriptions.Item>
        <Descriptions.Item label="数据源">{marketRegime.index_data_source ?? "-"}</Descriptions.Item>
      </Descriptions>

      {idxReviews.length > 0 && (
        <div className="recap-table-shell" style={{ marginTop: 8 }}>
          <Table
            dataSource={idxReviews.map((r, i) => ({ ...r, key: r.index_code || i }))}
            columns={columns}
            size="small"
            pagination={false}
            scroll={{ x: 1380 }}
          />
        </div>
      )}
    </div>
  );
}
