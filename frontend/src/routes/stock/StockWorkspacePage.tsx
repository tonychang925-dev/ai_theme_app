import { useEffect, useState } from "react";
import type { StockWorkspaceView } from "../../lib/api";
import { fetchStockWorkspace } from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

interface Props { stockId: string; }

export function StockWorkspacePage({ stockId }: Props) {
  const [payload, setPayload] = useState<StockWorkspaceView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true; setLoading(true); setError(null);
    fetchStockWorkspace(stockId)
      .then((data) => { if (active) setPayload(data); })
      .catch((err: Error) => { if (active) setError(err.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [stockId]);

  const p = payload as any;
  const themes = (Array.isArray(p?.themes) ? p.themes : []) as any[];
  const lightspots = (Array.isArray(p?.lightspots) ? p.lightspots : []) as any[];
  const dailySnaps = (Array.isArray(p?.daily_snapshots) ? p.daily_snapshots : []) as any[];
  const stockInfo = p?.stock_info as any;
  const profileExt = (p?.profile_ext ?? {}) as any;
  const stockDetail = p?.stock_detail as any;
  const moneyFlow = (Array.isArray(p?.money_flow) ? p.money_flow : []) as any[];
  const dragonTiger = (Array.isArray(p?.dragon_tiger) ? p.dragon_tiger : []) as any[];
  const auction = (Array.isArray(p?.auction_validation) ? p.auction_validation : []) as any[];
  const klinePos = p?.kline?.position as any;
  const klinePat = p?.kline?.pattern as any;
  const stockName = String(stockDetail?.name || stockInfo?.name || stockId);

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/intel")}>返回情报台</button>
        <div><p className="eyebrow">Stock Workspace</p><h1>{stockName}</h1><p className="subtle">{stockId}</p></div>
      </header>
      {loading && <div className="empty-state">加载中...</div>}
      {error && <div className="empty-state error">{error}</div>}
      {!loading && !error && payload && (
        <main className="workspace-layout single"><section className="workspace-column">

          <div className="workspace-card">
            <span className="metric-label">个股行情</span>
            <div className="recap-tag-stack" style={{marginTop:8}}>
              <span className="recap-chip is-basis">价格 {stockInfo?.price ?? stockDetail?.price ?? "--"}</span>
              <span className={`recap-chip ${Number(stockInfo?.pct_chg ?? 0)>=0 ? "is-pass":"is-risk"}`}>涨跌 {stockInfo?.pct_chg ?? "--"}%</span>
              <span className="recap-chip">市值 {fmt(stockInfo?.market_value)}</span>
              <span className="recap-chip">最高 {stockInfo?.high ?? "--"}</span>
              <span className="recap-chip">最低 {stockInfo?.low ?? "--"}</span>
            </div>
          </div>

          {lightspots.length > 0 && (
            <div className="workspace-card">
              <span className="metric-label">股票题材亮点</span>
              {lightspots.map((s: any, i: number) => <p className="workspace-note" key={i} style={{margin:"4px 0"}}>💡 {String(s.content ?? "--")}</p>)}
            </div>
          )}

          <div className="workspace-card">
            <span className="metric-label">所属题材</span>
            {themes.length > 0 ? (
              <div className="tag-row">{themes.map((item: any, idx: number) => (
                <button key={idx} type="button" className="tag tag-button" onClick={() => navigateTo(`/themes/${String(item.subject_key ?? "")}`)}>
                  {String(item.theme_name ?? item.subject_key ?? "--")}
                </button>
              ))}</div>
            ) : <p className="workspace-note">暂无</p>}
          </div>

          {dailySnaps.length > 0 && (
            <div className="workspace-card">
              <span className="metric-label">近20日走势</span>
              <div className="recap-table-wrap"><table className="recap-table">
                <thead><tr><th>日期</th><th>收盘</th><th>前收</th><th>涨跌</th></tr></thead>
                <tbody>{dailySnaps.slice(0,20).map((r: any, i: number) => {
                  const close=Number(r.close_price??0), pre=Number(r.pre_close??0);
                  const chg=pre?((close-pre)/pre*100).toFixed(2):"--";
                  return <tr key={i}><td>{String(r.trade_date??"--")}</td><td>{close.toFixed(2)}</td><td>{pre.toFixed(2)}</td><td className={Number(chg)>=0?"is-pass":"is-risk"}>{chg}%</td></tr>
                })}</tbody>
              </table></div>
            </div>
          )}

          {(profileExt?.profile_text || stockInfo?.detail_html) && (
            <div className="workspace-card">
              <span className="metric-label">公司概况</span>
              {profileExt?.profile_text && <p className="workspace-note">{String(profileExt.profile_text).slice(0,500)}</p>}
              {profileExt?.main_business_text && <details><summary>主营业务</summary><p className="workspace-note">{String(profileExt.main_business_text).slice(0,1000)}</p></details>}
              {profileExt?.product_text && <details><summary>产品信息</summary><p className="workspace-note">{String(profileExt.product_text).slice(0,500)}</p></details>}
              {stockInfo?.detail_html && <details><summary>详细报告</summary><div dangerouslySetInnerHTML={{__html: String(stockInfo.detail_html).slice(0,5000)}}/></details>}
            </div>
          )}

          <div className="workspace-card">
            <span className="metric-label">资金行为增强</span>
            {moneyFlow.length > 0 ? <ul className="workspace-list">{moneyFlow.slice(0,6).map((item:any,i:number)=>(
              <li key={i}><strong>{String(item.theme_name??"--")}</strong><p className="workspace-note">{String(item.role_enhanced??item.role_label??"--")} / {String(item.money_flow_tier??"--")} / 得分{String(item.money_flow_score??"--")}</p></li>
            ))}</ul> : <p className="workspace-note">暂无</p>}
          </div>

          <div className="workspace-card">
            <span className="metric-label">K线位置与形态</span>
            {klinePos || klinePat ? <div>
              {klinePos && <div style={{marginBottom:8}}><strong>{String(klinePos.position_label??"--")}</strong><p className="workspace-note">趋势分 {String(klinePos.trend_strength_score??"--")} | {String(klinePos.conclusion??"--")}</p></div>}
              {klinePat && <div><strong>形态标签</strong><p className="workspace-note">{String(klinePat.conclusion??"--")}</p></div>}
            </div> : <p className="workspace-note">暂无</p>}
          </div>

          <div className="workspace-card">
            <span className="metric-label">龙虎榜</span>
            {dragonTiger.length > 0 ? <ul className="workspace-list">{dragonTiger.slice(0,5).map((item:any,i:number)=>(
              <li key={i}><strong>{String(item.reason??"--")}</strong><p className="workspace-note">净额: {String(item.net_amount??"--")} / 席位: {String(item.institution_seat_count??"--")}</p></li>
            ))}</ul> : <p className="workspace-note">暂无</p>}
          </div>

          <div className="workspace-card">
            <span className="metric-label">竞价验证</span>
            {auction.length > 0 ? <ul className="workspace-list">{auction.slice(0,6).map((item:any,i:number)=>(
              <li key={i}><strong>{String(item.trade_date??"--")} / {String(item.theme_name??"--")}</strong><p className="workspace-note">{String(item.validation_result??"--")}</p></li>
            ))}</ul> : <p className="workspace-note">暂无</p>}
          </div>

        </section></main>
      )}
    </div>
  );
}
function fmt(v: unknown): string { const n=Number(v); if(!Number.isFinite(n)||n===0)return"--"; if(n>=1e8)return (n/1e8).toFixed(2)+"亿"; if(n>=1e4)return (n/1e4).toFixed(1)+"万"; return n.toFixed(0); }
