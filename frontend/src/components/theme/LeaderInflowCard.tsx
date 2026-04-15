import { navigateTo } from '../../lib/navigation';
import { formatBillion, formatNumber } from '../../lib/utils/format';
import type { ThemeLeaderStock } from '../../lib/api';

interface LeaderInflowCardProps {
  rankedLeaderStocks: ThemeLeaderStock[];
}

export function LeaderInflowCard({ rankedLeaderStocks }: LeaderInflowCardProps) {
  if (rankedLeaderStocks.length === 0) {
    return (
      <div className="workspace-card">
        <span className="metric-label">资金流入前排个股排序</span>
        <p className="workspace-note">暂无前排资金流入数据</p>
      </div>
    );
  }

  return (
    <div className="workspace-card">
      <span className="metric-label">资金流入前排个股排序</span>
      <div className="recap-table-wrap">
        <table className="recap-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>主力净流入</th>
              <th>涨幅</th>
              <th>量比</th>
              <th>排序</th>
              <th>资金分层</th>
            </tr>
          </thead>
          <tbody>
            {rankedLeaderStocks.slice(0, 10).map((item, idx) => (
              <tr key={`ranked-leader-stock-${idx}`}>
                <td>
                  <button
                    type="button"
                    className="recap-theme-link"
                    onClick={() =>
                      navigateTo(`/stocks/${String(item.stock_id ?? '')}`)
                    }
                  >
                    {String(item.stock_name ?? item.stock_id ?? '--')}
                  </button>
                </td>
                <td>{formatBillion(item.main_net_inflow)}</td>
                <td>{formatNumber(item.pct_chg)}%</td>
                <td>{formatNumber(item.volume_ratio)}</td>
                <td>{item.is_leader ? '龙头' : String(item.rank_order ?? '--')}</td>
                <td>{String(item.money_flow_tier ?? item.role_enhanced ?? '--')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}