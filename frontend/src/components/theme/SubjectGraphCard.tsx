export interface GraphStock {
  stock_id: string;
  stock_name: string;
  child_name?: string;
  reason?: string;
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

interface Props {
  graph: SubjectGraph | null;
}

function formatPct(pct: number | null | undefined): string {
  if (pct == null) return '--';
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

function pctColor(pct: number | null | undefined): string {
  if (pct == null) return '#888';
  if (pct > 0) return '#e74c3c';
  if (pct < 0) return '#2ecc71';
  return '#888';
}

const CHILD_COLORS = [
  { bg: '#fef9f0', border: '#d4a574', accent: '#b8860b' },
  { bg: '#f0f7fe', border: '#7eb8da', accent: '#4a90c4' },
  { bg: '#f5fef5', border: '#8cc78c', accent: '#5a9e5a' },
  { bg: '#fef5f9', border: '#d4a0b8', accent: '#b87090' },
  { bg: '#f5f5fe', border: '#9e9ed4', accent: '#6e6eb8' },
  { bg: '#fef9f5', border: '#d4b898', accent: '#b89070' },
];

export function SubjectGraphCard({ graph }: Props) {
  if (!graph || !graph.root) {
    return <div className="empty-state">暂无图谱数据</div>;
  }

  const { root, children, uncategorized_stocks } = graph;

  // Merge uncategorized into a synthetic child if needed
  const allChildren = [...(children || [])];
  if (uncategorized_stocks && uncategorized_stocks.length > 0) {
    allChildren.push({
      name: '其他成分股',
      stocks: uncategorized_stocks,
    });
  }

  if (allChildren.length === 0) {
    return <div className="empty-state">暂无子题材数据</div>;
  }

  return (
    <div className="sg-container">
      {/* Left: Root node */}
      <div className="sg-root-col">
        <div className="sg-node sg-root">
          <div className="sg-node-name">{root.name}</div>
          <div className="sg-node-pct" style={{ color: pctColor(root.pct_chg) }}>
            {formatPct(root.pct_chg)}
          </div>
        </div>
      </div>

      {/* Connector arrows */}
      <div className="sg-arrow-col">
        <div className="sg-arrow-line" />
      </div>

      {/* Right: Children → Grandchildren → Stocks */}
      <div className="sg-children-area">
        {(children || []).map((child, ci) => {
          const colors = CHILD_COLORS[ci % CHILD_COLORS.length];
          const grands = child.children || [];
          const directStocks = child.stocks || [];
          return (
            <div key={ci} className="sg-child-block">
              {/* Child header */}
              <div className="sg-child-header" style={{ borderColor: colors.border }}>
                <span className="sg-child-header-name">{child.name}</span>
                {child.pct_chg != null && (
                  <span className="sg-node-pct sm" style={{ color: pctColor(child.pct_chg) }}>{formatPct(child.pct_chg)}</span>
                )}
              </div>
              {/* Grandchildren rows */}
              <div className="sg-grands-area">
                {directStocks.length > 0 && (
                  <div className="sg-grand-row">
                    <div className="sg-grand-label">成分股</div>
                    <div className="sg-stocks-col">
                      <div className="sg-stocks-grid">
                        {directStocks.map((stock, si) => (
                          <div key={si} className="sg-stock" style={{ borderLeftColor: colors.accent }}
                            title={stock.reason || ''}>
                            <div className="sg-stock-top">
                              <span className="sg-stock-name">{stock.stock_name}</span>
                              <span className="sg-stock-code">{stock.stock_id}</span>
                            </div>
                            {stock.reason && <span className="sg-stock-reason">{stock.reason}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {grands.map((gc, gi) => (
                  <div key={gi} className="sg-grand-row">
                    <div className="sg-grand-label">{gc.name}</div>
                    <div className="sg-stocks-col">
                      {gc.stocks && gc.stocks.length > 0 ? (
                        <div className="sg-stocks-grid">
                          {gc.stocks.map((stock, si) => (
                            <div key={si} className="sg-stock" style={{ borderLeftColor: colors.accent }}
                              title={stock.reason || ''}>
                              <div className="sg-stock-top">
                                <span className="sg-stock-name">{stock.stock_name}</span>
                                <span className="sg-stock-code">{stock.stock_id}</span>
                              </div>
                              {stock.reason && <span className="sg-stock-reason">{stock.reason}</span>}
                            </div>
                          ))}
                        </div>
                      ) : <span className="sg-empty">--</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {/* Uncategorized */}
        {uncategorized_stocks && uncategorized_stocks.length > 0 && (
          <div className="sg-child-block">
            <div className="sg-child-header" style={{ borderColor: '#ccc' }}>
              <span className="sg-child-header-name">其他成分股 ({uncategorized_stocks.length})</span>
            </div>
            <div className="sg-grands-area">
              <div className="sg-stocks-grid">
                {uncategorized_stocks.map((stock, si) => (
                  <div key={si} className="sg-stock" style={{ borderLeftColor: '#ccc' }}>
                    <div className="sg-stock-top">
                      <span className="sg-stock-name">{stock.stock_name}</span>
                      <span className="sg-stock-code">{stock.stock_id}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .sg-container {
          display: flex;
          align-items: flex-start;
          gap: 0;
          padding: 24px 16px;
          overflow-x: auto;
          font-size: 14px;
          min-height: 200px;
        }
        .sg-root-col {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          padding-top: 20px;
        }
        .sg-node {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          padding: 16px 20px;
          border-radius: 10px;
          border: 2px solid #d4a574;
          text-align: center;
          min-width: 120px;
          white-space: nowrap;
        }
        .sg-node.sg-root {
          border-color: #b8860b;
          background: linear-gradient(135deg, #fff8dc, #f0e68c);
          min-width: 160px;
          padding: 20px 28px;
        }
        .sg-node.sg-child {
          min-width: 110px;
          padding: 12px 16px;
        }
        .sg-node-name {
          font-weight: 600;
          color: #5d4037;
        }
        .sg-root .sg-node-name { font-size: 17px; }
        .sg-child .sg-node-name { font-size: 14px; }
        .sg-node-pct { font-weight: 700; font-size: 16px; }
        .sg-node-pct.sm { font-size: 13px; }
        .sg-stock-count { font-size: 11px; color: #999; margin-top: 2px; }

        .sg-arrow-col {
          flex-shrink: 0;
          display: flex;
          align-items: center;
          width: 32px;
          min-height: 40px;
        }
        .sg-arrow-col.sm { width: 24px; }
        .sg-arrow-line {
          width: 100%;
          height: 2px;
          background: linear-gradient(to right, #d4a574, #e8d5b7);
          position: relative;
        }
        .sg-arrow-line::after {
          content: '▶';
          position: absolute;
          right: -2px;
          top: -8px;
          font-size: 10px;
          color: #d4a574;
        }
        .sg-arrow-line.sm { background: linear-gradient(to right, #ccc, #e8d5b7); }
        .sg-arrow-line.sm::after { color: #ccc; }

        .sg-children-area {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 12px;
          min-width: 0;
        }
        .sg-child-block {
          border: 1px solid #e8d5b7;
          border-radius: 8px;
          overflow: hidden;
        }
        .sg-child-header {
          padding: 8px 16px;
          border-left: 4px solid #d4a574;
          background: #fef9f0;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .sg-child-header-name { font-weight: 600; font-size: 14px; color: #5d4037; }
        .sg-grands-area { padding: 6px 12px 10px; }
        .sg-grand-row {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 4px 0;
          border-bottom: 1px dotted #f5ede0;
        }
        .sg-grand-row:last-child { border-bottom: none; }
        .sg-grand-label {
          width: 70px;
          flex-shrink: 0;
          font-size: 12px;
          font-weight: 500;
          color: #8d6e63;
          padding-top: 4px;
        }

        .sg-stocks-col {
          flex: 1;
          min-width: 0;
        }
        .sg-stocks-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .sg-stock {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          padding: 6px 10px;
          border-radius: 4px;
          border: 1px solid #e8d5b7;
          border-left: 3px solid #d4a574;
          background: #fffef9;
          font-size: 12px;
          max-width: 220px;
          gap: 3px;
        }
        .sg-stock-top { display: flex; align-items: center; gap: 6px; }
        .sg-stock-name { font-weight: 600; color: #333; }
        .sg-stock-code { color: #999; font-size: 10px; }
        .sg-stock-tag {
          font-size: 10px;
          background: #fef5e7;
          color: #b8860b;
          padding: 1px 5px;
          border-radius: 3px;
        }
        .sg-stock-reason {
          color: #666;
          font-size: 10px;
          line-height: 1.3;
        }
        .sg-empty { color: #ccc; font-size: 13px; padding: 8px; }
      `}</style>
    </div>
  );
}
