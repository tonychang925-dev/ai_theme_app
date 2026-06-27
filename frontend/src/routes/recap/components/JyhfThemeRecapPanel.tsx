import type { LimitUpThemeMatrix, LimitUpThemeMatrixColumn, ThemeLimitUpBoardGroup, ThemeLimitUpStock } from "../../../lib/api";
import { navigateTo } from "../../../lib/navigation";

interface Props {
  limitUpThemeMatrix?: LimitUpThemeMatrix | null;
  tradeDate?: string;
}

function stockLink(stockId?: string, tradeDate?: string) {
  if (!stockId) return "";
  return `/stocks/${encodeURIComponent(stockId)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`;
}

function validName(value?: string | null) {
  const text = String(value || "").trim();
  if (!text || /^\d+$/.test(text)) return "";
  if (/^\d+\.(SH|SZ|BJ)$/i.test(text)) return "";
  return text;
}

function displayTheme(col: LimitUpThemeMatrixColumn) {
  const raw = String(col.mainline_name || col.theme_name || "").trim();
  if (raw === "__independent__" || raw === "independent" || raw === "未归类" || raw.startsWith("__")) return null;
  return raw;
}

const BOARD_LABELS: Record<number, string> = { 4: "4连板", 3: "3连板", 2: "2连板", 1: "首板" };
const BOARD_ORDER = [4, 3, 2, 1];

function renderStocks(stocks: ThemeLimitUpStock[] | undefined, tradeDate?: string) {
  if (!stocks || stocks.length === 0) return <span className="jyhf-empty">—</span>;
  return (
    <div className="jyhf-stock-list">
      {stocks.map((s) => {
        const href = stockLink(s.stock_id, tradeDate);
        const name = validName(s.stock_name);
        return (
          <button
            key={`${s.stock_id || s.stock_name}-${s.board_count ?? 0}`}
            type="button"
            className="jyhf-stock-chip"
            onClick={() => href && navigateTo(href)}
          >
            {name || "--"}
          </button>
        );
      })}
    </div>
  );
}

/**
 * 模仿久赢恒丰App的题材复盘面板
 * 行 = 主题，列 = 连板梯度（4连板 / 3连板 / 2连板 / 首板）
 */
export default function JyhfThemeRecapPanel({ limitUpThemeMatrix, tradeDate }: Props) {
  const columns = (limitUpThemeMatrix?.columns ?? []).filter((col) => Number(col.limit_up_count || 0) > 0);
  if (!limitUpThemeMatrix || columns.length === 0) return null;

  const marketTotal = Object.values(limitUpThemeMatrix.market_board_totals ?? limitUpThemeMatrix.board_totals ?? {})
    .reduce((sum, v) => sum + Number(v || 0), 0);

  const themes = columns
    .map((col) => ({
      theme_name: displayTheme(col),
      subject_key: col.subject_key,
      limit_up_count: Number(col.limit_up_count || 0),
      board_groups: (col.board_groups || []) as ThemeLimitUpBoardGroup[],
    }))
    .filter((t) => t.theme_name && t.limit_up_count > 0);

  if (themes.length === 0) return null;

  return (
    <div className="jyhf-recap-panel">
      {/* 标题栏 */}
      <div className="jyhf-header">
        <div className="jyhf-title">
          {tradeDate
            ? `${tradeDate.replace(/^(\d{4})-(\d{2})-(\d{2})$/, "$1年$2月$3日")}热门题材复盘`
            : "热门题材复盘"}
        </div>
        <div className="jyhf-subtitle">全市场 {marketTotal} 只涨停</div>
      </div>

      {/* 题材矩阵 */}
      <div className="jyhf-matrix">
        {/* 表头：连板梯度 */}
        <div className="jyhf-row jyhf-head-row">
          <div className="jyhf-theme-col">题材</div>
          <div className="jyhf-pct-col">涨幅</div>
          {BOARD_ORDER.map((bc) => (
            <div key={bc} className="jyhf-board-col">
              {BOARD_LABELS[bc]}
            </div>
          ))}
        </div>

        {/* 每行一个主题 */}
        {themes.map((theme) => (
          <div key={theme.subject_key || theme.theme_name} className="jyhf-row jyhf-theme-row">
            {/* 题材名 */}
            <div className="jyhf-theme-col">
              {theme.subject_key ? (
                <button
                  type="button"
                  className="jyhf-theme-link"
                  onClick={() =>
                    navigateTo(
                      `/themes/${encodeURIComponent(theme.subject_key)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`,
                    )
                  }
                >
                  {theme.theme_name}
                </button>
              ) : (
                <span className="jyhf-theme-name">{theme.theme_name}</span>
              )}
            </div>

            {/* 涨幅 */}
            <div className="jyhf-pct-col jyhf-pct-up">+10.00%</div>

            {/* 各连板梯度股票 */}
            {BOARD_ORDER.map((bc) => {
              const group = theme.board_groups.find((g) => g.board_count === bc);
              return (
                <div key={bc} className="jyhf-board-col">
                  {group && group.stocks.length > 0 ? (
                    renderStocks(group.stocks, tradeDate)
                  ) : (
                    <span className="jyhf-empty">—</span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* 底部统计 */}
      <div className="jyhf-footer">
        {(() => {
          const totals = limitUpThemeMatrix.market_board_totals ?? limitUpThemeMatrix.board_totals ?? {};
          return BOARD_ORDER.map((bc) => {
            const count = Number(totals[String(bc)] || 0);
            return (
              <span key={bc} className="jyhf-footer-chip">
                {BOARD_LABELS[bc]} {count} 只
              </span>
            );
          });
        })()}
      </div>
    </div>
  );
}
