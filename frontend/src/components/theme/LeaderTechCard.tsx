import { navigateTo } from '../../lib/navigation';
import { formatBillion, formatNumber } from '../../lib/utils/format';
import type { ThemeLeaderStock } from '../../lib/api';

interface LeaderTechCardProps {
  leaderStocks: ThemeLeaderStock[];
}

export function LeaderTechCard({ leaderStocks }: LeaderTechCardProps) {
  if (leaderStocks.length === 0) {
    return (
      <div className="workspace-card">
        <span className="metric-label">前排股票技术与资金</span>
        <p className="workspace-note">暂无前排股票技术与资金数据</p>
      </div>
    );
  }

  return (
    <div className="workspace-card">
      <span className="metric-label">前排股票技术与资金</span>
      <div className="recap-table-wrap">
        <table className="recap-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>排序</th>
              <th>涨幅</th>
              <th>主力净流入</th>
              <th>量比</th>
              <th>Flag</th>
              <th>K线位置</th>
              <th>K线形态</th>
              <th>资金分层</th>
            </tr>
          </thead>
          <tbody>
            {leaderStocks.map((item, idx) => (
              <tr key={`leader-stock-${idx}`}>
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
                <td>{item.is_leader ? '龙头' : String(item.rank_order ?? '--')}</td>
                <td>{formatNumber(item.pct_chg)}%</td>
                <td>{formatBillion(item.main_net_inflow)}</td>
                <td>{formatNumber(item.volume_ratio)}</td>
                <td>{String(item.current_flag ?? '--')}</td>
                <td>{String(item.position_label ?? '--')}</td>
                <td>
                  {Array.isArray(item.pattern_labels)
                    ? item.pattern_labels.join('/') || '--'
                    : '--'}
                </td>
                <td>{String(item.money_flow_tier ?? item.role_enhanced ?? '--')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}