import React, { useEffect, useState, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { navigateTo } from "../../lib/navigation";

const API = "/api/v1/backtest";
const BLUE = "#2563eb"; const RED = "#dc2626"; const GREEN = "#16a34a";

interface ParamDef { type: string; default: any; options?: any[]; }
const nf = (v: any, d: number) => { const n = Number(v); return isNaN(n) ? "—" : n.toFixed(d); };
const fmtPct = (v: any) => { const n = Number(v); return isNaN(n) ? "—" : `${(n * 100).toFixed(2)}%`; };

export function StrategyLabPage() {
  const [schema, setSchema] = useState<Record<string, ParamDef>>({});
  const [params, setParams] = useState<Record<string, any>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [baseline, setBaseline] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"result" | "trades" | "history">("result");

  const safeJson = async (r: Response) => { const t = await r.text(); return t ? JSON.parse(t) : {}; };

  useEffect(() => {
    fetch(`${API}/param-schema`).then(safeJson).then(d => {
      setSchema(d.parameters || {});
      const defaults: Record<string, any> = {};
      Object.entries(d.parameters || {}).forEach(([k, v]: [string, any]) => { defaults[k] = v.default; });
      setParams(defaults);
    }).catch(e => setError(String(e)));
  }, []);

  useEffect(() => {
    fetch(`${API}/summary?strategy_ids=v2.0_previous_low_only_hold5d`)
      .then(safeJson).then(d => { if (d.items?.length) setBaseline(d.items[0]); }).catch(() => {});
    fetch(`${API}/runs`).then(safeJson).then(d => setRuns(Array.isArray(d.runs) ? d.runs : [])).catch(() => {});
  }, [result]);

  const runBacktest = useCallback(async () => {
    setRunning(true); setError("");
    try {
      const resp = await fetch(`${API}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ params }) });
      const data = await safeJson(resp);
      if (data?.run_id) {
        const rResp = await fetch(`${API}/result/${data.run_id}`);
        setResult(await safeJson(rResp));
      } else { setError(data?.detail || "No trades generated"); }
    } catch (e) { setError(String(e)); }
    finally { setRunning(false); }
  }, [params]);

  const updateParam = (key: string, value: any) => setParams((prev: any) => ({ ...prev, [key]: value }));

  const chartData = React.useMemo(() => {
    const map: Record<string, any> = {};
    if (result?.equity_curve) {
      result.equity_curve.forEach((p: any) => {
        const d = typeof p.trade_date === 'string' ? p.trade_date : String(p.trade_date);
        if (!map[d]) map[d] = { date: d };
        map[d].lab_equity = p.total_equity || p.equity;
        map[d].lab_dd = p.drawdown;
      });
    }
    return Object.values(map).sort((a: any, b: any) => a.date.localeCompare(b.date));
  }, [result]);

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/backtest/compare")}>返回回测对比</button>
        <div>
          <p className="eyebrow">Strategy Lab</p>
          <h1>策略参数实验台</h1>
          <p className="subtle">调参数 → 运行回测 → 对比 v2.0 baseline。不修改 UseCase，不重新生成候选。</p>
        </div>
      </header>

      <main className="collection-debug-grid" style={{ gridTemplateColumns: "320px 1fr" }}>
        {/* Left: Parameter Panel */}
        <section className="workspace-card collection-debug-control">
          <span className="metric-label section-title">参数配置</span>
          {Object.keys(schema).length === 0 && <p className="subtle">加载参数中...</p>}
          {Object.entries(schema).map(([key, def]) => (
            <div key={key} className="collection-field">
              <span>{key}</span>
              {def.options && def.type !== "multi" ? (
                <select value={params[key] ?? def.default}
                  onChange={e => updateParam(key, def.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value))}>
                  {def.options.map((o: any) => <option key={String(o)} value={o}>{String(o)}</option>)}
                </select>
              ) : def.type === "multi" ? (
                <div className="collection-action-row">
                  {(def.options || []).map((o: string) => {
                    const cur: string[] = Array.isArray(params[key]) ? params[key] : (def.default || []);
                    return (
                      <button key={o} type="button"
                        className={`tag tag-button ${cur.includes(o) ? "tag-active" : ""}`}
                        onClick={() => updateParam(key, cur.includes(o) ? cur.filter(x => x !== o) : [...cur, o])}>
                        {o}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <input type="number" step={def.type === "float" ? 0.0001 : 1}
                  value={params[key] ?? def.default}
                  onChange={e => updateParam(key, def.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value))} />
              )}
            </div>
          ))}
          <div className="collection-action-row" style={{ marginTop: 16 }}>
            <button type="button"
              className={`tag tag-button ${running ? "tag-active" : ""}`}
              onClick={runBacktest} disabled={running}>
              {running ? (
                <span className="screener-run-inline"><span className="screener-spinner" /> 运行中...</span>
              ) : "▶ Run Backtest"}
            </button>
          </div>
          {error && <div className="workspace-note" style={{ color: RED, marginTop: 8 }}>{error}</div>}
        </section>

        {/* Right: Results */}
        <div>
          {/* Metric Cards */}
          {result?.summary ? (
            <section className="workspace-card" style={{ marginBottom: 12 }}>
              <span className="metric-label section-title">
                回测结果 · <span style={{ color: "#94a3b8" }}>{result.run_id?.slice(0, 24)}</span>
              </span>
              <div className="collection-debug-status" style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
                <div>
                  <span className="metric-label">总收益</span>
                  <strong style={{ color: (Number(result.summary.total_return) || 0) >= 0 ? GREEN : RED }}>
                    {fmtPct(result.summary.total_return)}
                    {baseline ? <span style={{ fontSize: 10, color: "#94a3b8", marginLeft: 4 }}>vs {fmtPct(baseline.total_return)}</span> : null}
                  </strong>
                </div>
                <div><span className="metric-label">MaxDD</span><strong style={{ color: RED }}>{fmtPct(result.summary.max_drawdown)}</strong></div>
                <div><span className="metric-label">胜率</span><strong>{fmtPct(result.summary.win_rate)}</strong></div>
                <div><span className="metric-label">PF</span><strong>{nf(result.summary.profit_factor, 2)}</strong></div>
                <div><span className="metric-label">交易</span><strong>{result.summary.trade_count}</strong></div>
                <div><span className="metric-label">持仓</span><strong>{nf(result.summary.avg_hold_days, 1)}d</strong></div>
              </div>
            </section>
          ) : (
            <section className="workspace-card" style={{ marginBottom: 12, textAlign: "center", padding: 40 }}>
              <p className="subtle">点击左侧 ▶ Run Backtest 开始实验</p>
              <p className="subtle" style={{ fontSize: 11, marginTop: 4 }}>默认参数与 v2.0 baseline 一致</p>
            </section>
          )}

          {/* Tabs */}
          {result && (
            <section className="workspace-card">
              <div className="collection-action-row" style={{ marginBottom: 12 }}>
                {(["result", "trades", "history"] as const).map(t => (
                  <button key={t} type="button"
                    className={`tag tag-button ${tab === t ? "tag-active" : ""}`}
                    onClick={() => setTab(t)}>
                    {t === "result" ? "资金曲线" : t === "trades" ? "交易明细" : "历史实验"}
                  </button>
                ))}
              </div>

              {tab === "result" && chartData.length > 0 && (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickFormatter={(v: number) => `¥${(v / 10000).toFixed(0)}万`} />
                    <Tooltip formatter={(v: number) => `¥${v?.toLocaleString()}`} />
                    <Legend />
                    <Line type="monotone" dataKey="lab_equity" name="当前参数" stroke={BLUE} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}

              {tab === "trades" && result?.trades && (
                <div className="collection-log-panel" style={{ overflowX: "auto", fontSize: 12 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", color: "#e2e8f0" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid #334155" }}>
                        <th style={th}>日期</th><th style={th}>股票</th><th style={th}>买入</th><th style={th}>卖出</th>
                        <th style={th}>收益</th><th style={th}>天</th><th style={th}>退出</th><th style={th}>支撑</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(Array.isArray(result.trades) ? result.trades : []).slice(0, 50).map((t: any) => (
                        <tr key={t.trade_id || Math.random()} style={{ borderBottom: "1px solid #1e293b" }}>
                          <td style={td}>{t.entry_date?.slice(0, 10)}</td>
                          <td style={td}><strong>{t.stock_id}</strong></td>
                          <td style={td}>{nf(t.entry_price, 2)}</td>
                          <td style={td}>{nf(t.exit_price, 2)}</td>
                          <td style={{ ...td, color: (Number(t.return_pct) || 0) >= 0 ? "#4ade80" : "#f87171", fontWeight: 600 }}>{fmtPct(t.return_pct)}</td>
                          <td style={td}>{t.hold_days}d</td>
                          <td style={{ ...td, fontSize: 10, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis" }}>{t.exit_reason}</td>
                          <td style={td}>{t.support_type}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {tab === "history" && (
                <div className="collection-log-panel" style={{ overflowX: "auto", fontSize: 12 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", color: "#e2e8f0" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid #334155" }}>
                        <th style={th}>Name</th><th style={th}>Return</th><th style={th}>MaxDD</th>
                        <th style={th}>WR</th><th style={th}>PF</th><th style={th}>Trades</th><th style={th}>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(Array.isArray(runs) ? runs : []).slice(0, 30).map((r: any) => (
                        <tr key={r.run_id || Math.random()} style={{ borderBottom: "1px solid #1e293b", cursor: "pointer" }}
                          onClick={() => {
                            fetch(`${API}/result/${r.run_id}`).then(safeJson).then(setResult).catch(() => {});
                            setTab("result");
                          }}>
                          <td style={td}><strong>{r.strategy_name?.slice(0, 24) || r.run_id?.slice(0, 18)}</strong></td>
                          <td style={{ ...td, color: (Number(r.total_return) || 0) >= 0 ? "#4ade80" : "#f87171" }}>{fmtPct(r.total_return)}</td>
                          <td style={td}>{fmtPct(r.max_drawdown)}</td>
                          <td style={td}>{fmtPct(r.win_rate)}</td>
                          <td style={td}>{nf(r.profit_factor, 2)}</td>
                          <td style={td}>{r.trade_count}</td>
                          <td style={{ ...td, fontSize: 10, color: "#94a3b8" }}>{r.created_at?.slice(0, 16)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px 8px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap", fontSize: 11, color: "#94a3b8" };
const td: React.CSSProperties = { padding: "5px 8px", whiteSpace: "nowrap" };
export default StrategyLabPage;
