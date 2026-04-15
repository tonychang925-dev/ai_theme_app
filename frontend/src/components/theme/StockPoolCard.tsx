import { useMemo } from 'react';
import { navigateTo } from '../../lib/navigation';
import type { ThemeStock } from '../../lib/api';

interface StockPoolCardProps {
  stockItems: ThemeStock[];
  limit?: number;
}

export function StockPoolCard({ stockItems, limit = 12 }: StockPoolCardProps) {
  const poolButtons = useMemo(
    () =>
      stockItems.slice(0, limit).map((item, idx) => (
        <button
          key={`${item.stock_id ?? idx}`}
          type="button"
          className="tag tag-button"
          onClick={() => navigateTo(`/stocks/${String(item.stock_id ?? '')}`)}
        >
          {String(item.stock_name ?? item.stock_id ?? '--')}
        </button>
      )),
    [stockItems, limit],
  );

  if (poolButtons.length === 0) {
    return (
      <div className="workspace-card">
        <span className="metric-label">股票池</span>
        <p className="workspace-note">暂无股票池</p>
      </div>
    );
  }

  return (
    <div className="workspace-card">
      <span className="metric-label">股票池</span>
      <div className="tag-row">{poolButtons}</div>
    </div>
  );
}