import React, { useEffect, useState, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  BarChart, Bar, ResponsiveContainer,
} from "recharts";

const API = "/api/v1/backtest";

interface Strategy {
  strategy_id: string; strategy_name: string; strategy_version: string;
  total_return: number; max_drawdown: number; win_rate: number;
  profit_factor: number; trade_count: number;
  avg_return_per_trade: number; avg_hold_days: number;
  max_single_loss: number; max_consecutive_losses: number;
}

interface EquityPoint {
  date: string; equity: number; return_pct: number; drawdown: number;
}

interface TradeItem {
  trade_id: string; stock_id: string; stock_name: string;
  entry_date: string; exit_date: string;
  entry_price: number; exit_price: number;
  pnl: number; return_pct: number; hold_days: number;
  exit_reason: string; exit_rule: string;
  support_type: string; weak_type: string; candidate_score: number;
}

const COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"];

export function BacktestComparePage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<string[]>([
    "v2.0_previous_low_only_hold5d",
    "v2.5c_limitup_weakopen_exit",
    "v2.5_combo",
  ]);
  const [equityData, setEquityData] = useState<Record<string, EquityPoint[]>>({});
  const [trades, setTrades] = useState<TradeItem[]>([]);
  const [tradeStrategy, setTradeStrategy] = useState("v2.0_previous_low_only_hold5d");
  const [loading, setLoading] = useState(false);
  const [tradePage, setTradePage] = useState(1);

  useEffect(() => {
    fetch(`${API}/strategies`)
      .then(r => r.json())
      .then(d => setStrategies(d.strategies || []))
      .catch(e => console.error(e));
  }, []);

  useEffect(() => {
    if (selected.length === 0) return;
    setLoading(true);
    fetch(`${API}/equity-curve?strategy_ids=${selected.join(",")}`)
      .then(r => r.json())
      .then(d => {
        const map: Record<string, EquityPoint[]> = {};
        (d.series || []).forEach((s: any) => { map[s.strategy_id] = s.points; });
        setEquityData(map);
      })
      .catch(e => console.error(e))
      .finally(() => setLoading(false));
  }, [selected]);

  useEffect(() => {
    if (!tradeStrategy) return;
    fetch(`${API}/trades?strategy_id=${tradeStrategy}&page=${tradePage}&page_size=50`)
      .then(r => r.json())
      .then(d => setTrades(d.items || []))
      .catch(e => console.error(e));
  }, [tradeStrategy, tradePage]);

  const selectedMetrics = useMemo(() =>
    strategies.filter(s => selected.includes(s.strategy_id)),
    [strategies, selected]
  );

  const equitySeries = useMemo(() => {
    // Merge all selected strategies into one chart-friendly format
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

  const toggleStrategy = (id: string) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    );
  };

  const formatPct = (v: number | undefined) => v != null ? `${(v * 100).toFixed(2)}%` : "—";
  const formatMoney = (v: number | undefined) => v != null ? `¥${v.toLocaleString("zh-CN", { maximumFractionDigits: 0})}` : "—";

  return (
    <div style={{ padding: "20px", maxWidth: "1400px", margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: "24px", fontWeight: 700, marginBottom: "4px" }}>策略回测对比</h1>
      <p style={{ color: "#666", marginBottom: "20px", fontSize: "13px" }}>
        v2.0 FROZEN baseline · v2.5 dynamic exit · 数据来自 backtest_run / backtest_equity_curve / backtest_trade
      </p>

      {/* ── Strategy Selector ── */}
      <div style={{ marginBottom: "20px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
        {strategies.map(s => (
          <button
            key={s.strategy_id}
            onClick={() => toggleStrategy(s.strategy_id)}
            style={{
              padding: "6px 14px", borderRadius: "6px", border: "1px solid #d1d5db",
              background: selected.includes(s.strategy_id) ? "#2563eb" : "#fff",
              color: selected.includes(s.strategy_id) ? "#fff" : "#374151",
              cursor: "pointer", fontSize: "12px", fontWeight: 500,
            }}
          >
            {s.strategy_id.length > 28 ? s.strategy_id.slice(0, 28) + "…" : s.strategy_id}
          </button>
        ))}
      </div>

      {/* ── Metric Cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "12px", marginBottom: "24px" }}>
        {selectedMetrics.map((m, i) => (
          <div key={m.strategy_id} style={{
            border: `2px solid ${COLORS[i % COLORS.length]}`, borderRadius: "8px",
            padding: "14px", background: "#f9fafb",
          }}>
            <div style={{ fontSize: "12px", fontWeight: 600, color: COLORS[i % COLORS.length], marginBottom: "6px", wordBreak: "break-all" }}>
              {m.strategy_id.length > 32 ? m.strategy_id.slice(0, 32) + "…" : m.strategy_id}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px", fontSize: "12px" }}>
              <div><span style={{color:"#666"}}>收益</span><br/><b>{formatPct(m.total_return)}</b></div>
              <div><span style={{color:"#666"}}>MaxDD</span><br/><b style={{color:"#dc2626"}}>{formatPct(m.max_drawdown)}</b></div>
              <div><span style={{color:"#666"}}>胜率</span><br/><b>{formatPct(m.win_rate)}</b></div>
              <div><span style={{color:"#666"}}>PF</span><br/><b>{m.profit_factor?.toFixed(2) || "—"}</b></div>
              <div><span style={{color:"#666"}}>交易</span><br/><b>{m.trade_count}</b></div>
              <div><span style={{color:"#666"}}>持仓天</span><br/><b>{m.avg_hold_days?.toFixed(1)}d</b></div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Equity Curve ── */}
      <div style={{ marginBottom: "24px" }}>
        <h3 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "8px" }}>资金曲线</h3>
        {loading ? <div style={{height:300,display:"flex",alignItems:"center",justifyContent:"center"}}>加载中...</div> : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={equitySeries}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{fontSize:11}} />
              <YAxis tickFormatter={(v: number) => `¥${(v/10000).toFixed(0)}万`} tick={{fontSize:11}} />
              <Tooltip formatter={(v: number) => `¥${v.toLocaleString()}`} />
              <Legend />
              {selected.map((sid, i) => (
                <Line key={sid} type="monotone" dataKey={`${sid}_equity`}
                  name={sid.length > 24 ? sid.slice(0,24)+"…" : sid}
                  stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Drawdown Curve ── */}
      <div style={{ marginBottom: "24px" }}>
        <h3 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "8px" }}>回撤曲线</h3>
        {loading ? <div style={{height:200,display:"flex",alignItems:"center",justifyContent:"center"}}>加载中...</div> : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={equitySeries}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{fontSize:11}} />
              <YAxis tickFormatter={(v: number) => `${(v*100).toFixed(1)}%`} tick={{fontSize:11}} domain={[0, 'auto']} />
              <Tooltip formatter={(v: number) => `${(v*100).toFixed(2)}%`} />
              <Legend />
              {selected.map((sid, i) => (
                <Line key={sid} type="monotone" dataKey={`${sid}_dd`}
                  name={sid.length > 24 ? sid.slice(0,24)+"…" : sid}
                  stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Trade Table ── */}
      <div style={{ marginBottom: "24px" }}>
        <h3 style={{ fontSize: "16px", fontWeight: 600, marginBottom: "8px" }}>
          交易明细 —
          <select value={tradeStrategy} onChange={e => { setTradeStrategy(e.target.value); setTradePage(1); }}
            style={{ marginLeft: "8px", fontSize: "13px", padding: "2px 8px" }}>
            {strategies.map(s => (
              <option key={s.strategy_id} value={s.strategy_id}>{s.strategy_id}</option>
            ))}
          </select>
          <span style={{ fontSize: "12px", color: "#666", marginLeft: "8px" }}>
            第{tradePage}页
            <button onClick={() => setTradePage(p => Math.max(1, p - 1))} style={{ marginLeft: "8px" }}>◀</button>
            <button onClick={() => setTradePage(p => p + 1)} style={{ marginLeft: "4px" }}>▶</button>
          </span>
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr style={{ background: "#f3f4f6", borderBottom: "2px solid #d1d5db" }}>
                <th style={th}>日期</th><th style={th}>股票</th><th style={th}>买入价</th>
                <th style={th}>卖出价</th><th style={th}>收益</th><th style={th}>持天</th>
                <th style={th}>退出原因</th><th style={th}>支撑</th><th style={th}>弱类型</th>
                <th style={th}>候选分</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(t => (
                <tr key={t.trade_id} style={{ borderBottom: "1px solid #e5e7eb" }}>
                  <td style={td}>{t.entry_date?.slice(0,10)}</td>
                  <td style={td}><b>{t.stock_id}</b><br/><span style={{color:"#666",fontSize:"10px"}}>{t.stock_name}</span></td>
                  <td style={td}>{t.entry_price?.toFixed(2)}</td>
                  <td style={td}>{t.exit_price?.toFixed(2)}</td>
                  <td style={{...td, color: (t.return_pct||0) >= 0 ? "#16a34a" : "#dc2626", fontWeight: 600}}>
                    {formatPct(t.return_pct)}
                  </td>
                  <td style={td}>{t.hold_days}d</td>
                  <td style={{...td, fontSize:"10px",maxWidth:"120px"}}>{t.exit_reason}</td>
                  <td style={td}>{t.support_type}</td>
                  <td style={td}>{t.weak_type}</td>
                  <td style={td}>{t.candidate_score?.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px 8px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "5px 8px", whiteSpace: "nowrap" };

export default BacktestComparePage;
