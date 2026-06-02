import { Tag } from "antd";
import type { MarketOverviewReview, ThemeLimitUpColumn, ThemeLimitUpStock } from "../../../lib/api";
import { navigateTo } from "../../../lib/navigation";

interface Props {
  marketOverview?: MarketOverviewReview | null;
  tradeDate?: string;
}

function formatAmount(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const abs = Math.abs(Number(value));
  if (abs >= 1e8) return `${(Number(value) / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(Number(value) / 1e4).toFixed(2)}万`;
  return String(Math.round(Number(value)));
}

function translateTagText(value?: string | null) {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    "Layer C": "强势股池",
    "D1": "次日观察",
    focus: "重点关注",
    formal: "正式",
    observe_only: "观察",
    reject: "剔除",
    dragon: "龙头",
    sub_dragon: "次龙头",
    leader: "龙头",
    unknown: "未知",
    active: "活跃",
    weakening: "转弱",
    removed: "移除",
    pending: "待定",
    no_trade: "不交易",
    mainline_core_only: "主线核心",
    mainline_tradable: "主线可交易",
    ultra_short_only: "仅超短",
    mainline_participation: "主线参与",
    rotation_follow: "轮动跟随",
    rotation_watch: "轮动观察",
  };
  return map[key] || key || "--";
}

function translateCountMethod(value?: string | null) {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    display_by_theme: "按题材展示",
    display_by_theme_unique: "按题材去重展示",
  };
  return map[key] || key || "--";
}

function displayThemeName(col: ThemeLimitUpColumn) {
  const record = col as ThemeLimitUpColumn & Record<string, unknown>;
  return String(record.mainline_name || col.theme_name || "其他").trim() || "其他";
}

function renderFocusStock(stock: ThemeLimitUpStock | undefined, tradeDate?: string) {
  if (!stock) return <span style={{ color: "#66d9ef" }}>--</span>;
  const href = stock.stock_id ? `/stocks/${encodeURIComponent(stock.stock_id)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}` : "";
  const body = (
    <div className="recap-tag-stack" style={{ gap: 4 }}>
      <button type="button" className="recap-theme-link recap-stock-highlight" onClick={() => href && navigateTo(href)}>
        {stock.stock_name || stock.stock_id || "--"}
      </button>
      <div className="recap-tag-stack" style={{ gap: 4, flexWrap: "wrap" }}>
        {typeof stock.board_count === "number" && stock.board_count > 0 && <Tag color="gold">连板 {stock.board_count}</Tag>}
        {stock.in_layer_c && <Tag color="green">强势股池</Tag>}
        {stock.is_d1_candidate && <Tag color="blue">次日观察</Tag>}
        {stock.role_label && <Tag color="default">{translateTagText(stock.role_label)}</Tag>}
        {stock.trade_action && <Tag color="orange">{translateTagText(stock.trade_action)}</Tag>}
      </div>
    </div>
  );
  return body;
}

function columnStatusTag(col: ThemeLimitUpColumn) {
  const action = translateTagText(col.trade_action);
  if (action === "回避") return <Tag color="red">回避</Tag>;
  if (action === "主线参与") return <Tag color="green">主线参与</Tag>;
  if (action === "主线分歧") return <Tag color="orange">主线分歧</Tag>;
  if (action === "轮动跟随") return <Tag color="blue">轮动跟随</Tag>;
  if (col.active_mainline) return <Tag color="green">主线</Tag>;
  return <Tag color="default">轮动</Tag>;
}

export default function MarketOverviewPanel({ marketOverview, tradeDate }: Props) {
  const columns = marketOverview?.theme_limitup_matrix?.columns ?? [];
  if (!columns.length) return null;

  const maxRows = Math.max(
    marketOverview?.theme_limitup_matrix?.max_rows ?? 0,
    ...columns.map((col) => col.focus_stocks?.length ?? 0),
  );

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        行情概览
        <Tag color="gold" style={{ marginLeft: 8 }}>重点题材涨停矩阵</Tag>
        <Tag color="blue">{marketOverview?.limit_up_total ?? "--"} 涨停</Tag>
        {typeof marketOverview?.limit_down_total === "number" && <Tag color="red">跌停 {marketOverview.limit_down_total}</Tag>}
      </h3>
      <div className="workspace-note" style={{ marginBottom: 10 }}>
        展示方式：按题材独立统计涨停数目，聚焦今日赚钱效应集中方向与对应重点个股。
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="recap-table market-overview-matrix">
          <thead>
            <tr>
              <th style={{ minWidth: 130 }}>指标</th>
              {columns.map((col) => (
                <th key={col.subject_key} style={{ minWidth: 260, verticalAlign: "top" }}>
                  <div className="recap-tag-stack" style={{ gap: 4 }}>
                    <button type="button" className="recap-theme-link" onClick={() => navigateTo(`/themes/${encodeURIComponent(col.subject_key)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)}>
                      {displayThemeName(col)}
                    </button>
                    <div className="recap-tag-stack" style={{ gap: 4, flexWrap: "wrap" }}>
                      {columnStatusTag(col)}
                      <Tag color={col.active_mainline ? "green" : "default"}>{translateTagText(col.lifecycle_state)}</Tag>
                    </div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>涨停数目</strong></td>
              {columns.map((col) => (
                <td key={`${col.subject_key}-count`}>
                  <span className="recap-chip is-status">{col.limit_up_count ?? 0}</span>
                </td>
              ))}
            </tr>
            <tr>
              <td><strong>主线状态</strong></td>
              {columns.map((col) => (
                <td key={`${col.subject_key}-state`}>{col.active_mainline ? "主线" : "轮动观察"}</td>
              ))}
            </tr>
            <tr>
              <td><strong>交易动作</strong></td>
              {columns.map((col) => (
                <td key={`${col.subject_key}-action`}>{translateTagText(col.trade_action)}</td>
              ))}
            </tr>
            {Array.from({ length: maxRows }).map((_, rowIndex) => (
              <tr key={`focus-${rowIndex}`}>
                <td><strong>重点关注 {rowIndex + 1}</strong></td>
                {columns.map((col) => (
                  <td key={`${col.subject_key}-focus-${rowIndex}`} className="recap-cell-wrap">
                    {renderFocusStock(col.focus_stocks?.[rowIndex], tradeDate)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="workspace-note" style={{ marginTop: 8 }}>
        统计口径：{translateCountMethod(marketOverview?.theme_limitup_matrix?.count_method)}；题材数 {columns.length} 个。
      </div>
      {marketOverview?.diagnostics && (
        <div className="workspace-note" style={{ marginTop: 4 }}>
          诊断：主题 {String(marketOverview.diagnostics.theme_count ?? "--")}，股票 {String(marketOverview.diagnostics.stock_count ?? "--")}
        </div>
      )}
      {marketOverview?.total_amount != null && (
        <div className="workspace-note" style={{ marginTop: 4 }}>
          成交额：{formatAmount(marketOverview.total_amount)}
        </div>
      )}
    </div>
  );
}
