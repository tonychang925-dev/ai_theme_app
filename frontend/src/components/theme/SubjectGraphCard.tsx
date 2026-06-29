import { navigateTo } from "../../lib/navigation";

export interface GraphStock {
  stock_id: string;
  stock_name: string;
  child_name?: string;
  reason?: string;
  // Financial data from evidence_json (e.g. 龙虎榜 subjects)
  pct_chg?: number | null;
  amount?: number | null;
  amount_str?: string | null;
  vol?: number | null;
  rank_no?: number | null;
}

export interface GraphGrandChild {
  name: string;
  child_subject_key?: string;
  stocks: GraphStock[];
}

export interface GraphChild {
  name: string;
  child_subject_key?: string;
  pct_chg?: number;
  children?: GraphGrandChild[];
  stocks?: GraphStock[];
}

export interface SubjectGraph {
  root: {
    name: string;
    subject_key: string;
    pct_chg?: number;
  };
  children: GraphChild[];
  uncategorized_stocks: GraphStock[];
}

// Minimal types for the limit-up matrix data
interface BoardStock {
  stock_id: string;
  stock_name: string;
  board_count?: number | null;
}

interface BoardGroup {
  board_count: number;
  board_label: string;
  stock_count: number;
  stocks: BoardStock[];
}

interface ThemeColumn {
  subject_key: string;
  theme_name: string;
  limit_up_count: number;
  board_groups?: BoardGroup[];
}

interface MatrixData {
  columns: ThemeColumn[];
  market_board_totals?: Record<string, number>;
  board_totals?: Record<string, number>;
}

interface Props {
  graph: SubjectGraph | null;
  tradeDate?: string;
  /** 当 graph 无子题材时，从涨停矩阵数据构建 JYHF 展示 */
  fallbackMatrix?: MatrixData | null;
}

function formatPct(pct: number | null | undefined): string {
  if (pct == null) return "--";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function pctColor(pct: number | null | undefined): string {
  if (pct == null) return "#888";
  return pct >= 0 ? "#e03030" : "#2ecc71";
}

const BOARD_ORDER = [4, 3, 2, 1];
const BOARD_LABELS: Record<number, string> = { 4: "4连板", 3: "3连板", 2: "2连板", 1: "首板" };

/**
 * JYHF 风格题材图谱
 * - 有子题材 (graph.children): 主题层级树
 * - 无子题材 + fallbackMatrix: 涨停矩阵 JYHF 风格
 */
export function SubjectGraphCard({ graph, tradeDate, fallbackMatrix }: Props) {
  // ---- 优先从 graph 渲染 ----
  if (graph?.root && (graph.children?.length > 0 || graph.uncategorized_stocks?.length > 0)) {
    return renderGraphTree(graph, tradeDate);
  }

  // ---- 从涨停矩阵数据构建 JYHF 展示 ----
  if (fallbackMatrix && fallbackMatrix.columns && fallbackMatrix.columns.length > 0) {
    return renderMatrixView(fallbackMatrix, tradeDate);
  }

  // 无数据
  return <div className="empty-state">暂无图谱数据</div>;
}

/** 原有: 主题层级树 */
function renderGraphTree(graph: SubjectGraph, tradeDate?: string) {
  const { root, children, uncategorized_stocks } = graph;

  return (
    <div className="jyhf-recap-panel">
      <div className="jyhf-header">
        <div className="jyhf-title">
          {root.name}
          {root.pct_chg != null && (
            <span className="jyhf-pct-up" style={{ marginLeft: 8 }}>
              {formatPct(root.pct_chg)}
            </span>
          )}
        </div>
        <div className="jyhf-subtitle">
          {tradeDate ? `${tradeDate} 题材图谱` : "题材图谱"} · {children.length} 个子题材 ·{" "}
          {uncategorized_stocks.length > 0 ? `${uncategorized_stocks.length} 只未归类` : ""}
        </div>
      </div>

      <div className="jyhf-matrix">
        {children.map((child, ci) => {
          const allStocks = collectChildStocks(child);
          const grands = child.children || [];
          return (
            <div key={ci} className="jyhf-row jyhf-theme-row">
              <div className="jyhf-theme-col">
                {child.child_subject_key ? (
                  <button type="button" className="jyhf-theme-link" onClick={() => navigateTo(`/themes/${encodeURIComponent(child.child_subject_key)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)}>
                    {child.name}
                  </button>
                ) : (
                  <span className="jyhf-theme-name">{child.name}</span>
                )}
                {child.pct_chg != null && (
                  <span className="jyhf-pct-up" style={{ fontSize: 12, marginTop: 2 }}>{formatPct(child.pct_chg)}</span>
                )}
              </div>
              <div className="jyhf-board-col" style={{ gridColumn: "3 / -1" }}>
                {grands.length > 0 ? grands.map((gc, gi) => (
                  <div key={gi} style={{ marginBottom: gi < grands.length - 1 ? 6 : 0, width: "100%" }}>
                    <div className="jyhf-grand-label">{gc.name}</div>
                    <div className="jyhf-stock-list">
                      {gc.stocks.map((s, si) => (
                        <button key={si} type="button" className="jyhf-stock-chip" onClick={() => navigateTo(`/stocks/${encodeURIComponent(s.stock_id)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)} title={s.reason || ""}>
                          {s.stock_name}
                        </button>
                      ))}
                    </div>
                  </div>
                )) : (
                  <div className="jyhf-stock-list">
                    {allStocks.map((s, si) => (
                      <button key={si} type="button" className="jyhf-stock-chip" onClick={() => navigateTo(`/stocks/${encodeURIComponent(s.stock_id)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)} title={s.reason || ""}>
                        {s.stock_name}
                      </button>
                    ))}
                  </div>
                )}
                {grands.length === 0 && allStocks.length === 0 && <span className="jyhf-empty">—</span>}
              </div>
            </div>
          );
        })}
        {uncategorized_stocks.length > 0 && (
          root.name.includes("龙虎榜")
            ? renderFinancialTable(uncategorized_stocks, tradeDate)
            : (
              <div className="jyhf-row jyhf-theme-row">
                <div className="jyhf-theme-col">
                  <span className="jyhf-theme-name" style={{ color: "#999" }}>其他 ({uncategorized_stocks.length})</span>
                </div>
                <div className="jyhf-board-col" style={{ gridColumn: "2 / -1" }}>
                  <div className="jyhf-stock-list">
                    {uncategorized_stocks.map((s, si) => (
                      <button key={si} type="button" className="jyhf-stock-chip" onClick={() => navigateTo(`/stocks/${encodeURIComponent(s.stock_id)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)}>
                        {s.stock_name}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )
        )}
      </div>
      <JyhfStyles />
    </div>
  );
}

/** 从涨停矩阵数据构建 JYHF 风格视图 */
function renderMatrixView(matrix: MatrixData, tradeDate?: string) {
  const columns = matrix.columns.filter((c) => Number(c.limit_up_count || 0) > 0);
  const marketTotal = Object.values(matrix.market_board_totals ?? matrix.board_totals ?? {})
    .reduce((sum, v) => sum + Number(v || 0), 0);

  return (
    <div className="jyhf-recap-panel">
      {/* 标题 */}
      <div className="jyhf-header">
        <div className="jyhf-title">
          {tradeDate
            ? `${tradeDate.replace(/^(\d{4})-(\d{2})-(\d{2})$/, "$1年$2月$3日")}热门题材复盘`
            : "热门题材复盘"}
        </div>
        <div className="jyhf-subtitle">全市场 {marketTotal} 只涨停 · {columns.length} 个题材</div>
      </div>

      {/* 矩阵 */}
      <div className="jyhf-matrix">
        {/* 表头 */}
        <div className="jyhf-row jyhf-head-row">
          <div className="jyhf-theme-col">题材</div>
          <div className="jyhf-pct-col">涨幅</div>
          {BOARD_ORDER.map((bc) => (
            <div key={bc} className="jyhf-board-col">{BOARD_LABELS[bc]}</div>
          ))}
        </div>

        {columns.map((col) => (
          <div key={col.subject_key || col.theme_name} className="jyhf-row jyhf-theme-row">
            <div className="jyhf-theme-col">
              {col.subject_key ? (
                <button type="button" className="jyhf-theme-link" onClick={() => navigateTo(`/themes/${encodeURIComponent(col.subject_key)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)}>
                  {col.theme_name}
                </button>
              ) : (
                <span className="jyhf-theme-name">{col.theme_name}</span>
              )}
            </div>
            <div className="jyhf-pct-col jyhf-pct-up">+10.00%</div>
            {BOARD_ORDER.map((bc) => {
              const group = (col.board_groups || []).find((g) => g.board_count === bc);
              return (
                <div key={bc} className="jyhf-board-col">
                  {group && group.stocks.length > 0 ? (
                    <div className="jyhf-stock-list">
                      {group.stocks.map((s) => (
                        <button key={`${s.stock_id}-${bc}`} type="button" className="jyhf-stock-chip"
                          onClick={() => navigateTo(`/stocks/${encodeURIComponent(s.stock_id)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)}>
                          {s.stock_name}
                        </button>
                      ))}
                    </div>
                  ) : <span className="jyhf-empty">—</span>}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* 底部统计 */}
      <div className="jyhf-footer">
        {BOARD_ORDER.map((bc) => {
          const count = Number((matrix.market_board_totals ?? matrix.board_totals ?? {})[String(bc)] || 0);
          return <span key={bc} className="jyhf-footer-chip">{BOARD_LABELS[bc]} {count} 只</span>;
        })}
      </div>
      <JyhfStyles />
    </div>
  );
}

/** 龙虎榜金融数据表格（排名、股票、涨跌幅、成交额） */
function renderFinancialTable(stocks: GraphStock[], tradeDate?: string) {
  return (
    <div className="jyhf-financial-table">
      <div className="jyhf-row jyhf-head-row">
        <div className="jyhf-board-col">#</div>
        <div className="jyhf-theme-col">股票</div>
        <div className="jyhf-pct-col">涨跌幅</div>
        <div className="jyhf-board-col">成交额</div>
      </div>
      {stocks.map((s, si) => (
        <div key={si} className="jyhf-row jyhf-theme-row">
          <div className="jyhf-board-col" style={{ alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: 12, color: si < 3 ? "#e03030" : "#999" }}>
              {s.rank_no != null ? Number(s.rank_no).toFixed(0) : si + 1}
            </span>
          </div>
          <div className="jyhf-theme-col">
            <button
              type="button"
              className="jyhf-theme-link"
              onClick={() => navigateTo(`/stocks/${encodeURIComponent(s.stock_id)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`)}
            >
              {s.stock_name}
            </button>
            <span style={{ fontSize: 10, color: "#999" }}>{s.stock_id?.replace(/\.(SH|SZ)$/, "")}</span>
          </div>
          <div className="jyhf-pct-col">
            <span className="jyhf-pct-up" style={{ fontSize: 13 }}>
              {formatPct(s.pct_chg)}
            </span>
          </div>
          <div className="jyhf-board-col" style={{ alignItems: "flex-end", justifyContent: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#333" }}>
              {s.amount_str || (s.amount != null ? `${(s.amount / 1e8).toFixed(2)}亿` : "--")}
            </span>
          </div>
        </div>
      ))}
      <JyhfStyles />
    </div>
  );
}

/** 递归收集子题材下所有股票 */
function collectChildStocks(child: GraphChild): GraphStock[] {
  const direct = child.stocks || [];
  const grandStocks: GraphStock[] = [];
  for (const gc of child.children || []) {
    for (const s of gc.stocks || []) grandStocks.push(s);
  }
  return [...direct, ...grandStocks];
}

/** 内联 JYHF CSS */
function JyhfStyles() {
  return (
    <style>{`
      .jyhf-recap-panel { background:#fff; border-radius:12px; padding:20px 16px; margin:16px 0; box-shadow:0 2px 8px rgba(0,0,0,0.06); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif; max-width:100%; overflow-x:auto; }
      .jyhf-header { text-align:center; margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid #f0f0f0; }
      .jyhf-title { font-size:17px; font-weight:700; color:#1a1a1a; letter-spacing:0.5px; }
      .jyhf-subtitle { font-size:13px; color:#999; margin-top:4px; }
      .jyhf-matrix { display:flex; flex-direction:column; gap:0; }
      .jyhf-row { display:grid; grid-template-columns:120px 56px repeat(4,1fr); gap:1px; background:#f5f5f5; min-height:44px; }
      .jyhf-row>div { background:#fff; padding:8px 6px; display:flex; flex-direction:column; justify-content:center; align-items:flex-start; }
      .jyhf-head-row { background:#fafafa; font-size:12px; font-weight:600; color:#666; }
      .jyhf-head-row>div { background:#fafafa; align-items:center; justify-content:center; text-align:center; padding:8px 4px; }
      .jyhf-theme-row { border-bottom:1px solid #f0f0f0; }
      .jyhf-theme-col { align-items:flex-start!important; justify-content:center!important; padding-left:12px!important; }
      .jyhf-pct-col { align-items:center!important; justify-content:center!important; text-align:center; }
      .jyhf-board-col { align-items:flex-start!important; padding:6px 8px!important; width:100%; }
      .jyhf-theme-link { background:none; border:none; color:#1a6dd4; font-size:14px; font-weight:600; cursor:pointer; padding:0; text-align:left; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:110px; }
      .jyhf-theme-link:hover { color:#0d4fa8; text-decoration:underline; }
      .jyhf-theme-name { font-size:14px; font-weight:600; color:#333; }
      .jyhf-pct-up { color:#e03030; font-size:13px; font-weight:700; text-align:center; }
      .jyhf-stock-list { display:flex; flex-wrap:wrap; gap:4px; }
      .jyhf-stock-chip { background:#f0f5ff; border:1px solid #d6e4ff; border-radius:4px; color:#1a6dd4; font-size:12px; padding:3px 8px; cursor:pointer; white-space:nowrap; transition:background 0.15s; }
      .jyhf-stock-chip:hover { background:#d6e4ff; border-color:#91b8f5; }
      .jyhf-grand-label { font-size:11px; font-weight:600; color:#b8860b; margin-bottom:4px; padding-left:2px; }
      .jyhf-empty { color:#ccc; font-size:12px; text-align:center; width:100%; }
      .jyhf-footer { margin-top:12px; padding-top:10px; border-top:1px solid #f0f0f0; display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }
      .jyhf-footer-chip { background:#f5f5f5; border-radius:12px; padding:4px 10px; font-size:12px; color:#666; }
      .jyhf-financial-table { margin-top:8px; }
      .jyhf-financial-table .jyhf-row { grid-template-columns:40px 100px 56px 1fr; }
      @media(max-width:768px) {
        .jyhf-row { grid-template-columns:80px 48px repeat(4,1fr); }
        .jyhf-financial-table .jyhf-row { grid-template-columns:30px 70px 48px 1fr; }
        .jyhf-theme-link { font-size:12px; max-width:70px; }
        .jyhf-stock-chip { font-size:10px; padding:2px 5px; }
        .jyhf-recap-panel { padding:12px 8px; }
      }
    `}</style>
  );
}
