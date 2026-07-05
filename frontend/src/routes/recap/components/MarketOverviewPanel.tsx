import { Tag } from "antd";
import type { LimitUpThemeMatrix, LimitUpThemeMatrixColumn, ThemeLimitUpBoardGroup, ThemeLimitUpStock } from "../../../lib/api";
import { navigateTo } from "../../../lib/navigation";

interface Props {
  limitUpThemeMatrix?: LimitUpThemeMatrix | null;
  tradeDate?: string;
  subjectKeyToThemeName?: Map<string, string>;
}

interface DiagnosticLimitUpStock {
  stock_id?: string;
  stock_name?: string;
  stock_key?: string;
  board_count?: number;
  reason?: string;
  chosen_theme_name?: string;
  mainline_matches?: string[];
}

function stockLink(stockId?: string, tradeDate?: string) {
  if (!stockId) return "";
  return `/stocks/${encodeURIComponent(stockId)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`;
}

function displayThemeName(col: LimitUpThemeMatrixColumn, subjectKeyToThemeName?: Map<string, string>) {
  void subjectKeyToThemeName;
  const raw = String(col.mainline_name || col.theme_name || "其他").trim() || "其他";
  if (raw === "__independent__" || raw.toLowerCase() === "independent" || raw === "未归类" || raw.startsWith("__")) {
    return "未归类";
  }
  return raw;
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
    </div>
  );
}

function validDisplayName(value?: string | null) {
  const text = String(value || "").trim();
  if (!text || /^\d+$/.test(text)) return "";
  if (/^\d+\.(SH|SZ|BJ)$/i.test(text)) return "";
  return text;
}

function renderBoardStocks(stocks: ThemeLimitUpStock[] | undefined, tradeDate?: string) {
  if (!stocks || stocks.length === 0) return <span className="workspace-note">--</span>;
  return (
    <div className="market-overview-stock-list">
      {stocks.map((stock) => {
        const href = stockLink(stock.stock_id, tradeDate);
        const boardCount = Number(stock.board_count || 0);
        const cls = `recap-theme-link recap-stock-highlight market-overview-stock is-board-${boardCount >= 4 ? 4 : boardCount >= 3 ? 3 : boardCount >= 2 ? 2 : 1}`;
        const name = validDisplayName(stock.stock_name);
        return (
          <button
            key={`${stock.stock_id || stock.stock_name}-${stock.board_count ?? "x"}`}
            type="button"
            className={cls}
            onClick={() => href && navigateTo(href)}
          >
            {name || "--"}
          </button>
        );
      })}
    </div>
  );
}

function diagnosticRows(diagnostics: Record<string, unknown> | undefined, key: string): DiagnosticLimitUpStock[] {
  const value = diagnostics?.[key];
  return Array.isArray(value) ? (value as DiagnosticLimitUpStock[]) : [];
}

function renderDiagnosticStockPool(title: string, rows: DiagnosticLimitUpStock[], tradeDate?: string) {
  if (!rows.length) return null;
  const boardRows = [4, 3, 2, 1];
  return (
    <div className="workspace-card" style={{ marginTop: 12 }}>
      <div className="workspace-note" style={{ marginBottom: 8 }}>
        <strong>{title}</strong>
      </div>
      <div className="recap-table-wrap">
        <table className="recap-table">
          <thead>
            <tr>
              <th style={{ minWidth: 92 }}>板位</th>
              <th>股票</th>
              <th style={{ minWidth: 180 }}>原因</th>
            </tr>
          </thead>
          <tbody>
            {boardRows.map((boardCount) => {
              const items = rows.filter((row) => Number(row.board_count || 0) === boardCount);
              return (
                <tr key={`${title}-${boardCount}`}>
                  <td className="market-overview-rowhead"><strong>{boardCount === 1 ? "首板" : `${boardCount}板`}</strong></td>
                  <td>
                    {items.length ? (
                      <div className="market-overview-stock-list">
                        {items.map((row, idx) => {
                          const stockId = row.stock_id || row.stock_key || "";
                          const href = stockLink(stockId, tradeDate);
                          const name = validDisplayName(row.stock_name);
                          return (
                            <button
                              key={`${title}-${stockId || row.stock_name || idx}`}
                              type="button"
                              className={`recap-theme-link recap-stock-highlight market-overview-stock is-board-${boardCount >= 4 ? 4 : boardCount}`}
                              onClick={() => href && navigateTo(href)}
                            >
                              {name || "--"}
                            </button>
                          );
                        })}
                      </div>
                    ) : <span className="workspace-note">--</span>}
                  </td>
                  <td className="workspace-note">
                    {items.length ? Array.from(new Set(items.map((row) => row.reason || row.chosen_theme_name || "未说明"))).join("；") : "--"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MarketOverviewPanel({ limitUpThemeMatrix, tradeDate, subjectKeyToThemeName }: Props) {
  const columns = (limitUpThemeMatrix?.columns ?? []).filter((col) => Number(col.limit_up_count || 0) > 0);
  if (!limitUpThemeMatrix) return null;
  const marketBoardTotals = limitUpThemeMatrix?.market_board_totals ?? limitUpThemeMatrix?.board_totals ?? {};
  const mainlineBoardTotals = limitUpThemeMatrix?.mainline_board_totals ?? limitUpThemeMatrix?.board_totals ?? {};
  const marketTotal = Object.values(marketBoardTotals).reduce((sum, value) => sum + Number(value || 0), 0);
  const mainlineTotal = Object.values(mainlineBoardTotals).reduce((sum, value) => sum + Number(value || 0), 0);
  const nonMainlineRows = diagnosticRows(limitUpThemeMatrix.diagnostics, "non_mainline_limit_up_stocks")
    .filter((row) => row.reason !== "ambiguous_mainline_mapping");
  const ambiguousRows = diagnosticRows(limitUpThemeMatrix.diagnostics, "ambiguous_mainline_stocks");
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
        <Tag color="blue">全市场 {marketTotal} 涨停</Tag>
        <Tag color="green">主线 {mainlineTotal} 涨停</Tag>
      </h3>
      <div className="workspace-note" style={{ marginBottom: 10 }}>
        市场情绪看连板高度，板块热点看涨停家数；蓝色为 20cm 涨停，红色为 30cm 涨停，下划线为一字板。
      </div>
      {matrixColumns.length > 0 ? (
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
      ) : (
        <div className="workspace-note">暂无已确定映射到当前主线的涨停股。</div>
      )}
      <div className="workspace-note" style={{ marginTop: 8 }}>
        统计口径：热点图展示全市场已归入确定性题材的涨停股；题材数 {columns.length} 个。
        全市场连板：4板 {Number(marketBoardTotals["4"] || 0)}，3板 {Number(marketBoardTotals["3"] || 0)}，2板 {Number(marketBoardTotals["2"] || 0)}，首板 {Number(marketBoardTotals["1"] || 0)}。
        主线矩阵：4板 {Number(mainlineBoardTotals["4"] || 0)}，3板 {Number(mainlineBoardTotals["3"] || 0)}，2板 {Number(mainlineBoardTotals["2"] || 0)}，首板 {Number(mainlineBoardTotals["1"] || 0)}。
      </div>
      {limitUpThemeMatrix?.diagnostics && (
        <div className="workspace-note" style={{ marginTop: 4 }}>
          诊断：已归类 {String(limitUpThemeMatrix.diagnostics.candidate_count ?? "--")}，
          未归类 {String(limitUpThemeMatrix.diagnostics.non_mainline_limit_up_stock_count ?? "--")}，
          多义 {String(limitUpThemeMatrix.diagnostics.ambiguous_mainline_stock_count ?? "--")}
        </div>
      )}
      {(nonMainlineRows.length > 0 || ambiguousRows.length > 0) && (
        <details className="workspace-card" style={{ marginTop: 12 }}>
          <summary className="workspace-note">展开未归类/多义归因明细</summary>
          {renderDiagnosticStockPool("未归类涨停池", nonMainlineRows, tradeDate)}
          {renderDiagnosticStockPool("多义归因池", ambiguousRows, tradeDate)}
        </details>
      )}
    </div>
  );
}
