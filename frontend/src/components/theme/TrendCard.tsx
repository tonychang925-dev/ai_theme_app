import { toNumber, formatNumber } from '../../lib/utils/format';
import type { ThemeRecentRank } from '../../lib/api';

interface TrendCardProps {
  recentRankRows: ThemeRecentRank[];
  trendStats: {
    maxAbsPct: number;
    positiveDays: number;
    latestPct: number;
    latestHisPct: number;
  };
}

export function TrendCard({ recentRankRows, trendStats }: TrendCardProps) {
  if (recentRankRows.length === 0) {
    return (
      <div className="workspace-card">
        <span className="metric-label">近5日题材走势</span>
        <p className="workspace-note">暂无近5日题材走势数据</p>
      </div>
    );
  }

  return (
    <div className="workspace-card">
      <span className="metric-label">近5日题材走势</span>
      <>
        <div className="theme-trend-strip">
          <div className="workspace-card">
            <span className="metric-label">最近表现</span>
            <strong>{formatNumber(trendStats.latestPct)}%</strong>
            <p className="workspace-note">5日累计 {formatNumber(trendStats.latestHisPct)}%</p>
          </div>
          <div className="workspace-card">
            <span className="metric-label">红盘天数</span>
            <strong>{trendStats.positiveDays}/{recentRankRows.length}</strong>
            <p className="workspace-note">近5日题材强度</p>
          </div>
        </div>
        <div className="theme-trend-bars">
          {recentRankRows
            .slice()
            .reverse()
            .map((item, idx) => {
              const pct = toNumber(item.pct_chg);
              const width = `${Math.max((Math.abs(pct) / trendStats.maxAbsPct) * 100, 8)}%`;
              return (
                <div key={`trend-bar-${idx}`} className="theme-trend-bar-row">
                  <span className="theme-trend-date">
                    {String(item.rank_date ?? '--').slice(5)}
                  </span>
                  <div className="theme-trend-bar-track">
                    <div
                      className={`theme-trend-bar-fill ${pct >= 0 ? 'is-up' : 'is-down'}`}
                      style={{ width }}
                    />
                  </div>
                  <strong className="theme-trend-value">{formatNumber(pct)}%</strong>
                </div>
              );
            })}
        </div>
        <div className="recap-table-wrap">
          <table className="recap-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>当日涨幅</th>
                <th>累计涨幅</th>
                <th>红盘</th>
                <th>热度</th>
                <th>驱动摘要</th>
              </tr>
            </thead>
            <tbody>
              {recentRankRows.map((item, idx) => (
                <tr key={`rank-${idx}`}>
                  <td>{String(item.rank_date ?? '--')}</td>
                  <td>{formatNumber(item.pct_chg)}%</td>
                  <td>{formatNumber(item.his_pct_chg)}%</td>
                  <td>{Boolean(item.red) ? '是' : '否'}</td>
                  <td>{String(item.heat_name ?? '--')}</td>
                  <td className="recap-cell-wrap">{String(item.description ?? '--')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    </div>
  );
}