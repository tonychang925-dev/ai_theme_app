import { Tag } from "antd";
import type { LimitUpThemeMatrix, LimitUpThemeMatrixColumn, ThemeLimitUpBoardGroup, ThemeLimitUpStock } from "../../../lib/api";
import { navigateTo } from "../../../lib/navigation";

interface Props {
  limitUpThemeMatrix?: LimitUpThemeMatrix | null;
  tradeDate?: string;
  subjectKeyToThemeName?: Map<string, string>;
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

function stockLink(stockId?: string, tradeDate?: string) {
  if (!stockId) return "";
  return `/stocks/${encodeURIComponent(stockId)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`;
}

function displayThemeName(col: LimitUpThemeMatrixColumn, subjectKeyToThemeName?: Map<string, string>) {
  const mapped = subjectKeyToThemeName?.get(String(col.subject_key || "").trim())?.trim() || "";
  const raw = String(mapped || col.mainline_name || col.theme_name || "其他").trim() || "其他";
  if (raw === "__independent__" || raw.toLowerCase() === "independent" || raw === "未归类" || raw.startsWith("__")) {
    return "未归类";
  }
  return raw;
}

function columnStatusTag(col: LimitUpThemeMatrixColumn) {
  const action = translateTagText(col.trade_action);
  if (action === "回避") return <Tag color="red">回避</Tag>;
  if (action === "主线参与") return <Tag color="green">主线参与</Tag>;
  if (action === "主线分歧") return <Tag color="orange">主线分歧</Tag>;
  if (action === "轮动跟随") return <Tag color="blue">轮动跟随</Tag>;
  if (col.active_mainline) return <Tag color="green">主线</Tag>;
  return <Tag color="default">轮动</Tag>;
}

function renderThemeHead(col: LimitUpThemeMatrixColumn, tradeDate?: string, subjectKeyToThemeName?: Map<string, string>) {
  const themeName = displayThemeName(col, subjectKeyToThemeName);
  const canNavigate = Boolean(col.subject_key && themeName !== "未归类" && col.subject_key !== "__independent__");
  return (
    <div className="market-overview-theme-head">
      {canNavigate ? (
        <button
          type="button"
          className="recap-theme-link market-overview-theme-name"
          onClick={() => navigateTo(`/themes/${encodeURIComponent(col.subject_key)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)}
        >
          {themeName}
        </button>
      ) : (
        <span className="market-overview-theme-name">{themeName}</span>
      )}
      <div className="market-overview-theme-tags">
        {columnStatusTag(col)}
        <Tag color={col.active_mainline ? "green" : "default"}>{translateTagText(col.lifecycle_state)}</Tag>
      </div>
    </div>
  );
}

function renderBoardStocks(stocks: ThemeLimitUpStock[] | undefined, tradeDate?: string) {
  if (!stocks || stocks.length === 0) return <span className="workspace-note">--</span>;
  return (
    <div className="market-overview-stock-list">
      {stocks.map((stock) => {
        const href = stockLink(stock.stock_id, tradeDate);
        const boardCount = Number(stock.board_count || 0);
        const cls = `recap-theme-link recap-stock-highlight market-overview-stock is-board-${boardCount >= 4 ? 4 : boardCount >= 3 ? 3 : boardCount >= 2 ? 2 : 1}`;
        return (
          <button
            key={`${stock.stock_id || stock.stock_name}-${stock.board_count ?? "x"}`}
            type="button"
            className={cls}
            onClick={() => href && navigateTo(href)}
          >
            {stock.stock_name || stock.stock_id || "--"}
          </button>
        );
      })}
    </div>
  );
}

export default function MarketOverviewPanel({ limitUpThemeMatrix, tradeDate, subjectKeyToThemeName }: Props) {
  const columns = limitUpThemeMatrix?.columns ?? [];
  if (!columns.length) return null;
  const boardRows = [
    { board_count: 4, board_label: "4板" },
    { board_count: 3, board_label: "3板" },
    { board_count: 2, board_label: "2板" },
    { board_count: 1, board_label: "首板" },
  ];
  const matrixColumns: Array<LimitUpThemeMatrixColumn & { board_groups: ThemeLimitUpBoardGroup[] }> = columns.map((col) => ({
    ...col,
    board_groups: col.board_groups || [],
  }));

  return (
    <div className="workspace-card recap-engine-panel">
      <h3 className="section-title recap-panel-title">
        涨停热点分布图
        <Tag color="gold" style={{ marginLeft: 8 }}>题材矩阵</Tag>
        <Tag color="blue">{matrixColumns.reduce((sum, col) => sum + Number(col.limit_up_count || 0), 0)} 涨停</Tag>
      </h3>
      <div className="workspace-note" style={{ marginBottom: 10 }}>
        展示方式：按题材列展示各板位涨停股，便于查看主线、分歧与首板扩散结构。
      </div>
      <div className="recap-table-wrap">
        <table className="recap-table market-overview-distribution">
          <thead>
            <tr>
              <th style={{ minWidth: 92 }}>板位</th>
              {matrixColumns.map((col) => (
                <th key={col.subject_key} style={{ minWidth: 180, verticalAlign: "top" }}>
                  {renderThemeHead(col, tradeDate, subjectKeyToThemeName)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {boardRows.map((boardRow) => (
              <tr key={boardRow.board_count}>
                <td className="market-overview-rowhead">
                  <strong>{boardRow.board_label}</strong>
                </td>
                {matrixColumns.map((col) => {
                  const group = col.board_groups?.find((item) => item.board_count === boardRow.board_count);
                  return (
                    <td key={`${col.subject_key}-${boardRow.board_count}`} className="market-overview-cell">
                      {renderBoardStocks(group?.stocks, tradeDate)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="market-overview-rowhead"><strong>涨停数</strong></td>
              {matrixColumns.map((col) => (
                <td key={`${col.subject_key}-count`} className="market-overview-cell">
                  <span className="recap-chip is-status">{col.limit_up_count ?? 0}</span>
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <div className="workspace-note" style={{ marginTop: 8 }}>
        统计口径：按题材展示；题材数 {columns.length} 个。
      </div>
      {limitUpThemeMatrix?.diagnostics && (
        <div className="workspace-note" style={{ marginTop: 4 }}>
          诊断：主题 {String(limitUpThemeMatrix.diagnostics.theme_count ?? "--")}，股票 {String(limitUpThemeMatrix.diagnostics.candidate_count ?? "--")}
        </div>
      )}
    </div>
  );
}
