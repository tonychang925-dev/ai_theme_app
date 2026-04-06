import { useEffect, useState } from "react";
import type { StockWorkspaceView } from "../../lib/api";
import { fetchStockWorkspace } from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

interface Props {
  stockId: string;
}

export function StockWorkspacePage({ stockId }: Props) {
  const [payload, setPayload] = useState<StockWorkspaceView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchStockWorkspace(stockId)
      .then((data) => {
        if (active) setPayload(data);
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [stockId]);

  const themeItems = Array.isArray(payload?.themes) ? payload.themes : [];
  const moneyFlowItems = Array.isArray(payload?.money_flow) ? payload.money_flow : [];
  const dragonTigerItems = Array.isArray(payload?.dragon_tiger) ? payload.dragon_tiger : [];
  const auctionValidationItems = Array.isArray(payload?.auction_validation) ? payload.auction_validation : [];
  const klinePosition = payload?.kline?.position ?? null;
  const klinePattern = payload?.kline?.pattern ?? null;
  const stockName = typeof payload?.stock_detail?.name === "string" ? payload.stock_detail.name : stockId;

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/intel")}>
          返回情报台
        </button>
        <div>
          <p className="eyebrow">Stock Workspace</p>
          <h1>{stockName}</h1>
          <p className="subtle">stock_id: {stockId}</p>
        </div>
      </header>

      {loading && <div className="empty-state">正在加载个股工作台...</div>}
      {error && <div className="empty-state error">{error}</div>}

      {!loading && !error && payload && (
        <main className="workspace-layout single">
          <section className="workspace-column">
            <div className="workspace-card">
              <span className="metric-label">个股详情</span>
              <strong>{stockName}</strong>
              <p className="workspace-note">价格: {String(payload.stock_detail?.price ?? "--")}</p>
              <p className="workspace-note">涨跌幅: {String(payload.stock_detail?.pct_chg ?? "--")}</p>
            </div>

            <div className="workspace-card">
              <span className="metric-label">所属题材</span>
              {themeItems.length > 0 ? (
                <div className="tag-row">
                  {themeItems.map((item, idx) => (
                    <button
                      key={`${item.subject_key ?? idx}`}
                      type="button"
                      className="tag tag-button"
                      onClick={() => navigateTo(`/themes/${String(item.subject_key ?? "")}`)}
                    >
                      {String(item.theme_name ?? item.subject_key ?? "--")}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="workspace-note">暂无题材归属</p>
              )}
            </div>

            <div className="workspace-card">
              <span className="metric-label">资金行为增强</span>
              {moneyFlowItems.length > 0 ? (
                <ul className="workspace-list">
                  {moneyFlowItems.slice(0, 6).map((item, idx) => (
                    <li key={`money-${idx}`}>
                      <strong>{String(item.theme_name ?? "--")}</strong>
                      <p className="workspace-note">
                        {String(item.role_enhanced ?? item.role_label ?? "--")} / {String(item.money_flow_tier ?? "--")} / 得分{" "}
                        {String(item.money_flow_score ?? "--")}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="workspace-note">暂无资金行为增强结果</p>
              )}
            </div>

            <div className="workspace-card">
              <span className="metric-label">K线位置与形态</span>
              {klinePosition || klinePattern ? (
                <div className="workspace-kline-block">
                  {klinePosition && (
                    <div className="workspace-kline-section">
                      <strong>{String(klinePosition.position_label ?? "--")}</strong>
                      <p className="workspace-note">
                        {String(klinePosition.ma_alignment_status ?? "--")} / 趋势分 {String(klinePosition.trend_strength_score ?? "--")}
                      </p>
                      <p className="workspace-note">
                        距20日高点 {String(klinePosition.distance_to_20d_high ?? "--")} / 距60日高点 {String(klinePosition.distance_to_60d_high ?? "--")}
                      </p>
                      <p className="workspace-note">{String(klinePosition.conclusion ?? "--")}</p>
                    </div>
                  )}
                  {klinePattern && (
                    <div className="workspace-kline-section">
                      <strong>形态标签</strong>
                      <p className="workspace-note">
                        {Array.isArray(klinePattern.pattern_labels) && klinePattern.pattern_labels.length > 0
                          ? klinePattern.pattern_labels.map((item) => String(item)).join(" / ")
                          : "暂无显著强势形态"}
                      </p>
                      <p className="workspace-note">
                        {String(klinePattern.volume_pattern_status ?? "--")} / {String(klinePattern.breakout_status ?? "--")} /{" "}
                        {String(klinePattern.pullback_status ?? "--")}
                      </p>
                      <p className="workspace-note">{String(klinePattern.conclusion ?? "--")}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="workspace-note">暂无 K 线位置与形态结果</p>
              )}
            </div>

            <div className="workspace-card">
              <span className="metric-label">龙虎榜</span>
              {dragonTigerItems.length > 0 ? (
                <ul className="workspace-list">
                  {dragonTigerItems.slice(0, 5).map((item, idx) => (
                    <li key={`dragon-${idx}`}>
                      <strong>{String(item.reason ?? "--")}</strong>
                      <p className="workspace-note">
                        净额: {String(item.net_amount ?? "--")} / 席位: {String(item.institution_seat_count ?? "--")}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="workspace-note">暂无龙虎榜记录</p>
              )}
            </div>

            <div className="workspace-card">
              <span className="metric-label">竞价验证回看</span>
              {auctionValidationItems.length > 0 ? (
                <ul className="workspace-list">
                  {auctionValidationItems.slice(0, 6).map((item, idx) => (
                    <li key={`auction-validation-${idx}`}>
                      <strong>{String(item.trade_date ?? "--")} / {String(item.theme_name ?? "--")}</strong>
                      <p className="workspace-note">
                        {String(item.auction_signal_level ?? "--")} / {String(item.signal_type ?? "--")} / {String(item.validation_result ?? "--")}
                      </p>
                      <p className="workspace-note">
                        收盘涨跌幅: {String(item.close_pct ?? "--")} / 涨停: {String(item.hit_limit_up ?? "--")}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="workspace-note">暂无竞价验证结果</p>
              )}
            </div>
          </section>
        </main>
      )}
    </div>
  );
}
