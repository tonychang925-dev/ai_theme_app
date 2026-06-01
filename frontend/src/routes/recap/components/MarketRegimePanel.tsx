/** PR-14B: 大盘环境面板 — 指数技术分析 + 市场总闸门。 */
import { Descriptions, Table, Tag } from "antd";
import type { EngineMarketRegimeReview, IndexTechnicalReview } from "../../../lib/api";

interface Props {
  marketRegime: EngineMarketRegimeReview;
  indexReviews: IndexTechnicalReview[];
  tradeDate?: string;
}

const TREND_COLORS: Record<string, string> = {
  bullish_trend: "green", bearish_trend: "red", downtrend_rebound: "orange",
  neutral_box: "default",
};

export default function MarketRegimePanel({ marketRegime, indexReviews }: Props) {
  const allow = marketRegime.allow_trade;

  const columns = [
    { title: "指数", dataIndex: "index_name", key: "name", width: 70 },
    { title: "趋势", dataIndex: "trend_state", key: "trend", width: 70, render: (v: string) => <Tag color={TREND_COLORS[v] || "default"}>{v}</Tag> },
    { title: "评分", dataIndex: "trend_score", key: "score", width: 50 },
    { title: "MA5", dataIndex: "above_ma5", key: "ma5", width: 44, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "MA10", dataIndex: "above_ma10", key: "ma10", width: 44, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "MA20", dataIndex: "above_ma20", key: "ma20", width: 44, render: (v: boolean) => v ? "✓" : "✗" },
    { title: "MACD", dataIndex: "macd_state", key: "macd", width: 90, ellipsis: true },
    { title: "量能", dataIndex: "volume_pattern", key: "vol", width: 60 },
    { title: "支撑", dataIndex: "support_level", key: "sup", width: 56, render: (v: number) => v?.toFixed(0) ?? "-" },
    { title: "压力", dataIndex: "resistance_level", key: "res", width: 56, render: (v: number) => v?.toFixed(0) ?? "-" },
    { title: "风险", dataIndex: "risk_flags", key: "risk", render: (v: string[]) => v?.map((f: string) => <Tag key={f} color="red" style={{ fontSize: 10 }}>{f}</Tag>) },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 style={{ margin: "0 0 10px", color: "#e2e8f0", fontSize: 15 }}>
        大盘环境
        <Tag color={allow ? "green" : "red"} style={{ marginLeft: 8 }}>
          {allow ? (marketRegime.trade_mode || "可交易") : "不交易"}
        </Tag>
        {marketRegime.index_data_ready ? <Tag color="green">指数就绪</Tag> : <Tag color="orange">指数缺失</Tag>}
      </h3>

      <Descriptions size="small" column={3} style={{ marginBottom: 10 }}>
        <Descriptions.Item label="大盘环境">{marketRegime.broad_market_regime ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="短线情绪">{marketRegime.short_term_sentiment ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="主线环境">{marketRegime.mainline_environment ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="数据源">{marketRegime.index_data_source ?? "-"}</Descriptions.Item>
      </Descriptions>

      {indexReviews.length > 0 && (
        <Table
          dataSource={indexReviews.map((r, i) => ({ ...r, key: r.index_code || i }))}
          columns={columns}
          size="small"
          pagination={false}
          scroll={{ x: 800 }}
          style={{ marginTop: 8 }}
        />
      )}
    </div>
  );
}
