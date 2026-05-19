import React, { useEffect, useState, useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { navigateTo } from "../../lib/navigation";

const API = "/api/v1/backtest";
const COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"];

interface Strategy {
  strategy_id: string; strategy_name: string; total_return: number;
  max_drawdown: number; win_rate: number; profit_factor: number;
  trade_count: number; avg_hold_days: number;
}

interface TradeItem {
  trade_id: string; stock_id: string; stock_name: string;
  entry_date: string; exit_date: string; entry_price: number; exit_price: number;
  pnl: number; return_pct: number; hold_days: number;
  exit_reason: string; support_type: string; weak_type: string; candidate_score: number;
}

const nf = (v: any, d: number) => { const n = Number(v); return isNaN(n) ? "—" : n.toFixed(d); };
const fmtPct = (v: any) => { const n = Number(v); return isNaN(n) ? "—" : `${(n * 100).toFixed(2)}%`; };

export function BacktestComparePage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<string[]>([
    "v2.0_previous_low_only_hold5d", "v2.5c_limitup_weakopen_exit", "v2.5_combo",
  ]);
  const [equityData, setEquityData] = useState<Record<string, any[]>>({});
  const [trades, setTrades] = useState<TradeItem[]>([]);
  const [tradeStrategy, setTradeStrategy] = useState("v2.0_previous_low_only_hold5d");
  const [loading, setLoading] = useState(false);
  const [tradePage, setTradePage] = useState(1);

  const safeJson = async (r: Response) => { const t = await r.text(); return t ? JSON.parse(t) : {}; };

  useEffect(() => {
    fetch(`${API}/strategies`).then(safeJson).then(d => setStrategies(d.strategies || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (selected.length === 0) return;
    setLoading(true);
    fetch(`${API}/equity-curve?strategy_ids=${selected.join(",")}`)
      .then(safeJson).then(d => {
        const map: Record<string, any[]> = {};
        (d.series || []).forEach((s: any) => { map[s.strategy_id] = s.points; });
        setEquityData(map);
      }).catch(() => {}).finally(() => setLoading(false));
  }, [selected]);

  useEffect(() => {
    if (!tradeStrategy) return;
    fetch(`${API}/trades?strategy_id=${tradeStrategy}&page=${tradePage}&page_size=50`)
      .then(safeJson).then(d => setTrades(Array.isArray(d.items) ? d.items : [])).catch(() => {});
  }, [tradeStrategy, tradePage]);

  const selectedMetrics = useMemo(() => strategies.filter(s => selected.includes(s.strategy_id)), [strategies, selected]);

  const equitySeries = useMemo(() => {
    const dateMap: Record<string, any> = {};
    Object.entries(equityData).forEach(([sid, points]) => {
      points.forEach(p => {
        if (!dateMap[p.date]) dateMap[p.date] = { date: p.date };
        dateMap[p.date][`${sid}_equity`] = p.equity;
        dateMap[p.date][`${sid}_dd`] = p.drawdown;
      });
    });
    return Object.values(dateMap).sort((a: any, b: any) => a.date.localeCompare(b.date));
  }, [equityData]);

  const toggle = (id: string) => setSelected(p => p.includes(id) ? p.filter(s => s !== id) : [...p, id]);

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/")}>返回情报台</button>
        <div>
          <p className="eyebrow">Backtest Visualization</p>
          <h1>策略回测对比</h1>
          <p className="subtle">v2.0 FROZEN baseline · v2.5 dynamic exit · 数据来自 backtest_run / backtest_equity_curve</p>
        </div>
      </header>

      <main className="collection-debug-grid">
        {/* Strategy Selector + Metrics side by side */}
        <section className="workspace-card" style={{ gridColumn: "1 / -1", padding: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr" }}>
            <div style={{ padding: "16px 20px", borderRight: "1px solid #334155" }}>
              <span className="metric-label section-title">策略选择</span>
              <div className="collection-action-row">
                {strategies.map(s => (
                  <button key={s.strategy_id} type="button"
                    className={`tag tag-button ${selected.includes(s.strategy_id) ? "tag-active" : ""}`}
                    onClick={() => toggle(s.strategy_id)}>
                    {s.strategy_id.length > 30 ? s.strategy_id.slice(0, 30) + "…" : s.strategy_id}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ padding: "16px 20px" }}>
              <span className="metric-label section-title">核心指标</span>
              {selectedMetrics.length === 0 ? (
                <p className="subtle">请选择策略</p>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(selectedMetrics.length, 3)}, 1fr)`, gap: 10 }}>
                  {selectedMetrics.map((m, i) => (
                    <div key={m.strategy_id} style={{ borderLeft: `3px solid ${COLORS[i % COLORS.length]}`, paddingLeft: 10 }}>
                      <span className="metric-label" style={{ fontSize: 10 }}>{m.strategy_id.slice(0, 24)}</span>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1px 10px", marginTop: 2, fontSize: 11 }}>
                        <div>收益 <strong style={{ color: (Number(m.total_return) || 0) >= 0 ? "#4ade80" : "#f87171" }}>{fmtPct(m.total_return)}</strong></div>
                        <div>MaxDD <strong style={{ color: "#f87171" }}>{fmtPct(m.max_drawdown)}</strong></div>
                        <div>胜率 <strong>{fmtPct(m.win_rate)}</strong></div>
                        <div>PF <strong>{nf(m.profit_factor, 2)}</strong></div>
                        <div>交易 <strong>{m.trade_count}</strong></div>
                        <div>持仓 <strong>{nf(m.avg_hold_days, 1)}d</strong></div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Equity + Drawdown side by side */}
        <section className="workspace-card" style={{ gridColumn: "1 / -1", padding: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
            <div style={{ padding: "16px 20px", borderRight: "1px solid #334155" }}>
              <span className="metric-label section-title">资金曲线</span>
              {loading ? (
                <div style={{ height: 280, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <span className="screener-run-inline"><span className="screener-spinner" /> 加载中...</span>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={equitySeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tickFormatter={(v: number) => `¥${(v / 10000).toFixed(0)}万`} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <Tooltip formatter={(v: number) => `¥${v.toLocaleString()}`} />
                    <Legend />
                    {selected.map((sid, i) => (
                      <Line key={sid} type="monotone" dataKey={`${sid}_equity`}
                        name={sid.length > 20 ? sid.slice(0, 20) + "…" : sid}
                        stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
            <div style={{ padding: "16px 20px" }}>
              <span className="metric-label section-title">回撤曲线</span>
              {!loading && (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={equitySeries}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`} tick={{ fontSize: 10, fill: "#94a3b8" }} domain={[0, 'auto']} />
                    <Tooltip formatter={(v: number) => `${(v * 100).toFixed(2)}%`} />
                    <Legend />
                    {selected.map((sid, i) => (
                      <Line key={sid} type="monotone" dataKey={`${sid}_dd`}
                        name={sid.length > 20 ? sid.slice(0, 20) + "…" : sid}
                        stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </section>

        {/* Trade Table */}
        <section className="workspace-card" style={{ gridColumn: "1 / -1" }}>
          <span className="metric-label section-title">
            交易明细 —
            <select value={tradeStrategy} onChange={e => { setTradeStrategy(e.target.value); setTradePage(1); }}
              style={{ marginLeft: 8, fontSize: 12, padding: "2px 8px", background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 4 }}>
              {strategies.map(s => <option key={s.strategy_id} value={s.strategy_id}>{s.strategy_id}</option>)}
            </select>
            <span style={{ marginLeft: 8, fontSize: 11, color: "#94a3b8" }}>
              第{tradePage}页
              <button onClick={() => setTradePage(p => Math.max(1, p - 1))} style={{ marginLeft: 8, background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "1px 8px", cursor: "pointer" }}>◀</button>
              <button onClick={() => setTradePage(p => p + 1)} style={{ marginLeft: 4, background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "1px 8px", cursor: "pointer" }}>▶</button>
            </span>
          </span>
          <div className="collection-log-panel" style={{ overflowX: "auto", fontSize: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", color: "#e2e8f0" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #334155" }}>
                  <th style={th}>日期</th><th style={th}>股票</th><th style={th}>买入</th><th style={th}>卖出</th>
                  <th style={th}>收益</th><th style={th}>天</th><th style={th}>退出</th><th style={th}>支撑</th><th style={th}>弱类型</th><th style={th}>分</th>
                </tr>
              </thead>
              <tbody>
                {trades.map(t => (
                  <tr key={t.trade_id} style={{ borderBottom: "1px solid #1e293b" }}>
                    <td style={td}>{t.entry_date?.slice(0, 10)}</td>
                    <td style={td}><strong>{t.stock_id?.replace(/\.(SZ|SH|BJ)$/, "")}</strong><br/><span style={{ color: "#94a3b8", fontSize: 10 }}>{t.stock_name}</span></td>
                    <td style={td}>{nf(t.entry_price, 2)}</td>
                    <td style={td}>{nf(t.exit_price, 2)}</td>
                    <td style={{ ...td, color: (Number(t.return_pct) || 0) >= 0 ? "#4ade80" : "#f87171", fontWeight: 600 }}>{fmtPct(t.return_pct)}</td>
                    <td style={td}>{t.hold_days}d</td>
                    <td style={{ ...td, fontSize: 10, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis" }}>{t.exit_reason}</td>
                    <td style={td}>{t.support_type}</td>
                    <td style={td}>{t.weak_type}</td>
                    <td style={td}>{nf(t.candidate_score, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px 8px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap", fontSize: 11, color: "#94a3b8" };
const td: React.CSSProperties = { padding: "5px 8px", whiteSpace: "nowrap" };
export default BacktestComparePage;
